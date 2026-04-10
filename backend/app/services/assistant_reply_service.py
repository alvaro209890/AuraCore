from __future__ import annotations

from datetime import datetime
from typing import Sequence

from app.config import Settings
from app.services.assistant_context_service import (
    AssistantContextService,
    AssistantConversationTurn,
)
from app.services.deepseek_service import DeepSeekService
from app.services.supabase_store import ChatMessageRecord, SupabaseStore, WhatsAppAgentMessageRecord

ConversationRecord = ChatMessageRecord | WhatsAppAgentMessageRecord | AssistantConversationTurn


class AssistantReplyService:
    def __init__(
        self,
        *,
        settings: Settings,
        store: SupabaseStore,
        deepseek_service: DeepSeekService,
        context_service: AssistantContextService,
    ) -> None:
        self.settings = settings
        self.store = store
        self.deepseek_service = deepseek_service
        self.context_service = context_service

    async def generate_reply(
        self,
        *,
        user_message: str,
        recent_messages: Sequence[ConversationRecord],
        context_hint: str | None = None,
        priority_context: str | None = None,
        contact_memory_context: str | None = None,
        recent_messages_label: str | None = None,
        additional_rules: Sequence[str] | None = None,
        channel: str = "web_chat",
    ) -> str:
        normalized_history = self._normalize_messages(recent_messages)
        context_package = await self.context_service.build_reply_context(
            user_message=user_message,
            recent_messages=normalized_history,
            channel="whatsapp_agent" if channel == "whatsapp_agent" else "web_chat",
            context_hint=context_hint,
            priority_context=priority_context,
            contact_memory_context=contact_memory_context,
            additional_rules=additional_rules,
        )
        return await self.deepseek_service.generate_reply(
            user_message=user_message,
            current_life_summary=context_package.current_life_summary,
            recent_snapshots_context=context_package.recent_snapshots_context,
            recent_projects_context=context_package.recent_projects_context,
            recent_chat_context=context_package.recent_chat_context,
            interaction_mode=context_package.interaction_mode,
            context_hint=context_package.context_hint,
            priority_context=context_package.priority_context,
            recent_messages_label=recent_messages_label or "Historico recente desta conversa",
            additional_rules=context_package.additional_rules,
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
