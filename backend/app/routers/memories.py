from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from app.dependencies import get_memory_analysis_service
from app.schemas import (
    AnalyzeMemoryRequest,
    AnalyzeMemoryResponse,
    MemoryCurrentResponse,
    MemorySnapshotResponse,
    MemorySnapshotsListResponse,
)
from app.services.memory_service import MemoryAnalysisService
from app.services.supabase_store import MemorySnapshotRecord, PersonaRecord

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
    request: AnalyzeMemoryRequest,
    memory_service: MemoryAnalysisService = Depends(get_memory_analysis_service),
) -> AnalyzeMemoryResponse:
    outcome = await memory_service.analyze_window(window_hours=request.window_hours)
    return AnalyzeMemoryResponse(
        current=_to_persona_response(outcome.persona),
        snapshot=_to_snapshot_response(outcome.snapshot),
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
