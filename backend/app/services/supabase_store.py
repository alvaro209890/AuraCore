from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
import logging
from typing import Any, Sequence
from uuid import UUID, uuid4

from postgrest.exceptions import APIError
from supabase import Client, create_client

_UNSET = object()
observer_ingest_logger = logging.getLogger("auracore.observer_ingest")
contact_resolution_logger = logging.getLogger("auracore.contact_resolution")


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
    contact_name_source: str = "unknown"
    source: str = "baileys"
    source_event: str | None = None


@dataclass(slots=True)
class IngestSaveResult:
    saved_count: int
    ignored_count: int
    trimmed_existing_count: int = 0


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
    structural_strengths: list[str]
    structural_routines: list[str]
    structural_preferences: list[str]
    structural_open_questions: list[str]


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
class PersonMemorySeed:
    person_key: str
    contact_name: str
    contact_phone: str | None
    chat_jid: str | None
    profile_summary: str
    relationship_summary: str
    salient_facts: list[str]
    open_loops: list[str]
    recent_topics: list[str]
    source_message_count: int
    window_start: datetime | None = None
    window_end: datetime | None = None


@dataclass(slots=True)
class PersonMemoryRecord:
    id: str
    user_id: UUID
    person_key: str
    contact_name: str
    contact_phone: str | None
    chat_jid: str | None
    profile_summary: str
    relationship_summary: str
    salient_facts: list[str]
    open_loops: list[str]
    recent_topics: list[str]
    source_snapshot_id: str | None
    source_message_count: int
    last_message_at: datetime | None
    last_analyzed_at: datetime | None
    updated_at: datetime


@dataclass(slots=True)
class PersonMemorySnapshotRecord:
    id: str
    user_id: UUID
    person_memory_id: str | None
    person_key: str
    contact_name: str
    contact_phone: str | None
    chat_jid: str | None
    source_snapshot_id: str | None
    profile_summary: str
    relationship_summary: str
    salient_facts: list[str]
    open_loops: list[str]
    recent_topics: list[str]
    source_message_count: int
    window_start: datetime | None
    window_end: datetime | None
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
    observer_history_cutoff_at: datetime | None
    last_message_at: datetime | None
    updated_at: datetime | None


@dataclass(slots=True)
class KnownContactRecord:
    id: str
    user_id: UUID
    contact_phone: str
    chat_jid: str | None
    contact_name: str
    name_source: str
    last_seen_at: datetime | None
    updated_at: datetime


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


@dataclass(slots=True)
class WhatsAppAgentSettingsRecord:
    user_id: UUID
    auto_reply_enabled: bool
    allowed_contact_phone: str | None
    updated_at: datetime


@dataclass(slots=True)
class WhatsAppAgentThreadRecord:
    id: str
    user_id: UUID
    contact_phone: str | None
    chat_jid: str | None
    contact_name: str
    status: str
    last_message_at: datetime | None
    last_inbound_at: datetime | None
    last_outbound_at: datetime | None
    last_error_at: datetime | None
    last_error_text: str | None
    created_at: datetime
    updated_at: datetime


@dataclass(slots=True)
class WhatsAppAgentThreadSessionRecord:
    id: str
    user_id: UUID
    thread_id: str
    contact_phone: str | None
    chat_jid: str | None
    started_at: datetime
    last_activity_at: datetime
    ended_at: datetime | None
    reset_reason: str | None
    created_at: datetime
    updated_at: datetime


@dataclass(slots=True)
class WhatsAppAgentContactMemoryRecord:
    id: str
    user_id: UUID
    thread_id: str | None
    contact_phone: str | None
    chat_jid: str | None
    contact_name: str
    profile_summary: str
    preferred_tone: str
    preferences: list[str]
    objectives: list[str]
    durable_facts: list[str]
    constraints: list[str]
    recurring_instructions: list[str]
    learned_message_count: int
    last_learned_at: datetime | None
    updated_at: datetime


@dataclass(slots=True)
class WhatsAppAgentMessageRecord:
    id: str
    user_id: UUID
    thread_id: str
    direction: str
    role: str
    session_id: str | None
    whatsapp_message_id: str | None
    source_inbound_message_id: str | None
    contact_phone: str | None
    chat_jid: str | None
    content: str
    message_timestamp: datetime
    processing_status: str
    learning_status: str
    send_status: str | None
    error_text: str | None
    response_latency_ms: int | None
    model_run_id: str | None
    learned_at: datetime | None
    metadata: dict[str, Any]
    created_at: datetime


@dataclass(slots=True)
class ImportantMessageSeed:
    source_message_id: str
    contact_name: str
    contact_phone: str | None
    direction: str
    message_text: str
    message_timestamp: datetime
    category: str
    importance_reason: str
    confidence: int


@dataclass(slots=True)
class ImportantMessageReviewSeed:
    source_message_id: str
    decision: str
    review_notes: str
    confidence: int


@dataclass(slots=True)
class ImportantMessageRecord:
    id: str
    user_id: UUID
    source_message_id: str
    contact_name: str
    contact_phone: str | None
    direction: str
    message_text: str
    message_timestamp: datetime
    category: str
    importance_reason: str
    confidence: int
    status: str
    review_notes: str | None
    saved_at: datetime
    last_reviewed_at: datetime | None
    discarded_at: datetime | None


