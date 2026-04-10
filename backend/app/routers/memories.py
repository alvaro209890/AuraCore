from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Body, Depends, Query

from app.dependencies import get_memory_analysis_service, get_memory_job_service
from app.schemas import (
    AnalysisJobResponse,
    AnalyzeMemoryRequest,
    AnalyzeMemoryResponse,
    ImportantMessageResponse,
    ImportantMessagesListResponse,
    MemoryActivityResponse,
    MemoryAnalysisPreviewResponse,
    MemoryCurrentResponse,
    MemorySnapshotResponse,
    MemorySnapshotsListResponse,
    MemoryStatusResponse,
    ModelRunResponse,
    ProjectMemoryResponse,
    WhatsAppSyncRunResponse,
)
from app.services.memory_job_service import MemoryActivitySnapshot, MemoryJobService
from app.services.memory_service import MemoryAnalysisService
from app.services.supabase_store import (
    AnalysisJobRecord,
    ImportantMessageRecord,
    MemorySnapshotRecord,
    ModelRunRecord,
    PersonaRecord,
    ProjectMemoryRecord,
    WhatsAppSyncRunRecord,
)

router = APIRouter(prefix="/api/memories", tags=["memories"])


@router.get("/current", response_model=MemoryCurrentResponse)
async def get_current_memory(
    memory_service: MemoryAnalysisService = Depends(get_memory_analysis_service),
) -> MemoryCurrentResponse:
    return _to_persona_response(memory_service.get_current_persona())


@router.get("/status", response_model=MemoryStatusResponse)
async def get_memory_status(
    memory_service: MemoryAnalysisService = Depends(get_memory_analysis_service),
    memory_job_service: MemoryJobService = Depends(get_memory_job_service),
) -> MemoryStatusResponse:
    status = memory_service.get_memory_status()
    activity = await memory_job_service.get_activity_snapshot()
    current_job, latest_completed_job = _resolve_job_refs(activity.jobs)
    return MemoryStatusResponse(
        has_initial_analysis=status.has_initial_analysis,
        last_analyzed_at=status.last_analyzed_at,
        new_messages_after_first_analysis=status.new_messages_after_first_analysis,
        current_job=_to_job_response(current_job),
        latest_completed_job=_to_job_response(latest_completed_job),
        can_execute_analysis=current_job is None and status.can_run_next_batch,
    )


@router.get("/activity", response_model=MemoryActivityResponse)
async def get_memory_activity(
    memory_job_service: MemoryJobService = Depends(get_memory_job_service),
) -> MemoryActivityResponse:
    activity = await memory_job_service.get_activity_snapshot()
    return _to_activity_response(activity)


@router.get("/snapshots", response_model=MemorySnapshotsListResponse)
async def get_memory_snapshots(
    limit: int = Query(default=20, ge=1, le=100),
    memory_service: MemoryAnalysisService = Depends(get_memory_analysis_service),
) -> MemorySnapshotsListResponse:
    snapshots = memory_service.list_snapshots(limit=limit)
    return MemorySnapshotsListResponse(snapshots=[_to_snapshot_response(snapshot) for snapshot in snapshots])


@router.get("/important", response_model=ImportantMessagesListResponse)
async def get_important_messages(
    limit: int = Query(default=80, ge=1, le=200),
    memory_service: MemoryAnalysisService = Depends(get_memory_analysis_service),
) -> ImportantMessagesListResponse:
    messages = memory_service.list_important_messages(limit=limit)
    return ImportantMessagesListResponse(messages=[_to_important_message_response(message) for message in messages])


@router.post("/execute", response_model=AnalyzeMemoryResponse)
async def execute_memory_analysis(
    request: AnalyzeMemoryRequest | None = Body(default=None),
    memory_job_service: MemoryJobService = Depends(get_memory_job_service),
    memory_service: MemoryAnalysisService = Depends(get_memory_analysis_service),
) -> AnalyzeMemoryResponse:
    job = await memory_job_service.execute_manual_analysis(intent=request.intent if request else None)
    return _build_analyze_memory_response(memory_service=memory_service, job=job)


