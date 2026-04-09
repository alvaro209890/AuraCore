from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from app.config import Settings
from app.services.groq_service import GroqChatService
from app.services.supabase_store import (
    ChatMessageRecord,
    ChatThreadRecord,
    MemorySnapshotRecord,
    PersonaRecord,
    ProjectMemoryRecord,
    SupabaseStore,
)


class ChatServiceError(RuntimeError):
    """Raised when chat input or output cannot be handled."""


@dataclass(slots=True)
class ChatSessionState:
    thread: ChatThreadRecord
    persona: PersonaRecord
    projects: list[ProjectMemoryRecord]
    messages: list[ChatMessageRecord]


class ChatAssistantService:
    def __init__(
        self,
        *,
        settings: Settings,
        store: SupabaseStore,
        groq_service: GroqChatService,
    ) -> None:
        self.settings = settings
        self.store = store
        self.groq_service = groq_service

    def get_session(self) -> ChatSessionState:
        thread = self.store.get_or_create_chat_thread(user_id=self.settings.default_user_id)
        return self._build_session_state(thread=thread)

    async def send_message(self, *, message_text: str) -> ChatSessionState:
        normalized_text = " ".join(message_text.split()).strip()
        if not normalized_text:
            raise ChatServiceError("Envie uma mensagem com texto.")

        if len(normalized_text) > self.settings.chat_max_message_chars:
            raise ChatServiceError(
                f"A mensagem excede o limite de {self.settings.chat_max_message_chars} caracteres."
            )

        thread = self.store.get_or_create_chat_thread(user_id=self.settings.default_user_id)
        created_at = datetime.now(UTC)
        self.store.append_chat_message(
            thread_id=thread.id,
            role="user",
            content=normalized_text,
            created_at=created_at,
        )

        session = self._build_session_state(thread=thread)
        prior_messages = session.messages[:-1] if session.messages and session.messages[-1].role == "user" else session.messages

        assistant_reply = await self.groq_service.generate_reply(
            user_message=normalized_text,
            current_life_summary=session.persona.life_summary,
            recent_snapshots_context=self._build_snapshot_context(),
            recent_projects_context=self._build_project_context(session.projects),
            recent_chat_context=self._build_chat_context(prior_messages),
        )
        self.store.append_chat_message(
            thread_id=thread.id,
            role="assistant",
            content=assistant_reply,
            created_at=datetime.now(UTC),
        )
        return self._build_session_state(thread=thread)

    def _build_session_state(self, *, thread: ChatThreadRecord) -> ChatSessionState:
        persona = self.store.get_persona(self.settings.default_user_id) or PersonaRecord(
            user_id=self.settings.default_user_id,
            life_summary="",
            last_analyzed_at=None,
            last_snapshot_id=None,
            last_analyzed_ingested_count=None,
            last_analyzed_pruned_count=None,
        )
        projects = self.store.list_project_memories(
            self.settings.default_user_id,
            limit=max(1, self.settings.chat_context_projects),
        )
        messages = self.store.list_chat_messages(
            thread.id,
            limit=max(1, self.settings.chat_max_history_messages),
        )
        return ChatSessionState(
            thread=thread,
            persona=persona,
            projects=projects,
            messages=messages,
        )

    def _build_snapshot_context(self) -> str:
        limit = max(0, self.settings.chat_context_snapshots)
        if limit == 0:
            return ""

        snapshots = self.store.list_memory_snapshots(self.settings.default_user_id, limit=limit)
        return self._render_snapshot_context(snapshots)

    def _build_project_context(self, projects: list[ProjectMemoryRecord]) -> str:
        if not projects:
            return ""

        parts: list[str] = []
        current_size = 0
        char_budget = max(1000, self.settings.chat_context_chars)

        for project in projects:
            lines = [
                f"- {project.project_name}",
                f"  Resumo: {project.summary}",
            ]
            if project.status:
                lines.append(f"  Status: {project.status}")
            if project.what_is_being_built:
                lines.append(f"  O que esta sendo desenvolvido: {project.what_is_being_built}")
            if project.built_for:
                lines.append(f"  Para quem: {project.built_for}")
            if project.next_steps:
                lines.append(f"  Proximos passos: {'; '.join(project.next_steps[:4])}")
            if project.evidence:
                lines.append(f"  Evidencias: {'; '.join(project.evidence[:3])}")
            section = "\n".join(lines)
            projected = current_size + len(section) + 2
            if parts and projected > char_budget:
                break
            parts.append(section)
            current_size = projected

        return "\n\n".join(parts)

    def _build_chat_context(self, messages: list[ChatMessageRecord]) -> str:
        if not messages:
            return ""

        parts: list[str] = []
        current_size = 0
        char_budget = max(1000, self.settings.chat_context_chars // 2)

        for message in reversed(messages):
            role_label = "Dono" if message.role == "user" else "AuraCore"
            line = f"[{message.created_at.astimezone(UTC).strftime('%Y-%m-%d %H:%M UTC')}] {role_label}: {message.content}"
            projected = current_size + len(line) + 1
            if parts and projected > char_budget:
                break
            parts.append(line)
            current_size = projected

        return "\n".join(reversed(parts))

    def _render_snapshot_context(self, snapshots: list[MemorySnapshotRecord]) -> str:
        if not snapshots:
            return ""

        parts: list[str] = []
        current_size = 0
        char_budget = max(1000, self.settings.chat_context_chars // 2)

        for snapshot in snapshots:
            lines = [
                f"- Snapshot de {snapshot.window_hours}h em {snapshot.created_at.astimezone(UTC).strftime('%d/%m %H:%M UTC')}",
                f"  Resumo: {snapshot.window_summary}",
            ]
            if snapshot.key_learnings:
                lines.append(f"  Aprendizados: {'; '.join(snapshot.key_learnings[:4])}")
            section = "\n".join(lines)
            projected = current_size + len(section) + 2
            if parts and projected > char_budget:
                break
            parts.append(section)
            current_size = projected

        return "\n\n".join(parts)
