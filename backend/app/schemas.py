from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class ObserverStatusResponse(BaseModel):
    instance_name: str
    connected: bool
    state: str
    webhook_ready: bool
    profile_name: str | None = None
    owner_number: str | None = None
    qr_code: str | None = None
    pairing_code: str | None = None
    last_seen_at: datetime | None = None
    last_error: str | None = None


class WebhookAckResponse(BaseModel):
    ok: bool = True
    event: str
    accepted_count: int = Field(default=0, ge=0)
    ignored_count: int = Field(default=0, ge=0)

