from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class ObserverStatusResponse(BaseModel):
    instance_name: str
    connected: bool
    state: str
    gateway_ready: bool
    ingestion_ready: bool
    owner_number: str | None = None
    qr_code: str | None = None
    qr_expires_in_sec: int | None = None
    last_seen_at: datetime | None = None
    last_error: str | None = None


class IngestMessageRequestItem(BaseModel):
    model_config = ConfigDict(extra="ignore")

    message_id: str = Field(min_length=1)
    direction: Literal["inbound", "outbound"]
    contact_name: str | None = None
    contact_phone: str = Field(min_length=1)
    message_text: str = Field(min_length=1)
    timestamp: datetime
    source: str = Field(default="baileys", min_length=1)


class IngestMessagesRequest(BaseModel):
    messages: list[IngestMessageRequestItem] = Field(default_factory=list)


class IngestMessagesResponse(BaseModel):
    ok: bool = True
    accepted_count: int = Field(default=0, ge=0)
    ignored_count: int = Field(default=0, ge=0)


class AnalyzeMemoryRequest(BaseModel):
    window_hours: int = Field(default=24, ge=1)


class MemoryCurrentResponse(BaseModel):
    user_id: str
    life_summary: str = ""
    last_analyzed_at: datetime | None = None
    last_snapshot_id: str | None = None


class MemorySnapshotResponse(BaseModel):
    id: str
    window_hours: int = Field(ge=1)
    window_start: datetime
    window_end: datetime
    source_message_count: int = Field(ge=0)
    window_summary: str
    key_learnings: list[str] = Field(default_factory=list)
    people_and_relationships: list[str] = Field(default_factory=list)
    routine_signals: list[str] = Field(default_factory=list)
    preferences: list[str] = Field(default_factory=list)
    open_questions: list[str] = Field(default_factory=list)
    created_at: datetime


class AnalyzeMemoryResponse(BaseModel):
    current: MemoryCurrentResponse
    snapshot: MemorySnapshotResponse


class MemorySnapshotsListResponse(BaseModel):
    snapshots: list[MemorySnapshotResponse] = Field(default_factory=list)

