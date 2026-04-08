from __future__ import annotations

from functools import lru_cache

from app.config import Settings
from app.services.evolution_api import EvolutionApiService
from app.services.supabase_store import SupabaseStore


@lru_cache
def get_settings() -> Settings:
    return Settings()


@lru_cache
def get_evolution_api_service() -> EvolutionApiService:
    return EvolutionApiService(settings=get_settings())


@lru_cache
def get_supabase_store() -> SupabaseStore:
    settings = get_settings()
    return SupabaseStore(
        supabase_url=settings.supabase_url,
        supabase_key=settings.supabase_service_role_key,
        default_user_id=settings.default_user_id,
    )