@router.post("/analyze", response_model=AnalyzeMemoryResponse)
async def analyze_memory_alias(
    request: AnalyzeMemoryRequest | None = Body(default=None),
    memory_job_service: MemoryJobService = Depends(get_memory_job_service),
    memory_service: MemoryAnalysisService = Depends(get_memory_analysis_service),
) -> AnalyzeMemoryResponse:
    job = await memory_job_service.execute_manual_analysis(intent=request.intent if request else None)
    return _build_analyze_memory_response(memory_service=memory_service, job=job)


@router.post("/first-analysis", response_model=AnalyzeMemoryResponse)
async def run_first_memory_analysis(
    memory_job_service: MemoryJobService = Depends(get_memory_job_service),
    memory_service: MemoryAnalysisService = Depends(get_memory_analysis_service),
) -> AnalyzeMemoryResponse:
    job = await memory_job_service.execute_manual_analysis(intent="first_analysis")
    return _build_analyze_memory_response(memory_service=memory_service, job=job)


@router.post("/process-next-batch", response_model=AnalyzeMemoryResponse)
async def run_next_memory_batch(
    memory_job_service: MemoryJobService = Depends(get_memory_job_service),
    memory_service: MemoryAnalysisService = Depends(get_memory_analysis_service),
) -> AnalyzeMemoryResponse:
    job = await memory_job_service.execute_manual_analysis(intent="improve_memory")
    return _build_analyze_memory_response(memory_service=memory_service, job=job)


@router.post("/preview", response_model=MemoryAnalysisPreviewResponse)
async def preview_memory_analysis(
    request: AnalyzeMemoryRequest = Body(...),
    memory_service: MemoryAnalysisService = Depends(get_memory_analysis_service),
) -> MemoryAnalysisPreviewResponse:
    preview = await memory_service.get_analysis_preview(
        target_message_count=request.target_message_count or 120,
        max_lookback_hours=request.max_lookback_hours or 72,
        detail_mode=request.detail_mode,
    )
    return MemoryAnalysisPreviewResponse(
        target_message_count=preview.target_message_count,
        max_lookback_hours=preview.max_lookback_hours,
        detail_mode=preview.detail_mode,
        deepseek_model=preview.deepseek_model,
        available_message_count=preview.available_message_count,
        selected_message_count=preview.selected_message_count,
        new_message_count=preview.new_message_count,
        replaced_message_count=preview.replaced_message_count,
        retained_message_count=preview.retained_message_count,
        retention_limit=preview.retention_limit,
        current_char_budget=preview.current_char_budget,
        selected_transcript_chars=preview.selected_transcript_chars,
        selected_transcript_tokens=preview.selected_transcript_tokens,
        average_selected_message_chars=preview.average_selected_message_chars,
        average_selected_message_tokens=preview.average_selected_message_tokens,
        estimated_prompt_context_tokens=preview.estimated_prompt_context_tokens,
        model_context_limit_floor_tokens=preview.model_context_limit_floor_tokens,
        model_context_limit_ceiling_tokens=preview.model_context_limit_ceiling_tokens,
        safe_input_budget_floor_tokens=preview.safe_input_budget_floor_tokens,
        safe_input_budget_ceiling_tokens=preview.safe_input_budget_ceiling_tokens,
        remaining_input_headroom_floor_tokens=preview.remaining_input_headroom_floor_tokens,
        remaining_input_headroom_ceiling_tokens=preview.remaining_input_headroom_ceiling_tokens,
        model_default_output_tokens=preview.model_default_output_tokens,
        model_max_output_tokens=preview.model_max_output_tokens,
        request_output_reserve_tokens=preview.request_output_reserve_tokens,
        estimated_reasoning_tokens=preview.estimated_reasoning_tokens,
        planner_message_capacity=preview.planner_message_capacity,
        stack_max_message_capacity=preview.stack_max_message_capacity,
        model_message_capacity_floor=preview.model_message_capacity_floor,
        model_message_capacity_ceiling=preview.model_message_capacity_ceiling,
        estimated_input_tokens=preview.estimated_input_tokens,
        estimated_output_tokens=preview.estimated_output_tokens,
        estimated_total_tokens=preview.estimated_total_tokens,
        estimated_cost_input_floor_usd=preview.estimated_cost_input_floor_usd,
        estimated_cost_input_ceiling_usd=preview.estimated_cost_input_ceiling_usd,
        estimated_cost_output_floor_usd=preview.estimated_cost_output_floor_usd,
        estimated_cost_output_ceiling_usd=preview.estimated_cost_output_ceiling_usd,
        estimated_cost_total_floor_usd=preview.estimated_cost_total_floor_usd,
        estimated_cost_total_ceiling_usd=preview.estimated_cost_total_ceiling_usd,
        documentation_context_note=preview.documentation_context_note,
        documentation_pricing_note=preview.documentation_pricing_note,
        recommendation_score=preview.recommendation_score,
        recommendation_label=preview.recommendation_label,
        recommendation_summary=preview.recommendation_summary,
        should_analyze=preview.should_analyze,
    )


