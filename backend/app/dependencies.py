from __future__ import annotations

from functools import lru_cache

from app.services.chat_service import ChatAssistantService
from app.config import Settings
from app.services.deepseek_service import DeepSeekService
from app.services.groq_service import GroqChatService
from app.services.memory_service import MemoryAnalysisService
from app.services.observer_gateway import ObserverGatewayService
from app.services.supabase_store import SupabaseStore


@lru_cache
def get_settings() -> Settings:
    return Settings()


@lru_cache
def get_supabase_store() -> SupabaseStore:
    settings = get_settings()
    return SupabaseStore(
        supabase_url=settings.supabase_url,
        supabase_key=settings.supabase_service_role_key,
        default_user_id=settings.default_user_id,
        message_retention_max_rows=min(
            settings.message_retention_max_rows,
            settings.memory_analysis_max_messages,
        ),
    )


@lru_cache
def get_observer_gateway_service() -> ObserverGatewayService:
    return ObserverGatewayService(settings=get_settings())


@lru_cache
def get_deepseek_service() -> DeepSeekService:
    return DeepSeekService(settings=get_settings())


@lru_cache
def get_groq_service() -> GroqChatService:
    return GroqChatService(settings=get_settings())


@lru_cache
def get_memory_analysis_service() -> MemoryAnalysisService:
    return MemoryAnalysisService(
        settings=get_settings(),
        store=get_supabase_store(),
        deepseek_service=get_deepseek_service(),
        groq_service=get_groq_service(),
    )


@lru_cache
def get_chat_assistant_service() -> ChatAssistantService:
    return ChatAssistantService(
        settings=get_settings(),
        store=get_supabase_store(),
        groq_service=get_groq_service(),
    )
