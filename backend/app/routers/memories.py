from __future__ import annotations

from fastapi import APIRouter, Body, Depends, Query

from app.dependencies import get_automation_service, get_memory_analysis_service
from app.schemas import (
    AnalyzeMemoryRequest,
    AnalyzeMemoryResponse,
    ImportantMessageResponse,
    ImportantMessagesListResponse,
    MemoryAnalysisPreviewResponse,
    MemoryCurrentResponse,
    MemoryStatusResponse,
    MemorySnapshotResponse,
    MemorySnapshotsListResponse,
    ProjectMemoryResponse,
    RefineMemoryResponse,
    AnalysisJobResponse,
)
from app.services.automation_service import AutomationService
from app.services.memory_service import MemoryAnalysisService
from app.services.supabase_store import ImportantMessageRecord, MemorySnapshotRecord, PersonaRecord, ProjectMemoryRecord

router = APIRouter(prefix="/api/memories", tags=["memories"])


@router.get("/current", response_model=MemoryCurrentResponse)
async def get_current_memory(
    memory_service: MemoryAnalysisService = Depends(get_memory_analysis_service),
) -> MemoryCurrentResponse:
    persona = memory_service.get_current_persona()
    return _to_persona_response(persona)


@router.get("/status", response_model=MemoryStatusResponse)
async def get_memory_status(
    memory_service: MemoryAnalysisService = Depends(get_memory_analysis_service),
) -> MemoryStatusResponse:
    status = memory_service.get_memory_status()
    return MemoryStatusResponse(
        has_initial_analysis=status.has_initial_analysis,
        last_analyzed_at=status.last_analyzed_at,
        pending_new_message_count=status.pending_new_message_count,
        next_process_message_count=status.next_process_message_count,
        messages_until_auto_process=status.messages_until_auto_process,
        can_run_first_analysis=status.can_run_first_analysis,
        can_run_next_batch=status.can_run_next_batch,
    )


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


@router.post("/analyze", response_model=AnalyzeMemoryResponse)
async def analyze_memory(
    request: AnalyzeMemoryRequest | None = Body(default=None),
    window_hours: int | None = Query(default=None, ge=1),
    automation_service: AutomationService = Depends(get_automation_service),
    memory_service: MemoryAnalysisService = Depends(get_memory_analysis_service),
) -> AnalyzeMemoryResponse:
    if request is not None and request.target_message_count is not None:
        intent = request.intent or (
            "improve_memory" if memory_service.get_current_persona().last_analyzed_at else "first_analysis"
        )
        job = await automation_service.enqueue_manual_analysis(
            intent=intent,
            target_message_count=request.target_message_count,
            max_lookback_hours=request.max_lookback_hours or 72,
            detail_mode=request.detail_mode,
        )
    else:
        resolved_window_hours = (
            request.window_hours
            if request is not None and request.window_hours is not None
            else window_hours or 24
        )
        target_message_count = min(
            memory_service.settings.memory_analysis_max_messages,
            max(20, resolved_window_hours * 4),
        )
        intent = request.intent or (
            "improve_memory" if memory_service.get_current_persona().last_analyzed_at else "first_analysis"
        )
        job = await automation_service.enqueue_manual_analysis(
            intent=intent,
            target_message_count=target_message_count,
            max_lookback_hours=resolved_window_hours,
            detail_mode=request.detail_mode if request is not None else "balanced",
        )
    current = memory_service.get_current_persona()
    snapshots = memory_service.list_snapshots(limit=1)
    snapshot = snapshots[0] if snapshots else None
    jobs = memory_service.store.list_analysis_jobs(user_id=current.user_id, limit=5)
    # Procura um job rodando ou o último concluído
    running_job = next((j for j in jobs if j.status in ("queued", "running")), None)
    latest_job = running_job or (jobs[0] if jobs else None)
    
    return AnalyzeMemoryResponse(
        current=_to_persona_response(current),
        snapshot=_to_snapshot_response(snapshot) if snapshot else None,
        projects=[_to_project_response(project) for project in memory_service.list_projects()],
        job=_to_job_response(latest_job) if latest_job else None,
    )


@router.post("/first-analysis", response_model=AnalyzeMemoryResponse)
async def run_first_memory_analysis(
    automation_service: AutomationService = Depends(get_automation_service),
    memory_service: MemoryAnalysisService = Depends(get_memory_analysis_service),
) -> AnalyzeMemoryResponse:
    job = await automation_service.enqueue_manual_first_analysis()
    current = memory_service.get_current_persona()
    snapshots = memory_service.list_snapshots(limit=1)
    snapshot = snapshots[0] if snapshots else None
    return AnalyzeMemoryResponse(
        current=_to_persona_response(current),
        snapshot=_to_snapshot_response(snapshot) if snapshot else None,
        projects=[_to_project_response(project) for project in memory_service.list_projects()],
        job=_to_job_response(job),
    )


@router.post("/process-next-batch", response_model=AnalyzeMemoryResponse)
async def run_next_memory_batch(
    automation_service: AutomationService = Depends(get_automation_service),
    memory_service: MemoryAnalysisService = Depends(get_memory_analysis_service),
) -> AnalyzeMemoryResponse:
    job = await automation_service.enqueue_manual_next_batch()
    current = memory_service.get_current_persona()
    snapshots = memory_service.list_snapshots(limit=1)
    snapshot = snapshots[0] if snapshots else None
    return AnalyzeMemoryResponse(
        current=_to_persona_response(current),
        snapshot=_to_snapshot_response(snapshot) if snapshot else None,
        projects=[_to_project_response(project) for project in memory_service.list_projects()],
        job=_to_job_response(job),
    )


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


@router.post("/refine", response_model=RefineMemoryResponse)
async def refine_saved_memory(
    automation_service: AutomationService = Depends(get_automation_service),
    memory_service: MemoryAnalysisService = Depends(get_memory_analysis_service),
) -> RefineMemoryResponse:
    job = await automation_service.enqueue_manual_refinement()
    return RefineMemoryResponse(
        current=_to_persona_response(memory_service.get_current_persona()),
        projects=[_to_project_response(project) for project in memory_service.list_projects()],
        job=_to_job_response(job),
    )



@router.get("/projects", response_model=list[ProjectMemoryResponse])
async def get_memory_projects(
    memory_service: MemoryAnalysisService = Depends(get_memory_analysis_service),
) -> list[ProjectMemoryResponse]:
    projects = memory_service.list_projects()
    return [_to_project_response(project) for project in projects]
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
