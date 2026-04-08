from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Sequence
from uuid import UUID

from supabase import Client, create_client


@dataclass(slots=True)
class IngestedMessageRecord:
    message_id: str
    user_id: UUID
    direction: str
    contact_name: str
    contact_phone: str | None
    message_text: str
    timestamp: datetime
    source: str = "baileys"


@dataclass(slots=True)
class StoredMessageRecord:
    message_id: str
    user_id: UUID
    direction: str
    contact_name: str
    contact_phone: str | None
    message_text: str
    timestamp: datetime
    source: str


@dataclass(slots=True)
class PersonaRecord:
    user_id: UUID
    life_summary: str
    last_analyzed_at: datetime | None
    last_snapshot_id: str | None


@dataclass(slots=True)
class MemorySnapshotRecord:
    id: str
    user_id: UUID
    window_hours: int
    window_start: datetime
    window_end: datetime
    source_message_count: int
    window_summary: str
    key_learnings: list[str]
    people_and_relationships: list[str]
    routine_signals: list[str]
    preferences: list[str]
    open_questions: list[str]
    created_at: datetime


class SupabaseStore:
    def __init__(self, supabase_url: str, supabase_key: str, default_user_id: UUID) -> None:
        self.client: Client = create_client(supabase_url, supabase_key)
        self.default_user_id = default_user_id

    def save_ingested_messages(self, messages: Sequence[IngestedMessageRecord]) -> int:
        if not messages:
            return 0

        records = [
            {
                "id": message.message_id,
                "user_id": str(message.user_id),
                "contact_name": message.contact_name,
                "contact_phone": message.contact_phone,
                "direction": message.direction,
                "message_text": message.message_text,
                "timestamp": message.timestamp.isoformat(),
                "source": message.source,
                "embedding": None,
            }
            for message in messages
        ]

        self.client.table("mensagens").upsert(records, on_conflict="id").execute()
        return len(records)

    def list_messages_in_window(
        self,
        *,
        user_id: UUID,
        window_start: datetime,
        window_end: datetime,
    ) -> list[StoredMessageRecord]:
        response = (
            self.client.table("mensagens")
            .select("id,user_id,contact_name,contact_phone,direction,message_text,timestamp,source")
            .eq("user_id", str(user_id))
            .gte("timestamp", window_start.isoformat())
            .lte("timestamp", window_end.isoformat())
            .order("timestamp", desc=False)
            .execute()
        )

        rows = response.data or []
        messages: list[StoredMessageRecord] = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            message_text = str(row.get("message_text") or "").strip()
            if not message_text:
                continue
            messages.append(
                StoredMessageRecord(
                    message_id=str(row.get("id") or ""),
                    user_id=self._parse_uuid(row.get("user_id")) or user_id,
                    direction=str(row.get("direction") or "inbound"),
                    contact_name=str(row.get("contact_name") or row.get("contact_phone") or "Contato"),
                    contact_phone=self._optional_text(row.get("contact_phone")),
                    message_text=message_text,
                    timestamp=self._parse_datetime(row.get("timestamp")) or datetime.now(UTC),
                    source=str(row.get("source") or "unknown"),
                )
            )
        return messages

    def get_persona(self, user_id: UUID) -> PersonaRecord | None:
        response = (
            self.client.table("persona")
            .select("user_id,life_summary,last_analyzed_at,last_snapshot_id")
            .eq("user_id", str(user_id))
            .limit(1)
            .execute()
        )

        rows = response.data or []
        if not rows:
            return None

        row = rows[0]
        if not isinstance(row, dict):
            return None

        return PersonaRecord(
            user_id=self._parse_uuid(row.get("user_id")) or user_id,
            life_summary=str(row.get("life_summary") or ""),
            last_analyzed_at=self._parse_datetime(row.get("last_analyzed_at")),
            last_snapshot_id=self._optional_text(row.get("last_snapshot_id")),
        )

    def persist_memory_analysis(
        self,
        *,
        snapshot: MemorySnapshotRecord,
        updated_life_summary: str,
        analyzed_at: datetime,
    ) -> PersonaRecord:
        self._insert_memory_snapshot(snapshot)
        try:
            persona_record = {
                "user_id": str(snapshot.user_id),
                "life_summary": updated_life_summary,
                "last_analyzed_at": analyzed_at.isoformat(),
                "last_snapshot_id": snapshot.id,
                "updated_at": analyzed_at.isoformat(),
            }
            self.client.table("persona").upsert(persona_record, on_conflict="user_id").execute()
        except Exception:
            self._delete_memory_snapshot(snapshot.id)
            raise

        persona = self.get_persona(snapshot.user_id)
        if persona is None:
            raise RuntimeError("Memory analysis persisted but persona record could not be fetched.")
        return persona

    def list_memory_snapshots(self, user_id: UUID, *, limit: int = 20) -> list[MemorySnapshotRecord]:
        response = (
            self.client.table("memory_snapshots")
            .select(
                "id,user_id,window_hours,window_start,window_end,source_message_count,"
                "window_summary,key_learnings,people_and_relationships,routine_signals,"
                "preferences,open_questions,created_at"
            )
            .eq("user_id", str(user_id))
            .order("created_at", desc=True)
            .limit(limit)
            .execute()
        )

        rows = response.data or []
        snapshots: list[MemorySnapshotRecord] = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            snapshots.append(
                MemorySnapshotRecord(
                    id=str(row.get("id") or ""),
                    user_id=self._parse_uuid(row.get("user_id")) or user_id,
                    window_hours=int(row.get("window_hours") or 1),
                    window_start=self._parse_datetime(row.get("window_start")) or datetime.now(UTC),
                    window_end=self._parse_datetime(row.get("window_end")) or datetime.now(UTC),
                    source_message_count=int(row.get("source_message_count") or 0),
                    window_summary=str(row.get("window_summary") or ""),
                    key_learnings=self._parse_string_list(row.get("key_learnings")),
                    people_and_relationships=self._parse_string_list(row.get("people_and_relationships")),
                    routine_signals=self._parse_string_list(row.get("routine_signals")),
                    preferences=self._parse_string_list(row.get("preferences")),
                    open_questions=self._parse_string_list(row.get("open_questions")),
                    created_at=self._parse_datetime(row.get("created_at")) or datetime.now(UTC),
                )
            )
        return snapshots

    def _insert_memory_snapshot(self, snapshot: MemorySnapshotRecord) -> None:
        record = {
            "id": snapshot.id,
            "user_id": str(snapshot.user_id),
            "window_hours": snapshot.window_hours,
            "window_start": snapshot.window_start.isoformat(),
            "window_end": snapshot.window_end.isoformat(),
            "source_message_count": snapshot.source_message_count,
            "window_summary": snapshot.window_summary,
            "key_learnings": snapshot.key_learnings,
            "people_and_relationships": snapshot.people_and_relationships,
            "routine_signals": snapshot.routine_signals,
            "preferences": snapshot.preferences,
            "open_questions": snapshot.open_questions,
            "created_at": snapshot.created_at.isoformat(),
        }
        self.client.table("memory_snapshots").insert(record).execute()

    def _delete_memory_snapshot(self, snapshot_id: str) -> None:
        self.client.table("memory_snapshots").delete().eq("id", snapshot_id).execute()

    def _parse_uuid(self, value: Any) -> UUID | None:
        if value is None:
            return None
        try:
            return UUID(str(value))
        except (TypeError, ValueError):
            return None

    def _optional_text(self, value: Any) -> str | None:
        if value is None:
            return None
        text = str(value).strip()
        return text or None

    def _parse_datetime(self, value: Any) -> datetime | None:
        if value is None:
            return None
        if isinstance(value, datetime):
            return value.astimezone(UTC)
        if isinstance(value, str):
            try:
                return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(UTC)
            except ValueError:
                return None
        return None

    def _parse_string_list(self, value: Any) -> list[str]:
        if not isinstance(value, list):
            return []
        items: list[str] = []
        for item in value:
            if item is None:
                continue
            text = str(item).strip()
            if text:
                items.append(text)
        return items
