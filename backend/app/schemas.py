from __future__ import annotations

from datetime import datetime
from typing import Any, List, Literal, Optional

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


class ObserverMessageRefreshResponse(BaseModel):
    ok: bool = True
    refresh_started: bool = True
    status: ObserverStatusResponse
    message: str
    sync_run_id: str | None = None


class WhatsAppAgentStatusResponse(BaseModel):
    instance_name: str
    connected: bool
    state: str
    gateway_ready: bool
    auto_reply_enabled: bool
    reply_scope: Literal["all_direct_contacts"] = "all_direct_contacts"
    owner_number: str | None = None
    allowed_contact_phone: str | None = None
    qr_code: str | None = None
    qr_expires_in_sec: int | None = None
    last_seen_at: datetime | None = None
    last_error: str | None = None


class WhatsAppAgentSettingsResponse(BaseModel):
    user_id: str
    auto_reply_enabled: bool
    reply_scope: Literal["all_direct_contacts"] = "all_direct_contacts"
    allowed_contact_phone: str | None = None
    updated_at: datetime


class WhatsAppAgentSessionResponse(BaseModel):
    id: str
    thread_id: str
    contact_phone: str | None = None
    chat_jid: str | None = None
    started_at: datetime
    last_activity_at: datetime
    ended_at: datetime | None = None
    reset_reason: str | None = None
    created_at: datetime
    updated_at: datetime


class WhatsAppAgentContactMemoryResponse(BaseModel):
    id: str
    thread_id: str | None = None
    contact_name: str
    contact_phone: str | None = None
    chat_jid: str | None = None
    profile_summary: str
    preferred_tone: str = ""
    preferences: list[str] = Field(default_factory=list)
    objectives: list[str] = Field(default_factory=list)
    durable_facts: list[str] = Field(default_factory=list)
    constraints: list[str] = Field(default_factory=list)
    recurring_instructions: list[str] = Field(default_factory=list)
    learned_message_count: int = Field(default=0, ge=0)
    last_learned_at: datetime | None = None
    updated_at: datetime


class UpdateWhatsAppAgentSettingsRequest(BaseModel):
    auto_reply_enabled: bool | None = None


class WhatsAppAgentMessageResponse(BaseModel):
    id: str
    thread_id: str
    direction: Literal["inbound", "outbound"]
    role: Literal["user", "assistant"]
    session_id: str | None = None
    whatsapp_message_id: str | None = None
    source_inbound_message_id: str | None = None
    contact_phone: str | None = None
    chat_jid: str | None = None
    content: str
    message_timestamp: datetime
    processing_status: str
    learning_status: str = "not_applicable"
    send_status: str | None = None
    error_text: str | None = None
    response_latency_ms: int | None = None
    model_run_id: str | None = None
    learned_at: datetime | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime


class WhatsAppAgentThreadResponse(BaseModel):
    id: str
    contact_name: str
    contact_phone: str | None = None
    chat_jid: str | None = None
    status: str
    active_session_id: str | None = None
    session_started_at: datetime | None = None
    session_last_activity_at: datetime | None = None
    session_message_count: int = Field(default=0, ge=0)
    last_message_preview: str | None = None
    last_message_at: datetime | None = None
    last_inbound_at: datetime | None = None
    last_outbound_at: datetime | None = None
    last_error_at: datetime | None = None
    last_error_text: str | None = None
    created_at: datetime
    updated_at: datetime


class WhatsAppAgentThreadsListResponse(BaseModel):
    threads: list[WhatsAppAgentThreadResponse] = Field(default_factory=list)


class WhatsAppAgentMessagesListResponse(BaseModel):
    messages: list[WhatsAppAgentMessageResponse] = Field(default_factory=list)


class WhatsAppAgentWorkspaceResponse(BaseModel):
    status: WhatsAppAgentStatusResponse
    settings: WhatsAppAgentSettingsResponse
    observer_status: ObserverStatusResponse
    active_thread_id: str | None = None
    active_session: WhatsAppAgentSessionResponse | None = None
    contact_memory: WhatsAppAgentContactMemoryResponse | None = None
    threads: list[WhatsAppAgentThreadResponse] = Field(default_factory=list)
    messages: list[WhatsAppAgentMessageResponse] = Field(default_factory=list)


