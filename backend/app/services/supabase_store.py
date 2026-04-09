from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Sequence
from uuid import UUID, uuid4

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
    last_analyzed_ingested_count: int | None
    last_analyzed_pruned_count: int | None


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


@dataclass(slots=True)
class ProjectMemorySeed:
    project_name: str
    summary: str
    status: str
    what_is_being_built: str
    built_for: str
    next_steps: list[str]
    evidence: list[str]


@dataclass(slots=True)
class ProjectMemoryRecord:
    id: str
    user_id: UUID
    project_key: str
    project_name: str
    summary: str
    status: str
    what_is_being_built: str
    built_for: str
    next_steps: list[str]
    evidence: list[str]
    source_snapshot_id: str | None
    last_seen_at: datetime | None
    updated_at: datetime


@dataclass(slots=True)
class MessageRetentionStateRecord:
    user_id: UUID
    total_direct_ingested_count: int
    total_direct_pruned_count: int
    last_message_at: datetime | None
    updated_at: datetime | None


@dataclass(slots=True)
class ChatThreadRecord:
    id: str
    user_id: UUID
    thread_key: str
    title: str
    created_at: datetime
    updated_at: datetime


@dataclass(slots=True)
class ChatMessageRecord:
    id: str
    thread_id: str
    role: str
    content: str
    created_at: datetime


