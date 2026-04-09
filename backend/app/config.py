from __future__ import annotations

import re
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
        "http://localhost:3000,https://auracore-82bf2.web.app,https://auracore-82bf2.firebaseapp.com",
        alias="FRONTEND_ORIGINS",
    )
    whatsapp_gateway_url: str = Field(..., alias="WHATSAPP_GATEWAY_URL")
    internal_api_token: str = Field(..., alias="INTERNAL_API_TOKEN")
    deepseek_api_key: str = Field(..., alias="DEEPSEEK_API_KEY")
    deepseek_model: str = Field("deepseek-reasoner", alias="DEEPSEEK_MODEL")
    deepseek_api_base_url: str = Field("https://api.deepseek.com", alias="DEEPSEEK_API_BASE_URL")
    deepseek_timeout_seconds: float = Field(60.0, alias="DEEPSEEK_TIMEOUT_SECONDS")
    groq_api_key: str | None = Field(default=None, alias="GROQ_API_KEY")
    groq_model: str = Field("llama-3.1-8b-instant", alias="GROQ_MODEL")
    groq_api_base_url: str = Field("https://api.groq.com/openai/v1", alias="GROQ_API_BASE_URL")
    groq_timeout_seconds: float = Field(45.0, alias="GROQ_TIMEOUT_SECONDS")
    memory_analysis_max_messages: int = Field(250, alias="MEMORY_ANALYSIS_MAX_MESSAGES")
    memory_analysis_max_chars: int = Field(60000, alias="MEMORY_ANALYSIS_MAX_CHARS")
    memory_analysis_max_window_hours: int = Field(168, alias="MEMORY_ANALYSIS_MAX_WINDOW_HOURS")
    memory_analysis_context_snapshots: int = Field(5, alias="MEMORY_ANALYSIS_CONTEXT_SNAPSHOTS")
    memory_analysis_snapshot_context_chars: int = Field(18000, alias="MEMORY_ANALYSIS_SNAPSHOT_CONTEXT_CHARS")
    chat_max_history_messages: int = Field(18, alias="CHAT_MAX_HISTORY_MESSAGES")
    chat_context_snapshots: int = Field(5, alias="CHAT_CONTEXT_SNAPSHOTS")
    chat_context_projects: int = Field(8, alias="CHAT_CONTEXT_PROJECTS")
    chat_context_chars: int = Field(18000, alias="CHAT_CONTEXT_CHARS")
    chat_max_message_chars: int = Field(2000, alias="CHAT_MAX_MESSAGE_CHARS")
    message_retention_max_rows: int = Field(3000, alias="MESSAGE_RETENTION_MAX_ROWS")
    request_timeout_seconds: float = Field(20.0, alias="REQUEST_TIMEOUT_SECONDS")

    @property
    def allowed_origins(self) -> list[str]:
        raw_items = re.split(r"[\s,;]+", self.frontend_origins)
        origins = [origin.strip().rstrip("/") for origin in raw_items if origin.strip()]
        if origins:
            return origins
        return [
            "http://localhost:3000",
            "https://auracore-82bf2.web.app",
            "https://auracore-82bf2.firebaseapp.com",
        ]

    @property
    def normalized_whatsapp_gateway_url(self) -> str:
        return self.whatsapp_gateway_url.rstrip("/")

    @property
    def normalized_deepseek_api_base_url(self) -> str:
        return self.deepseek_api_base_url.rstrip("/")

    @property
    def normalized_groq_api_base_url(self) -> str:
        return self.groq_api_base_url.rstrip("/")