class IngestMessageRequestItem(BaseModel):
    model_config = ConfigDict(extra="ignore")

    message_id: str = Field(min_length=1)
    chat_type: Literal["direct", "group"] = "direct"
    chat_name: str | None = None
    direction: Literal["inbound", "outbound"]
    contact_name: str | None = None
    contact_name_source: str | None = None
    chat_jid: str = Field(min_length=1)
    contact_phone: str | None = None
    participant_name: str | None = None
    participant_phone: str | None = None
    participant_jid: str | None = None
    message_text: str = Field(min_length=1)
    timestamp: datetime
    source: str = Field(default="baileys", min_length=1)
    source_event: str | None = None


class IngestMessagesRequest(BaseModel):
    messages: list[IngestMessageRequestItem] = Field(default_factory=list)


class IngestMessagesResponse(BaseModel):
    ok: bool = True
    accepted_count: int = Field(default=0, ge=0)
    ignored_count: int = Field(default=0, ge=0)


class GroupMetadataUpdateRequestItem(BaseModel):
    model_config = ConfigDict(extra="ignore")

    chat_jid: str = Field(min_length=1)
    chat_name: str = Field(min_length=1)
    seen_at: datetime | None = None


class GroupMetadataUpdateRequest(BaseModel):
    groups: list[GroupMetadataUpdateRequestItem] = Field(default_factory=list)


class WhatsAppAgentInboundMessageRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    message_id: str = Field(min_length=1)
    direction: Literal["inbound", "outbound"] = "inbound"
    from_me: bool = False
    contact_name: str | None = None
    contact_name_source: str | None = None
    chat_jid: str = Field(min_length=1)
    contact_phone: str = Field(min_length=1)
    message_text: str = Field(min_length=1)
    timestamp: datetime
    source: str = Field(default="baileys", min_length=1)
    source_event: str | None = None


class WhatsAppAgentInboundMessagesRequest(BaseModel):
    messages: list[WhatsAppAgentInboundMessageRequest] = Field(default_factory=list)


class WhatsAppAgentInboundMessageResponse(BaseModel):
    ok: bool = True
    action: str
    thread_id: str | None = None
    inbound_message_id: str | None = None
    outbound_message_id: str | None = None


class WhatsAppAgentInboundMessagesResponse(BaseModel):
    ok: bool = True
    accepted_count: int = Field(default=0, ge=0)
    ignored_count: int = Field(default=0, ge=0)


class WhatsAppSessionCredsResponse(BaseModel):
    creds: Any | None = None


class WhatsAppSessionCredsUpsertRequest(BaseModel):
    creds: Any


class WhatsAppSessionKeysLoadRequest(BaseModel):
    category: str = Field(min_length=1)
    ids: list[str] = Field(default_factory=list)


class WhatsAppSessionKeysLoadResponse(BaseModel):
    values: dict[str, Any] = Field(default_factory=dict)


class WhatsAppSessionKeysUpsertRequest(BaseModel):
    category: str = Field(min_length=1)
    values: dict[str, Any] = Field(default_factory=dict)


class WhatsAppSessionKeysDeleteRequest(BaseModel):
    category: str = Field(min_length=1)
    ids: list[str] = Field(default_factory=list)


class SimpleOkResponse(BaseModel):
    ok: bool = True


class AnalyzeMemoryRequest(BaseModel):
    intent: Literal["first_analysis", "improve_memory"] | None = None
    window_hours: int | None = Field(default=None, ge=1)
    target_message_count: int | None = Field(default=None, ge=20, le=500)
    max_lookback_hours: int | None = Field(default=None, ge=1, le=336)
    detail_mode: Literal["light", "balanced", "deep"] = "balanced"


