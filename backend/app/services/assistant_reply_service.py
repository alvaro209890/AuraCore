from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Sequence

from app.config import Settings
from app.services.groq_service import GroqChatService
from app.services.supabase_store import (
    ChatMessageRecord,
    ImportantMessageRecord,
    MemorySnapshotRecord,
    PersonMemoryRecord,
    PersonaRecord,
    ProjectMemoryRecord,
    SupabaseStore,
    WhatsAppAgentMessageRecord,
)


@dataclass(slots=True)
class AssistantConversationTurn:
    role: str
    content: str
    created_at: datetime


ConversationRecord = ChatMessageRecord | WhatsAppAgentMessageRecord | AssistantConversationTurn


class AssistantReplyService:
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

    async def generate_reply(
        self,
        *,
        user_message: str,
        recent_messages: Sequence[ConversationRecord],
        context_hint: str | None = None,
        priority_context: str | None = None,
        recent_messages_label: str | None = None,
        additional_rules: Sequence[str] | None = None,
    ) -> str:
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
        interaction_mode = self._resolve_interaction_mode(user_message)
        use_light_touch_context = interaction_mode == "light_touch"

        search_hint = (context_hint or "").strip()
        if interaction_mode != "light_touch":
            intent = await self.groq_service.extract_chat_search_intent(user_message)
            if intent.has_queries:
                search_results: list[str] = []
                if intent.contact_queries:
                    people = self.store.search_person_memories(self.settings.default_user_id, intent.contact_queries)
                    if people:
                        search_results.append("Resultados da busca por contatos:\n" + self._format_search_people(people))
                if intent.vault_queries:
                    vault_items = self.store.search_important_messages(self.settings.default_user_id, intent.vault_queries)
                    if vault_items:
                        search_results.append("Resultados da busca no cofre (mensagens importantes):\n" + self._format_search_vault(vault_items))
                if search_results:
                    search_hint = "\n\n".join(part for part in [search_hint, *search_results] if part).strip()

        normalized_history = self._normalize_messages(recent_messages)
        return await self.groq_service.generate_reply(
            user_message=user_message,
            current_life_summary="" if use_light_touch_context else persona.life_summary,
            recent_snapshots_context="" if use_light_touch_context else self._build_snapshot_context(),
            recent_projects_context="" if use_light_touch_context else self._build_project_context(projects),
            recent_chat_context="" if use_light_touch_context else self._build_chat_context(normalized_history),
            interaction_mode=interaction_mode,
            context_hint=search_hint,
            priority_context=priority_context or "",
            recent_messages_label=recent_messages_label or "Historico recente desta conversa",
            additional_rules=list(additional_rules or []),
        )

    def _normalize_messages(self, messages: Sequence[ConversationRecord]) -> list[AssistantConversationTurn]:
        normalized: list[AssistantConversationTurn] = []
        for message in messages:
            role = str(getattr(message, "role", "") or "").strip().lower()
            content = str(getattr(message, "content", "") or "").strip()
            timestamp = getattr(message, "message_timestamp", None)
            created_at = timestamp if isinstance(timestamp, datetime) else getattr(message, "created_at", None)
            if role not in {"user", "assistant"} or not content or not isinstance(created_at, datetime):
                continue
            normalized.append(
                AssistantConversationTurn(
                    role=role,
                    content=content,
                    created_at=created_at,
                )
            )
        return normalized

    def _resolve_interaction_mode(self, message_text: str) -> str:
        normalized = " ".join(message_text.lower().split()).strip()
        if not normalized:
            return "light_touch"
        if len(normalized) <= 24 and normalized in {
            "oi",
            "ola",
            "opa",
            "bom dia",
            "boa tarde",
            "boa noite",
            "e ai",
            "salve",
            "fala",
            "oii",
        }:
            return "light_touch"
        if len(normalized) <= 18 and normalized.rstrip("!?.,") in {"oi", "ola", "opa", "fala"}:
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

    def _build_chat_context(self, messages: list[AssistantConversationTurn]) -> str:
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

    def _format_search_people(self, people: list[PersonMemoryRecord]) -> str:
        blocks: list[str] = []
        for person in people:
            lines = [f"- Nome: {person.contact_name}"]
            if person.profile_summary:
                lines.append(f"  Quem e: {person.profile_summary}")
            if person.relationship_summary:
                lines.append(f"  Relacao: {person.relationship_summary}")
            if person.salient_facts:
                lines.append(f"  Fatos: {'; '.join(person.salient_facts[:4])}")
            blocks.append("\n".join(lines))
        return "\n\n".join(blocks)

    def _format_search_vault(self, messages: list[ImportantMessageRecord]) -> str:
        blocks: list[str] = []
        for message in messages:
            date_str = message.message_timestamp.astimezone(UTC).strftime("%d/%m/%Y")
            lines = [
                f"- Mensagem de {message.contact_name} em {date_str}:",
                f"  Conteudo: {message.message_text}",
                f"  Por que e importante: {message.importance_reason}",
            ]
            blocks.append("\n".join(lines))
        return "\n\n".join(blocks)