@router.get("/projects", response_model=list[ProjectMemoryResponse])
async def get_memory_projects(
    memory_service: MemoryAnalysisService = Depends(get_memory_analysis_service),
) -> list[ProjectMemoryResponse]:
    return [_to_project_response(project) for project in memory_service.list_projects()]


def _build_analyze_memory_response(
    *,
    memory_service: MemoryAnalysisService,
    job: AnalysisJobRecord | None,
) -> AnalyzeMemoryResponse:
    current = memory_service.get_current_persona()
    snapshots = memory_service.list_snapshots(limit=1)
    snapshot = snapshots[0] if snapshots else None
    return AnalyzeMemoryResponse(
        current=_to_persona_response(current),
        snapshot=_to_snapshot_response(snapshot) if snapshot else None,
        projects=[_to_project_response(project) for project in memory_service.list_projects()],
        job=_to_job_response(job),
    )


def _resolve_job_refs(jobs: list[AnalysisJobRecord]) -> tuple[AnalysisJobRecord | None, AnalysisJobRecord | None]:
    current_job = next((job for job in jobs if job.status in {"queued", "running"}), None)
    latest_completed_job = next((job for job in jobs if job.status in {"succeeded", "failed"}), None)
    return current_job, latest_completed_job


def _to_activity_response(activity: MemoryActivitySnapshot) -> MemoryActivityResponse:
    queued_jobs_count = sum(1 for job in activity.jobs if job.status == "queued")
    return MemoryActivityResponse(
        sync_runs=[_to_sync_run_response(sync_run) for sync_run in activity.sync_runs],
        jobs=[_to_job_response(job) for job in activity.jobs if _to_job_response(job) is not None],
        model_runs=[_to_model_run_response(model_run) for model_run in activity.model_runs],
        running_job_id=activity.running_job_id,
        decisions=[],
        queued_jobs_count=queued_jobs_count,
        daily_auto_jobs_count=0,
        settings=None,
    )


def _to_persona_response(persona: PersonaRecord) -> MemoryCurrentResponse:
    return MemoryCurrentResponse(
        user_id=str(persona.user_id),
        life_summary=persona.life_summary,
        last_analyzed_at=persona.last_analyzed_at,
        last_snapshot_id=persona.last_snapshot_id,
        structural_strengths=persona.structural_strengths,
        structural_routines=persona.structural_routines,
        structural_preferences=persona.structural_preferences,
        structural_open_questions=persona.structural_open_questions,
    )


def _to_snapshot_response(snapshot: MemorySnapshotRecord) -> MemorySnapshotResponse:
    return MemorySnapshotResponse(
        id=snapshot.id,
        window_hours=snapshot.window_hours,
        window_start=snapshot.window_start,
        window_end=snapshot.window_end,
        source_message_count=snapshot.source_message_count,
        window_summary=snapshot.window_summary,
        key_learnings=snapshot.key_learnings,
        people_and_relationships=snapshot.people_and_relationships,
        routine_signals=snapshot.routine_signals,
        preferences=snapshot.preferences,
        open_questions=snapshot.open_questions,
        created_at=snapshot.created_at,
    )