class SupabaseStore:
    def __init__(
        self,
        supabase_url: str,
        supabase_key: str,
        default_user_id: UUID,
        *,
        message_retention_max_rows: int = 5000,
        first_analysis_queue_limit: int | None = None,
    ) -> None:
        self.client: Client = create_client(supabase_url, supabase_key)
        self.default_user_id = default_user_id
        self.message_retention_max_rows = max(20, message_retention_max_rows)
        resolved_first_analysis_limit = (
            first_analysis_queue_limit
            if first_analysis_queue_limit is not None
            else self.message_retention_max_rows
        )
        self.first_analysis_queue_limit = max(
            20,
            min(resolved_first_analysis_limit, self.message_retention_max_rows),
        )
        self._compat_sync_runs: dict[str, WhatsAppSyncRunRecord] = {}
        self._compat_decisions: dict[str, AutomationDecisionRecord] = {}
        self._compat_analysis_jobs: dict[str, AnalysisJobRecord] = {}
        self._compat_model_runs: dict[str, ModelRunRecord] = {}

    def save_ingested_messages(self, messages: Sequence[IngestedMessageRecord]) -> IngestSaveResult:
        filtered_messages = [message for message in messages if self.is_normal_contact_phone(message.contact_phone)]
        if not filtered_messages:
            return IngestSaveResult(saved_count=0, ignored_count=0)

        for message in filtered_messages:
            self.upsert_known_contact(
                user_id=self.default_user_id,
                contact_phone=message.contact_phone,
                chat_jid=message.chat_jid,
                contact_name=message.contact_name,
                name_source=message.contact_name_source,
                seen_at=message.timestamp,
            )

        self.reconcile_observer_backlog(user_id=self.default_user_id)
        known_contact_names = self._load_known_contact_names(
            [message.contact_phone for message in filtered_messages if message.contact_phone]
        )
        existing_ids = self._fetch_existing_message_ids([message.message_id for message in filtered_messages])
        processed_ids = self._fetch_processed_message_ids([message.message_id for message in filtered_messages])
        pending_messages = [
            message for message in filtered_messages
            if message.message_id not in existing_ids and message.message_id not in processed_ids
        ]
        deduped_ignored_count = max(0, len(filtered_messages) - len(pending_messages))
        if not pending_messages:
            return IngestSaveResult(saved_count=0, ignored_count=deduped_ignored_count)

        cutoff_at = self.get_observer_history_cutoff(user_id=self.default_user_id)
        stale_history_ids: list[str] = []
        if cutoff_at is not None:
            fresh_pending_messages: list[IngestedMessageRecord] = []
            for message in pending_messages:
                if message.timestamp < cutoff_at:
                    stale_history_ids.append(message.message_id)
                else:
                    fresh_pending_messages.append(message)
            pending_messages = fresh_pending_messages

        (
            pending_messages,
            overflow_message_ids,
            trimmed_existing_ids,
        ) = self._prepare_ingest_batch(pending_messages)

        if stale_history_ids or overflow_message_ids or trimmed_existing_ids:
            self.mark_messages_processed(
                user_id=self.default_user_id,
                message_ids=[*stale_history_ids, *overflow_message_ids, *trimmed_existing_ids],
                processed_at=datetime.now(UTC),
            )
        if trimmed_existing_ids:
            self.delete_messages_by_ids(message_ids=trimmed_existing_ids)

        new_message_count = len(pending_messages)
        if not pending_messages:
            return IngestSaveResult(
                saved_count=0,
                ignored_count=deduped_ignored_count + len(stale_history_ids) + len(overflow_message_ids),
                trimmed_existing_count=len(trimmed_existing_ids),
            )

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
            for message in pending_messages
        ]

        try:
            self.client.table("mensagens").upsert(records, on_conflict="id").execute()
        except Exception as exc:
            if not (
                self._is_missing_column_error(exc, column_name="chat_jid", table_name="mensagens")
                or self._is_missing_column_error(exc, column_name="ingested_at", table_name="mensagens")
            ):
                raise
            legacy_records = []
            for record in records:
                legacy_record = dict(record)
                legacy_record.pop("chat_jid", None)
                legacy_record.pop("ingested_at", None)
                legacy_records.append(legacy_record)
            self.client.table("mensagens").upsert(legacy_records, on_conflict="id").execute()
        if new_message_count > 0:
            self.bump_message_retention_state(
                user_id=self.default_user_id,
                ingested_increment=new_message_count,
                last_message_at=max(message.timestamp for message in pending_messages),
            )
        self.prune_non_direct_messages(self.default_user_id)
        pruned_count = self.prune_old_messages(self.default_user_id)
        if pruned_count > 0:
            self.bump_message_retention_state(
                user_id=self.default_user_id,
                pruned_increment=pruned_count,
            )
        observer_ingest_logger.info(
            "observer_ingest_saved saved=%s ignored=%s stale_history=%s overflow=%s trimmed_existing=%s",
            len(records),
            deduped_ignored_count + len(stale_history_ids) + len(overflow_message_ids),
            len(stale_history_ids),
            len(overflow_message_ids),
            len(trimmed_existing_ids),
        )
        return IngestSaveResult(
            saved_count=len(records),
            ignored_count=deduped_ignored_count + len(stale_history_ids) + len(overflow_message_ids),
            trimmed_existing_count=len(trimmed_existing_ids),
        )

    def _prepare_ingest_batch(
        self,
        pending_messages: Sequence[IngestedMessageRecord],
    ) -> tuple[list[IngestedMessageRecord], list[str], list[str]]:
        if self._has_initial_memory_analysis():
            return list(pending_messages), [], []

        existing_pending = self.list_pending_messages(
            user_id=self.default_user_id,
            limit=self.message_retention_max_rows,
            newest_first=True,
        )
        combined_by_id: dict[str, StoredMessageRecord | IngestedMessageRecord] = {
            message.message_id: message
            for message in existing_pending
        }
        for message in pending_messages:
            combined_by_id[message.message_id] = message

        ordered_messages = sorted(
            combined_by_id.values(),
            key=lambda message: (message.timestamp, message.message_id),
            reverse=True,
        )
        keep_ids = {
            message.message_id
            for message in ordered_messages[: self.first_analysis_queue_limit]
        }
        kept_pending_messages = [
            message
            for message in pending_messages
            if message.message_id in keep_ids
        ]
        overflow_message_ids = [
            message.message_id
            for message in pending_messages
            if message.message_id not in keep_ids
        ]
        trimmed_existing_ids = [
            message.message_id
            for message in existing_pending
            if message.message_id not in keep_ids
        ]
        return kept_pending_messages, overflow_message_ids, trimmed_existing_ids

    def _has_initial_memory_analysis(self) -> bool:
        persona = self.get_persona(self.default_user_id)
        return bool(persona and (persona.last_analyzed_at or persona.last_snapshot_id))

    def mark_messages_processed(self, *, user_id: UUID, message_ids: Sequence[str], processed_at: datetime | None = None) -> int:
        cleaned_ids = [message_id.strip() for message_id in message_ids if message_id and message_id.strip()]
        if not cleaned_ids:
            return 0
        resolved_processed_at = processed_at or datetime.now(UTC)
        records = [
            {
                "message_id": message_id,
                "user_id": str(user_id),
                "processed_at": resolved_processed_at.isoformat(),
            }
            for message_id in dict.fromkeys(cleaned_ids)
        ]
        try:
            self.client.table("processed_message_ids").upsert(records, on_conflict="message_id").execute()
        except Exception as exc:
            if not self._is_missing_table_error(exc, "processed_message_ids"):
                raise
            return 0
        return len(records)

    def delete_messages_by_ids(self, *, message_ids: Sequence[str]) -> int:
        cleaned_ids = [message_id.strip() for message_id in message_ids if message_id and message_id.strip()]
        if not cleaned_ids:
            return 0
        deleted_total = 0
        chunk_size = 500
        for start in range(0, len(cleaned_ids), chunk_size):
            chunk = cleaned_ids[start:start + chunk_size]
            self.client.table("mensagens").delete().in_("id", chunk).execute()
            deleted_total += len(chunk)
        return deleted_total

    def list_messages_in_window(
        self,
        *,
        user_id: UUID,
        window_start: datetime,
        window_end: datetime,
    ) -> list[StoredMessageRecord]:
        try:
            response = (
                self.client.table("mensagens")
                .select("id,user_id,contact_name,chat_jid,contact_phone,direction,message_text,timestamp,source")
                .eq("user_id", str(user_id))
                .gte("timestamp", window_start.isoformat())
                .lte("timestamp", window_end.isoformat())
                .order("timestamp", desc=False)
                .execute()
            )
        except Exception as exc:
            if not self._is_missing_column_error(exc, column_name="chat_jid", table_name="mensagens"):
                raise
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
        known_contact_names = self._load_known_contact_names(
            [self._optional_text(row.get("contact_phone")) for row in rows if isinstance(row, dict)]
        )
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
                    contact_name=self._resolve_contact_name(
                        incoming_name=self._optional_text(row.get("contact_name")),
                        contact_phone=contact_phone,
                        known_name=known_contact_names.get(contact_phone or ""),
                    ),
                    chat_jid=self._optional_text(row.get("chat_jid")),
                    contact_phone=contact_phone,
                    message_text=message_text,
                    timestamp=self._parse_datetime(row.get("timestamp")) or datetime.now(UTC),
                    source=str(row.get("source") or "unknown"),
                )
            )
        return messages

    def list_pending_messages(
        self,
        *,
        user_id: UUID,
        limit: int,
        newest_first: bool = False,
    ) -> list[StoredMessageRecord]:
        self.reconcile_observer_backlog(user_id=user_id)
        resolved_limit = max(1, min(limit, self.message_retention_max_rows))
        cutoff_at = self.get_observer_history_cutoff(user_id=user_id)
        messages: list[StoredMessageRecord] = []
        seen_ids: set[str] = set()
        chunk_size = min(200, self.message_retention_max_rows)
        offset = 0

        while len(messages) < resolved_limit and offset < self.message_retention_max_rows:
            range_end = min(offset + chunk_size - 1, self.message_retention_max_rows - 1)
            try:
                response = (
                    self.client.table("mensagens")
                    .select("id,user_id,contact_name,chat_jid,contact_phone,direction,message_text,timestamp,source")
                    .eq("user_id", str(user_id))
                    .order("timestamp", desc=newest_first)
                    .range(offset, range_end)
                    .execute()
                )
            except Exception as exc:
                if not self._is_missing_column_error(exc, column_name="chat_jid", table_name="mensagens"):
                    raise
                response = (
                    self.client.table("mensagens")
                    .select("id,user_id,contact_name,contact_phone,direction,message_text,timestamp,source")
                    .eq("user_id", str(user_id))
                    .order("timestamp", desc=newest_first)
                    .range(offset, range_end)
                    .execute()
                )

            rows = [row for row in (response.data or []) if isinstance(row, dict)]
            if not rows:
                break
            known_contact_names = self._load_known_contact_names(
                [self._optional_text(row.get("contact_phone")) for row in rows]
            )

            processed_ids = self._fetch_processed_message_ids(
                [str(row.get("id") or "").strip() for row in rows if str(row.get("id") or "").strip()]
            )

            for row in rows:
                message_id = str(row.get("id") or "").strip()
                if not message_id or message_id in seen_ids or message_id in processed_ids:
                    continue
                message_text = str(row.get("message_text") or "").strip()
                contact_phone = self._optional_text(row.get("contact_phone"))
                timestamp = self._parse_datetime(row.get("timestamp")) or datetime.now(UTC)
                if not message_text or not self.is_normal_contact_phone(contact_phone):
                    continue
                if cutoff_at is not None and timestamp < cutoff_at:
                    continue
                seen_ids.add(message_id)
                messages.append(
                    StoredMessageRecord(
                        message_id=message_id,
                        user_id=self._parse_uuid(row.get("user_id")) or user_id,
                        direction=str(row.get("direction") or "inbound"),
                        contact_name=self._resolve_contact_name(
                            incoming_name=self._optional_text(row.get("contact_name")),
                            contact_phone=contact_phone,
                            known_name=known_contact_names.get(contact_phone or ""),
                        ),
                        chat_jid=self._optional_text(row.get("chat_jid")),
                        contact_phone=contact_phone,
                        message_text=message_text,
                        timestamp=timestamp,
                        source=str(row.get("source") or "unknown"),
                    )
                )
                if len(messages) >= resolved_limit:
                    break

            if len(rows) < chunk_size:
                break
            offset += chunk_size

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
        try:
            response = (
                self.client.table("persona")
                .select(
                    "user_id,life_summary,last_analyzed_at,last_snapshot_id,"
                    "last_analyzed_ingested_count,last_analyzed_pruned_count,"
                    "structural_strengths,structural_routines,structural_preferences,structural_open_questions"
                )
                .eq("user_id", str(user_id))
                .limit(1)
                .execute()
            )
        except Exception as exc:
            if not (
                self._is_missing_column_error(exc, column_name="last_analyzed_ingested_count", table_name="persona")
                or self._is_missing_column_error(exc, column_name="last_analyzed_pruned_count", table_name="persona")
                or self._is_missing_column_error(exc, column_name="structural_strengths", table_name="persona")
                or self._is_missing_column_error(exc, column_name="structural_routines", table_name="persona")
                or self._is_missing_column_error(exc, column_name="structural_preferences", table_name="persona")
                or self._is_missing_column_error(exc, column_name="structural_open_questions", table_name="persona")
            ):
                raise
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
            last_analyzed_ingested_count=self._parse_int(row.get("last_analyzed_ingested_count")),
            last_analyzed_pruned_count=self._parse_int(row.get("last_analyzed_pruned_count")),
            structural_strengths=self._parse_string_list(row.get("structural_strengths")),
            structural_routines=self._parse_string_list(row.get("structural_routines")),
            structural_preferences=self._parse_string_list(row.get("structural_preferences")),
            structural_open_questions=self._parse_string_list(row.get("structural_open_questions")),
        )

    def persist_memory_analysis(
        self,
        *,
        snapshot: MemorySnapshotRecord,
        updated_life_summary: str,
        analyzed_at: datetime,
        structural_strengths: Sequence[str] = (),
        structural_routines: Sequence[str] = (),
        structural_preferences: Sequence[str] = (),
        structural_open_questions: Sequence[str] = (),
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
                "structural_strengths": self._normalize_string_list(structural_strengths, limit=8),
                "structural_routines": self._normalize_string_list(structural_routines, limit=8),
                "structural_preferences": self._normalize_string_list(structural_preferences, limit=8),
                "structural_open_questions": self._normalize_string_list(structural_open_questions, limit=6),
                "updated_at": analyzed_at.isoformat(),
            }
            try:
                self.client.table("persona").upsert(persona_record, on_conflict="user_id").execute()
            except Exception as exc:
                if not (
                    self._is_missing_column_error(exc, column_name="last_analyzed_ingested_count", table_name="persona")
                    or self._is_missing_column_error(exc, column_name="last_analyzed_pruned_count", table_name="persona")
                    or self._is_missing_column_error(exc, column_name="structural_strengths", table_name="persona")
                    or self._is_missing_column_error(exc, column_name="structural_routines", table_name="persona")
                    or self._is_missing_column_error(exc, column_name="structural_preferences", table_name="persona")
                    or self._is_missing_column_error(exc, column_name="structural_open_questions", table_name="persona")
                ):
                    raise
                legacy_persona_record = dict(persona_record)
                legacy_persona_record.pop("last_analyzed_ingested_count", None)
                legacy_persona_record.pop("last_analyzed_pruned_count", None)
                legacy_persona_record.pop("structural_strengths", None)
                legacy_persona_record.pop("structural_routines", None)
                legacy_persona_record.pop("structural_preferences", None)
                legacy_persona_record.pop("structural_open_questions", None)
                self.client.table("persona").upsert(legacy_persona_record, on_conflict="user_id").execute()
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
        structural_strengths: Sequence[str] = (),
        structural_routines: Sequence[str] = (),
        structural_preferences: Sequence[str] = (),
        structural_open_questions: Sequence[str] = (),
    ) -> PersonaRecord:
        current = self.get_persona(user_id)
        persona_record = {
            "user_id": str(user_id),
            "life_summary": updated_life_summary,
            "last_analyzed_at": analyzed_at.isoformat(),
            "last_snapshot_id": current.last_snapshot_id if current else None,
            "last_analyzed_ingested_count": current.last_analyzed_ingested_count if current else None,
            "last_analyzed_pruned_count": current.last_analyzed_pruned_count if current else None,
            "structural_strengths": self._normalize_string_list(structural_strengths or (current.structural_strengths if current else []), limit=8),
            "structural_routines": self._normalize_string_list(structural_routines or (current.structural_routines if current else []), limit=8),
            "structural_preferences": self._normalize_string_list(structural_preferences or (current.structural_preferences if current else []), limit=8),
            "structural_open_questions": self._normalize_string_list(structural_open_questions or (current.structural_open_questions if current else []), limit=6),
            "updated_at": analyzed_at.isoformat(),
        }
        try:
            self.client.table("persona").upsert(persona_record, on_conflict="user_id").execute()
        except Exception as exc:
            if not (
                self._is_missing_column_error(exc, column_name="last_analyzed_ingested_count", table_name="persona")
                or self._is_missing_column_error(exc, column_name="last_analyzed_pruned_count", table_name="persona")
                or self._is_missing_column_error(exc, column_name="structural_strengths", table_name="persona")
                or self._is_missing_column_error(exc, column_name="structural_routines", table_name="persona")
                or self._is_missing_column_error(exc, column_name="structural_preferences", table_name="persona")
                or self._is_missing_column_error(exc, column_name="structural_open_questions", table_name="persona")
            ):
                raise
            legacy_persona_record = dict(persona_record)
            legacy_persona_record.pop("last_analyzed_ingested_count", None)
            legacy_persona_record.pop("last_analyzed_pruned_count", None)
            legacy_persona_record.pop("structural_strengths", None)
            legacy_persona_record.pop("structural_routines", None)
            legacy_persona_record.pop("structural_preferences", None)
            legacy_persona_record.pop("structural_open_questions", None)
            self.client.table("persona").upsert(legacy_persona_record, on_conflict="user_id").execute()

        persona = self.get_persona(user_id)
        if persona is None:
            raise RuntimeError("Persona summary was updated but could not be fetched afterwards.")
        return persona

    def update_persona_structural_profile(
        self,
        *,
        user_id: UUID,
        structural_strengths: Sequence[str] = (),
        structural_routines: Sequence[str] = (),
        structural_preferences: Sequence[str] = (),
        structural_open_questions: Sequence[str] = (),
        updated_at: datetime | None = None,
    ) -> PersonaRecord:
        current = self.get_persona(user_id)
        resolved_updated_at = updated_at or datetime.now(UTC)
        persona_record = {
            "user_id": str(user_id),
            "life_summary": current.life_summary if current else "",
            "last_analyzed_at": current.last_analyzed_at.isoformat() if current and current.last_analyzed_at else None,
            "last_snapshot_id": str(current.last_snapshot_id) if current and current.last_snapshot_id else None,
            "last_analyzed_ingested_count": current.last_analyzed_ingested_count if current else None,
            "last_analyzed_pruned_count": current.last_analyzed_pruned_count if current else None,
            "structural_strengths": self._normalize_string_list(structural_strengths or (current.structural_strengths if current else []), limit=8),
            "structural_routines": self._normalize_string_list(structural_routines or (current.structural_routines if current else []), limit=8),
            "structural_preferences": self._normalize_string_list(structural_preferences or (current.structural_preferences if current else []), limit=8),
            "structural_open_questions": self._normalize_string_list(structural_open_questions or (current.structural_open_questions if current else []), limit=6),
            "updated_at": resolved_updated_at.isoformat(),
        }
        try:
            self.client.table("persona").upsert(persona_record, on_conflict="user_id").execute()
        except Exception as exc:
            if not (
                self._is_missing_column_error(exc, column_name="last_analyzed_ingested_count", table_name="persona")
                or self._is_missing_column_error(exc, column_name="last_analyzed_pruned_count", table_name="persona")
                or self._is_missing_column_error(exc, column_name="structural_strengths", table_name="persona")
                or self._is_missing_column_error(exc, column_name="structural_routines", table_name="persona")
                or self._is_missing_column_error(exc, column_name="structural_preferences", table_name="persona")
                or self._is_missing_column_error(exc, column_name="structural_open_questions", table_name="persona")
            ):
                raise
            legacy_persona_record = dict(persona_record)
            legacy_persona_record.pop("last_analyzed_ingested_count", None)
            legacy_persona_record.pop("last_analyzed_pruned_count", None)
            legacy_persona_record.pop("structural_strengths", None)
            legacy_persona_record.pop("structural_routines", None)
            legacy_persona_record.pop("structural_preferences", None)
            legacy_persona_record.pop("structural_open_questions", None)
            self.client.table("persona").upsert(legacy_persona_record, on_conflict="user_id").execute()

        persona = self.get_persona(user_id)
        if persona is None:
            raise RuntimeError("Persona structural profile was updated but could not be fetched afterwards.")
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

    def list_person_memories(self, user_id: UUID, *, limit: int = 80) -> list[PersonMemoryRecord]:
        try:
            response = (
                self.client.table("person_memories")
                .select(
                    "id,user_id,person_key,contact_name,contact_phone,chat_jid,profile_summary,"
                    "relationship_summary,salient_facts,open_loops,recent_topics,source_snapshot_id,"
                    "source_message_count,last_message_at,last_analyzed_at,updated_at"
                )
                .eq("user_id", str(user_id))
                .order("last_message_at", desc=True)
                .limit(limit)
                .execute()
            )
        except Exception as exc:
            if not self._is_missing_table_error(exc, "person_memories"):
                raise
            return []

        rows = response.data or []
        records: list[PersonMemoryRecord] = []
        for row in rows:
            parsed = self._parse_person_memory(row, fallback_user_id=user_id)
            if parsed is not None:
                records.append(parsed)
        return records

    def list_person_memories_by_keys(
        self,
        *,
        user_id: UUID,
        person_keys: Sequence[str],
    ) -> list[PersonMemoryRecord]:
        cleaned_keys = [key.strip() for key in person_keys if key and key.strip()]
        if not cleaned_keys:
            return []
        try:
            response = (
                self.client.table("person_memories")
                .select(
                    "id,user_id,person_key,contact_name,contact_phone,chat_jid,profile_summary,"
                    "relationship_summary,salient_facts,open_loops,recent_topics,source_snapshot_id,"
                    "source_message_count,last_message_at,last_analyzed_at,updated_at"
                )
                .eq("user_id", str(user_id))
                .in_("person_key", cleaned_keys)
                .execute()
            )
        except Exception as exc:
            if not self._is_missing_table_error(exc, "person_memories"):
                raise
            return []

        rows = response.data or []
        records: list[PersonMemoryRecord] = []
        for row in rows:
            parsed = self._parse_person_memory(row, fallback_user_id=user_id)
            if parsed is not None:
                records.append(parsed)
        return records

    def search_person_memories(self, user_id: UUID, queries: list[str], *, limit: int = 3) -> list[PersonMemoryRecord]:
        if not queries:
            return []
        try:
            query = (
                self.client.table("person_memories")
                .select(
                    "id,user_id,person_key,contact_name,contact_phone,chat_jid,profile_summary,"
                    "relationship_summary,salient_facts,open_loops,recent_topics,source_snapshot_id,"
                    "source_message_count,last_message_at,last_analyzed_at,updated_at"
                )
                .eq("user_id", str(user_id))
            )
            or_clauses = []
            for q in queries:
                if q.strip():
                    term = f"%{q.strip()}%"
                    or_clauses.append(f"contact_name.ilike.{term}")
                    or_clauses.append(f"profile_summary.ilike.{term}")
                    or_clauses.append(f"relationship_summary.ilike.{term}")
            if or_clauses:
                query = query.or_(",".join(or_clauses))
            response = query.order("last_message_at", desc=True).limit(limit).execute()
        except Exception as exc:
            if not self._is_missing_table_error(exc, "person_memories"):
                raise
            return []

        rows = response.data or []
        records: list[PersonMemoryRecord] = []
        for row in rows:
            parsed = self._parse_person_memory(row, fallback_user_id=user_id)
            if parsed is not None:
                records.append(parsed)
        return records

    def upsert_person_memories(
        self,
        *,
        user_id: UUID,
        source_snapshot_id: str | None,
        people: Sequence[PersonMemorySeed],
        observed_at: datetime,
    ) -> list[PersonMemoryRecord]:
        normalized_people: list[PersonMemorySeed] = []
        seen_keys: set[str] = set()
        for person in people:
            person_key = person.person_key.strip()
            profile_summary = person.profile_summary.strip()
            relationship_summary = person.relationship_summary.strip()
            if not person_key or not profile_summary:
                continue
            if person_key in seen_keys:
                continue
            seen_keys.add(person_key)
            normalized_people.append(
                PersonMemorySeed(
                    person_key=person_key,
                    contact_name=person.contact_name.strip() or person.contact_phone or "Contato",
                    contact_phone=self._optional_text(person.contact_phone),
                    chat_jid=self._optional_text(person.chat_jid),
                    profile_summary=profile_summary,
                    relationship_summary=relationship_summary,
                    salient_facts=self._clean_and_unique_string_list(person.salient_facts),
                    open_loops=self._clean_and_unique_string_list(person.open_loops),
                    recent_topics=self._clean_and_unique_string_list(person.recent_topics),
                    source_message_count=max(0, int(person.source_message_count)),
                    window_start=person.window_start,
                    window_end=person.window_end,
                )
            )

        if not normalized_people:
            return []

        existing_by_key = {
            record.person_key: record
            for record in self.list_person_memories_by_keys(
                user_id=user_id,
                person_keys=[person.person_key for person in normalized_people],
            )
        }

        records: list[dict[str, Any]] = []
        snapshot_records: list[dict[str, Any]] = []
        for person in normalized_people:
            existing = existing_by_key.get(person.person_key)
            person_memory_id = existing.id if existing is not None else str(uuid4())
            merged_contact_name = self._resolve_contact_name(
                incoming_name=person.contact_name,
                contact_phone=person.contact_phone,
                known_name=existing.contact_name if existing is not None else None,
            )
            merged_profile_summary = person.profile_summary or (existing.profile_summary if existing is not None else "")
            merged_relationship_summary = (
                person.relationship_summary or (existing.relationship_summary if existing is not None else "")
            )
            merged_salient_facts = self._merge_unique_string_lists(
                existing.salient_facts if existing is not None else [],
                person.salient_facts,
            )
            merged_open_loops = self._merge_unique_string_lists(
                existing.open_loops if existing is not None else [],
                person.open_loops,
            )
            merged_recent_topics = self._merge_unique_string_lists(
                existing.recent_topics if existing is not None else [],
                person.recent_topics,
            )
            merged_source_message_count = (
                (existing.source_message_count if existing is not None else 0) + max(0, person.source_message_count)
            )
            merged_last_message_at = self._latest_datetime(
                existing.last_message_at if existing is not None else None,
                person.window_end,
            )

            records.append(
                {
                    "id": person_memory_id,
                    "user_id": str(user_id),
                    "person_key": person.person_key,
                    "contact_name": merged_contact_name,
                    "contact_phone": person.contact_phone or (existing.contact_phone if existing is not None else None),
                    "chat_jid": person.chat_jid or (existing.chat_jid if existing is not None else None),
                    "profile_summary": merged_profile_summary,
                    "relationship_summary": merged_relationship_summary,
                    "salient_facts": merged_salient_facts,
                    "open_loops": merged_open_loops,
                    "recent_topics": merged_recent_topics,
                    "source_snapshot_id": source_snapshot_id,
                    "source_message_count": merged_source_message_count,
                    "last_message_at": merged_last_message_at.isoformat() if merged_last_message_at else None,
                    "last_analyzed_at": observed_at.isoformat(),
                    "updated_at": observed_at.isoformat(),
                }
            )
            snapshot_records.append(
                {
                    "id": str(uuid4()),
                    "user_id": str(user_id),
                    "person_memory_id": person_memory_id,
                    "person_key": person.person_key,
                    "contact_name": merged_contact_name,
                    "contact_phone": person.contact_phone or (existing.contact_phone if existing is not None else None),
                    "chat_jid": person.chat_jid or (existing.chat_jid if existing is not None else None),
                    "source_snapshot_id": source_snapshot_id,
                    "profile_summary": merged_profile_summary,
                    "relationship_summary": merged_relationship_summary,
                    "salient_facts": merged_salient_facts,
                    "open_loops": merged_open_loops,
                    "recent_topics": merged_recent_topics,
                    "source_message_count": max(0, person.source_message_count),
                    "window_start": person.window_start.isoformat() if person.window_start else None,
                    "window_end": person.window_end.isoformat() if person.window_end else None,
                    "created_at": observed_at.isoformat(),
                }
            )

        self.client.table("person_memories").upsert(records, on_conflict="user_id,person_key").execute()
        self.client.table("person_memory_snapshots").insert(snapshot_records).execute()
        return self.list_person_memories_by_keys(
            user_id=user_id,
            person_keys=[person.person_key for person in normalized_people],
        )

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

        try:
            self.client.table("project_memories").upsert(records, on_conflict="user_id,project_key").execute()
        except Exception as exc:
            if not (
                self._is_missing_column_error(exc, column_name="what_is_being_built", table_name="project_memories")
                or self._is_missing_column_error(exc, column_name="built_for", table_name="project_memories")
            ):
                raise
            legacy_records = []
            for record in records:
                legacy_record = dict(record)
                legacy_record.pop("what_is_being_built", None)
                legacy_record.pop("built_for", None)
                legacy_records.append(legacy_record)
            self.client.table("project_memories").upsert(legacy_records, on_conflict="user_id,project_key").execute()
        return self.list_project_memories(user_id, limit=max(8, len(records)))

    def list_project_memories(self, user_id: UUID, *, limit: int = 8) -> list[ProjectMemoryRecord]:
        try:
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
        except Exception as exc:
            if not (
                self._is_missing_column_error(exc, column_name="what_is_being_built", table_name="project_memories")
                or self._is_missing_column_error(exc, column_name="built_for", table_name="project_memories")
            ):
                raise
            response = (
                self.client.table("project_memories")
                .select(
                    "id,user_id,project_key,project_name,summary,status,next_steps,evidence,"
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

    def upsert_important_messages(
        self,
        *,
        user_id: UUID,
        messages: Sequence[ImportantMessageSeed],
        saved_at: datetime,
    ) -> int:
        records: list[dict[str, Any]] = []
        seen_source_ids: set[str] = set()

        for message in messages:
            source_message_id = message.source_message_id.strip()
            message_text = message.message_text.strip()
            importance_reason = message.importance_reason.strip()
            category = self._normalize_importance_category(message.category)
            if not source_message_id or source_message_id in seen_source_ids:
                continue
            if not message_text or not importance_reason:
                continue
            seen_source_ids.add(source_message_id)
            records.append(
                {
                    "user_id": str(user_id),
                    "source_message_id": source_message_id,
                    "contact_name": message.contact_name.strip() or message.contact_phone or "Contato",
                    "contact_phone": self._optional_text(message.contact_phone),
                    "direction": message.direction.strip() or "inbound",
                    "message_text": message_text,
                    "message_timestamp": message.message_timestamp.isoformat(),
                    "category": category,
                    "importance_reason": importance_reason,
                    "confidence": max(0, min(100, int(message.confidence))),
                    "status": "active",
                    "review_notes": None,
                    "saved_at": saved_at.isoformat(),
                    "last_reviewed_at": None,
                    "discarded_at": None,
                }
            )

        if not records:
            return 0

        try:
            self.client.table("important_messages").upsert(records, on_conflict="user_id,source_message_id").execute()
        except Exception as exc:
            if not self._is_missing_table_error(exc, "important_messages"):
                raise
            return 0
        return len(records)

    def list_important_messages(
        self,
        user_id: UUID,
        *,
        limit: int = 80,
        include_discarded: bool = False,
    ) -> list[ImportantMessageRecord]:
        try:
            query = (
                self.client.table("important_messages")
                .select(
                    "id,user_id,source_message_id,contact_name,contact_phone,direction,message_text,"
                    "message_timestamp,category,importance_reason,confidence,status,review_notes,"
                    "saved_at,last_reviewed_at,discarded_at"
                )
                .eq("user_id", str(user_id))
            )
            if not include_discarded:
                query = query.eq("status", "active")
            response = query.order("message_timestamp", desc=True).limit(limit).execute()
        except Exception as exc:
            if not self._is_missing_table_error(exc, "important_messages"):
                raise
            return []

        rows = response.data or []
        messages: list[ImportantMessageRecord] = []
        for row in rows:
            parsed = self._parse_important_message(row, fallback_user_id=user_id)
            if parsed is not None:
                messages.append(parsed)
        return messages

    def search_important_messages(self, user_id: UUID, queries: list[str], *, limit: int = 5) -> list[ImportantMessageRecord]:
        if not queries:
            return []
        try:
            query = (
                self.client.table("important_messages")
                .select(
                    "id,user_id,source_message_id,contact_name,contact_phone,direction,message_text,"
                    "message_timestamp,category,importance_reason,confidence,status,review_notes,"
                    "saved_at,last_reviewed_at,discarded_at"
                )
                .eq("user_id", str(user_id))
                .eq("status", "active")
            )
            or_clauses = []
            for q in queries:
                if q.strip():
                    term = f"%{q.strip()}%"
                    or_clauses.append(f"message_text.ilike.{term}")
                    or_clauses.append(f"importance_reason.ilike.{term}")
            if or_clauses:
                query = query.or_(",".join(or_clauses))
            response = query.order("message_timestamp", desc=True).limit(limit).execute()
        except Exception as exc:
            if not self._is_missing_table_error(exc, "important_messages"):
                raise
            return []

        rows = response.data or []
        messages: list[ImportantMessageRecord] = []
        for row in rows:
            parsed = self._parse_important_message(row, fallback_user_id=user_id)
            if parsed is not None:
                messages.append(parsed)
        return messages

    def list_important_messages_pending_review(
        self,
        *,
        user_id: UUID,
        reviewed_before: datetime,
        limit: int = 120,
    ) -> list[ImportantMessageRecord]:
        active_messages = self.list_important_messages(
            user_id,
            limit=max(limit * 2, 160),
            include_discarded=False,
        )
        pending = [
            message
            for message in active_messages
            if message.last_reviewed_at is None or message.last_reviewed_at < reviewed_before
        ]
        pending.sort(
            key=lambda message: (
                message.last_reviewed_at or datetime.min.replace(tzinfo=UTC),
                message.message_timestamp,
            )
        )
        return pending[:limit]

    def apply_important_message_reviews(
        self,
        *,
        user_id: UUID,
        reviews: Sequence[ImportantMessageReviewSeed],
        reviewed_at: datetime,
    ) -> tuple[int, int]:
        kept_count = 0
        discarded_count = 0
        seen_source_ids: set[str] = set()

        for review in reviews:
            source_message_id = review.source_message_id.strip()
            if not source_message_id or source_message_id in seen_source_ids:
                continue
            seen_source_ids.add(source_message_id)
            decision = "discard" if review.decision.strip().lower() == "discard" else "keep"
            payload = {
                "status": "discarded" if decision == "discard" else "active",
                "review_notes": review.review_notes.strip(),
                "confidence": max(0, min(100, int(review.confidence))),
                "last_reviewed_at": reviewed_at.isoformat(),
                "discarded_at": reviewed_at.isoformat() if decision == "discard" else None,
            }
            try:
                self.client.table("important_messages").update(payload).eq("user_id", str(user_id)).eq("source_message_id", source_message_id).execute()
            except Exception as exc:
                if not self._is_missing_table_error(exc, "important_messages"):
                    raise
                return 0, 0
            if decision == "discard":
                discarded_count += 1
            else:
                kept_count += 1
        return kept_count, discarded_count

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

    def get_chat_thread(self, *, user_id: UUID, thread_id: str) -> ChatThreadRecord | None:
        response = (
            self.client.table("chat_threads")
            .select("id,user_id,thread_key,title,created_at,updated_at")
            .eq("user_id", str(user_id))
            .eq("id", thread_id)
            .limit(1)
            .execute()
        )

        rows = response.data or []
        if not rows:
            return None
        return self._parse_chat_thread(rows[0], fallback_user_id=user_id)

    def list_chat_threads(self, *, user_id: UUID, limit: int = 24) -> list[ChatThreadRecord]:
        response = (
            self.client.table("chat_threads")
            .select("id,user_id,thread_key,title,created_at,updated_at")
            .eq("user_id", str(user_id))
            .order("updated_at", desc=True)
            .limit(limit)
            .execute()
        )

        rows = response.data or []
        threads: list[ChatThreadRecord] = []
        for row in rows:
            parsed = self._parse_chat_thread(row, fallback_user_id=user_id)
            if parsed is not None:
                threads.append(parsed)
        return threads

    def create_chat_thread(
        self,
        *,
        user_id: UUID,
        title: str,
        thread_key: str,
        created_at: datetime | None = None,
    ) -> ChatThreadRecord:
        resolved_created_at = created_at or datetime.now(UTC)
        thread_id = str(uuid4())
        record = {
            "id": thread_id,
            "user_id": str(user_id),
            "thread_key": thread_key,
            "title": title,
            "created_at": resolved_created_at.isoformat(),
            "updated_at": resolved_created_at.isoformat(),
        }
        self.client.table("chat_threads").insert(record).execute()
        created = self.get_chat_thread(user_id=user_id, thread_id=thread_id)
        if created is None:
            raise RuntimeError("Chat thread could not be created.")
        return created

    def update_chat_thread(
        self,
        *,
        thread_id: str,
        title: str | None = None,
        updated_at: datetime | None = None,
    ) -> ChatThreadRecord | None:
        payload: dict[str, Any] = {}
        if title is not None:
            payload["title"] = title
        if updated_at is not None:
            payload["updated_at"] = updated_at.isoformat()
        if not payload:
            return self.get_chat_thread(user_id=self.default_user_id, thread_id=thread_id)
        self.client.table("chat_threads").update(payload).eq("id", thread_id).execute()
        return self.get_chat_thread(user_id=self.default_user_id, thread_id=thread_id)

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

    def count_chat_messages(self, thread_id: str) -> int:
        response = (
            self.client.table("chat_messages")
            .select("id")
            .eq("thread_id", thread_id)
            .limit(5000)
            .execute()
        )
        rows = response.data or []
        return sum(1 for row in rows if isinstance(row, dict))

    def get_whatsapp_agent_settings(self, user_id: UUID) -> WhatsAppAgentSettingsRecord:
        try:
            response = (
                self.client.table("whatsapp_agent_settings")
                .select("user_id,auto_reply_enabled,allowed_contact_phone,updated_at")
                .eq("user_id", str(user_id))
                .limit(1)
                .execute()
            )
        except Exception as exc:
            if not self._is_missing_table_error(exc, "whatsapp_agent_settings"):
                raise
            return self._default_whatsapp_agent_settings(user_id=user_id)

        rows = response.data or []
        if not rows or not isinstance(rows[0], dict):
            created_at = datetime.now(UTC)
            payload = self._default_whatsapp_agent_settings_record(user_id=user_id, updated_at=created_at)
            try:
                self.client.table("whatsapp_agent_settings").upsert(payload, on_conflict="user_id").execute()
            except Exception as exc:
                if not self._is_missing_table_error(exc, "whatsapp_agent_settings"):
                    raise
                return self._default_whatsapp_agent_settings(user_id=user_id)
            return self._parse_whatsapp_agent_settings(payload, fallback_user_id=user_id) or self._default_whatsapp_agent_settings(user_id=user_id)

        parsed = self._parse_whatsapp_agent_settings(rows[0], fallback_user_id=user_id)
        return parsed or self._default_whatsapp_agent_settings(user_id=user_id)

    def update_whatsapp_agent_settings(
        self,
        *,
        user_id: UUID,
        auto_reply_enabled: bool | None = None,
        allowed_contact_phone: str | None | object = _UNSET,
        updated_at: datetime | None = None,
    ) -> WhatsAppAgentSettingsRecord:
        current = self.get_whatsapp_agent_settings(user_id)
        resolved_updated_at = updated_at or datetime.now(UTC)
        payload = {
            "user_id": str(user_id),
            "auto_reply_enabled": current.auto_reply_enabled if auto_reply_enabled is None else bool(auto_reply_enabled),
            "allowed_contact_phone": (
                current.allowed_contact_phone
                if allowed_contact_phone is _UNSET
                else self.normalize_contact_phone(allowed_contact_phone if isinstance(allowed_contact_phone, str) else None)
            ),
            "updated_at": resolved_updated_at.isoformat(),
        }
        try:
            self.client.table("whatsapp_agent_settings").upsert(payload, on_conflict="user_id").execute()
        except Exception as exc:
            if not self._is_missing_table_error(exc, "whatsapp_agent_settings"):
                raise
            return self._parse_whatsapp_agent_settings(payload, fallback_user_id=user_id) or self._default_whatsapp_agent_settings(user_id=user_id)
        return self._parse_whatsapp_agent_settings(payload, fallback_user_id=user_id) or self._default_whatsapp_agent_settings(user_id=user_id)

    def get_whatsapp_agent_thread(self, *, user_id: UUID, thread_id: str) -> WhatsAppAgentThreadRecord | None:
        try:
            response = (
                self.client.table("whatsapp_agent_threads")
                .select(
                    "id,user_id,contact_phone,chat_jid,contact_name,status,last_message_at,last_inbound_at,"
                    "last_outbound_at,last_error_at,last_error_text,created_at,updated_at"
                )
                .eq("user_id", str(user_id))
                .eq("id", thread_id)
                .limit(1)
                .execute()
            )
        except Exception as exc:
            if not self._is_missing_table_error(exc, "whatsapp_agent_threads"):
                raise
            return None
        rows = response.data or []
        if not rows:
            return None
        return self._parse_whatsapp_agent_thread(rows[0], fallback_user_id=user_id)

    def get_whatsapp_agent_thread_by_contact(
        self,
        *,
        user_id: UUID,
        contact_phone: str,
    ) -> WhatsAppAgentThreadRecord | None:
        normalized_phone = self.normalize_contact_phone(contact_phone)
        if not normalized_phone:
            return None
        try:
            response = (
                self.client.table("whatsapp_agent_threads")
                .select(
                    "id,user_id,contact_phone,chat_jid,contact_name,status,last_message_at,last_inbound_at,"
                    "last_outbound_at,last_error_at,last_error_text,created_at,updated_at"
                )
                .eq("user_id", str(user_id))
                .eq("contact_phone", normalized_phone)
                .limit(1)
                .execute()
            )
        except Exception as exc:
            if not self._is_missing_table_error(exc, "whatsapp_agent_threads"):
                raise
            return None
        rows = response.data or []
        if not rows:
            return None
        return self._parse_whatsapp_agent_thread(rows[0], fallback_user_id=user_id)

    def get_whatsapp_agent_thread_by_chat_jid(
        self,
        *,
        user_id: UUID,
        chat_jid: str | None,
    ) -> WhatsAppAgentThreadRecord | None:
        normalized_jid = self._optional_text(chat_jid)
        if not normalized_jid:
            return None
        try:
            response = (
                self.client.table("whatsapp_agent_threads")
                .select(
                    "id,user_id,contact_phone,chat_jid,contact_name,status,last_message_at,last_inbound_at,"
                    "last_outbound_at,last_error_at,last_error_text,created_at,updated_at"
                )
                .eq("user_id", str(user_id))
                .eq("chat_jid", normalized_jid)
                .order("updated_at", desc=True)
                .limit(1)
                .execute()
            )
        except Exception as exc:
            if not self._is_missing_table_error(exc, "whatsapp_agent_threads"):
                raise
            return None
        rows = response.data or []
        if not rows:
            return None
        return self._parse_whatsapp_agent_thread(rows[0], fallback_user_id=user_id)

    def get_or_create_whatsapp_agent_thread(
        self,
        *,
        user_id: UUID,
        contact_phone: str,
        chat_jid: str | None,
        contact_name: str | None,
        created_at: datetime | None = None,
    ) -> WhatsAppAgentThreadRecord:
        normalized_phone = self.normalize_contact_phone(contact_phone)
        if not normalized_phone:
            raise RuntimeError("WhatsApp agent thread requires a valid contact phone.")

        self.upsert_known_contact(
            user_id=user_id,
            contact_phone=normalized_phone,
            chat_jid=chat_jid,
            contact_name=contact_name,
            name_source="agent_inbound",
            seen_at=created_at,
        )

        existing = self.get_whatsapp_agent_thread_by_contact(user_id=user_id, contact_phone=normalized_phone)
        if existing is None:
            existing = self.get_whatsapp_agent_thread_by_chat_jid(user_id=user_id, chat_jid=chat_jid)
        resolved_name = self._resolve_contact_name(
            incoming_name=contact_name,
            contact_phone=normalized_phone,
            known_name=self._load_known_contact_names([normalized_phone]).get(normalized_phone),
        )
        resolved_chat_jid = self._optional_text(chat_jid)
        now = created_at or datetime.now(UTC)

        if existing is not None:
            payload: dict[str, Any] = {"updated_at": now.isoformat()}
            if normalized_phone and normalized_phone != existing.contact_phone:
                payload["contact_phone"] = normalized_phone
            if resolved_name and resolved_name != existing.contact_name:
                payload["contact_name"] = resolved_name
            if resolved_chat_jid and resolved_chat_jid != existing.chat_jid:
                payload["chat_jid"] = resolved_chat_jid
            if payload:
                try:
                    self.client.table("whatsapp_agent_threads").update(payload).eq("id", existing.id).execute()
                except Exception as exc:
                    if not self._is_missing_table_error(exc, "whatsapp_agent_threads"):
                        raise
                    return existing
                refreshed = self.get_whatsapp_agent_thread(user_id=user_id, thread_id=existing.id)
                return refreshed or existing
            return existing

        thread_id = str(uuid4())
        record = {
            "id": thread_id,
            "user_id": str(user_id),
            "contact_phone": normalized_phone,
            "chat_jid": resolved_chat_jid,
            "contact_name": resolved_name,
            "status": "active",
            "last_message_at": None,
            "last_inbound_at": None,
            "last_outbound_at": None,
            "last_error_at": None,
            "last_error_text": None,
            "created_at": now.isoformat(),
            "updated_at": now.isoformat(),
        }
        try:
            self.client.table("whatsapp_agent_threads").insert(record).execute()
        except Exception as exc:
            if not self._is_missing_table_error(exc, "whatsapp_agent_threads"):
                raise
            parsed = self._parse_whatsapp_agent_thread(record, fallback_user_id=user_id)
            if parsed is None:
                raise RuntimeError("WhatsApp agent thread could not be created.")
            return parsed
        created = self.get_whatsapp_agent_thread(user_id=user_id, thread_id=thread_id)
        if created is None:
            raise RuntimeError("WhatsApp agent thread could not be created.")
        return created

    def update_whatsapp_agent_thread(
        self,
        *,
        thread_id: str,
        contact_name: str | None | object = _UNSET,
        chat_jid: str | None | object = _UNSET,
        status: str | None | object = _UNSET,
        last_message_at: datetime | None | object = _UNSET,
        last_inbound_at: datetime | None | object = _UNSET,
        last_outbound_at: datetime | None | object = _UNSET,
        last_error_at: datetime | None | object = _UNSET,
        last_error_text: str | None | object = _UNSET,
        updated_at: datetime | None = None,
    ) -> WhatsAppAgentThreadRecord | None:
        current = self.get_whatsapp_agent_thread(user_id=self.default_user_id, thread_id=thread_id)
        if current is None:
            return None

        payload: dict[str, Any] = {"updated_at": (updated_at or datetime.now(UTC)).isoformat()}
        if contact_name is not _UNSET:
            payload["contact_name"] = self._resolve_contact_name(
                incoming_name=contact_name if isinstance(contact_name, str) else None,
                contact_phone=current.contact_phone,
                known_name=current.contact_name,
            )
        if chat_jid is not _UNSET:
            payload["chat_jid"] = self._optional_text(chat_jid if isinstance(chat_jid, str) else None)
        if status is not _UNSET:
            payload["status"] = str(status or "active").strip().lower() or "active"
        if last_message_at is not _UNSET:
            payload["last_message_at"] = last_message_at.isoformat() if isinstance(last_message_at, datetime) else None
        if last_inbound_at is not _UNSET:
            payload["last_inbound_at"] = last_inbound_at.isoformat() if isinstance(last_inbound_at, datetime) else None
        if last_outbound_at is not _UNSET:
            payload["last_outbound_at"] = last_outbound_at.isoformat() if isinstance(last_outbound_at, datetime) else None
        if last_error_at is not _UNSET:
            payload["last_error_at"] = last_error_at.isoformat() if isinstance(last_error_at, datetime) else None
        if last_error_text is not _UNSET:
            payload["last_error_text"] = self._optional_text(last_error_text)

        try:
            self.client.table("whatsapp_agent_threads").update(payload).eq("id", thread_id).execute()
        except Exception as exc:
            if not self._is_missing_table_error(exc, "whatsapp_agent_threads"):
                raise
            merged = {
                "id": current.id,
                "user_id": str(current.user_id),
                "contact_phone": current.contact_phone,
                "chat_jid": payload.get("chat_jid", current.chat_jid),
                "contact_name": payload.get("contact_name", current.contact_name),
                "status": payload.get("status", current.status),
                "last_message_at": payload.get("last_message_at", current.last_message_at.isoformat() if current.last_message_at else None),
                "last_inbound_at": payload.get("last_inbound_at", current.last_inbound_at.isoformat() if current.last_inbound_at else None),
                "last_outbound_at": payload.get("last_outbound_at", current.last_outbound_at.isoformat() if current.last_outbound_at else None),
                "last_error_at": payload.get("last_error_at", current.last_error_at.isoformat() if current.last_error_at else None),
                "last_error_text": payload.get("last_error_text", current.last_error_text),
                "created_at": current.created_at.isoformat(),
                "updated_at": payload["updated_at"],
            }
            return self._parse_whatsapp_agent_thread(merged, fallback_user_id=current.user_id)

        return self.get_whatsapp_agent_thread(user_id=current.user_id, thread_id=thread_id)

    def list_whatsapp_agent_threads(self, *, user_id: UUID, limit: int = 24) -> list[WhatsAppAgentThreadRecord]:
        try:
            response = (
                self.client.table("whatsapp_agent_threads")
                .select(
                    "id,user_id,contact_phone,chat_jid,contact_name,status,last_message_at,last_inbound_at,"
                    "last_outbound_at,last_error_at,last_error_text,created_at,updated_at"
                )
                .eq("user_id", str(user_id))
                .order("last_message_at", desc=True)
                .order("updated_at", desc=True)
                .limit(limit)
                .execute()
            )
        except Exception as exc:
            if not self._is_missing_table_error(exc, "whatsapp_agent_threads"):
                raise
            return []

        rows = response.data or []
        threads: list[WhatsAppAgentThreadRecord] = []
        for row in rows:
            parsed = self._parse_whatsapp_agent_thread(row, fallback_user_id=user_id)
            if parsed is not None:
                threads.append(parsed)
        return threads

    def get_whatsapp_agent_session(
        self,
        *,
        user_id: UUID,
        session_id: str,
    ) -> WhatsAppAgentThreadSessionRecord | None:
        try:
            response = (
                self.client.table("whatsapp_agent_thread_sessions")
                .select(
                    "id,user_id,thread_id,contact_phone,chat_jid,started_at,last_activity_at,ended_at,"
                    "reset_reason,created_at,updated_at"
                )
                .eq("user_id", str(user_id))
                .eq("id", session_id)
                .limit(1)
                .execute()
            )
        except Exception as exc:
            if not self._is_missing_table_error(exc, "whatsapp_agent_thread_sessions"):
                raise
            return None
        rows = response.data or []
        if not rows:
            return None
        return self._parse_whatsapp_agent_thread_session(rows[0], fallback_user_id=user_id)

    def get_whatsapp_agent_active_session(
        self,
        *,
        user_id: UUID,
        thread_id: str,
    ) -> WhatsAppAgentThreadSessionRecord | None:
        try:
            response = (
                self.client.table("whatsapp_agent_thread_sessions")
                .select(
                    "id,user_id,thread_id,contact_phone,chat_jid,started_at,last_activity_at,ended_at,"
                    "reset_reason,created_at,updated_at"
                )
                .eq("user_id", str(user_id))
                .eq("thread_id", thread_id)
                .order("last_activity_at", desc=True)
                .order("created_at", desc=True)
                .limit(12)
                .execute()
            )
        except Exception as exc:
            if not self._is_missing_table_error(exc, "whatsapp_agent_thread_sessions"):
                raise
            return None

        rows = response.data or []
        for row in rows:
            parsed = self._parse_whatsapp_agent_thread_session(row, fallback_user_id=user_id)
            if parsed is not None and parsed.ended_at is None:
                return parsed
        return None

    def create_whatsapp_agent_session(
        self,
        *,
        user_id: UUID,
        thread_id: str,
        contact_phone: str | None,
        chat_jid: str | None,
        started_at: datetime,
    ) -> WhatsAppAgentThreadSessionRecord:
        record_id = str(uuid4())
        record = {
            "id": record_id,
            "user_id": str(user_id),
            "thread_id": thread_id,
            "contact_phone": self.normalize_contact_phone(contact_phone),
            "chat_jid": self._optional_text(chat_jid),
            "started_at": started_at.isoformat(),
            "last_activity_at": started_at.isoformat(),
            "ended_at": None,
            "reset_reason": None,
            "created_at": started_at.isoformat(),
            "updated_at": started_at.isoformat(),
        }
        try:
            self.client.table("whatsapp_agent_thread_sessions").insert(record).execute()
        except Exception as exc:
            if not self._is_missing_table_error(exc, "whatsapp_agent_thread_sessions"):
                raise
            parsed = self._parse_whatsapp_agent_thread_session(record, fallback_user_id=user_id)
            if parsed is None:
                raise RuntimeError("WhatsApp agent session could not be created.")
            return parsed
        created = self.get_whatsapp_agent_session(user_id=user_id, session_id=record_id)
        if created is None:
            raise RuntimeError("WhatsApp agent session could not be created.")
        return created

    def update_whatsapp_agent_session(
        self,
        *,
        session_id: str,
        last_activity_at: datetime | None | object = _UNSET,
        ended_at: datetime | None | object = _UNSET,
        reset_reason: str | None | object = _UNSET,
        updated_at: datetime | None = None,
    ) -> WhatsAppAgentThreadSessionRecord | None:
        current = self.get_whatsapp_agent_session(user_id=self.default_user_id, session_id=session_id)
        if current is None:
            return None

        payload: dict[str, Any] = {"updated_at": (updated_at or datetime.now(UTC)).isoformat()}
        if last_activity_at is not _UNSET:
            payload["last_activity_at"] = (
                last_activity_at.isoformat() if isinstance(last_activity_at, datetime) else None
            )
        if ended_at is not _UNSET:
            payload["ended_at"] = ended_at.isoformat() if isinstance(ended_at, datetime) else None
        if reset_reason is not _UNSET:
            payload["reset_reason"] = self._optional_text(reset_reason)

        try:
            self.client.table("whatsapp_agent_thread_sessions").update(payload).eq("id", session_id).execute()
        except Exception as exc:
            if not self._is_missing_table_error(exc, "whatsapp_agent_thread_sessions"):
                raise
            merged = {
                "id": current.id,
                "user_id": str(current.user_id),
                "thread_id": current.thread_id,
                "contact_phone": current.contact_phone,
                "chat_jid": current.chat_jid,
                "started_at": current.started_at.isoformat(),
                "last_activity_at": payload.get(
                    "last_activity_at",
                    current.last_activity_at.isoformat(),
                ),
                "ended_at": payload.get("ended_at", current.ended_at.isoformat() if current.ended_at else None),
                "reset_reason": payload.get("reset_reason", current.reset_reason),
                "created_at": current.created_at.isoformat(),
                "updated_at": payload["updated_at"],
            }
            return self._parse_whatsapp_agent_thread_session(merged, fallback_user_id=current.user_id)

        return self.get_whatsapp_agent_session(user_id=current.user_id, session_id=session_id)

    def resolve_whatsapp_agent_session(
        self,
        *,
        user_id: UUID,
        thread_id: str,
        contact_phone: str | None,
        chat_jid: str | None,
        activity_at: datetime,
        idle_timeout_minutes: int,
    ) -> tuple[WhatsAppAgentThreadSessionRecord, bool]:
        active = self.get_whatsapp_agent_active_session(user_id=user_id, thread_id=thread_id)
        threshold_seconds = max(1, idle_timeout_minutes) * 60
        if active is not None:
            gap_seconds = max(0.0, (activity_at - active.last_activity_at).total_seconds())
            if gap_seconds <= threshold_seconds:
                updated = self.update_whatsapp_agent_session(
                    session_id=active.id,
                    last_activity_at=self._latest_datetime(active.last_activity_at, activity_at) or activity_at,
                    updated_at=activity_at,
                )
                return updated or active, False
            self.update_whatsapp_agent_session(
                session_id=active.id,
                ended_at=activity_at,
                reset_reason="idle_timeout",
                updated_at=activity_at,
            )
        created = self.create_whatsapp_agent_session(
            user_id=user_id,
            thread_id=thread_id,
            contact_phone=contact_phone,
            chat_jid=chat_jid,
            started_at=activity_at,
        )
        return created, True

    def count_whatsapp_agent_session_messages(self, *, session_id: str) -> int:
        try:
            response = (
                self.client.table("whatsapp_agent_messages")
                .select("id")
                .eq("session_id", session_id)
                .limit(1000)
                .execute()
            )
        except Exception as exc:
            if not self._is_missing_table_error(exc, "whatsapp_agent_messages"):
                raise
            return 0
        rows = response.data or []
        return sum(1 for row in rows if isinstance(row, dict))

    def get_whatsapp_agent_contact_memory(
        self,
        *,
        user_id: UUID,
        contact_phone: str,
    ) -> WhatsAppAgentContactMemoryRecord | None:
        normalized_phone = self.normalize_contact_phone(contact_phone)
        if not normalized_phone:
            return None
        try:
            response = (
                self.client.table("whatsapp_agent_contact_memories")
                .select(
                    "id,user_id,thread_id,contact_phone,chat_jid,contact_name,profile_summary,preferred_tone,"
                    "preferences,objectives,durable_facts,constraints,recurring_instructions,"
                    "learned_message_count,last_learned_at,updated_at"
                )
                .eq("user_id", str(user_id))
                .eq("contact_phone", normalized_phone)
                .limit(1)
                .execute()
            )
        except Exception as exc:
            if not self._is_missing_table_error(exc, "whatsapp_agent_contact_memories"):
                raise
            return None

        rows = response.data or []
        if not rows:
            return None
        return self._parse_whatsapp_agent_contact_memory(rows[0], fallback_user_id=user_id)

    def upsert_whatsapp_agent_contact_memory(
        self,
        *,
        user_id: UUID,
        thread_id: str | None,
        contact_phone: str,
        chat_jid: str | None,
        contact_name: str | None,
        profile_summary: str,
        preferred_tone: str,
        preferences: Sequence[str],
        objectives: Sequence[str],
        durable_facts: Sequence[str],
        constraints: Sequence[str],
        recurring_instructions: Sequence[str],
        learned_message_count: int,
        last_learned_at: datetime | None,
        updated_at: datetime | None = None,
    ) -> WhatsAppAgentContactMemoryRecord:
        normalized_phone = self.normalize_contact_phone(contact_phone)
        if not normalized_phone:
            raise RuntimeError("WhatsApp agent memory requires a valid contact phone.")

        self.upsert_known_contact(
            user_id=user_id,
            contact_phone=normalized_phone,
            chat_jid=chat_jid,
            contact_name=contact_name,
            name_source="agent_memory",
            seen_at=last_learned_at,
        )

        current = self.get_whatsapp_agent_contact_memory(user_id=user_id, contact_phone=normalized_phone)
        record_id = current.id if current is not None else str(uuid4())
        now = updated_at or datetime.now(UTC)
        payload = {
            "id": record_id,
            "user_id": str(user_id),
            "thread_id": self._optional_text(thread_id),
            "contact_phone": normalized_phone,
            "chat_jid": self._optional_text(chat_jid),
            "contact_name": self._resolve_contact_name(
                incoming_name=contact_name,
                contact_phone=normalized_phone,
                known_name=current.contact_name if current is not None else None,
            ),
            "profile_summary": profile_summary.strip(),
            "preferred_tone": preferred_tone.strip(),
            "preferences": self._normalize_string_list(preferences),
            "objectives": self._normalize_string_list(objectives),
            "durable_facts": self._normalize_string_list(durable_facts),
            "constraints": self._normalize_string_list(constraints),
            "recurring_instructions": self._normalize_string_list(recurring_instructions),
            "learned_message_count": max(0, int(learned_message_count)),
            "last_learned_at": last_learned_at.isoformat() if isinstance(last_learned_at, datetime) else None,
            "updated_at": now.isoformat(),
        }
        try:
            self.client.table("whatsapp_agent_contact_memories").upsert(
                payload,
                on_conflict="user_id,contact_phone",
            ).execute()
        except Exception as exc:
            if not self._is_missing_table_error(exc, "whatsapp_agent_contact_memories"):
                raise
            parsed = self._parse_whatsapp_agent_contact_memory(payload, fallback_user_id=user_id)
            if parsed is None:
                raise RuntimeError("WhatsApp agent contact memory could not be stored.")
            return parsed
        stored = self.get_whatsapp_agent_contact_memory(user_id=user_id, contact_phone=normalized_phone)
        if stored is None:
            raise RuntimeError("WhatsApp agent contact memory could not be stored.")
        return stored

    def get_whatsapp_agent_message_by_whatsapp_id(
        self,
        *,
        user_id: UUID,
        whatsapp_message_id: str,
    ) -> WhatsAppAgentMessageRecord | None:
        normalized_id = self._optional_text(whatsapp_message_id)
        if not normalized_id:
            return None
        try:
            response = (
                self.client.table("whatsapp_agent_messages")
                .select(
                    "id,user_id,thread_id,direction,role,session_id,whatsapp_message_id,source_inbound_message_id,"
                    "contact_phone,chat_jid,content,message_timestamp,processing_status,learning_status,send_status,"
                    "error_text,response_latency_ms,model_run_id,learned_at,metadata,created_at"
                )
                .eq("user_id", str(user_id))
                .eq("whatsapp_message_id", normalized_id)
                .limit(1)
                .execute()
            )
        except Exception as exc:
            if not self._is_missing_table_error(exc, "whatsapp_agent_messages"):
                raise
            return None

        rows = response.data or []
        if not rows:
            return None
        return self._parse_whatsapp_agent_message(rows[0], fallback_user_id=user_id)

    def get_whatsapp_agent_outbound_for_source_inbound(
        self,
        *,
        user_id: UUID,
        source_inbound_message_id: str,
    ) -> WhatsAppAgentMessageRecord | None:
        normalized_id = self._optional_text(source_inbound_message_id)
        if not normalized_id:
            return None
        try:
            response = (
                self.client.table("whatsapp_agent_messages")
                .select(
                    "id,user_id,thread_id,direction,role,session_id,whatsapp_message_id,source_inbound_message_id,"
                    "contact_phone,chat_jid,content,message_timestamp,processing_status,learning_status,send_status,"
                    "error_text,response_latency_ms,model_run_id,learned_at,metadata,created_at"
                )
                .eq("user_id", str(user_id))
                .eq("direction", "outbound")
                .eq("source_inbound_message_id", normalized_id)
                .limit(1)
                .execute()
            )
        except Exception as exc:
            if not self._is_missing_table_error(exc, "whatsapp_agent_messages"):
                raise
            return None

        rows = response.data or []
        if not rows:
            return None
        return self._parse_whatsapp_agent_message(rows[0], fallback_user_id=user_id)

    def append_whatsapp_agent_message(
        self,
        *,
        user_id: UUID,
        thread_id: str,
        direction: str,
        role: str,
        content: str,
        message_timestamp: datetime,
        contact_phone: str | None,
        chat_jid: str | None,
        session_id: str | None = None,
        whatsapp_message_id: str | None = None,
        source_inbound_message_id: str | None = None,
        processing_status: str = "received",
        learning_status: str = "not_applicable",
        send_status: str | None = None,
        error_text: str | None = None,
        response_latency_ms: int | None = None,
        model_run_id: str | None = None,
        learned_at: datetime | None = None,
        metadata: dict[str, Any] | None = None,
        created_at: datetime | None = None,
    ) -> WhatsAppAgentMessageRecord:
        record_id = str(uuid4())
        resolved_created_at = created_at or datetime.now(UTC)
        record = {
            "id": record_id,
            "user_id": str(user_id),
            "thread_id": thread_id,
            "direction": direction,
            "role": role,
            "session_id": self._optional_text(session_id),
            "whatsapp_message_id": self._optional_text(whatsapp_message_id),
            "source_inbound_message_id": self._optional_text(source_inbound_message_id),
            "contact_phone": self.normalize_contact_phone(contact_phone),
            "chat_jid": self._optional_text(chat_jid),
            "content": content.strip(),
            "message_timestamp": message_timestamp.isoformat(),
            "processing_status": str(processing_status or "received").strip().lower() or "received",
            "learning_status": str(learning_status or "not_applicable").strip().lower() or "not_applicable",
            "send_status": self._optional_text(send_status),
            "error_text": self._optional_text(error_text),
            "response_latency_ms": response_latency_ms,
            "model_run_id": self._optional_text(model_run_id),
            "learned_at": learned_at.isoformat() if isinstance(learned_at, datetime) else None,
            "metadata": metadata or {},
            "created_at": resolved_created_at.isoformat(),
        }
        try:
            self.client.table("whatsapp_agent_messages").insert(record).execute()
        except Exception as exc:
            if not self._is_missing_table_error(exc, "whatsapp_agent_messages"):
                raise
            parsed = self._parse_whatsapp_agent_message(record, fallback_user_id=user_id)
            if parsed is None:
                raise RuntimeError("WhatsApp agent message could not be stored.")
            return parsed
        parsed = self.get_whatsapp_agent_message(user_id=user_id, message_id=record_id)
        if parsed is None:
            raise RuntimeError("WhatsApp agent message could not be stored.")
        return parsed

    def get_whatsapp_agent_message(self, *, user_id: UUID, message_id: str) -> WhatsAppAgentMessageRecord | None:
        try:
            response = (
                self.client.table("whatsapp_agent_messages")
                .select(
                    "id,user_id,thread_id,direction,role,session_id,whatsapp_message_id,source_inbound_message_id,"
                    "contact_phone,chat_jid,content,message_timestamp,processing_status,learning_status,send_status,"
                    "error_text,response_latency_ms,model_run_id,learned_at,metadata,created_at"
                )
                .eq("user_id", str(user_id))
                .eq("id", message_id)
                .limit(1)
                .execute()
            )
        except Exception as exc:
            if not self._is_missing_table_error(exc, "whatsapp_agent_messages"):
                raise
            return None
        rows = response.data or []
        if not rows:
            return None
        return self._parse_whatsapp_agent_message(rows[0], fallback_user_id=user_id)

    def update_whatsapp_agent_message(
        self,
        *,
        message_id: str,
        processing_status: str | None | object = _UNSET,
        learning_status: str | None | object = _UNSET,
        send_status: str | None | object = _UNSET,
        error_text: str | None | object = _UNSET,
        response_latency_ms: int | None | object = _UNSET,
        model_run_id: str | None | object = _UNSET,
        session_id: str | None | object = _UNSET,
        whatsapp_message_id: str | None | object = _UNSET,
        learned_at: datetime | None | object = _UNSET,
        metadata: dict[str, Any] | object = _UNSET,
        message_timestamp: datetime | None | object = _UNSET,
    ) -> WhatsAppAgentMessageRecord | None:
        current = self.get_whatsapp_agent_message(user_id=self.default_user_id, message_id=message_id)
        if current is None:
            return None
        payload: dict[str, Any] = {}
        if processing_status is not _UNSET:
            payload["processing_status"] = str(processing_status or current.processing_status).strip().lower() or current.processing_status
        if learning_status is not _UNSET:
            payload["learning_status"] = str(learning_status or current.learning_status).strip().lower() or current.learning_status
        if send_status is not _UNSET:
            payload["send_status"] = self._optional_text(send_status)
        if error_text is not _UNSET:
            payload["error_text"] = self._optional_text(error_text)
        if response_latency_ms is not _UNSET:
            payload["response_latency_ms"] = int(response_latency_ms) if isinstance(response_latency_ms, int) else None
        if model_run_id is not _UNSET:
            payload["model_run_id"] = self._optional_text(model_run_id)
        if session_id is not _UNSET:
            payload["session_id"] = self._optional_text(session_id)
        if whatsapp_message_id is not _UNSET:
            payload["whatsapp_message_id"] = self._optional_text(whatsapp_message_id)
        if learned_at is not _UNSET:
            payload["learned_at"] = learned_at.isoformat() if isinstance(learned_at, datetime) else None
        if metadata is not _UNSET:
            payload["metadata"] = metadata if isinstance(metadata, dict) else {}
        if message_timestamp is not _UNSET:
            payload["message_timestamp"] = message_timestamp.isoformat() if isinstance(message_timestamp, datetime) else None
        if not payload:
            return current
        try:
            self.client.table("whatsapp_agent_messages").update(payload).eq("id", message_id).execute()
        except Exception as exc:
            if not self._is_missing_table_error(exc, "whatsapp_agent_messages"):
                raise
            merged = {
                "id": current.id,
                "user_id": str(current.user_id),
                "thread_id": current.thread_id,
                "direction": current.direction,
                "role": current.role,
                "session_id": payload.get("session_id", current.session_id),
                "whatsapp_message_id": payload.get("whatsapp_message_id", current.whatsapp_message_id),
                "source_inbound_message_id": current.source_inbound_message_id,
                "contact_phone": current.contact_phone,
                "chat_jid": current.chat_jid,
                "content": current.content,
                "message_timestamp": payload.get("message_timestamp", current.message_timestamp.isoformat()),
                "processing_status": payload.get("processing_status", current.processing_status),
                "learning_status": payload.get("learning_status", current.learning_status),
                "send_status": payload.get("send_status", current.send_status),
                "error_text": payload.get("error_text", current.error_text),
                "response_latency_ms": payload.get("response_latency_ms", current.response_latency_ms),
                "model_run_id": payload.get("model_run_id", current.model_run_id),
                "learned_at": payload.get("learned_at", current.learned_at.isoformat() if current.learned_at else None),
                "metadata": payload.get("metadata", current.metadata),
                "created_at": current.created_at.isoformat(),
            }
            return self._parse_whatsapp_agent_message(merged, fallback_user_id=current.user_id)
        return self.get_whatsapp_agent_message(user_id=current.user_id, message_id=message_id)

    def list_whatsapp_agent_messages(self, *, thread_id: str, limit: int = 40) -> list[WhatsAppAgentMessageRecord]:
        try:
            response = (
                self.client.table("whatsapp_agent_messages")
                .select(
                    "id,user_id,thread_id,direction,role,session_id,whatsapp_message_id,source_inbound_message_id,"
                    "contact_phone,chat_jid,content,message_timestamp,processing_status,learning_status,send_status,"
                    "error_text,response_latency_ms,model_run_id,learned_at,metadata,created_at"
                )
                .eq("thread_id", thread_id)
                .order("message_timestamp", desc=True)
                .limit(limit)
                .execute()
            )
        except Exception as exc:
            if not self._is_missing_table_error(exc, "whatsapp_agent_messages"):
                raise
            return []

        rows = response.data or []
        messages: list[WhatsAppAgentMessageRecord] = []
        for row in reversed(rows):
            parsed = self._parse_whatsapp_agent_message(row, fallback_user_id=self.default_user_id)
            if parsed is not None:
                messages.append(parsed)
        return messages

    def list_whatsapp_agent_session_messages(self, *, session_id: str, limit: int = 40) -> list[WhatsAppAgentMessageRecord]:
        try:
            response = (
                self.client.table("whatsapp_agent_messages")
                .select(
                    "id,user_id,thread_id,direction,role,session_id,whatsapp_message_id,source_inbound_message_id,"
                    "contact_phone,chat_jid,content,message_timestamp,processing_status,learning_status,send_status,"
                    "error_text,response_latency_ms,model_run_id,learned_at,metadata,created_at"
                )
                .eq("session_id", session_id)
                .order("message_timestamp", desc=True)
                .limit(limit)
                .execute()
            )
        except Exception as exc:
            if not self._is_missing_table_error(exc, "whatsapp_agent_messages"):
                raise
            return []

        rows = response.data or []
        messages: list[WhatsAppAgentMessageRecord] = []
        for row in reversed(rows):
            parsed = self._parse_whatsapp_agent_message(row, fallback_user_id=self.default_user_id)
            if parsed is not None:
                messages.append(parsed)
        return messages

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

    def count_pending_messages(self, user_id: UUID) -> int:
        return len(
            self.list_pending_messages(
                user_id=user_id,
                limit=self.message_retention_max_rows,
                newest_first=False,
            )
        )

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
        try:
            response = (
                self.client.table("message_retention_state")
                .select(
                    "user_id,total_direct_ingested_count,total_direct_pruned_count,"
                    "observer_history_cutoff_at,last_message_at,updated_at"
                )
                .eq("user_id", str(user_id))
                .limit(1)
                .execute()
            )
        except Exception as exc:
            if self._is_missing_column_error(exc, column_name="observer_history_cutoff_at", table_name="message_retention_state"):
                response = (
                    self.client.table("message_retention_state")
                    .select("user_id,total_direct_ingested_count,total_direct_pruned_count,last_message_at,updated_at")
                    .eq("user_id", str(user_id))
                    .limit(1)
                    .execute()
                )
            else:
                if not self._is_missing_table_error(exc, "message_retention_state"):
                    raise
                current_count = self.count_messages(user_id)
                last_message_at = self.get_latest_message_timestamp(user_id)
                return MessageRetentionStateRecord(
                    user_id=user_id,
                    total_direct_ingested_count=current_count,
                    total_direct_pruned_count=0,
                    observer_history_cutoff_at=None,
                    last_message_at=last_message_at,
                    updated_at=datetime.now(UTC),
                )
        rows = response.data or []
        if rows and isinstance(rows[0], dict):
            row = rows[0]
            return MessageRetentionStateRecord(
                user_id=self._parse_uuid(row.get("user_id")) or user_id,
                total_direct_ingested_count=self._parse_int(row.get("total_direct_ingested_count")) or 0,
                total_direct_pruned_count=self._parse_int(row.get("total_direct_pruned_count")) or 0,
                observer_history_cutoff_at=self._parse_datetime(row.get("observer_history_cutoff_at")),
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
            "observer_history_cutoff_at": None,
            "last_message_at": last_message_at.isoformat() if last_message_at else None,
            "updated_at": created_at.isoformat(),
        }
        try:
            self.client.table("message_retention_state").upsert(record, on_conflict="user_id").execute()
        except Exception as exc:
            if self._is_missing_column_error(exc, column_name="observer_history_cutoff_at", table_name="message_retention_state"):
                legacy_record = dict(record)
                legacy_record.pop("observer_history_cutoff_at", None)
                self.client.table("message_retention_state").upsert(legacy_record, on_conflict="user_id").execute()
            elif not self._is_missing_table_error(exc, "message_retention_state"):
                raise
        return MessageRetentionStateRecord(
            user_id=user_id,
            total_direct_ingested_count=current_count,
            total_direct_pruned_count=0,
            observer_history_cutoff_at=None,
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
            "observer_history_cutoff_at": (
                current.observer_history_cutoff_at.isoformat()
                if current.observer_history_cutoff_at
                else None
            ),
            "last_message_at": resolved_last_message_at.isoformat() if resolved_last_message_at else None,
            "updated_at": updated_at.isoformat(),
        }
        try:
            self.client.table("message_retention_state").upsert(record, on_conflict="user_id").execute()
        except Exception as exc:
            if self._is_missing_column_error(exc, column_name="observer_history_cutoff_at", table_name="message_retention_state"):
                legacy_record = dict(record)
                legacy_record.pop("observer_history_cutoff_at", None)
                self.client.table("message_retention_state").upsert(legacy_record, on_conflict="user_id").execute()
            elif not self._is_missing_table_error(exc, "message_retention_state"):
                raise
        return MessageRetentionStateRecord(
            user_id=user_id,
            total_direct_ingested_count=int(record["total_direct_ingested_count"]),
            total_direct_pruned_count=int(record["total_direct_pruned_count"]),
            observer_history_cutoff_at=current.observer_history_cutoff_at,
            last_message_at=resolved_last_message_at,
            updated_at=updated_at,
        )

    def set_observer_history_cutoff(
        self,
        *,
        user_id: UUID,
        cutoff_at: datetime,
    ) -> MessageRetentionStateRecord:
        current = self.get_message_retention_state(user_id)
        effective_cutoff = (
            min(current.observer_history_cutoff_at, cutoff_at)
            if current.observer_history_cutoff_at is not None
            else cutoff_at
        )
        updated_at = datetime.now(UTC)
        record = {
            "user_id": str(user_id),
            "total_direct_ingested_count": current.total_direct_ingested_count,
            "total_direct_pruned_count": current.total_direct_pruned_count,
            "observer_history_cutoff_at": effective_cutoff.isoformat(),
            "last_message_at": current.last_message_at.isoformat() if current.last_message_at else None,
            "updated_at": updated_at.isoformat(),
        }
        try:
            self.client.table("message_retention_state").upsert(record, on_conflict="user_id").execute()
        except Exception as exc:
            if self._is_missing_column_error(exc, column_name="observer_history_cutoff_at", table_name="message_retention_state"):
                legacy_record = dict(record)
                legacy_record.pop("observer_history_cutoff_at", None)
                self.client.table("message_retention_state").upsert(legacy_record, on_conflict="user_id").execute()
            elif not self._is_missing_table_error(exc, "message_retention_state"):
                raise
        return MessageRetentionStateRecord(
            user_id=user_id,
            total_direct_ingested_count=current.total_direct_ingested_count,
            total_direct_pruned_count=current.total_direct_pruned_count,
            observer_history_cutoff_at=effective_cutoff,
            last_message_at=current.last_message_at,
            updated_at=updated_at,
        )

    def get_observer_history_cutoff(self, *, user_id: UUID) -> datetime | None:
        return self.get_message_retention_state(user_id).observer_history_cutoff_at

    def reconcile_observer_backlog(self, *, user_id: UUID) -> int:
        cutoff_at = self.get_observer_history_cutoff(user_id=user_id)
        if cutoff_at is None:
            return 0

        deleted_total = 0
        while True:
            try:
                response = (
                    self.client.table("mensagens")
                    .select("id")
                    .eq("user_id", str(user_id))
                    .lt("timestamp", cutoff_at.isoformat())
                    .order("timestamp", desc=False)
                    .limit(500)
                    .execute()
                )
            except Exception as exc:
                if not self._is_missing_table_error(exc, "mensagens"):
                    raise
                return deleted_total

            rows = response.data or []
            stale_ids = [
                str(row.get("id") or "").strip()
                for row in rows
                if isinstance(row, dict) and str(row.get("id") or "").strip()
            ]
            if not stale_ids:
                break

            self.mark_messages_processed(
                user_id=user_id,
                message_ids=stale_ids,
                processed_at=datetime.now(UTC),
            )
            self.delete_messages_by_ids(message_ids=stale_ids)
            deleted_total += len(stale_ids)

        if deleted_total > 0:
            observer_ingest_logger.info(
                "observer_backlog_reconciled deleted=%s cutoff_at=%s",
                deleted_total,
                cutoff_at.isoformat(),
            )
        return deleted_total

    def get_known_contact_by_phone(
        self,
        *,
        user_id: UUID,
        contact_phone: str | None,
    ) -> KnownContactRecord | None:
        normalized_phone = self.normalize_contact_phone(contact_phone)
        if not normalized_phone:
            return None
        try:
            response = (
                self.client.table("whatsapp_known_contacts")
                .select("id,user_id,contact_phone,chat_jid,contact_name,name_source,last_seen_at,updated_at")
                .eq("user_id", str(user_id))
                .eq("contact_phone", normalized_phone)
                .limit(1)
                .execute()
            )
        except Exception as exc:
            if not self._is_missing_table_error(exc, "whatsapp_known_contacts"):
                raise
            return None
        rows = response.data or []
        if not rows:
            return None
        return self._parse_known_contact(rows[0], fallback_user_id=user_id)

    def get_known_contact_by_chat_jid(
        self,
        *,
        user_id: UUID,
        chat_jid: str | None,
    ) -> KnownContactRecord | None:
        normalized_jid = self._optional_text(chat_jid)
        if not normalized_jid:
            return None
        try:
            response = (
                self.client.table("whatsapp_known_contacts")
                .select("id,user_id,contact_phone,chat_jid,contact_name,name_source,last_seen_at,updated_at")
                .eq("user_id", str(user_id))
                .eq("chat_jid", normalized_jid)
                .order("updated_at", desc=True)
                .limit(1)
                .execute()
            )
        except Exception as exc:
            if not self._is_missing_table_error(exc, "whatsapp_known_contacts"):
                raise
            return None
        rows = response.data or []
        if not rows:
            return None
        return self._parse_known_contact(rows[0], fallback_user_id=user_id)

    def upsert_known_contact(
        self,
        *,
        user_id: UUID,
        contact_phone: str | None,
        chat_jid: str | None,
        contact_name: str | None,
        name_source: str | None,
        seen_at: datetime | None,
    ) -> KnownContactRecord | None:
        normalized_phone = self.normalize_contact_phone(contact_phone)
        if not normalized_phone:
            return None
        known = self.get_known_contact_by_phone(user_id=user_id, contact_phone=normalized_phone)
        resolved_name = self._resolve_contact_name(
            incoming_name=contact_name,
            contact_phone=normalized_phone,
            known_name=known.contact_name if known is not None else None,
        )
        resolved_name_source = self._optional_text(name_source) or (known.name_source if known is not None else "unknown")
        resolved_chat_jid = self._optional_text(chat_jid) or (known.chat_jid if known is not None else None)
        resolved_seen_at = self._latest_datetime(known.last_seen_at if known is not None else None, seen_at)
        updated_at = datetime.now(UTC)
        payload = {
            "id": known.id if known is not None else str(uuid4()),
            "user_id": str(user_id),
            "contact_phone": normalized_phone,
            "chat_jid": resolved_chat_jid,
            "contact_name": resolved_name,
            "name_source": resolved_name_source,
            "last_seen_at": resolved_seen_at.isoformat() if resolved_seen_at else None,
            "updated_at": updated_at.isoformat(),
        }
        try:
            self.client.table("whatsapp_known_contacts").upsert(payload, on_conflict="user_id,contact_phone").execute()
        except Exception as exc:
            if not self._is_missing_table_error(exc, "whatsapp_known_contacts"):
                raise
            return None
        if (
            known is None
            or known.contact_name != resolved_name
            or known.chat_jid != resolved_chat_jid
            or known.name_source != resolved_name_source
        ):
            contact_resolution_logger.info(
                "known_contact_upserted contact_phone=%s chat_jid=%s name_source=%s",
                normalized_phone,
                resolved_chat_jid,
                resolved_name_source,
            )
        return self.get_known_contact_by_phone(user_id=user_id, contact_phone=normalized_phone)

    def get_automation_settings(self, user_id: UUID) -> AutomationSettingsRecord:
        try:
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
        except Exception as exc:
            if not self._is_missing_table_error(exc, "automation_settings"):
                raise
            created_at = datetime.now(UTC)
            record = self._default_automation_settings_record(user_id=user_id, updated_at=created_at)
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
        rows = response.data or []
        if rows and isinstance(rows[0], dict):
            parsed = self._parse_automation_settings(rows[0], fallback_user_id=user_id)
            if parsed is not None:
                return parsed

        created_at = datetime.now(UTC)
        record = self._default_automation_settings_record(user_id=user_id, updated_at=created_at)
        try:
            self.client.table("automation_settings").upsert(record, on_conflict="user_id").execute()
        except Exception as exc:
            if not self._is_missing_table_error(exc, "automation_settings"):
                raise
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
        try:
            self.client.table("automation_settings").upsert(record, on_conflict="user_id").execute()
        except Exception as exc:
            if not self._is_missing_table_error(exc, "automation_settings"):
                raise
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
                updated_at=updated_at,
            )
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
        try:
            self.client.table("wa_sync_runs").insert(record).execute()
        except Exception as exc:
            if not self._is_missing_table_error(exc, "wa_sync_runs"):
                raise
            compat_record = WhatsAppSyncRunRecord(
                id=sync_run_id,
                user_id=user_id,
                trigger=trigger,
                status="running",
                messages_seen_count=0,
                messages_saved_count=0,
                messages_ignored_count=0,
                messages_pruned_count=0,
                oldest_message_at=None,
                newest_message_at=None,
                error_text=None,
                started_at=started_at,
                finished_at=None,
                last_activity_at=started_at,
            )
            self._compat_sync_runs[sync_run_id] = compat_record
            return compat_record
        sync_run = self.get_whatsapp_sync_run(sync_run_id)
        if sync_run is None:
            raise RuntimeError("WhatsApp sync run could not be created.")
        return sync_run

    def get_whatsapp_sync_run(self, sync_run_id: str) -> WhatsAppSyncRunRecord | None:
        try:
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
        except Exception as exc:
            if not self._is_missing_table_error(exc, "wa_sync_runs"):
                raise
            return self._compat_sync_runs.get(sync_run_id)
        rows = response.data or []
        if not rows or not isinstance(rows[0], dict):
            return None
        return self._parse_whatsapp_sync_run(rows[0], fallback_user_id=self.default_user_id)

    def get_latest_running_sync_run(self, user_id: UUID) -> WhatsAppSyncRunRecord | None:
        try:
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
        except Exception as exc:
            if not self._is_missing_table_error(exc, "wa_sync_runs"):
                raise
            running = [
                run for run in self._compat_sync_runs.values()
                if run.user_id == user_id and run.status == "running"
            ]
            running.sort(key=lambda run: run.started_at, reverse=True)
            return running[0] if running else None
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
        try:
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
        except Exception as exc:
            if not self._is_missing_table_error(exc, "wa_sync_runs"):
                raise
            current = self.get_latest_running_sync_run(user_id)
            if current is None:
                return None
            updated = WhatsAppSyncRunRecord(
                id=current.id,
                user_id=current.user_id,
                trigger=current.trigger,
                status=current.status,
                messages_seen_count=current.messages_seen_count + max(0, seen_increment),
                messages_saved_count=current.messages_saved_count + max(0, saved_increment),
                messages_ignored_count=current.messages_ignored_count + max(0, ignored_increment),
                messages_pruned_count=current.messages_pruned_count,
                oldest_message_at=self._earliest_datetime(current.oldest_message_at, oldest_message_at),
                newest_message_at=self._latest_datetime(current.newest_message_at, newest_message_at),
                error_text=current.error_text,
                started_at=current.started_at,
                finished_at=current.finished_at,
                last_activity_at=activity_at,
            )
            self._compat_sync_runs[current.id] = updated
            return updated

    def mark_whatsapp_sync_run_failed(self, *, sync_run_id: str, error_text: str, finished_at: datetime) -> WhatsAppSyncRunRecord | None:
        try:
            self.client.table("wa_sync_runs").update(
                {
                    "status": "failed",
                    "error_text": error_text,
                    "finished_at": finished_at.isoformat(),
                    "last_activity_at": finished_at.isoformat(),
                }
            ).eq("id", sync_run_id).execute()
            return self.get_whatsapp_sync_run(sync_run_id)
        except Exception as exc:
            if not self._is_missing_table_error(exc, "wa_sync_runs"):
                raise
            current = self._compat_sync_runs.get(sync_run_id)
            if current is None:
                return None
            updated = WhatsAppSyncRunRecord(
                id=current.id,
                user_id=current.user_id,
                trigger=current.trigger,
                status="failed",
                messages_seen_count=current.messages_seen_count,
                messages_saved_count=current.messages_saved_count,
                messages_ignored_count=current.messages_ignored_count,
                messages_pruned_count=current.messages_pruned_count,
                oldest_message_at=current.oldest_message_at,
                newest_message_at=current.newest_message_at,
                error_text=error_text,
                started_at=current.started_at,
                finished_at=finished_at,
                last_activity_at=finished_at,
            )
            self._compat_sync_runs[sync_run_id] = updated
            return updated

    def finalize_whatsapp_sync_run(self, *, user_id: UUID, sync_run_id: str, finished_at: datetime) -> WhatsAppSyncRunRecord | None:
        try:
            response = (
                self.client.table("wa_sync_runs")
                .select(
                    "id,user_id,trigger,status,messages_seen_count,messages_saved_count,messages_ignored_count,"
                    "messages_pruned_count,oldest_message_at,newest_message_at,error_text,started_at,finished_at,"
                    "last_activity_at,baseline_ingested_count,baseline_pruned_count"
                )
                .eq("user_id", str(user_id))
                .eq("id", sync_run_id)
                .limit(1)
                .execute()
            )
        except Exception as exc:
            if not self._is_missing_table_error(exc, "wa_sync_runs"):
                raise
            current = self._compat_sync_runs.get(sync_run_id)
            if current is None or current.user_id != user_id:
                return None
            if current.status != "running":
                return current
            retention_state = self.get_message_retention_state(user_id)
            last_activity = current.last_activity_at or current.started_at
            updated = WhatsAppSyncRunRecord(
                id=current.id,
                user_id=current.user_id,
                trigger=current.trigger,
                status="succeeded",
                messages_seen_count=current.messages_seen_count,
                messages_saved_count=max(current.messages_saved_count, retention_state.total_direct_ingested_count),
                messages_ignored_count=current.messages_ignored_count,
                messages_pruned_count=max(current.messages_pruned_count, retention_state.total_direct_pruned_count),
                oldest_message_at=current.oldest_message_at,
                newest_message_at=current.newest_message_at,
                error_text=current.error_text,
                started_at=current.started_at,
                finished_at=finished_at,
                last_activity_at=last_activity,
            )
            self._compat_sync_runs[sync_run_id] = updated
            return updated

        rows = response.data or []
        if not rows or not isinstance(rows[0], dict):
            return None
        row = rows[0]
        if str(row.get("status") or "") != "running":
            return self.get_whatsapp_sync_run(sync_run_id)

        retention_state = self.get_message_retention_state(user_id)
        baseline_ingested_count = self._parse_int(row.get("baseline_ingested_count")) or 0
        baseline_pruned_count = self._parse_int(row.get("baseline_pruned_count")) or 0
        saved_from_retention = max(0, retention_state.total_direct_ingested_count - baseline_ingested_count)
        pruned_from_retention = max(0, retention_state.total_direct_pruned_count - baseline_pruned_count)
        last_activity_at = self._parse_datetime(row.get("last_activity_at")) or self._parse_datetime(row.get("started_at")) or finished_at

        self.client.table("wa_sync_runs").update(
            {
                "status": "succeeded",
                "messages_saved_count": max(self._parse_int(row.get("messages_saved_count")) or 0, saved_from_retention),
                "messages_pruned_count": max(self._parse_int(row.get("messages_pruned_count")) or 0, pruned_from_retention),
                "finished_at": finished_at.isoformat(),
                "last_activity_at": last_activity_at.isoformat(),
            }
        ).eq("id", sync_run_id).execute()
        return self.get_whatsapp_sync_run(sync_run_id)

    def finalize_idle_sync_runs(self, *, user_id: UUID, idle_before: datetime) -> list[WhatsAppSyncRunRecord]:
        try:
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
        except Exception as exc:
            if not self._is_missing_table_error(exc, "wa_sync_runs"):
                raise
            finalized: list[WhatsAppSyncRunRecord] = []
            finished_at = datetime.now(UTC)
            retention_state = self.get_message_retention_state(user_id)
            for sync_run_id, current in list(self._compat_sync_runs.items()):
                if current.user_id != user_id or current.status != "running":
                    continue
                last_activity = current.last_activity_at or current.started_at
                if last_activity > idle_before:
                    continue
                updated = WhatsAppSyncRunRecord(
                    id=current.id,
                    user_id=current.user_id,
                    trigger=current.trigger,
                    status="succeeded",
                    messages_seen_count=current.messages_seen_count,
                    messages_saved_count=max(current.messages_saved_count, retention_state.total_direct_ingested_count),
                    messages_ignored_count=current.messages_ignored_count,
                    messages_pruned_count=max(current.messages_pruned_count, retention_state.total_direct_pruned_count),
                    oldest_message_at=current.oldest_message_at,
                    newest_message_at=current.newest_message_at,
                    error_text=current.error_text,
                    started_at=current.started_at,
                    finished_at=finished_at,
                    last_activity_at=last_activity,
                )
                self._compat_sync_runs[sync_run_id] = updated
                finalized.append(updated)
            return finalized
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
        try:
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
        except Exception as exc:
            if not self._is_missing_table_error(exc, "wa_sync_runs"):
                raise
            runs = [run for run in self._compat_sync_runs.values() if run.user_id == user_id]
            runs.sort(key=lambda run: run.started_at, reverse=True)
            return runs[:limit]
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
        try:
            self.client.table("automation_decisions").insert(record).execute()
        except Exception as exc:
            if not self._is_missing_table_error(exc, "automation_decisions"):
                raise
            compat_record = AutomationDecisionRecord(
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
            self._compat_decisions[decision_id] = compat_record
            return compat_record
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
        try:
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
        except Exception as exc:
            if not self._is_missing_table_error(exc, "automation_decisions"):
                raise
            decisions = [decision for decision in self._compat_decisions.values() if decision.user_id == user_id]
            decisions.sort(key=lambda decision: decision.created_at, reverse=True)
            return decisions[:limit]
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
        try:
            self.client.table("analysis_jobs").insert(record).execute()
        except Exception as exc:
            if not self._is_missing_table_error(exc, "analysis_jobs"):
                raise
            compat_job = AnalysisJobRecord(
                id=job_id,
                user_id=user_id,
                intent=intent,
                status=status,
                trigger_source=trigger_source,
                decision_id=decision_id,
                sync_run_id=sync_run_id,
                target_message_count=int(record["target_message_count"]),
                max_lookback_hours=int(record["max_lookback_hours"]),
                detail_mode=str(record["detail_mode"]),
                selected_message_count=int(record["selected_message_count"]),
                selected_transcript_chars=int(record["selected_transcript_chars"]),
                estimated_input_tokens=int(record["estimated_input_tokens"]),
                estimated_output_tokens=int(record["estimated_output_tokens"]),
                estimated_cost_floor_usd=float(record["estimated_cost_floor_usd"]),
                estimated_cost_ceiling_usd=float(record["estimated_cost_ceiling_usd"]),
                snapshot_id=snapshot_id,
                error_text=error_text,
                started_at=started_at,
                finished_at=finished_at,
                created_at=resolved_created_at,
            )
            self._compat_analysis_jobs[job_id] = compat_job
            return compat_job
        job = self.get_analysis_job(job_id)
        if job is None:
            raise RuntimeError("Analysis job could not be created.")
        return job

    def get_analysis_job(self, job_id: str) -> AnalysisJobRecord | None:
        try:
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
        except Exception as exc:
            if not self._is_missing_table_error(exc, "analysis_jobs"):
                raise
            return self._compat_analysis_jobs.get(job_id)
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
            try:
                self.client.table("analysis_jobs").update(payload).eq("id", job_id).execute()
            except Exception as exc:
                if not self._is_missing_table_error(exc, "analysis_jobs"):
                    raise
                current = self._compat_analysis_jobs.get(job_id)
                if current is None:
                    return None
                updated = AnalysisJobRecord(
                    id=current.id,
                    user_id=current.user_id,
                    intent=current.intent,
                    status=str(payload.get("status", current.status)),
                    trigger_source=current.trigger_source,
                    decision_id=str(payload.get("decision_id", current.decision_id)) if payload.get("decision_id", current.decision_id) is not None else None,
                    sync_run_id=str(payload.get("sync_run_id", current.sync_run_id)) if payload.get("sync_run_id", current.sync_run_id) is not None else None,
                    target_message_count=int(payload.get("target_message_count", current.target_message_count)),
                    max_lookback_hours=int(payload.get("max_lookback_hours", current.max_lookback_hours)),
                    detail_mode=str(payload.get("detail_mode", current.detail_mode)),
                    selected_message_count=int(payload.get("selected_message_count", current.selected_message_count)),
                    selected_transcript_chars=int(payload.get("selected_transcript_chars", current.selected_transcript_chars)),
                    estimated_input_tokens=int(payload.get("estimated_input_tokens", current.estimated_input_tokens)),
                    estimated_output_tokens=int(payload.get("estimated_output_tokens", current.estimated_output_tokens)),
                    estimated_cost_floor_usd=float(payload.get("estimated_cost_floor_usd", current.estimated_cost_floor_usd)),
                    estimated_cost_ceiling_usd=float(payload.get("estimated_cost_ceiling_usd", current.estimated_cost_ceiling_usd)),
                    snapshot_id=str(payload.get("snapshot_id", current.snapshot_id)) if payload.get("snapshot_id", current.snapshot_id) is not None else None,
                    error_text=str(payload.get("error_text", current.error_text)) if payload.get("error_text", current.error_text) is not None else None,
                    started_at=self._parse_datetime(payload.get("started_at")) or current.started_at,
                    finished_at=self._parse_datetime(payload.get("finished_at")) or current.finished_at,
                    created_at=current.created_at,
                )
                self._compat_analysis_jobs[job_id] = updated
                return updated
        return self.get_analysis_job(job_id)

    def claim_next_queued_analysis_job(self, *, user_id: UUID) -> AnalysisJobRecord | None:
        try:
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
        except Exception as exc:
            if not self._is_missing_table_error(exc, "analysis_jobs"):
                raise
            queued = [
                job for job in self._compat_analysis_jobs.values()
                if job.user_id == user_id and job.status == "queued"
            ]
            queued.sort(key=lambda job: job.created_at)
            if not queued:
                return None
            return self.update_analysis_job(
                job_id=queued[0].id,
                status="running",
                started_at=datetime.now(UTC),
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
        try:
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
        except Exception as exc:
            if not self._is_missing_table_error(exc, "analysis_jobs"):
                raise
            jobs = [job for job in self._compat_analysis_jobs.values() if job.user_id == user_id]
            jobs.sort(key=lambda job: job.created_at, reverse=True)
            return jobs[:limit]
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
        try:
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
        except Exception as exc:
            if not self._is_missing_table_error(exc, "analysis_jobs"):
                raise
            return sum(
                1
                for job in self._compat_analysis_jobs.values()
                if job.user_id == user_id
                and job.created_at >= since
                and (trigger_source is None or job.trigger_source == trigger_source)
            )

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
        try:
            self.client.table("analysis_job_messages").upsert(records, on_conflict="job_id,message_id").execute()
        except Exception as exc:
            if not self._is_missing_table_error(exc, "analysis_job_messages"):
                raise

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
        try:
            self.client.table("model_runs").insert(record).execute()
        except Exception as exc:
            if not self._is_missing_table_error(exc, "model_runs"):
                raise
            compat_run = ModelRunRecord(
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
            self._compat_model_runs[model_run_id] = compat_run
            return compat_run
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
        try:
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
        except Exception as exc:
            if not self._is_missing_table_error(exc, "model_runs"):
                raise
            runs = [run for run in self._compat_model_runs.values() if run.user_id == user_id]
            runs.sort(key=lambda run: run.created_at, reverse=True)
            return runs[:limit]
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
        try:
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
        except Exception as exc:
            if not self._is_missing_table_error(exc, "model_runs"):
                raise
            total = 0.0
            for run in self._compat_model_runs.values():
                if run.user_id != user_id or run.created_at < since:
                    continue
                total += run.estimated_cost_usd or 0.0
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
            "min_new_messages_threshold": 12,
            "stale_hours_threshold": 24,
            "pruned_messages_threshold": 1,
            "default_detail_mode": "balanced",
            "default_target_message_count": min(120, self.message_retention_max_rows),
            "default_lookback_hours": 72,
            "daily_budget_usd": 0.25,
            "max_auto_jobs_per_day": 4,
            "updated_at": updated_at.isoformat(),
        }

    def _default_whatsapp_agent_settings_record(self, *, user_id: UUID, updated_at: datetime) -> dict[str, Any]:
        return {
            "user_id": str(user_id),
            "auto_reply_enabled": False,
            "allowed_contact_phone": None,
            "updated_at": updated_at.isoformat(),
        }

    def _default_whatsapp_agent_settings(self, *, user_id: UUID) -> WhatsAppAgentSettingsRecord:
        parsed = self._parse_whatsapp_agent_settings(
            self._default_whatsapp_agent_settings_record(user_id=user_id, updated_at=datetime.now(UTC)),
            fallback_user_id=user_id,
        )
        if parsed is None:
            raise RuntimeError("Could not build default WhatsApp agent settings.")
        return parsed

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

    def _api_error_dict(self, exc: Exception) -> dict[str, Any]:
        if isinstance(exc, APIError) and exc.args:
            first = exc.args[0]
            if isinstance(first, dict):
                return first
        return {}

    def _api_error_message(self, exc: Exception) -> str:
        payload = self._api_error_dict(exc)
        message = payload.get("message")
        if isinstance(message, str) and message.strip():
            return message.strip().lower()
        return str(exc).strip().lower()

    def _api_error_code(self, exc: Exception) -> str:
        payload = self._api_error_dict(exc)
        code = payload.get("code")
        return str(code or "").strip().upper()

    def _is_missing_table_error(self, exc: Exception, table_name: str) -> bool:
        message = self._api_error_message(exc)
        code = self._api_error_code(exc)
        return code == "42P01" or f"relation {table_name.lower()}" in message or f"table {table_name.lower()}" in message

    def _is_missing_column_error(self, exc: Exception, *, column_name: str, table_name: str | None = None) -> bool:
        message = self._api_error_message(exc)
        code = self._api_error_code(exc)
        if code != "42703" and f"column {column_name.lower()}" not in message:
            return False
        if table_name is None:
            return True
        return table_name.lower() in message or "does not exist" in message

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

    def normalize_contact_phone(self, value: str | None) -> str | None:
        if value is None:
            return None
        digits = "".join(char for char in str(value) if char.isdigit())
        if len(digits) >= 12 and digits.startswith("55"):
            digits = digits[2:]
        if len(digits) > 11:
            digits = digits[-11:]
        if 8 <= len(digits) <= 11:
            return digits
        return None

    def build_phone_variants(self, value: str | None) -> set[str]:
        normalized = self.normalize_contact_phone(value)
        if not normalized:
            return set()

        digits = normalized
        variants = {digits}

        # Mirror the SaldoPro strategy for Brazilian WhatsApp numbers:
        # keep the DDD intact and only toggle the mobile "9" digit.
        if len(digits) == 11 and digits[2] == "9":
            variants.add(f"{digits[:2]}{digits[3:]}")
        elif len(digits) == 10:
            variants.add(f"{digits[:2]}9{digits[2:]}")
        elif len(digits) == 9 and digits[0] == "9":
            variants.add(digits[1:])
        elif len(digits) == 8:
            variants.add(f"9{digits}")

        return {variant for variant in variants if 8 <= len(variant) <= 11}

    def phone_matches(self, left: str | None, right: str | None) -> bool:
        left_variants = self.build_phone_variants(left)
        right_variants = self.build_phone_variants(right)
        if not left_variants or not right_variants:
            return False
        return bool(left_variants.intersection(right_variants))

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

    def _normalize_string_list(self, items: Sequence[Any], *, limit: int = 8) -> list[str]:
        return self._clean_and_unique_string_list(items, limit=limit)

    def _clean_and_unique_string_list(self, items: Sequence[Any], *, limit: int = 8) -> list[str]:
        cleaned: list[str] = []
        seen_normalized: set[str] = set()
        for item in items:
            if item is None:
                continue
            text = str(item).strip()
            normalized = text.casefold()
            if not text or normalized in seen_normalized:
                continue
            seen_normalized.add(normalized)
            cleaned.append(text)
            if len(cleaned) >= limit:
                break
        return cleaned

    def _merge_unique_string_lists(
        self,
        existing: Sequence[Any],
        incoming: Sequence[Any],
        *,
        limit: int = 8,
    ) -> list[str]:
        return self._clean_and_unique_string_list([*existing, *incoming], limit=limit)

    def _load_known_contact_names(self, contact_phones: Sequence[str | None]) -> dict[str, str]:
        cleaned_phones = sorted({phone.strip() for phone in contact_phones if phone and phone.strip()})
        if not cleaned_phones:
            return {}

        known_names: dict[str, str] = {}
        chunk_size = 100
        for start in range(0, len(cleaned_phones), chunk_size):
            chunk = cleaned_phones[start:start + chunk_size]
            rows: list[Any] = []
            try:
                response = (
                    self.client.table("whatsapp_known_contacts")
                    .select("contact_phone,contact_name,updated_at")
                    .in_("contact_phone", chunk)
                    .order("updated_at", desc=True)
                    .limit(max(200, len(chunk) * 6))
                    .execute()
                )
                rows.extend(response.data or [])
            except Exception as exc:
                if not self._is_missing_table_error(exc, "whatsapp_known_contacts"):
                    raise
            response = (
                self.client.table("mensagens")
                .select("contact_phone,contact_name,timestamp")
                .in_("contact_phone", chunk)
                .order("timestamp", desc=True)
                .limit(max(200, len(chunk) * 12))
                .execute()
            )
            rows.extend(response.data or [])
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
        return self.normalize_contact_phone(value) is not None

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

    def build_person_key(
        self,
        *,
        contact_phone: str | None,
        chat_jid: str | None,
        contact_name: str | None,
    ) -> str:
        phone = self._optional_text(contact_phone)
        if phone:
            phone_digits = "".join(char for char in phone if char.isdigit())
            if phone_digits:
                return f"phone:{phone_digits}"

        jid = self._optional_text(chat_jid)
        if jid:
            return f"jid:{jid.strip().lower()}"

        name = self._optional_text(contact_name)
        if name:
            normalized_chars = [
                char.lower() if char.isalnum() else "-"
                for char in name
            ]
            collapsed = "".join(normalized_chars)
            while "--" in collapsed:
                collapsed = collapsed.replace("--", "-")
            collapsed = collapsed.strip("-")
            if collapsed:
                return f"name:{collapsed}"
        return "person:unknown"

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

    def _fetch_processed_message_ids(self, message_ids: Sequence[str]) -> set[str]:
        cleaned_ids = [message_id.strip() for message_id in message_ids if message_id and message_id.strip()]
        if not cleaned_ids:
            return set()

        processed: set[str] = set()
        chunk_size = 500
        for start in range(0, len(cleaned_ids), chunk_size):
            chunk = cleaned_ids[start:start + chunk_size]
            try:
                response = self.client.table("processed_message_ids").select("message_id").in_("message_id", chunk).execute()
            except Exception as exc:
                if not self._is_missing_table_error(exc, "processed_message_ids"):
                    raise
                return set()
            rows = response.data or []
            processed.update(
                str(row.get("message_id") or "").strip()
                for row in rows
                if isinstance(row, dict) and str(row.get("message_id") or "").strip()
            )
        return processed

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

    def _parse_known_contact(self, value: Any, *, fallback_user_id: UUID) -> KnownContactRecord | None:
        if not isinstance(value, dict):
            return None
        contact_phone = self.normalize_contact_phone(self._optional_text(value.get("contact_phone")))
        if not contact_phone:
            return None
        return KnownContactRecord(
            id=str(value.get("id") or ""),
            user_id=self._parse_uuid(value.get("user_id")) or fallback_user_id,
            contact_phone=contact_phone,
            chat_jid=self._optional_text(value.get("chat_jid")),
            contact_name=self._resolve_contact_name(
                incoming_name=self._optional_text(value.get("contact_name")),
                contact_phone=contact_phone,
                known_name=self._optional_text(value.get("contact_name")),
            ),
            name_source=self._optional_text(value.get("name_source")) or "unknown",
            last_seen_at=self._parse_datetime(value.get("last_seen_at")),
            updated_at=self._parse_datetime(value.get("updated_at")) or datetime.now(UTC),
        )

    def _parse_whatsapp_agent_settings(self, value: Any, *, fallback_user_id: UUID) -> WhatsAppAgentSettingsRecord | None:
        if not isinstance(value, dict):
            return None
        return WhatsAppAgentSettingsRecord(
            user_id=self._parse_uuid(value.get("user_id")) or fallback_user_id,
            auto_reply_enabled=self._parse_bool(value.get("auto_reply_enabled")) if self._parse_bool(value.get("auto_reply_enabled")) is not None else False,
            allowed_contact_phone=self.normalize_contact_phone(self._optional_text(value.get("allowed_contact_phone"))),
            updated_at=self._parse_datetime(value.get("updated_at")) or datetime.now(UTC),
        )

    def _parse_whatsapp_agent_thread(self, value: Any, *, fallback_user_id: UUID) -> WhatsAppAgentThreadRecord | None:
        if not isinstance(value, dict):
            return None
        contact_name = self._resolve_contact_name(
            incoming_name=self._optional_text(value.get("contact_name")),
            contact_phone=self._optional_text(value.get("contact_phone")),
            known_name=self._optional_text(value.get("contact_name")),
        )
        return WhatsAppAgentThreadRecord(
            id=str(value.get("id") or ""),
            user_id=self._parse_uuid(value.get("user_id")) or fallback_user_id,
            contact_phone=self.normalize_contact_phone(self._optional_text(value.get("contact_phone"))),
            chat_jid=self._optional_text(value.get("chat_jid")),
            contact_name=contact_name,
            status=str(value.get("status") or "active").strip().lower() or "active",
            last_message_at=self._parse_datetime(value.get("last_message_at")),
            last_inbound_at=self._parse_datetime(value.get("last_inbound_at")),
            last_outbound_at=self._parse_datetime(value.get("last_outbound_at")),
            last_error_at=self._parse_datetime(value.get("last_error_at")),
            last_error_text=self._optional_text(value.get("last_error_text")),
            created_at=self._parse_datetime(value.get("created_at")) or datetime.now(UTC),
            updated_at=self._parse_datetime(value.get("updated_at")) or datetime.now(UTC),
        )

    def _parse_whatsapp_agent_thread_session(
        self,
        value: Any,
        *,
        fallback_user_id: UUID,
    ) -> WhatsAppAgentThreadSessionRecord | None:
        if not isinstance(value, dict):
            return None
        thread_id = self._optional_text(value.get("thread_id"))
        if not thread_id:
            return None
        return WhatsAppAgentThreadSessionRecord(
            id=str(value.get("id") or ""),
            user_id=self._parse_uuid(value.get("user_id")) or fallback_user_id,
            thread_id=thread_id,
            contact_phone=self.normalize_contact_phone(self._optional_text(value.get("contact_phone"))),
            chat_jid=self._optional_text(value.get("chat_jid")),
            started_at=self._parse_datetime(value.get("started_at")) or datetime.now(UTC),
            last_activity_at=self._parse_datetime(value.get("last_activity_at")) or datetime.now(UTC),
            ended_at=self._parse_datetime(value.get("ended_at")),
            reset_reason=self._optional_text(value.get("reset_reason")),
            created_at=self._parse_datetime(value.get("created_at")) or datetime.now(UTC),
            updated_at=self._parse_datetime(value.get("updated_at")) or datetime.now(UTC),
        )

    def _parse_whatsapp_agent_contact_memory(
        self,
        value: Any,
        *,
        fallback_user_id: UUID,
    ) -> WhatsAppAgentContactMemoryRecord | None:
        if not isinstance(value, dict):
            return None
        contact_phone = self.normalize_contact_phone(self._optional_text(value.get("contact_phone")))
        contact_name = self._resolve_contact_name(
            incoming_name=self._optional_text(value.get("contact_name")),
            contact_phone=contact_phone,
            known_name=self._optional_text(value.get("contact_name")),
        )
        return WhatsAppAgentContactMemoryRecord(
            id=str(value.get("id") or ""),
            user_id=self._parse_uuid(value.get("user_id")) or fallback_user_id,
            thread_id=self._optional_text(value.get("thread_id")),
            contact_phone=contact_phone,
            chat_jid=self._optional_text(value.get("chat_jid")),
            contact_name=contact_name,
            profile_summary=str(value.get("profile_summary") or "").strip(),
            preferred_tone=str(value.get("preferred_tone") or "").strip(),
            preferences=self._parse_string_list(value.get("preferences")),
            objectives=self._parse_string_list(value.get("objectives")),
            durable_facts=self._parse_string_list(value.get("durable_facts")),
            constraints=self._parse_string_list(value.get("constraints")),
            recurring_instructions=self._parse_string_list(value.get("recurring_instructions")),
            learned_message_count=max(0, self._parse_int(value.get("learned_message_count")) or 0),
            last_learned_at=self._parse_datetime(value.get("last_learned_at")),
            updated_at=self._parse_datetime(value.get("updated_at")) or datetime.now(UTC),
        )

    def _parse_whatsapp_agent_message(self, value: Any, *, fallback_user_id: UUID) -> WhatsAppAgentMessageRecord | None:
        if not isinstance(value, dict):
            return None
        role = str(value.get("role") or "").strip().lower()
        direction = str(value.get("direction") or "").strip().lower()
        content = self._optional_text(value.get("content"))
        thread_id = self._optional_text(value.get("thread_id"))
        if role not in {"user", "assistant"} or direction not in {"inbound", "outbound"} or not content or not thread_id:
            return None
        metadata = value.get("metadata")
        if not isinstance(metadata, dict):
            metadata = {}
        return WhatsAppAgentMessageRecord(
            id=str(value.get("id") or ""),
            user_id=self._parse_uuid(value.get("user_id")) or fallback_user_id,
            thread_id=thread_id,
            direction=direction,
            role=role,
            session_id=self._optional_text(value.get("session_id")),
            whatsapp_message_id=self._optional_text(value.get("whatsapp_message_id")),
            source_inbound_message_id=self._optional_text(value.get("source_inbound_message_id")),
            contact_phone=self.normalize_contact_phone(self._optional_text(value.get("contact_phone"))),
            chat_jid=self._optional_text(value.get("chat_jid")),
            content=content,
            message_timestamp=self._parse_datetime(value.get("message_timestamp")) or datetime.now(UTC),
            processing_status=str(value.get("processing_status") or "received").strip().lower() or "received",
            learning_status=str(value.get("learning_status") or "not_applicable").strip().lower() or "not_applicable",
            send_status=self._optional_text(value.get("send_status")),
            error_text=self._optional_text(value.get("error_text")),
            response_latency_ms=self._parse_int(value.get("response_latency_ms")),
            model_run_id=self._optional_text(value.get("model_run_id")),
            learned_at=self._parse_datetime(value.get("learned_at")),
            metadata=metadata,
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
            min_new_messages_threshold=self._parse_int(value.get("min_new_messages_threshold")) or 12,
            stale_hours_threshold=self._parse_int(value.get("stale_hours_threshold")) or 24,
            pruned_messages_threshold=self._parse_int(value.get("pruned_messages_threshold")) or 1,
            default_detail_mode=self._normalize_detail_mode(self._optional_text(value.get("default_detail_mode")) or "balanced"),
            default_target_message_count=self._parse_int(value.get("default_target_message_count")) or min(120, self.message_retention_max_rows),
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

    def _parse_important_message(self, value: Any, *, fallback_user_id: UUID) -> ImportantMessageRecord | None:
        if not isinstance(value, dict):
            return None
        message_text = self._optional_text(value.get("message_text"))
        source_message_id = self._optional_text(value.get("source_message_id"))
        if not message_text or not source_message_id:
            return None
        return ImportantMessageRecord(
            id=str(value.get("id") or ""),
            user_id=self._parse_uuid(value.get("user_id")) or fallback_user_id,
            source_message_id=source_message_id,
            contact_name=str(value.get("contact_name") or value.get("contact_phone") or "Contato"),
            contact_phone=self._optional_text(value.get("contact_phone")),
            direction=str(value.get("direction") or "inbound"),
            message_text=message_text,
            message_timestamp=self._parse_datetime(value.get("message_timestamp")) or datetime.now(UTC),
            category=self._normalize_importance_category(self._optional_text(value.get("category")) or "other"),
            importance_reason=str(value.get("importance_reason") or ""),
            confidence=max(0, min(100, self._parse_int(value.get("confidence")) or 0)),
            status=self._normalize_importance_status(self._optional_text(value.get("status")) or "active"),
            review_notes=self._optional_text(value.get("review_notes")),
            saved_at=self._parse_datetime(value.get("saved_at")) or datetime.now(UTC),
            last_reviewed_at=self._parse_datetime(value.get("last_reviewed_at")),
            discarded_at=self._parse_datetime(value.get("discarded_at")),
        )

    def _parse_person_memory(self, value: Any, *, fallback_user_id: UUID) -> PersonMemoryRecord | None:
        if not isinstance(value, dict):
            return None
        person_key = self._optional_text(value.get("person_key"))
        if not person_key:
            return None
        return PersonMemoryRecord(
            id=str(value.get("id") or ""),
            user_id=self._parse_uuid(value.get("user_id")) or fallback_user_id,
            person_key=person_key,
            contact_name=str(value.get("contact_name") or value.get("contact_phone") or "Contato"),
            contact_phone=self._optional_text(value.get("contact_phone")),
            chat_jid=self._optional_text(value.get("chat_jid")),
            profile_summary=str(value.get("profile_summary") or ""),
            relationship_summary=str(value.get("relationship_summary") or ""),
            salient_facts=self._parse_string_list(value.get("salient_facts")),
            open_loops=self._parse_string_list(value.get("open_loops")),
            recent_topics=self._parse_string_list(value.get("recent_topics")),
            source_snapshot_id=self._optional_text(value.get("source_snapshot_id")),
            source_message_count=self._parse_int(value.get("source_message_count")) or 0,
            last_message_at=self._parse_datetime(value.get("last_message_at")),
            last_analyzed_at=self._parse_datetime(value.get("last_analyzed_at")),
            updated_at=self._parse_datetime(value.get("updated_at")) or datetime.now(UTC),
        )

    def _normalize_detail_mode(self, value: str) -> str:
        normalized = value.strip().lower()
        if normalized in {"light", "balanced", "deep"}:
            return normalized
        return "balanced"

    def _normalize_importance_category(self, value: str) -> str:
        normalized = value.strip().lower()
        if normalized in {"credential", "access", "project", "money", "client", "deadline", "document", "risk", "other"}:
            return normalized
        return "other"

    def _normalize_importance_status(self, value: str) -> str:
        normalized = value.strip().lower()
        if normalized in {"active", "discarded"}:
            return normalized
        return "active"

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