class MemoryAnalysisPreviewResponse(BaseModel):
    target_message_count: int = Field(ge=1)
    max_lookback_hours: int = Field(ge=1)
    detail_mode: Literal["light", "balanced", "deep"]
    deepseek_model: str
    available_message_count: int = Field(ge=0)
    selected_message_count: int = Field(ge=0)
    new_message_count: int = Field(ge=0)
    replaced_message_count: int = Field(ge=0)
    retained_message_count: int = Field(ge=0)
    retention_limit: int = Field(ge=1)
    current_char_budget: int = Field(ge=1)
    selected_transcript_chars: int = Field(ge=0)
    selected_transcript_tokens: int = Field(ge=0)
    average_selected_message_chars: int = Field(ge=0)
    average_selected_message_tokens: int = Field(ge=0)
    estimated_prompt_context_tokens: int = Field(ge=0)
    model_context_limit_floor_tokens: int = Field(ge=1)
    model_context_limit_ceiling_tokens: int = Field(ge=1)
    safe_input_budget_floor_tokens: int = Field(ge=0)
    safe_input_budget_ceiling_tokens: int = Field(ge=0)
    remaining_input_headroom_floor_tokens: int = Field(ge=0)
    remaining_input_headroom_ceiling_tokens: int = Field(ge=0)
    model_default_output_tokens: int = Field(ge=0)
    model_max_output_tokens: int = Field(ge=0)
    request_output_reserve_tokens: int = Field(ge=0)
    estimated_reasoning_tokens: int = Field(ge=0)
    planner_message_capacity: int = Field(ge=0)
    stack_max_message_capacity: int = Field(ge=0)
    model_message_capacity_floor: int = Field(ge=0)
    model_message_capacity_ceiling: int = Field(ge=0)
    estimated_input_tokens: int = Field(ge=0)
    estimated_output_tokens: int = Field(ge=0)
    estimated_total_tokens: int = Field(ge=0)
    estimated_cost_input_floor_usd: float = Field(ge=0)
    estimated_cost_input_ceiling_usd: float = Field(ge=0)
    estimated_cost_output_floor_usd: float = Field(ge=0)
    estimated_cost_output_ceiling_usd: float = Field(ge=0)
    estimated_cost_total_floor_usd: float = Field(ge=0)
    estimated_cost_total_ceiling_usd: float = Field(ge=0)
    documentation_context_note: str
    documentation_pricing_note: str
    recommendation_score: int = Field(ge=0, le=100)
    recommendation_label: str
    recommendation_summary: str
    should_analyze: bool


class MemoryCurrentResponse(BaseModel):
    user_id: str
    life_summary: str = ""
    last_analyzed_at: datetime | None = None
    last_snapshot_id: str | None = None
    structural_strengths: list[str] = Field(default_factory=list)
    structural_routines: list[str] = Field(default_factory=list)
    structural_preferences: list[str] = Field(default_factory=list)
    structural_open_questions: list[str] = Field(default_factory=list)


class MemoryStatusResponse(BaseModel):
    has_initial_analysis: bool
    last_analyzed_at: datetime | None = None
    new_messages_after_first_analysis: int = Field(ge=0)
    current_job: "AnalysisJobResponse | None" = None
    latest_completed_job: "AnalysisJobResponse | None" = None
    can_execute_analysis: bool


class WhatsAppGroupSelectionResponse(BaseModel):
    chat_jid: str
    chat_name: str
    enabled_for_analysis: bool
    last_seen_at: datetime | None = None
    last_message_at: datetime | None = None
    message_count: int = Field(ge=0)
    pending_message_count: int = Field(ge=0)


class WhatsAppGroupSelectionsListResponse(BaseModel):
    groups: list[WhatsAppGroupSelectionResponse] = Field(default_factory=list)


class UpdateWhatsAppGroupSelectionRequest(BaseModel):
    enabled_for_analysis: bool


class MemorySnapshotResponse(BaseModel):
    id: str
    window_hours: int = Field(ge=1)
    window_start: datetime
    window_end: datetime
    source_message_count: int = Field(ge=0)
    distinct_contact_count: int = Field(ge=0)
    inbound_message_count: int = Field(ge=0)
    outbound_message_count: int = Field(ge=0)
    coverage_score: int = Field(ge=0, le=100)
    window_summary: str
    key_learnings: list[str] = Field(default_factory=list)
    people_and_relationships: list[str] = Field(default_factory=list)
    routine_signals: list[str] = Field(default_factory=list)
    preferences: list[str] = Field(default_factory=list)
    open_questions: list[str] = Field(default_factory=list)
    created_at: datetime


