from __future__ import annotations

from fastapi import APIRouter, Body, Depends, Query

from app.dependencies import get_memory_analysis_service
from app.schemas import (
    AnalyzeMemoryRequest,
    AnalyzeMemoryResponse,
    MemoryCurrentResponse,
    MemoryAnalysisPreviewResponse,
    MemorySnapshotResponse,
    MemorySnapshotsListResponse,
    ProjectMemoryResponse,
    RefineMemoryResponse,
)
from app.services.memory_service import MemoryAnalysisService
from app.services.supabase_store import MemorySnapshotRecord, PersonaRecord, ProjectMemoryRecord

router = APIRouter(prefix="/api/memories", tags=["memories"])


@router.get("/current", response_model=MemoryCurrentResponse)
async def get_current_memory(
    memory_service: MemoryAnalysisService = Depends(get_memory_analysis_service),
) -> MemoryCurrentResponse:
    persona = memory_service.get_current_persona()
    return _to_persona_response(persona)


@router.get("/snapshots", response_model=MemorySnapshotsListResponse)
async def get_memory_snapshots(
    limit: int = Query(default=20, ge=1, le=100),
    memory_service: MemoryAnalysisService = Depends(get_memory_analysis_service),
) -> MemorySnapshotsListResponse:
    snapshots = memory_service.list_snapshots(limit=limit)
    return MemorySnapshotsListResponse(snapshots=[_to_snapshot_response(snapshot) for snapshot in snapshots])


@router.post("/analyze", response_model=AnalyzeMemoryResponse)
async def analyze_memory(
    request: AnalyzeMemoryRequest | None = Body(default=None),
    window_hours: int | None = Query(default=None, ge=1),
    memory_service: MemoryAnalysisService = Depends(get_memory_analysis_service),
) -> AnalyzeMemoryResponse:
    if request is not None and request.target_message_count is not None:
        outcome = await memory_service.analyze_selection(
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
        outcome = await memory_service.analyze_window(window_hours=resolved_window_hours)
    return AnalyzeMemoryResponse(
        current=_to_persona_response(outcome.persona),
        snapshot=_to_snapshot_response(outcome.snapshot),
        projects=[_to_project_response(project) for project in outcome.projects],
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
    memory_service: MemoryAnalysisService = Depends(get_memory_analysis_service),
) -> RefineMemoryResponse:
    outcome = await memory_service.refine_saved_memory()
    return RefineMemoryResponse(
        current=_to_persona_response(outcome.persona),
        projects=[_to_project_response(project) for project in outcome.projects],
    )


def _to_persona_response(persona: PersonaRecord) -> MemoryCurrentResponse:
    return MemoryCurrentResponse(
        user_id=str(persona.user_id),
        life_summary=persona.life_summary,
        last_analyzed_at=persona.last_analyzed_at,
        last_snapshot_id=persona.last_snapshot_id,
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
