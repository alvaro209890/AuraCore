from __future__ import annotations

from uuid import UUID

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    app_name: str = "AuraCore Observer API"
    environment: str = "development"
    supabase_url: str = Field(..., alias="SUPABASE_URL")
    supabase_service_role_key: str = Field(..., alias="SUPABASE_SERVICE_ROLE_KEY")
    default_user_id: UUID = Field(
        UUID("00000000-0000-0000-0000-000000000001"),
        alias="DEFAULT_USER_ID",
    )
    frontend_origins: str = Field(
        "http://localhost:3000,https://auracore-82bf2.web.app",
        alias="FRONTEND_ORIGINS",
    )
    whatsapp_gateway_url: str = Field(..., alias="WHATSAPP_GATEWAY_URL")
    internal_api_token: str = Field(..., alias="INTERNAL_API_TOKEN")
    deepseek_api_key: str = Field(..., alias="DEEPSEEK_API_KEY")
    deepseek_model: str = Field("deepseek-chat", alias="DEEPSEEK_MODEL")
    deepseek_api_base_url: str = Field("https://api.deepseek.com", alias="DEEPSEEK_API_BASE_URL")
    deepseek_timeout_seconds: float = Field(60.0, alias="DEEPSEEK_TIMEOUT_SECONDS")
    memory_analysis_max_messages: int = Field(250, alias="MEMORY_ANALYSIS_MAX_MESSAGES")
    memory_analysis_max_chars: int = Field(60000, alias="MEMORY_ANALYSIS_MAX_CHARS")
    memory_analysis_max_window_hours: int = Field(168, alias="MEMORY_ANALYSIS_MAX_WINDOW_HOURS")
    memory_analysis_context_snapshots: int = Field(5, alias="MEMORY_ANALYSIS_CONTEXT_SNAPSHOTS")
    memory_analysis_snapshot_context_chars: int = Field(12000, alias="MEMORY_ANALYSIS_SNAPSHOT_CONTEXT_CHARS")
    request_timeout_seconds: float = Field(20.0, alias="REQUEST_TIMEOUT_SECONDS")

    @property
    def allowed_origins(self) -> list[str]:
        return [origin.strip() for origin in self.frontend_origins.split(",") if origin.strip()]

    @property
    def normalized_whatsapp_gateway_url(self) -> str:
        return self.whatsapp_gateway_url.rstrip("/")

    @property
    def normalized_deepseek_api_base_url(self) -> str:
        return self.deepseek_api_base_url.rstrip("/")
