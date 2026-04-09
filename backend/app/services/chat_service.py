from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import uuid4

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


@dataclass(slots=True)
class ChatThreadSummary:
    thread: ChatThreadRecord
    message_count: int
    last_message_preview: str | None
    last_message_role: str | None
    last_message_at: datetime | None


@dataclass(slots=True)
class ChatWorkspaceState:
    session: ChatSessionState
    threads: list[ChatThreadSummary]


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

    def get_session(self, *, thread_id: str | None = None) -> ChatSessionState:
        thread = self._resolve_thread(thread_id=thread_id)
        return self._build_session_state(thread=thread)

    def get_workspace(self, *, thread_id: str | None = None) -> ChatWorkspaceState:
        thread_summaries = self._list_thread_summaries()
        resolved_thread = self._resolve_thread(thread_id=thread_id)
        if not any(summary.thread.id == resolved_thread.id for summary in thread_summaries):
            thread_summaries.insert(0, self._build_thread_summary(resolved_thread))
        return ChatWorkspaceState(
            session=self._build_session_state(thread=resolved_thread),
            threads=thread_summaries,
        )

    def create_thread(self, *, title: str | None = None) -> ChatWorkspaceState:
        created_at = datetime.now(UTC)
        created_thread = self.store.create_chat_thread(
            user_id=self.settings.default_user_id,
            title=self._resolve_new_thread_title(title),
            thread_key=f"thread-{uuid4().hex}",
            created_at=created_at,
        )
        return self.get_workspace(thread_id=created_thread.id)

    async def send_message(self, *, message_text: str, thread_id: str | None = None) -> ChatWorkspaceState:
        normalized_text = " ".join(message_text.split()).strip()
        if not normalized_text:
            raise ChatServiceError("Envie uma mensagem com texto.")

        if len(normalized_text) > self.settings.chat_max_message_chars:
            raise ChatServiceError(
                f"A mensagem excede o limite de {self.settings.chat_max_message_chars} caracteres."
            )

        thread = self._resolve_thread(thread_id=thread_id)
        created_at = datetime.now(UTC)
        self.store.append_chat_message(
            thread_id=thread.id,
            role="user",
            content=normalized_text,
            created_at=created_at,
        )
        thread = self._maybe_autorename_thread(thread=thread, first_user_message=normalized_text, updated_at=created_at)

        session = self._build_session_state(thread=thread)
        prior_messages = session.messages[:-1] if session.messages and session.messages[-1].role == "user" else session.messages
        interaction_mode = self._resolve_interaction_mode(normalized_text)
        use_light_touch_context = interaction_mode == "light_touch"

        assistant_reply = await self.groq_service.generate_reply(
            user_message=normalized_text,
            current_life_summary="" if use_light_touch_context else session.persona.life_summary,
            recent_snapshots_context="" if use_light_touch_context else self._build_snapshot_context(),
            recent_projects_context="" if use_light_touch_context else self._build_project_context(session.projects),
            recent_chat_context="" if use_light_touch_context else self._build_chat_context(prior_messages),
            interaction_mode=interaction_mode,
        )
        self.store.append_chat_message(
            thread_id=thread.id,
            role="assistant",
            content=assistant_reply,
            created_at=datetime.now(UTC),
        )
        return self.get_workspace(thread_id=thread.id)

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

    def _resolve_thread(self, *, thread_id: str | None = None) -> ChatThreadRecord:
        if thread_id:
            resolved = self.store.get_chat_thread(
                user_id=self.settings.default_user_id,
                thread_id=thread_id,
            )
            if resolved is None:
                raise ChatServiceError("A conversa selecionada nao foi encontrada.")
            return resolved

        existing = self.store.list_chat_threads(user_id=self.settings.default_user_id, limit=1)
        if existing:
            return existing[0]
        return self.store.get_or_create_chat_thread(user_id=self.settings.default_user_id)

    def _list_thread_summaries(self) -> list[ChatThreadSummary]:
        threads = self.store.list_chat_threads(user_id=self.settings.default_user_id, limit=24)
        if not threads:
            threads = [self.store.get_or_create_chat_thread(user_id=self.settings.default_user_id)]
        return [self._build_thread_summary(thread) for thread in threads]

    def _build_thread_summary(self, thread: ChatThreadRecord) -> ChatThreadSummary:
        latest_messages = self.store.list_chat_messages(thread.id, limit=1)
        latest_message = latest_messages[-1] if latest_messages else None
        return ChatThreadSummary(
            thread=thread,
            message_count=self.store.count_chat_messages(thread.id),
            last_message_preview=self._build_thread_preview(latest_message.content) if latest_message is not None else None,
            last_message_role=latest_message.role if latest_message is not None else None,
            last_message_at=latest_message.created_at if latest_message is not None else None,
        )

    def _resolve_new_thread_title(self, title: str | None) -> str:
        normalized_title = " ".join((title or "").split()).strip()
        if normalized_title:
            return normalized_title[:80]
        existing_threads = self.store.list_chat_threads(user_id=self.settings.default_user_id, limit=100)
        return f"Nova conversa {len(existing_threads) + 1}"

    def _maybe_autorename_thread(
        self,
        *,
        thread: ChatThreadRecord,
        first_user_message: str,
        updated_at: datetime,
    ) -> ChatThreadRecord:
        if not self._is_generic_thread_title(thread.title):
            return thread
        if self.store.count_chat_messages(thread.id) > 1:
            return thread

        next_title = self._title_from_message(first_user_message)
        updated = self.store.update_chat_thread(
            thread_id=thread.id,
            title=next_title,
            updated_at=updated_at,
        )
        return updated or thread

    def _is_generic_thread_title(self, value: str) -> bool:
        normalized = " ".join(value.split()).strip().lower()
        return normalized == "conversa principal" or normalized.startswith("nova conversa")

    def _title_from_message(self, message_text: str) -> str:
        normalized = " ".join(message_text.split()).strip()
        if not normalized:
            return "Nova conversa"
        if len(normalized) <= 48:
            return normalized
        return f"{normalized[:45].rstrip()}..."

    def _build_thread_preview(self, content: str) -> str:
        normalized = " ".join(content.split()).strip()
        if len(normalized) <= 84:
            return normalized
        return f"{normalized[:81].rstrip()}..."

    def _resolve_interaction_mode(self, message_text: str) -> str:
        normalized = " ".join(message_text.lower().split()).strip()
        if not normalized:
            return "light_touch"
        if len(normalized) <= 24 and normalized in {
            "oi",
            "ola",
            "olá",
            "opa",
            "bom dia",
            "boa tarde",
            "boa noite",
            "e ai",
            "e aí",
            "salve",
            "fala",
            "oii",
        }:
            return "light_touch"
        if len(normalized) <= 18 and normalized.rstrip("!?.,") in {"oi", "ola", "olá", "opa", "fala"}:
            return "light_touch"
        return "contextual"

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
