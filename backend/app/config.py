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
    evolution_api_url: str = Field(..., alias="EVOLUTION_API_URL")
    evolution_api_key: str = Field(..., alias="EVOLUTION_API_KEY")
    evolution_instance_name: str = Field("observer", alias="EVOLUTION_INSTANCE_NAME")
    webhook_public_base_url: str = Field(..., alias="WEBHOOK_PUBLIC_BASE_URL")
    webhook_secret: str = Field("change-me", alias="WEBHOOK_SECRET")
    supabase_url: str = Field(..., alias="SUPABASE_URL")
    supabase_service_role_key: str = Field(..., alias="SUPABASE_SERVICE_ROLE_KEY")
    default_user_id: UUID = Field(
        UUID("00000000-0000-0000-0000-000000000001"),
        alias="DEFAULT_USER_ID",
    )
    frontend_origins: str = Field("http://localhost:3000", alias="FRONTEND_ORIGINS")
    request_timeout_seconds: float = Field(20.0, alias="REQUEST_TIMEOUT_SECONDS")

    @property
    def allowed_origins(self) -> list[str]:
        return [origin.strip() for origin in self.frontend_origins.split(",") if origin.strip()]

    @property
    def normalized_evolution_api_url(self) -> str:
        return self.evolution_api_url.rstrip("/")

    @property
    def observer_webhook_url(self) -> str:
        base_url = self.webhook_public_base_url.rstrip("/")
        return f"{base_url}/api/webhooks/evolution/{self.webhook_secret}"