class ProjectMemoryResponse(BaseModel):
    id: str
    project_key: str
    project_name: str
    summary: str
    status: str = ""
    what_is_being_built: str = ""
    built_for: str = ""
    next_steps: list[str] = Field(default_factory=list)
    evidence: list[str] = Field(default_factory=list)
    source_snapshot_id: str | None = None
    last_seen_at: datetime | None = None
    updated_at: datetime


class ImportantMessageResponse(BaseModel):
    id: str
    source_message_id: str
    contact_name: str
    contact_phone: str | None = None
    direction: Literal["inbound", "outbound"]
    message_text: str
    message_timestamp: datetime
    category: str
    importance_reason: str
    confidence: int = Field(ge=0, le=100)
    status: str
    review_notes: str | None = None
    saved_at: datetime
    last_reviewed_at: datetime | None = None
    discarded_at: datetime | None = None


class ImportantMessagesListResponse(BaseModel):
    messages: list[ImportantMessageResponse] = Field(default_factory=list)


class AnalyzeMemoryResponse(BaseModel):
    current: MemoryCurrentResponse
    snapshot: MemorySnapshotResponse | None = None
    projects: list[ProjectMemoryResponse] = Field(default_factory=list)
    job: "AnalysisJobResponse | None" = None


class RefineMemoryResponse(BaseModel):
    current: MemoryCurrentResponse
    projects: list[ProjectMemoryResponse] = Field(default_factory=list)
    job: "AnalysisJobResponse | None" = None


class MemorySnapshotsListResponse(BaseModel):
    snapshots: list[MemorySnapshotResponse] = Field(default_factory=list)


class ChatMessageResponse(BaseModel):
    id: str
    role: Literal["user", "assistant"]
    content: str
    created_at: datetime


class ChatThreadResponse(BaseModel):
    id: str
    thread_key: str
    title: str
    message_count: int = Field(ge=0)
    last_message_preview: str | None = None
    last_message_role: Literal["user", "assistant"] | None = None
    last_message_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class ChatSessionResponse(BaseModel):
    thread_id: str
    title: str
    current: MemoryCurrentResponse
    projects: list[ProjectMemoryResponse] = Field(default_factory=list)
    messages: list[ChatMessageResponse] = Field(default_factory=list)


class ChatWorkspaceResponse(BaseModel):
    active_thread_id: str
    threads: list[ChatThreadResponse] = Field(default_factory=list)
    session: ChatSessionResponse


class SendChatMessageRequest(BaseModel):
    thread_id: str | None = None
    message_text: str = Field(min_length=1, max_length=4000)
    context_hint: str | None = Field(default=None, max_length=2000)


class CreateChatThreadRequest(BaseModel):
    title: str | None = Field(default=None, max_length=80)


class AutomationSettingsResponse(BaseModel):
    user_id: str
    auto_sync_enabled: bool
    auto_analyze_enabled: bool
    auto_refine_enabled: bool
    min_new_messages_threshold: int = Field(ge=1)
    stale_hours_threshold: int = Field(ge=1)
    pruned_messages_threshold: int = Field(ge=0)
    default_detail_mode: Literal["light", "balanced", "deep"]
    default_target_message_count: int = Field(ge=20)
    default_lookback_hours: int = Field(ge=1)
    daily_budget_usd: float = Field(ge=0)
    max_auto_jobs_per_day: int = Field(ge=1)
    updated_at: datetime