def _to_project_response(project: ProjectMemoryRecord) -> ProjectMemoryResponse:
    return ProjectMemoryResponse(
        id=project.id,
        project_key=project.project_key,
        project_name=project.project_name,
        summary=project.summary,
        status=project.status,
        what_is_being_built=project.what_is_being_built,
        built_for=project.built_for,
        next_steps=project.next_steps,
        evidence=project.evidence,
        source_snapshot_id=project.source_snapshot_id,
        last_seen_at=project.last_seen_at,
        updated_at=project.updated_at,
    )


def _to_important_message_response(message: ImportantMessageRecord) -> ImportantMessageResponse:
    direction = "outbound" if message.direction == "outbound" else "inbound"
    return ImportantMessageResponse(
        id=message.id,
        source_message_id=message.source_message_id,
        contact_name=message.contact_name,
        contact_phone=message.contact_phone,
        direction=direction,
        message_text=message.message_text,
        message_timestamp=message.message_timestamp,
        category=message.category,
        importance_reason=message.importance_reason,
        confidence=message.confidence,
        status=message.status,
        review_notes=message.review_notes,
        saved_at=message.saved_at,
        last_reviewed_at=message.last_reviewed_at,
        discarded_at=message.discarded_at,
    )


def _to_sync_run_response(sync_run: WhatsAppSyncRunRecord) -> WhatsAppSyncRunResponse:
    return WhatsAppSyncRunResponse(
        id=sync_run.id,
        trigger=sync_run.trigger,
        status=sync_run.status,
        messages_seen_count=sync_run.messages_seen_count,
        messages_saved_count=sync_run.messages_saved_count,
        messages_ignored_count=sync_run.messages_ignored_count,
        messages_pruned_count=sync_run.messages_pruned_count,
        oldest_message_at=sync_run.oldest_message_at,
        newest_message_at=sync_run.newest_message_at,
        error_text=sync_run.error_text,
        started_at=sync_run.started_at,
        finished_at=sync_run.finished_at,
        last_activity_at=sync_run.last_activity_at,
    )


def _to_model_run_response(model_run: ModelRunRecord) -> ModelRunResponse:
    return ModelRunResponse(
        id=model_run.id,
        job_id=model_run.job_id,
        provider=model_run.provider,
        model_name=model_run.model_name,
        run_type=model_run.run_type,
        success=model_run.success,
        latency_ms=model_run.latency_ms,
        input_tokens=model_run.input_tokens,
        output_tokens=model_run.output_tokens,
        reasoning_tokens=model_run.reasoning_tokens,
        estimated_cost_usd=model_run.estimated_cost_usd,
        error_text=model_run.error_text,
        created_at=model_run.created_at,
    )


def _to_job_response(job: Any) -> AnalysisJobResponse | None:
    if job is None:
        return None
    return AnalysisJobResponse(
        id=job.id,
        intent=job.intent,
        status=job.status,
        trigger_source=job.trigger_source,
        decision_id=job.decision_id,
        sync_run_id=job.sync_run_id,
        target_message_count=job.target_message_count,
        max_lookback_hours=job.max_lookback_hours,
        detail_mode=job.detail_mode,
        selected_message_count=job.selected_message_count,
        selected_transcript_chars=job.selected_transcript_chars,
        estimated_input_tokens=job.estimated_input_tokens,
        estimated_output_tokens=job.estimated_output_tokens,
        estimated_cost_floor_usd=job.estimated_cost_floor_usd,
        estimated_cost_ceiling_usd=job.estimated_cost_ceiling_usd,
        snapshot_id=job.snapshot_id,
        error_text=job.error_text,
        started_at=job.started_at,
        finished_at=job.finished_at,
        created_at=job.created_at,
    )