class SupabaseStore:
    def __init__(
        self,
        supabase_url: str,
        supabase_key: str,
        default_user_id: UUID,
        *,
        message_retention_max_rows: int = 5000,
    ) -> None:
        self.client: Client = create_client(supabase_url, supabase_key)
        self.default_user_id = default_user_id
        self.message_retention_max_rows = max(200, message_retention_max_rows)

    def save_ingested_messages(self, messages: Sequence[IngestedMessageRecord]) -> int:
        filtered_messages = [message for message in messages if self.is_normal_contact_phone(message.contact_phone)]
        if not filtered_messages:
            return 0

        known_contact_names = self._load_known_contact_names(
            [message.contact_phone for message in filtered_messages if message.contact_phone]
        )
        existing_ids = self._fetch_existing_message_ids([message.message_id for message in filtered_messages])
        new_message_count = sum(1 for message in filtered_messages if message.message_id not in existing_ids)

        records = [
            {
                "id": message.message_id,
                "user_id": str(message.user_id),
                "contact_name": self._resolve_contact_name(
                    incoming_name=message.contact_name,
                    contact_phone=message.contact_phone,
                    known_name=known_contact_names.get(message.contact_phone or ""),
                ),
                "contact_phone": message.contact_phone,
                "direction": message.direction,
                "message_text": message.message_text,
                "timestamp": message.timestamp.isoformat(),
                "source": message.source,
                "embedding": None,
            }
            for message in filtered_messages
        ]

        self.client.table("mensagens").upsert(records, on_conflict="id").execute()
        if new_message_count > 0:
            self.bump_message_retention_state(
                user_id=self.default_user_id,
                ingested_increment=new_message_count,
                last_message_at=max(message.timestamp for message in filtered_messages),
            )
        self.prune_non_direct_messages(self.default_user_id)
        pruned_count = self.prune_old_messages(self.default_user_id)
        if pruned_count > 0:
            self.bump_message_retention_state(
                user_id=self.default_user_id,
                pruned_increment=pruned_count,
            )
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
            contact_phone = self._optional_text(row.get("contact_phone"))
            if not message_text or not self.is_normal_contact_phone(contact_phone):
                continue
            messages.append(
                StoredMessageRecord(
                    message_id=str(row.get("id") or ""),
                    user_id=self._parse_uuid(row.get("user_id")) or user_id,
                    direction=str(row.get("direction") or "inbound"),
                    contact_name=str(row.get("contact_name") or row.get("contact_phone") or "Contato"),
                    contact_phone=contact_phone,
                    message_text=message_text,
                    timestamp=self._parse_datetime(row.get("timestamp")) or datetime.now(UTC),
                    source=str(row.get("source") or "unknown"),
                )
            )
        return messages

    def prune_non_direct_messages(self, user_id: UUID) -> int:
        deleted_total = 0
        while True:
            response = (
                self.client.table("mensagens")
                .select("id,contact_phone")
                .eq("user_id", str(user_id))
                .limit(5000)
                .execute()
            )

            rows = response.data or []
            delete_ids: list[str] = []
            for row in rows:
                if not isinstance(row, dict):
                    continue
                message_id = str(row.get("id") or "").strip()
                contact_phone = self._optional_text(row.get("contact_phone"))
                if message_id and not self.is_normal_contact_phone(contact_phone):
                    delete_ids.append(message_id)

            if not delete_ids:
                break

            self.client.table("mensagens").delete().in_("id", delete_ids).execute()
            deleted_total += len(delete_ids)
        return deleted_total

    def prune_old_messages(self, user_id: UUID) -> int:
        offset = self.message_retention_max_rows
        deleted_total = 0
        while True:
            response = (
                self.client.table("mensagens")
                .select("id")
                .eq("user_id", str(user_id))
                .order("timestamp", desc=True)
                .range(offset, offset + 999)
                .execute()
            )

            rows = response.data or []
            delete_ids = [str(row.get("id") or "").strip() for row in rows if isinstance(row, dict) and str(row.get("id") or "").strip()]
            if not delete_ids:
                break

            self.client.table("mensagens").delete().in_("id", delete_ids).execute()
            deleted_total += len(delete_ids)
        return deleted_total

    def get_persona(self, user_id: UUID) -> PersonaRecord | None:
        response = (
            self.client.table("persona")
            .select(
                "user_id,life_summary,last_analyzed_at,last_snapshot_id,"
                "last_analyzed_ingested_count,last_analyzed_pruned_count"
            )
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
            last_analyzed_ingested_count=self._parse_int(row.get("last_analyzed_ingested_count")),
            last_analyzed_pruned_count=self._parse_int(row.get("last_analyzed_pruned_count")),
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
            retention_state = self.get_message_retention_state(snapshot.user_id)
            persona_record = {
                "user_id": str(snapshot.user_id),
                "life_summary": updated_life_summary,
                "last_analyzed_at": analyzed_at.isoformat(),
                "last_snapshot_id": snapshot.id,
                "last_analyzed_ingested_count": retention_state.total_direct_ingested_count,
                "last_analyzed_pruned_count": retention_state.total_direct_pruned_count,
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

    def update_persona_summary(
        self,
        *,
        user_id: UUID,
        updated_life_summary: str,
        analyzed_at: datetime,
    ) -> PersonaRecord:
        current = self.get_persona(user_id)
        retention_state = self.get_message_retention_state(user_id)
        persona_record = {
            "user_id": str(user_id),
            "life_summary": updated_life_summary,
            "last_analyzed_at": analyzed_at.isoformat(),
            "last_snapshot_id": current.last_snapshot_id if current else None,
            "last_analyzed_ingested_count": retention_state.total_direct_ingested_count,
            "last_analyzed_pruned_count": retention_state.total_direct_pruned_count,
            "updated_at": analyzed_at.isoformat(),
        }
        self.client.table("persona").upsert(persona_record, on_conflict="user_id").execute()

        persona = self.get_persona(user_id)
        if persona is None:
            raise RuntimeError("Persona summary was updated but could not be fetched afterwards.")
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

    def upsert_project_memories(
        self,
        *,
        user_id: UUID,
        source_snapshot_id: str | None,
        projects: Sequence[ProjectMemorySeed],
        observed_at: datetime,
    ) -> list[ProjectMemoryRecord]:
        records: list[dict[str, Any]] = []
        seen_keys: set[str] = set()

        for project in projects:
            project_name = project.project_name.strip()
            summary = project.summary.strip()
            if not project_name or not summary:
                continue

            project_key = self._normalize_project_key(project_name)
            if not project_key or project_key in seen_keys:
                continue

            seen_keys.add(project_key)
            records.append(
                {
                    "id": str(uuid4()),
                    "user_id": str(user_id),
                    "project_key": project_key,
                    "project_name": project_name,
                    "summary": summary,
                    "status": project.status.strip(),
                    "what_is_being_built": project.what_is_being_built.strip(),
                    "built_for": project.built_for.strip(),
                    "next_steps": self._clean_string_list(project.next_steps),
                    "evidence": self._clean_string_list(project.evidence),
                    "source_snapshot_id": source_snapshot_id,
                    "last_seen_at": observed_at.isoformat(),
                    "updated_at": observed_at.isoformat(),
                }
            )

        if not records:
            return self.list_project_memories(user_id, limit=8)

        self.client.table("project_memories").upsert(records, on_conflict="user_id,project_key").execute()
        return self.list_project_memories(user_id, limit=max(8, len(records)))

    def list_project_memories(self, user_id: UUID, *, limit: int = 8) -> list[ProjectMemoryRecord]:
        response = (
            self.client.table("project_memories")
            .select(
                "id,user_id,project_key,project_name,summary,status,what_is_being_built,built_for,next_steps,evidence,"
                "source_snapshot_id,last_seen_at,updated_at"
            )
            .eq("user_id", str(user_id))
            .order("last_seen_at", desc=True)
            .limit(limit)
            .execute()
        )

        rows = response.data or []
        projects: list[ProjectMemoryRecord] = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            projects.append(
                ProjectMemoryRecord(
                    id=str(row.get("id") or ""),
                    user_id=self._parse_uuid(row.get("user_id")) or user_id,
                    project_key=str(row.get("project_key") or ""),
                    project_name=str(row.get("project_name") or ""),
                    summary=str(row.get("summary") or ""),
                    status=str(row.get("status") or ""),
                    what_is_being_built=str(row.get("what_is_being_built") or ""),
                    built_for=str(row.get("built_for") or ""),
                    next_steps=self._parse_string_list(row.get("next_steps")),
                    evidence=self._parse_string_list(row.get("evidence")),
                    source_snapshot_id=self._optional_text(row.get("source_snapshot_id")),
                    last_seen_at=self._parse_datetime(row.get("last_seen_at")),
                    updated_at=self._parse_datetime(row.get("updated_at")) or datetime.now(UTC),
                )
            )
        return projects

    def get_or_create_chat_thread(
        self,
        *,
        user_id: UUID,
        thread_key: str = "default",
        title: str = "Conversa principal",
    ) -> ChatThreadRecord:
        response = (
            self.client.table("chat_threads")
            .select("id,user_id,thread_key,title,created_at,updated_at")
            .eq("user_id", str(user_id))
            .eq("thread_key", thread_key)
            .limit(1)
            .execute()
        )

        rows = response.data or []
        if rows:
            parsed = self._parse_chat_thread(rows[0], fallback_user_id=user_id)
            if parsed is not None:
                return parsed

        created_at = datetime.now(UTC)
        record = {
            "id": str(uuid4()),
            "user_id": str(user_id),
            "thread_key": thread_key,
            "title": title,
            "created_at": created_at.isoformat(),
            "updated_at": created_at.isoformat(),
        }
        self.client.table("chat_threads").upsert(record, on_conflict="user_id,thread_key").execute()

        response = (
            self.client.table("chat_threads")
            .select("id,user_id,thread_key,title,created_at,updated_at")
            .eq("user_id", str(user_id))
            .eq("thread_key", thread_key)
            .limit(1)
            .execute()
        )
        rows = response.data or []
        if not rows:
            raise RuntimeError("Default chat thread could not be created.")

        parsed = self._parse_chat_thread(rows[0], fallback_user_id=user_id)
        if parsed is None:
            raise RuntimeError("Default chat thread returned an invalid payload.")
        return parsed

    def list_chat_messages(self, thread_id: str, *, limit: int = 30) -> list[ChatMessageRecord]:
        response = (
            self.client.table("chat_messages")
            .select("id,thread_id,role,content,created_at")
            .eq("thread_id", thread_id)
            .order("created_at", desc=True)
            .limit(limit)
            .execute()
        )

        rows = response.data or []
        messages: list[ChatMessageRecord] = []
        for row in reversed(rows):
            parsed = self._parse_chat_message(row, fallback_thread_id=thread_id)
            if parsed is not None:
                messages.append(parsed)
        return messages

    def append_chat_message(
        self,
        *,
        thread_id: str,
        role: str,
        content: str,
        created_at: datetime,
    ) -> ChatMessageRecord:
        message_id = str(uuid4())
        record = {
            "id": message_id,
            "thread_id": thread_id,
            "role": role,
            "content": content,
            "created_at": created_at.isoformat(),
        }
        self.client.table("chat_messages").insert(record).execute()
        self.client.table("chat_threads").update({"updated_at": created_at.isoformat()}).eq("id", thread_id).execute()
        return ChatMessageRecord(
            id=message_id,
            thread_id=thread_id,
            role=role,
            content=content,
            created_at=created_at,
        )

    def count_messages(self, user_id: UUID) -> int:
        response = (
            self.client.table("mensagens")
            .select("id")
            .eq("user_id", str(user_id))
            .limit(self.message_retention_max_rows)
            .execute()
        )
        rows = response.data or []
        return sum(1 for row in rows if isinstance(row, dict))

    def count_messages_in_window(self, *, user_id: UUID, window_start: datetime, window_end: datetime) -> int:
        response = (
            self.client.table("mensagens")
            .select("id")
            .eq("user_id", str(user_id))
            .gte("timestamp", window_start.isoformat())
            .lte("timestamp", window_end.isoformat())
            .limit(self.message_retention_max_rows)
            .execute()
        )
        rows = response.data or []
        return sum(1 for row in rows if isinstance(row, dict))

    def get_latest_message_timestamp(self, user_id: UUID) -> datetime | None:
        response = (
            self.client.table("mensagens")
            .select("timestamp")
            .eq("user_id", str(user_id))
            .order("timestamp", desc=True)
            .limit(1)
            .execute()
        )
        rows = response.data or []
        if not rows or not isinstance(rows[0], dict):
            return None
        return self._parse_datetime(rows[0].get("timestamp"))

    def get_message_retention_state(self, user_id: UUID) -> MessageRetentionStateRecord:
        response = (
            self.client.table("message_retention_state")
            .select("user_id,total_direct_ingested_count,total_direct_pruned_count,last_message_at,updated_at")
            .eq("user_id", str(user_id))
            .limit(1)
            .execute()
        )
        rows = response.data or []
        if rows and isinstance(rows[0], dict):
            row = rows[0]
            return MessageRetentionStateRecord(
                user_id=self._parse_uuid(row.get("user_id")) or user_id,
                total_direct_ingested_count=self._parse_int(row.get("total_direct_ingested_count")) or 0,
                total_direct_pruned_count=self._parse_int(row.get("total_direct_pruned_count")) or 0,
                last_message_at=self._parse_datetime(row.get("last_message_at")),
                updated_at=self._parse_datetime(row.get("updated_at")),
            )

        created_at = datetime.now(UTC)
        current_count = self.count_messages(user_id)
        last_message_at = self.get_latest_message_timestamp(user_id)
        record = {
            "user_id": str(user_id),
            "total_direct_ingested_count": current_count,
            "total_direct_pruned_count": 0,
            "last_message_at": last_message_at.isoformat() if last_message_at else None,
            "updated_at": created_at.isoformat(),
        }
        self.client.table("message_retention_state").upsert(record, on_conflict="user_id").execute()
        return MessageRetentionStateRecord(
            user_id=user_id,
            total_direct_ingested_count=current_count,
            total_direct_pruned_count=0,
            last_message_at=last_message_at,
            updated_at=created_at,
        )

    def bump_message_retention_state(
        self,
        *,
        user_id: UUID,
        ingested_increment: int = 0,
        pruned_increment: int = 0,
        last_message_at: datetime | None = None,
    ) -> MessageRetentionStateRecord:
        current = self.get_message_retention_state(user_id)
        updated_at = datetime.now(UTC)
        resolved_last_message_at = last_message_at or current.last_message_at
        record = {
            "user_id": str(user_id),
            "total_direct_ingested_count": current.total_direct_ingested_count + max(0, ingested_increment),
            "total_direct_pruned_count": current.total_direct_pruned_count + max(0, pruned_increment),
            "last_message_at": resolved_last_message_at.isoformat() if resolved_last_message_at else None,
            "updated_at": updated_at.isoformat(),
        }
        self.client.table("message_retention_state").upsert(record, on_conflict="user_id").execute()
        return MessageRetentionStateRecord(
            user_id=user_id,
            total_direct_ingested_count=int(record["total_direct_ingested_count"]),
            total_direct_pruned_count=int(record["total_direct_pruned_count"]),
            last_message_at=resolved_last_message_at,
            updated_at=updated_at,
        )

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

    def _parse_int(self, value: Any) -> int | None:
        if value is None:
            return None
        try:
            return int(value)
        except (TypeError, ValueError):
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

    def _clean_string_list(self, items: Sequence[Any]) -> list[str]:
        cleaned: list[str] = []
        for item in items:
            if item is None:
                continue
            text = str(item).strip()
            if text:
                cleaned.append(text)
        return cleaned

    def _load_known_contact_names(self, contact_phones: Sequence[str | None]) -> dict[str, str]:
        cleaned_phones = sorted({phone.strip() for phone in contact_phones if phone and phone.strip()})
        if not cleaned_phones:
            return {}

        known_names: dict[str, str] = {}
        chunk_size = 100
        for start in range(0, len(cleaned_phones), chunk_size):
            chunk = cleaned_phones[start:start + chunk_size]
            response = (
                self.client.table("mensagens")
                .select("contact_phone,contact_name,timestamp")
                .in_("contact_phone", chunk)
                .order("timestamp", desc=True)
                .limit(max(200, len(chunk) * 12))
                .execute()
            )
            rows = response.data or []
            for row in rows:
                if not isinstance(row, dict):
                    continue
                phone = self._optional_text(row.get("contact_phone"))
                name = self._optional_text(row.get("contact_name"))
                if not phone or phone in known_names:
                    continue
                if self._is_useful_contact_name(name, phone):
                    known_names[phone] = name or phone
        return known_names

    def _resolve_contact_name(
        self,
        *,
        incoming_name: str | None,
        contact_phone: str | None,
        known_name: str | None,
    ) -> str:
        phone = self._optional_text(contact_phone) or "Contato"
        incoming = self._optional_text(incoming_name)
        if self._is_useful_contact_name(incoming, phone):
            return incoming or phone
        if self._is_useful_contact_name(known_name, phone):
            return known_name or phone
        return incoming or phone

    def is_normal_contact_phone(self, value: str | None) -> bool:
        return self._is_normal_contact_phone(value)

    def is_direct_chat_jid(self, value: str | None) -> bool:
        return self._is_direct_chat_jid(value)

    def _is_normal_contact_phone(self, value: str | None) -> bool:
        if value is None:
            return False
        digits = "".join(char for char in value if char.isdigit())
        return 8 <= len(digits) <= 15

    def _is_direct_chat_jid(self, value: str | None) -> bool:
        if value is None:
            return False
        normalized = value.strip().lower()
        if not normalized or "@" not in normalized:
            return False
        if normalized == "status@broadcast":
            return False
        return not (
            normalized.endswith("@g.us")
            or normalized.endswith("@broadcast")
            or normalized.endswith("@newsletter")
        )

    def _is_useful_contact_name(self, value: str | None, contact_phone: str | None) -> bool:
        text = self._optional_text(value)
        phone = self._optional_text(contact_phone)
        if not text:
            return False
        if not phone:
            return True
        if text == phone:
            return False
        text_digits = "".join(char for char in text if char.isdigit())
        phone_digits = "".join(char for char in phone if char.isdigit())
        return not text_digits or text_digits != phone_digits

    def _normalize_project_key(self, value: str) -> str:
        normalized_chars = [
            char.lower() if char.isalnum() else "-"
            for char in value.strip()
        ]
        collapsed = "".join(normalized_chars)
        while "--" in collapsed:
            collapsed = collapsed.replace("--", "-")
        return collapsed.strip("-")

    def _fetch_existing_message_ids(self, message_ids: Sequence[str]) -> set[str]:
        cleaned_ids = [message_id.strip() for message_id in message_ids if message_id and message_id.strip()]
        if not cleaned_ids:
            return set()

        chunk_size = 500
        existing: set[str] = set()
        for start in range(0, len(cleaned_ids), chunk_size):
            chunk = cleaned_ids[start:start + chunk_size]
            response = self.client.table("mensagens").select("id").in_("id", chunk).execute()
            rows = response.data or []
            existing.update(
                str(row.get("id") or "").strip()
                for row in rows
                if isinstance(row, dict) and str(row.get("id") or "").strip()
            )
        return existing

    def _parse_chat_thread(self, value: Any, *, fallback_user_id: UUID) -> ChatThreadRecord | None:
        if not isinstance(value, dict):
            return None
        return ChatThreadRecord(
            id=str(value.get("id") or ""),
            user_id=self._parse_uuid(value.get("user_id")) or fallback_user_id,
            thread_key=str(value.get("thread_key") or "default"),
            title=str(value.get("title") or "Conversa principal"),
            created_at=self._parse_datetime(value.get("created_at")) or datetime.now(UTC),
            updated_at=self._parse_datetime(value.get("updated_at")) or datetime.now(UTC),
        )

    def _parse_chat_message(self, value: Any, *, fallback_thread_id: str) -> ChatMessageRecord | None:
        if not isinstance(value, dict):
            return None
        role = str(value.get("role") or "").strip()
        if role not in {"user", "assistant"}:
            return None
        content = str(value.get("content") or "").strip()
        if not content:
            return None
        return ChatMessageRecord(
            id=str(value.get("id") or ""),
            thread_id=str(value.get("thread_id") or fallback_thread_id),
            role=role,
            content=content,
            created_at=self._parse_datetime(value.get("created_at")) or datetime.now(UTC),
        )
