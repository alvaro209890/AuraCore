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
    chat_jid: str
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
    chat_jid: str | None
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


@dataclass(slots=True)
class AutomationSettingsRecord:
    user_id: UUID
    auto_sync_enabled: bool
    auto_analyze_enabled: bool
    auto_refine_enabled: bool
    min_new_messages_threshold: int
    stale_hours_threshold: int
    pruned_messages_threshold: int
    default_detail_mode: str
    default_target_message_count: int
    default_lookback_hours: int
    daily_budget_usd: float
    max_auto_jobs_per_day: int
    updated_at: datetime


@dataclass(slots=True)
class WhatsAppSyncRunRecord:
    id: str
    user_id: UUID
    trigger: str
    status: str
    messages_seen_count: int
    messages_saved_count: int
    messages_ignored_count: int
    messages_pruned_count: int
    oldest_message_at: datetime | None
    newest_message_at: datetime | None
    error_text: str | None
    started_at: datetime
    finished_at: datetime | None
    last_activity_at: datetime | None


@dataclass(slots=True)
class AutomationDecisionRecord:
    id: str
    user_id: UUID
    sync_run_id: str | None
    intent: str
    action: str
    reason_code: str
    score: int
    should_analyze: bool
    available_message_count: int
    selected_message_count: int
    new_message_count: int
    replaced_message_count: int
    estimated_total_tokens: int
    estimated_cost_ceiling_usd: float
    explanation: str
    created_at: datetime


@dataclass(slots=True)
class AnalysisJobRecord:
    id: str
    user_id: UUID
    intent: str
    status: str
    trigger_source: str
    decision_id: str | None
    sync_run_id: str | None
    target_message_count: int
    max_lookback_hours: int
    detail_mode: str
    selected_message_count: int
    selected_transcript_chars: int
    estimated_input_tokens: int
    estimated_output_tokens: int
    estimated_cost_floor_usd: float
    estimated_cost_ceiling_usd: float
    snapshot_id: str | None
    error_text: str | None
    started_at: datetime | None
    finished_at: datetime | None
    created_at: datetime