class UpdateAutomationSettingsRequest(BaseModel):
    auto_sync_enabled: bool | None = None
    auto_analyze_enabled: bool | None = None
    auto_refine_enabled: bool | None = None
    min_new_messages_threshold: int | None = Field(default=None, ge=1, le=500)
    stale_hours_threshold: int | None = Field(default=None, ge=1, le=336)
    pruned_messages_threshold: int | None = Field(default=None, ge=0, le=500)
    default_detail_mode: Literal["light", "balanced", "deep"] | None = None
    default_target_message_count: int | None = Field(default=None, ge=20, le=500)
    default_lookback_hours: int | None = Field(default=None, ge=1, le=336)
    daily_budget_usd: float | None = Field(default=None, ge=0, le=50)
    max_auto_jobs_per_day: int | None = Field(default=None, ge=1, le=100)


class WhatsAppSyncRunResponse(BaseModel):
    id: str
    trigger: str
    status: str
    messages_seen_count: int = Field(ge=0)
    messages_saved_count: int = Field(ge=0)
    messages_ignored_count: int = Field(ge=0)
    messages_pruned_count: int = Field(ge=0)
    oldest_message_at: datetime | None = None
    newest_message_at: datetime | None = None
    error_text: str | None = None
    started_at: datetime
    finished_at: datetime | None = None
    last_activity_at: datetime | None = None


class AutomationDecisionResponse(BaseModel):
    id: str
    sync_run_id: str | None = None
    intent: str
    action: str
    reason_code: str
    score: int = Field(ge=0, le=100)
    should_analyze: bool
    available_message_count: int = Field(ge=0)
    selected_message_count: int = Field(ge=0)
    new_message_count: int = Field(ge=0)
    replaced_message_count: int = Field(ge=0)
    estimated_total_tokens: int = Field(ge=0)
    estimated_cost_ceiling_usd: float = Field(ge=0)
    explanation: str
    created_at: datetime


class AnalysisJobResponse(BaseModel):
    id: str
    intent: str
    status: str
    trigger_source: str
    decision_id: str | None = None
    sync_run_id: str | None = None
    target_message_count: int = Field(ge=0)
    max_lookback_hours: int = Field(ge=0)
    detail_mode: str
    selected_message_count: int = Field(ge=0)
    selected_transcript_chars: int = Field(ge=0)
    estimated_input_tokens: int = Field(ge=0)
    estimated_output_tokens: int = Field(ge=0)
    estimated_cost_floor_usd: float = Field(ge=0)
    estimated_cost_ceiling_usd: float = Field(ge=0)
    snapshot_id: str | None = None
    error_text: str | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None
    created_at: datetime


class MemoryActivityResponse(BaseModel):
    sync_runs: list["WhatsAppSyncRunResponse"] = Field(default_factory=list)
    jobs: list[AnalysisJobResponse] = Field(default_factory=list)
    model_runs: list["ModelRunResponse"] = Field(default_factory=list)
    running_job_id: str | None = None
    decisions: list["AutomationDecisionResponse"] = Field(default_factory=list)
    queued_jobs_count: int = Field(default=0, ge=0)
    daily_auto_jobs_count: int = Field(default=0, ge=0)
    settings: "AutomationSettingsResponse | None" = None


class ModelRunResponse(BaseModel):
    id: str
    job_id: str | None = None
    provider: str
    model_name: str
    run_type: str
    success: bool
    latency_ms: int | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    reasoning_tokens: int | None = None
    estimated_cost_usd: float | None = None
    error_text: str | None = None
    created_at: datetime


class AutomationJobsListResponse(BaseModel):
    jobs: list[AnalysisJobResponse] = Field(default_factory=list)


class AutomationDecisionsListResponse(BaseModel):
    decisions: list[AutomationDecisionResponse] = Field(default_factory=list)


class AutomationStatusResponse(BaseModel):
    settings: AutomationSettingsResponse
    sync_runs: list[WhatsAppSyncRunResponse] = Field(default_factory=list)
    decisions: list[AutomationDecisionResponse] = Field(default_factory=list)
    jobs: list[AnalysisJobResponse] = Field(default_factory=list)
    model_runs: list[ModelRunResponse] = Field(default_factory=list)
    daily_cost_usd: float = Field(ge=0)
    daily_auto_jobs_count: int = Field(ge=0)
    queued_jobs_count: int = Field(ge=0)
    running_job_id: str | None = None


AnalyzeMemoryResponse.model_rebuild()
RefineMemoryResponse.model_rebuild()