@dataclass(slots=True)
class ModelRunRecord:
    id: str
    user_id: UUID
    job_id: str | None
    provider: str
    model_name: str
    run_type: str
    success: bool
    latency_ms: int | None
    input_tokens: int | None
    output_tokens: int | None
    reasoning_tokens: int | None
    estimated_cost_usd: float | None
    error_text: str | None
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
                "chat_jid": message.chat_jid,
                "contact_phone": message.contact_phone,
                "direction": message.direction,
                "message_text": message.message_text,
                "timestamp": message.timestamp.isoformat(),
                "source": message.source,
                "embedding": None,
                "ingested_at": datetime.now(UTC).isoformat(),
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
            .select("id,user_id,contact_name,chat_jid,contact_phone,direction,message_text,timestamp,source")
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
                    chat_jid=self._optional_text(row.get("chat_jid")),
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

    def get_automation_settings(self, user_id: UUID) -> AutomationSettingsRecord:
        response = (
            self.client.table("automation_settings")
            .select(
                "user_id,auto_sync_enabled,auto_analyze_enabled,auto_refine_enabled,"
                "min_new_messages_threshold,stale_hours_threshold,pruned_messages_threshold,"
                "default_detail_mode,default_target_message_count,default_lookback_hours,"
                "daily_budget_usd,max_auto_jobs_per_day,updated_at"
            )
            .eq("user_id", str(user_id))
            .limit(1)
            .execute()
        )
        rows = response.data or []
        if rows and isinstance(rows[0], dict):
            parsed = self._parse_automation_settings(rows[0], fallback_user_id=user_id)
            if parsed is not None:
                return parsed

        created_at = datetime.now(UTC)
        record = self._default_automation_settings_record(user_id=user_id, updated_at=created_at)
        self.client.table("automation_settings").upsert(record, on_conflict="user_id").execute()
        return AutomationSettingsRecord(
            user_id=user_id,
            auto_sync_enabled=bool(record["auto_sync_enabled"]),
            auto_analyze_enabled=bool(record["auto_analyze_enabled"]),
            auto_refine_enabled=bool(record["auto_refine_enabled"]),
            min_new_messages_threshold=int(record["min_new_messages_threshold"]),
            stale_hours_threshold=int(record["stale_hours_threshold"]),
            pruned_messages_threshold=int(record["pruned_messages_threshold"]),
            default_detail_mode=str(record["default_detail_mode"]),
            default_target_message_count=int(record["default_target_message_count"]),
            default_lookback_hours=int(record["default_lookback_hours"]),
            daily_budget_usd=float(record["daily_budget_usd"]),
            max_auto_jobs_per_day=int(record["max_auto_jobs_per_day"]),
            updated_at=created_at,
        )

    def update_automation_settings(
        self,
        *,
        user_id: UUID,
        auto_sync_enabled: bool | None = None,
        auto_analyze_enabled: bool | None = None,
        auto_refine_enabled: bool | None = None,
        min_new_messages_threshold: int | None = None,
        stale_hours_threshold: int | None = None,
        pruned_messages_threshold: int | None = None,
        default_detail_mode: str | None = None,
        default_target_message_count: int | None = None,
        default_lookback_hours: int | None = None,
        daily_budget_usd: float | None = None,
        max_auto_jobs_per_day: int | None = None,
    ) -> AutomationSettingsRecord:
        current = self.get_automation_settings(user_id)
        updated_at = datetime.now(UTC)
        record = {
            "user_id": str(user_id),
            "auto_sync_enabled": current.auto_sync_enabled if auto_sync_enabled is None else bool(auto_sync_enabled),
            "auto_analyze_enabled": current.auto_analyze_enabled if auto_analyze_enabled is None else bool(auto_analyze_enabled),
            "auto_refine_enabled": current.auto_refine_enabled if auto_refine_enabled is None else bool(auto_refine_enabled),
            "min_new_messages_threshold": max(1, min_new_messages_threshold if min_new_messages_threshold is not None else current.min_new_messages_threshold),
            "stale_hours_threshold": max(1, stale_hours_threshold if stale_hours_threshold is not None else current.stale_hours_threshold),
            "pruned_messages_threshold": max(0, pruned_messages_threshold if pruned_messages_threshold is not None else current.pruned_messages_threshold),
            "default_detail_mode": self._normalize_detail_mode(default_detail_mode or current.default_detail_mode),
            "default_target_message_count": max(20, min(
                self.message_retention_max_rows,
                default_target_message_count if default_target_message_count is not None else current.default_target_message_count,
            )),
            "default_lookback_hours": max(1, default_lookback_hours if default_lookback_hours is not None else current.default_lookback_hours),
            "daily_budget_usd": max(0.0, daily_budget_usd if daily_budget_usd is not None else current.daily_budget_usd),
            "max_auto_jobs_per_day": max(1, max_auto_jobs_per_day if max_auto_jobs_per_day is not None else current.max_auto_jobs_per_day),
            "updated_at": updated_at.isoformat(),
        }
        self.client.table("automation_settings").upsert(record, on_conflict="user_id").execute()
        refreshed = self.get_automation_settings(user_id)
        return refreshed

    def create_whatsapp_sync_run(
        self,
        *,
        user_id: UUID,
        trigger: str,
        started_at: datetime,
    ) -> WhatsAppSyncRunRecord:
        retention_state = self.get_message_retention_state(user_id)
        sync_run_id = str(uuid4())
        record = {
            "id": sync_run_id,
            "user_id": str(user_id),
            "trigger": trigger,
            "status": "running",
            "messages_seen_count": 0,
            "messages_saved_count": 0,
            "messages_ignored_count": 0,
            "messages_pruned_count": 0,
            "oldest_message_at": None,
            "newest_message_at": None,
            "error_text": None,
            "baseline_ingested_count": retention_state.total_direct_ingested_count,
            "baseline_pruned_count": retention_state.total_direct_pruned_count,
            "last_activity_at": started_at.isoformat(),
            "started_at": started_at.isoformat(),
            "finished_at": None,
        }
        self.client.table("wa_sync_runs").insert(record).execute()
        sync_run = self.get_whatsapp_sync_run(sync_run_id)
        if sync_run is None:
            raise RuntimeError("WhatsApp sync run could not be created.")
        return sync_run

    def get_whatsapp_sync_run(self, sync_run_id: str) -> WhatsAppSyncRunRecord | None:
        response = (
            self.client.table("wa_sync_runs")
            .select(
                "id,user_id,trigger,status,messages_seen_count,messages_saved_count,messages_ignored_count,"
                "messages_pruned_count,oldest_message_at,newest_message_at,error_text,started_at,finished_at,last_activity_at"
            )
            .eq("id", sync_run_id)
            .limit(1)
            .execute()
        )
        rows = response.data or []
        if not rows or not isinstance(rows[0], dict):
            return None
        return self._parse_whatsapp_sync_run(rows[0], fallback_user_id=self.default_user_id)

    def get_latest_running_sync_run(self, user_id: UUID) -> WhatsAppSyncRunRecord | None:
        response = (
            self.client.table("wa_sync_runs")
            .select(
                "id,user_id,trigger,status,messages_seen_count,messages_saved_count,messages_ignored_count,"
                "messages_pruned_count,oldest_message_at,newest_message_at,error_text,started_at,finished_at,last_activity_at"
            )
            .eq("user_id", str(user_id))
            .eq("status", "running")
            .order("started_at", desc=True)
            .limit(1)
            .execute()
        )
        rows = response.data or []
        if not rows or not isinstance(rows[0], dict):
            return None
        return self._parse_whatsapp_sync_run(rows[0], fallback_user_id=user_id)

    def touch_latest_running_sync_run(
        self,
        *,
        user_id: UUID,
        seen_increment: int,
        saved_increment: int,
        ignored_increment: int,
        oldest_message_at: datetime | None,
        newest_message_at: datetime | None,
        activity_at: datetime,
    ) -> WhatsAppSyncRunRecord | None:
        row = self._get_latest_running_sync_run_row(user_id)
        if row is None:
            return None

        sync_run_id = str(row.get("id") or "")
        current_oldest = self._parse_datetime(row.get("oldest_message_at"))
        current_newest = self._parse_datetime(row.get("newest_message_at"))
        update_payload = {
            "messages_seen_count": (self._parse_int(row.get("messages_seen_count")) or 0) + max(0, seen_increment),
            "messages_saved_count": (self._parse_int(row.get("messages_saved_count")) or 0) + max(0, saved_increment),
            "messages_ignored_count": (self._parse_int(row.get("messages_ignored_count")) or 0) + max(0, ignored_increment),
            "oldest_message_at": self._earliest_datetime(current_oldest, oldest_message_at),
            "newest_message_at": self._latest_datetime(current_newest, newest_message_at),
            "last_activity_at": activity_at.isoformat(),
        }
        if isinstance(update_payload["oldest_message_at"], datetime):
            update_payload["oldest_message_at"] = update_payload["oldest_message_at"].isoformat()
        if isinstance(update_payload["newest_message_at"], datetime):
            update_payload["newest_message_at"] = update_payload["newest_message_at"].isoformat()

        self.client.table("wa_sync_runs").update(update_payload).eq("id", sync_run_id).execute()
        return self.get_whatsapp_sync_run(sync_run_id)

    def mark_whatsapp_sync_run_failed(self, *, sync_run_id: str, error_text: str, finished_at: datetime) -> WhatsAppSyncRunRecord | None:
        self.client.table("wa_sync_runs").update(
            {
                "status": "failed",
                "error_text": error_text,
                "finished_at": finished_at.isoformat(),
                "last_activity_at": finished_at.isoformat(),
            }
        ).eq("id", sync_run_id).execute()
        return self.get_whatsapp_sync_run(sync_run_id)

    def finalize_idle_sync_runs(self, *, user_id: UUID, idle_before: datetime) -> list[WhatsAppSyncRunRecord]:
        response = (
            self.client.table("wa_sync_runs")
            .select(
                "id,user_id,trigger,status,messages_seen_count,messages_saved_count,messages_ignored_count,"
                "messages_pruned_count,oldest_message_at,newest_message_at,error_text,started_at,finished_at,"
                "last_activity_at,baseline_ingested_count,baseline_pruned_count"
            )
            .eq("user_id", str(user_id))
            .eq("status", "running")
            .order("started_at", desc=False)
            .limit(20)
            .execute()
        )
        rows = response.data or []
        if not rows:
            return []

        retention_state = self.get_message_retention_state(user_id)
        finalized: list[WhatsAppSyncRunRecord] = []
        finished_at = datetime.now(UTC)
        for row in rows:
            if not isinstance(row, dict):
                continue
            last_activity_at = self._parse_datetime(row.get("last_activity_at")) or self._parse_datetime(row.get("started_at"))
            if last_activity_at is not None and last_activity_at > idle_before:
                continue

            baseline_ingested_count = self._parse_int(row.get("baseline_ingested_count")) or 0
            baseline_pruned_count = self._parse_int(row.get("baseline_pruned_count")) or 0
            saved_from_retention = max(0, retention_state.total_direct_ingested_count - baseline_ingested_count)
            pruned_from_retention = max(0, retention_state.total_direct_pruned_count - baseline_pruned_count)

            sync_run_id = str(row.get("id") or "")
            self.client.table("wa_sync_runs").update(
                {
                    "status": "succeeded",
                    "messages_saved_count": max(self._parse_int(row.get("messages_saved_count")) or 0, saved_from_retention),
                    "messages_pruned_count": max(self._parse_int(row.get("messages_pruned_count")) or 0, pruned_from_retention),
                    "finished_at": finished_at.isoformat(),
                    "last_activity_at": (last_activity_at or finished_at).isoformat(),
                }
            ).eq("id", sync_run_id).execute()
            resolved = self.get_whatsapp_sync_run(sync_run_id)
            if resolved is not None:
                finalized.append(resolved)
        return finalized

    def list_whatsapp_sync_runs(self, *, user_id: UUID, limit: int = 8) -> list[WhatsAppSyncRunRecord]:
        response = (
            self.client.table("wa_sync_runs")
            .select(
                "id,user_id,trigger,status,messages_seen_count,messages_saved_count,messages_ignored_count,"
                "messages_pruned_count,oldest_message_at,newest_message_at,error_text,started_at,finished_at,last_activity_at"
            )
            .eq("user_id", str(user_id))
            .order("started_at", desc=True)
            .limit(limit)
            .execute()
        )
        rows = response.data or []
        runs: list[WhatsAppSyncRunRecord] = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            parsed = self._parse_whatsapp_sync_run(row, fallback_user_id=user_id)
            if parsed is not None:
                runs.append(parsed)
        return runs

    def create_automation_decision(
        self,
        *,
        user_id: UUID,
        sync_run_id: str | None,
        intent: str,
        action: str,
        reason_code: str,
        score: int,
        should_analyze: bool,
        available_message_count: int,
        selected_message_count: int,
        new_message_count: int,
        replaced_message_count: int,
        estimated_total_tokens: int,
        estimated_cost_ceiling_usd: float,
        explanation: str,
        created_at: datetime,
    ) -> AutomationDecisionRecord:
        decision_id = str(uuid4())
        record = {
            "id": decision_id,
            "user_id": str(user_id),
            "sync_run_id": sync_run_id,
            "intent": intent,
            "action": action,
            "reason_code": reason_code,
            "score": max(0, min(100, score)),
            "should_analyze": bool(should_analyze),
            "available_message_count": max(0, available_message_count),
            "selected_message_count": max(0, selected_message_count),
            "new_message_count": max(0, new_message_count),
            "replaced_message_count": max(0, replaced_message_count),
            "estimated_total_tokens": max(0, estimated_total_tokens),
            "estimated_cost_ceiling_usd": max(0.0, estimated_cost_ceiling_usd),
            "explanation": explanation.strip(),
            "created_at": created_at.isoformat(),
        }
        self.client.table("automation_decisions").insert(record).execute()
        return AutomationDecisionRecord(
            id=decision_id,
            user_id=user_id,
            sync_run_id=sync_run_id,
            intent=intent,
            action=action,
            reason_code=reason_code,
            score=int(record["score"]),
            should_analyze=bool(record["should_analyze"]),
            available_message_count=int(record["available_message_count"]),
            selected_message_count=int(record["selected_message_count"]),
            new_message_count=int(record["new_message_count"]),
            replaced_message_count=int(record["replaced_message_count"]),
            estimated_total_tokens=int(record["estimated_total_tokens"]),
            estimated_cost_ceiling_usd=float(record["estimated_cost_ceiling_usd"]),
            explanation=str(record["explanation"]),
            created_at=created_at,
        )

    def list_automation_decisions(self, *, user_id: UUID, limit: int = 10) -> list[AutomationDecisionRecord]:
        response = (
            self.client.table("automation_decisions")
            .select(
                "id,user_id,sync_run_id,intent,action,reason_code,score,should_analyze,available_message_count,"
                "selected_message_count,new_message_count,replaced_message_count,estimated_total_tokens,"
                "estimated_cost_ceiling_usd,explanation,created_at"
            )
            .eq("user_id", str(user_id))
            .order("created_at", desc=True)
            .limit(limit)
            .execute()
        )
        rows = response.data or []
        decisions: list[AutomationDecisionRecord] = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            parsed = self._parse_automation_decision(row, fallback_user_id=user_id)
            if parsed is not None:
                decisions.append(parsed)
        return decisions

    def create_analysis_job(
        self,
        *,
        user_id: UUID,
        intent: str,
        status: str,
        trigger_source: str,
        decision_id: str | None,
        sync_run_id: str | None,
        target_message_count: int,
        max_lookback_hours: int,
        detail_mode: str,
        selected_message_count: int = 0,
        selected_transcript_chars: int = 0,
        estimated_input_tokens: int = 0,
        estimated_output_tokens: int = 0,
        estimated_cost_floor_usd: float = 0.0,
        estimated_cost_ceiling_usd: float = 0.0,
        snapshot_id: str | None = None,
        error_text: str | None = None,
        started_at: datetime | None = None,
        finished_at: datetime | None = None,
        created_at: datetime | None = None,
    ) -> AnalysisJobRecord:
        resolved_created_at = created_at or datetime.now(UTC)
        job_id = str(uuid4())
        record = {
            "id": job_id,
            "user_id": str(user_id),
            "intent": intent,
            "status": status,
            "trigger_source": trigger_source,
            "decision_id": decision_id,
            "sync_run_id": sync_run_id,
            "target_message_count": max(0, target_message_count),
            "max_lookback_hours": max(0, max_lookback_hours),
            "detail_mode": self._normalize_detail_mode(detail_mode),
            "selected_message_count": max(0, selected_message_count),
            "selected_transcript_chars": max(0, selected_transcript_chars),
            "estimated_input_tokens": max(0, estimated_input_tokens),
            "estimated_output_tokens": max(0, estimated_output_tokens),
            "estimated_cost_floor_usd": max(0.0, estimated_cost_floor_usd),
            "estimated_cost_ceiling_usd": max(0.0, estimated_cost_ceiling_usd),
            "snapshot_id": snapshot_id,
            "error_text": error_text,
            "started_at": started_at.isoformat() if started_at else None,
            "finished_at": finished_at.isoformat() if finished_at else None,
            "created_at": resolved_created_at.isoformat(),
        }
        self.client.table("analysis_jobs").insert(record).execute()
        job = self.get_analysis_job(job_id)
        if job is None:
            raise RuntimeError("Analysis job could not be created.")
        return job

    def get_analysis_job(self, job_id: str) -> AnalysisJobRecord | None:
        response = (
            self.client.table("analysis_jobs")
            .select(
                "id,user_id,intent,status,trigger_source,decision_id,sync_run_id,target_message_count,"
                "max_lookback_hours,detail_mode,selected_message_count,selected_transcript_chars,"
                "estimated_input_tokens,estimated_output_tokens,estimated_cost_floor_usd,"
                "estimated_cost_ceiling_usd,snapshot_id,error_text,started_at,finished_at,created_at"
            )
            .eq("id", job_id)
            .limit(1)
            .execute()
        )
        rows = response.data or []
        if not rows or not isinstance(rows[0], dict):
            return None
        return self._parse_analysis_job(rows[0], fallback_user_id=self.default_user_id)

    def update_analysis_job(
        self,
        *,
        job_id: str,
        status: str | None = None,
        decision_id: str | None = None,
        sync_run_id: str | None = None,
        target_message_count: int | None = None,
        max_lookback_hours: int | None = None,
        detail_mode: str | None = None,
        selected_message_count: int | None = None,
        selected_transcript_chars: int | None = None,
        estimated_input_tokens: int | None = None,
        estimated_output_tokens: int | None = None,
        estimated_cost_floor_usd: float | None = None,
        estimated_cost_ceiling_usd: float | None = None,
        snapshot_id: str | None = None,
        error_text: str | None = None,
        started_at: datetime | None = None,
        finished_at: datetime | None = None,
    ) -> AnalysisJobRecord | None:
        payload: dict[str, Any] = {}
        if status is not None:
            payload["status"] = status
        if decision_id is not None:
            payload["decision_id"] = decision_id
        if sync_run_id is not None:
            payload["sync_run_id"] = sync_run_id
        if target_message_count is not None:
            payload["target_message_count"] = max(0, target_message_count)
        if max_lookback_hours is not None:
            payload["max_lookback_hours"] = max(0, max_lookback_hours)
        if detail_mode is not None:
            payload["detail_mode"] = self._normalize_detail_mode(detail_mode)
        if selected_message_count is not None:
            payload["selected_message_count"] = max(0, selected_message_count)
        if selected_transcript_chars is not None:
            payload["selected_transcript_chars"] = max(0, selected_transcript_chars)
        if estimated_input_tokens is not None:
            payload["estimated_input_tokens"] = max(0, estimated_input_tokens)
        if estimated_output_tokens is not None:
            payload["estimated_output_tokens"] = max(0, estimated_output_tokens)
        if estimated_cost_floor_usd is not None:
            payload["estimated_cost_floor_usd"] = max(0.0, estimated_cost_floor_usd)
        if estimated_cost_ceiling_usd is not None:
            payload["estimated_cost_ceiling_usd"] = max(0.0, estimated_cost_ceiling_usd)
        if snapshot_id is not None:
            payload["snapshot_id"] = snapshot_id
        if error_text is not None:
            payload["error_text"] = error_text
        if started_at is not None:
            payload["started_at"] = started_at.isoformat()
        if finished_at is not None:
            payload["finished_at"] = finished_at.isoformat()
        if payload:
            self.client.table("analysis_jobs").update(payload).eq("id", job_id).execute()
        return self.get_analysis_job(job_id)

    def claim_next_queued_analysis_job(self, *, user_id: UUID) -> AnalysisJobRecord | None:
        response = (
            self.client.table("analysis_jobs")
            .select(
                "id,user_id,intent,status,trigger_source,decision_id,sync_run_id,target_message_count,"
                "max_lookback_hours,detail_mode,selected_message_count,selected_transcript_chars,"
                "estimated_input_tokens,estimated_output_tokens,estimated_cost_floor_usd,"
                "estimated_cost_ceiling_usd,snapshot_id,error_text,started_at,finished_at,created_at"
            )
            .eq("user_id", str(user_id))
            .eq("status", "queued")
            .order("created_at", desc=False)
            .limit(1)
            .execute()
        )
        rows = response.data or []
        if not rows or not isinstance(rows[0], dict):
            return None
        job_id = str(rows[0].get("id") or "")
        self.client.table("analysis_jobs").update(
            {
                "status": "running",
                "started_at": datetime.now(UTC).isoformat(),
            }
        ).eq("id", job_id).execute()
        return self.get_analysis_job(job_id)

    def list_analysis_jobs(self, *, user_id: UUID, limit: int = 12) -> list[AnalysisJobRecord]:
        response = (
            self.client.table("analysis_jobs")
            .select(
                "id,user_id,intent,status,trigger_source,decision_id,sync_run_id,target_message_count,"
                "max_lookback_hours,detail_mode,selected_message_count,selected_transcript_chars,"
                "estimated_input_tokens,estimated_output_tokens,estimated_cost_floor_usd,"
                "estimated_cost_ceiling_usd,snapshot_id,error_text,started_at,finished_at,created_at"
            )
            .eq("user_id", str(user_id))
            .order("created_at", desc=True)
            .limit(limit)
            .execute()
        )
        rows = response.data or []
        jobs: list[AnalysisJobRecord] = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            parsed = self._parse_analysis_job(row, fallback_user_id=user_id)
            if parsed is not None:
                jobs.append(parsed)
        return jobs

    def count_analysis_jobs_since(
        self,
        *,
        user_id: UUID,
        since: datetime,
        trigger_source: str | None = None,
    ) -> int:
        query = (
            self.client.table("analysis_jobs")
            .select("id,trigger_source")
            .eq("user_id", str(user_id))
            .gte("created_at", since.isoformat())
            .limit(500)
        )
        if trigger_source is not None:
            query = query.eq("trigger_source", trigger_source)
        response = query.execute()
        rows = response.data or []
        return sum(1 for row in rows if isinstance(row, dict))

    def save_analysis_job_messages(self, *, job_id: str, message_ids: Sequence[str]) -> None:
        cleaned = [message_id.strip() for message_id in message_ids if message_id and message_id.strip()]
        if not cleaned:
            return
        records = [
            {
                "job_id": job_id,
                "message_id": message_id,
                "created_at": datetime.now(UTC).isoformat(),
            }
            for message_id in dict.fromkeys(cleaned)
        ]
        self.client.table("analysis_job_messages").upsert(records, on_conflict="job_id,message_id").execute()

    def create_model_run(
        self,
        *,
        user_id: UUID,
        job_id: str | None,
        provider: str,
        model_name: str,
        run_type: str,
        success: bool,
        latency_ms: int | None,
        input_tokens: int | None,
        output_tokens: int | None,
        reasoning_tokens: int | None,
        estimated_cost_usd: float | None,
        error_text: str | None,
        created_at: datetime,
    ) -> ModelRunRecord:
        model_run_id = str(uuid4())
        record = {
            "id": model_run_id,
            "user_id": str(user_id),
            "job_id": job_id,
            "provider": provider,
            "model_name": model_name,
            "run_type": run_type,
            "success": bool(success),
            "latency_ms": latency_ms,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "reasoning_tokens": reasoning_tokens,
            "estimated_cost_usd": estimated_cost_usd,
            "error_text": error_text,
            "created_at": created_at.isoformat(),
        }
        self.client.table("model_runs").insert(record).execute()
        return ModelRunRecord(
            id=model_run_id,
            user_id=user_id,
            job_id=job_id,
            provider=provider,
            model_name=model_name,
            run_type=run_type,
            success=bool(success),
            latency_ms=latency_ms,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            reasoning_tokens=reasoning_tokens,
            estimated_cost_usd=estimated_cost_usd,
            error_text=error_text,
            created_at=created_at,
        )

    def list_model_runs(self, *, user_id: UUID, limit: int = 12) -> list[ModelRunRecord]:
        response = (
            self.client.table("model_runs")
            .select(
                "id,user_id,job_id,provider,model_name,run_type,success,latency_ms,input_tokens,"
                "output_tokens,reasoning_tokens,estimated_cost_usd,error_text,created_at"
            )
            .eq("user_id", str(user_id))
            .order("created_at", desc=True)
            .limit(limit)
            .execute()
        )
        rows = response.data or []
        runs: list[ModelRunRecord] = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            parsed = self._parse_model_run(row, fallback_user_id=user_id)
            if parsed is not None:
                runs.append(parsed)
        return runs

    def sum_model_run_cost_since(self, *, user_id: UUID, since: datetime) -> float:
        response = (
            self.client.table("model_runs")
            .select("estimated_cost_usd")
            .eq("user_id", str(user_id))
            .gte("created_at", since.isoformat())
            .limit(500)
            .execute()
        )
        rows = response.data or []
        total = 0.0
        for row in rows:
            if not isinstance(row, dict):
                continue
            total += self._parse_float(row.get("estimated_cost_usd")) or 0.0
        return round(total, 6)

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

    def _default_automation_settings_record(self, *, user_id: UUID, updated_at: datetime) -> dict[str, Any]:
        return {
            "user_id": str(user_id),
            "auto_sync_enabled": True,
            "auto_analyze_enabled": True,
            "auto_refine_enabled": False,
            "min_new_messages_threshold": 25,
            "stale_hours_threshold": 24,
            "pruned_messages_threshold": 1,
            "default_detail_mode": "balanced",
            "default_target_message_count": min(200, self.message_retention_max_rows),
            "default_lookback_hours": 72,
            "daily_budget_usd": 0.25,
            "max_auto_jobs_per_day": 4,
            "updated_at": updated_at.isoformat(),
        }

    def _get_latest_running_sync_run_row(self, user_id: UUID) -> dict[str, Any] | None:
        response = (
            self.client.table("wa_sync_runs")
            .select(
                "id,user_id,trigger,status,messages_seen_count,messages_saved_count,messages_ignored_count,"
                "messages_pruned_count,oldest_message_at,newest_message_at,error_text,started_at,finished_at,"
                "last_activity_at,baseline_ingested_count,baseline_pruned_count"
            )
            .eq("user_id", str(user_id))
            .eq("status", "running")
            .order("started_at", desc=True)
            .limit(1)
            .execute()
        )
        rows = response.data or []
        if not rows or not isinstance(rows[0], dict):
            return None
        return rows[0]

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

    def _parse_float(self, value: Any) -> float | None:
        if value is None:
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    def _parse_bool(self, value: Any) -> bool | None:
        if isinstance(value, bool):
            return value
        if value is None:
            return None
        text = str(value).strip().lower()
        if text in {"true", "t", "1", "yes", "y"}:
            return True
        if text in {"false", "f", "0", "no", "n"}:
            return False
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

    def _parse_automation_settings(self, value: Any, *, fallback_user_id: UUID) -> AutomationSettingsRecord | None:
        if not isinstance(value, dict):
            return None
        return AutomationSettingsRecord(
            user_id=self._parse_uuid(value.get("user_id")) or fallback_user_id,
            auto_sync_enabled=self._parse_bool(value.get("auto_sync_enabled")) if self._parse_bool(value.get("auto_sync_enabled")) is not None else True,
            auto_analyze_enabled=self._parse_bool(value.get("auto_analyze_enabled")) if self._parse_bool(value.get("auto_analyze_enabled")) is not None else True,
            auto_refine_enabled=self._parse_bool(value.get("auto_refine_enabled")) if self._parse_bool(value.get("auto_refine_enabled")) is not None else False,
            min_new_messages_threshold=self._parse_int(value.get("min_new_messages_threshold")) or 25,
            stale_hours_threshold=self._parse_int(value.get("stale_hours_threshold")) or 24,
            pruned_messages_threshold=self._parse_int(value.get("pruned_messages_threshold")) or 1,
            default_detail_mode=self._normalize_detail_mode(self._optional_text(value.get("default_detail_mode")) or "balanced"),
            default_target_message_count=self._parse_int(value.get("default_target_message_count")) or min(200, self.message_retention_max_rows),
            default_lookback_hours=self._parse_int(value.get("default_lookback_hours")) or 72,
            daily_budget_usd=self._parse_float(value.get("daily_budget_usd")) or 0.25,
            max_auto_jobs_per_day=self._parse_int(value.get("max_auto_jobs_per_day")) or 4,
            updated_at=self._parse_datetime(value.get("updated_at")) or datetime.now(UTC),
        )

    def _parse_whatsapp_sync_run(self, value: Any, *, fallback_user_id: UUID) -> WhatsAppSyncRunRecord | None:
        if not isinstance(value, dict):
            return None
        return WhatsAppSyncRunRecord(
            id=str(value.get("id") or ""),
            user_id=self._parse_uuid(value.get("user_id")) or fallback_user_id,
            trigger=str(value.get("trigger") or "manual"),
            status=str(value.get("status") or "unknown"),
            messages_seen_count=self._parse_int(value.get("messages_seen_count")) or 0,
            messages_saved_count=self._parse_int(value.get("messages_saved_count")) or 0,
            messages_ignored_count=self._parse_int(value.get("messages_ignored_count")) or 0,
            messages_pruned_count=self._parse_int(value.get("messages_pruned_count")) or 0,
            oldest_message_at=self._parse_datetime(value.get("oldest_message_at")),
            newest_message_at=self._parse_datetime(value.get("newest_message_at")),
            error_text=self._optional_text(value.get("error_text")),
            started_at=self._parse_datetime(value.get("started_at")) or datetime.now(UTC),
            finished_at=self._parse_datetime(value.get("finished_at")),
            last_activity_at=self._parse_datetime(value.get("last_activity_at")),
        )

    def _parse_automation_decision(self, value: Any, *, fallback_user_id: UUID) -> AutomationDecisionRecord | None:
        if not isinstance(value, dict):
            return None
        return AutomationDecisionRecord(
            id=str(value.get("id") or ""),
            user_id=self._parse_uuid(value.get("user_id")) or fallback_user_id,
            sync_run_id=self._optional_text(value.get("sync_run_id")),
            intent=str(value.get("intent") or "improve_memory"),
            action=str(value.get("action") or "skip"),
            reason_code=str(value.get("reason_code") or "unknown"),
            score=self._parse_int(value.get("score")) or 0,
            should_analyze=bool(self._parse_bool(value.get("should_analyze"))),
            available_message_count=self._parse_int(value.get("available_message_count")) or 0,
            selected_message_count=self._parse_int(value.get("selected_message_count")) or 0,
            new_message_count=self._parse_int(value.get("new_message_count")) or 0,
            replaced_message_count=self._parse_int(value.get("replaced_message_count")) or 0,
            estimated_total_tokens=self._parse_int(value.get("estimated_total_tokens")) or 0,
            estimated_cost_ceiling_usd=self._parse_float(value.get("estimated_cost_ceiling_usd")) or 0.0,
            explanation=str(value.get("explanation") or ""),
            created_at=self._parse_datetime(value.get("created_at")) or datetime.now(UTC),
        )

    def _parse_analysis_job(self, value: Any, *, fallback_user_id: UUID) -> AnalysisJobRecord | None:
        if not isinstance(value, dict):
            return None
        return AnalysisJobRecord(
            id=str(value.get("id") or ""),
            user_id=self._parse_uuid(value.get("user_id")) or fallback_user_id,
            intent=str(value.get("intent") or "improve_memory"),
            status=str(value.get("status") or "queued"),
            trigger_source=str(value.get("trigger_source") or "manual"),
            decision_id=self._optional_text(value.get("decision_id")),
            sync_run_id=self._optional_text(value.get("sync_run_id")),
            target_message_count=self._parse_int(value.get("target_message_count")) or 0,
            max_lookback_hours=self._parse_int(value.get("max_lookback_hours")) or 0,
            detail_mode=self._normalize_detail_mode(self._optional_text(value.get("detail_mode")) or "balanced"),
            selected_message_count=self._parse_int(value.get("selected_message_count")) or 0,
            selected_transcript_chars=self._parse_int(value.get("selected_transcript_chars")) or 0,
            estimated_input_tokens=self._parse_int(value.get("estimated_input_tokens")) or 0,
            estimated_output_tokens=self._parse_int(value.get("estimated_output_tokens")) or 0,
            estimated_cost_floor_usd=self._parse_float(value.get("estimated_cost_floor_usd")) or 0.0,
            estimated_cost_ceiling_usd=self._parse_float(value.get("estimated_cost_ceiling_usd")) or 0.0,
            snapshot_id=self._optional_text(value.get("snapshot_id")),
            error_text=self._optional_text(value.get("error_text")),
            started_at=self._parse_datetime(value.get("started_at")),
            finished_at=self._parse_datetime(value.get("finished_at")),
            created_at=self._parse_datetime(value.get("created_at")) or datetime.now(UTC),
        )

    def _parse_model_run(self, value: Any, *, fallback_user_id: UUID) -> ModelRunRecord | None:
        if not isinstance(value, dict):
            return None
        return ModelRunRecord(
            id=str(value.get("id") or ""),
            user_id=self._parse_uuid(value.get("user_id")) or fallback_user_id,
            job_id=self._optional_text(value.get("job_id")),
            provider=str(value.get("provider") or "unknown"),
            model_name=str(value.get("model_name") or ""),
            run_type=str(value.get("run_type") or ""),
            success=bool(self._parse_bool(value.get("success"))),
            latency_ms=self._parse_int(value.get("latency_ms")),
            input_tokens=self._parse_int(value.get("input_tokens")),
            output_tokens=self._parse_int(value.get("output_tokens")),
            reasoning_tokens=self._parse_int(value.get("reasoning_tokens")),
            estimated_cost_usd=self._parse_float(value.get("estimated_cost_usd")),
            error_text=self._optional_text(value.get("error_text")),
            created_at=self._parse_datetime(value.get("created_at")) or datetime.now(UTC),
        )

    def _normalize_detail_mode(self, value: str) -> str:
        normalized = value.strip().lower()
        if normalized in {"light", "balanced", "deep"}:
            return normalized
        return "balanced"

    def _earliest_datetime(self, first: datetime | None, second: datetime | None) -> datetime | None:
        if first is None:
            return second
        if second is None:
            return first
        return first if first <= second else second

    def _latest_datetime(self, first: datetime | None, second: datetime | None) -> datetime | None:
        if first is None:
            return second
        if second is None:
            return first
        return first if first >= second else second
