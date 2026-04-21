from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Body, Depends, HTTPException, Query, status
from fastapi.concurrency import run_in_threadpool

from app.dependencies import (
    get_memory_analysis_service,
    get_memory_job_service,
    get_observer_gateway_service,
    get_banco_de_dados_local_store,
    get_whatsapp_agent_gateway_service,
)
from app.schemas import (
    AnalysisJobResponse,
    AnalyzeMemoryRequest,
    AnalyzeMemoryResponse,
    CreateProjectMemoryRequest,
    MemoryActivityResponse,
    MemoryAnalysisPreviewResponse,
    MemoryCurrentResponse,
    MemoryLiveSummaryResponse,
    ProjectAssistantEditRequest,
    ProjectAssistantEditResponse,
    PersonMemoryResponse,
    MemorySnapshotResponse,
    MemorySnapshotsListResponse,
    MemoryStatusResponse,
    ModelRunResponse,
    ProjectMemoryResponse,
    SimpleOkResponse,
    UpdateProjectMemoryRequest,
    UpdatePersonMemoryRequest,
    UpdateWhatsAppGroupSelectionRequest,
    WhatsAppSyncRunResponse,
    WhatsAppGroupSelectionResponse,
    WhatsAppGroupSelectionsListResponse,
)
from app.services.memory_job_service import MemoryActivitySnapshot, MemoryJobService
from app.services.memory_service import MemoryAnalysisService
from app.services.observer_gateway import ObserverGatewayService, WhatsAppAgentGatewayService
from app.services.banco_de_dados_local_store import (
    AnalysisJobRecord,
    KnownGroupRecord,
    MemorySnapshotRecord,
    ModelRunRecord,
    PersonaRecord,
    PersonMemoryRecord,
    ProjectMemoryRecord,
    BancoDeDadosLocalStore,
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
    sync_in_progress = bool(
        not status.has_initial_analysis
        and activity.sync_runs
        and activity.sync_runs[0].status == "running"
    )
    return MemoryStatusResponse(
        has_initial_analysis=status.has_initial_analysis,
        last_analyzed_at=status.last_analyzed_at,
        new_messages_after_first_analysis=status.new_messages_after_first_analysis,
        current_job=_to_job_response(current_job),
        latest_completed_job=_to_job_response(latest_completed_job),
        sync_in_progress=sync_in_progress,
        can_execute_analysis=current_job is None and not sync_in_progress and status.can_run_next_batch,
    )


@router.get("/activity", response_model=MemoryActivityResponse)
async def get_memory_activity(
    memory_job_service: MemoryJobService = Depends(get_memory_job_service),
) -> MemoryActivityResponse:
    activity = await memory_job_service.get_activity_snapshot()
    return _to_activity_response(activity)


@router.get("/live-summary", response_model=MemoryLiveSummaryResponse)
async def get_memory_live_summary(
    memory_service: MemoryAnalysisService = Depends(get_memory_analysis_service),
    memory_job_service: MemoryJobService = Depends(get_memory_job_service),
) -> MemoryLiveSummaryResponse:
    memory_status, snapshots, projects, relations = await asyncio.gather(
        run_in_threadpool(memory_service.get_memory_status),
        run_in_threadpool(memory_service.list_snapshots, limit=1),
        run_in_threadpool(memory_service.list_projects, limit=8),
        run_in_threadpool(memory_service.list_relations, limit=80),
    )
    activity = await memory_job_service.get_activity_snapshot()
    current_job, latest_completed_job = _resolve_job_refs(activity.jobs)
    latest_snapshot = snapshots[0] if snapshots else None
    latest_project = projects[0] if projects else None
    latest_relation = relations[0] if relations else None

    return MemoryLiveSummaryResponse(
        generated_at=datetime.now(UTC),
        pending_new_messages=memory_status.new_messages_after_first_analysis,
        has_initial_analysis=memory_status.has_initial_analysis,
        current_job_id=current_job.id if current_job else None,
        current_job_status=current_job.status if current_job else None,
        latest_completed_job_id=latest_completed_job.id if latest_completed_job else None,
        latest_completed_job_status=latest_completed_job.status if latest_completed_job else None,
        latest_snapshot_id=latest_snapshot.id if latest_snapshot else None,
        latest_snapshot_created_at=latest_snapshot.created_at if latest_snapshot else None,
        latest_project_id=latest_project.id if latest_project else None,
        latest_project_updated_at=latest_project.updated_at if latest_project else None,
        latest_relation_id=latest_relation.id if latest_relation else None,
        latest_relation_updated_at=latest_relation.updated_at if latest_relation else None,
        memory_signature=_build_live_signature(
            memory_status.has_initial_analysis,
            memory_status.new_messages_after_first_analysis,
            memory_status.last_analyzed_at,
            current_job.id if current_job else None,
            current_job.status if current_job else None,
            latest_snapshot.id if latest_snapshot else None,
            latest_snapshot.created_at if latest_snapshot else None,
        ),
        activity_signature=_build_live_signature(
            activity.running_job_id,
            activity.sync_runs[0].id if activity.sync_runs else None,
            activity.sync_runs[0].status if activity.sync_runs else None,
            activity.sync_runs[0].last_activity_at if activity.sync_runs else None,
            current_job.id if current_job else None,
            current_job.status if current_job else None,
            latest_completed_job.id if latest_completed_job else None,
            latest_completed_job.status if latest_completed_job else None,
            activity.model_runs[0].id if activity.model_runs else None,
            activity.model_runs[0].success if activity.model_runs else None,
        ),
        projects_signature=_build_live_signature(
            len(projects),
            latest_project.id if latest_project else None,
            latest_project.updated_at if latest_project else None,
        ),
        relations_signature=_build_live_signature(
            len(relations),
            latest_relation.id if latest_relation else None,
            latest_relation.updated_at if latest_relation else None,
        ),
    )


@router.get("/snapshots", response_model=MemorySnapshotsListResponse)
async def get_memory_snapshots(
    limit: int = Query(default=20, ge=1, le=100),
    memory_service: MemoryAnalysisService = Depends(get_memory_analysis_service),
) -> MemorySnapshotsListResponse:
    snapshots = memory_service.list_snapshots(limit=limit)
    return MemorySnapshotsListResponse(snapshots=[_to_snapshot_response(snapshot) for snapshot in snapshots])


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


@router.post("/projects", response_model=ProjectMemoryResponse)
async def create_memory_project(
    request: CreateProjectMemoryRequest,
    memory_service: MemoryAnalysisService = Depends(get_memory_analysis_service),
) -> ProjectMemoryResponse:
    try:
        created = await run_in_threadpool(
            memory_service.create_project,
            project_name=request.project_name,
            summary=request.summary,
            status=request.status,
            what_is_being_built=request.what_is_being_built,
            built_for=request.built_for,
            aliases=request.aliases,
            stage=request.stage,
            priority=request.priority,
            blockers=request.blockers,
            next_steps=request.next_steps,
            evidence=request.evidence,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    return _to_project_response(created)


@router.get("/relations", response_model=list[PersonMemoryResponse])
async def get_memory_relations(
    memory_service: MemoryAnalysisService = Depends(get_memory_analysis_service),
) -> list[PersonMemoryResponse]:
    return [_to_person_memory_response(person) for person in memory_service.list_relations()]


@router.put("/relations/{contact_name}", response_model=PersonMemoryResponse)
async def update_memory_relation(
    contact_name: str,
    request: UpdatePersonMemoryRequest,
    memory_service: MemoryAnalysisService = Depends(get_memory_analysis_service),
) -> PersonMemoryResponse:
    updated = await run_in_threadpool(
        memory_service.update_relation,
        contact_name=contact_name,
        new_contact_name=request.contact_name,
        relationship_type=request.relationship_type,
    )
    if updated is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Relação não encontrada.")
    return _to_person_memory_response(updated)


@router.put("/projects/{project_key}", response_model=ProjectMemoryResponse)
async def update_memory_project(
    project_key: str,
    request: UpdateProjectMemoryRequest,
    memory_service: MemoryAnalysisService = Depends(get_memory_analysis_service),
) -> ProjectMemoryResponse:
    updated: ProjectMemoryRecord | None
    try:
        if request.completed is not None:
            updated = await run_in_threadpool(
                memory_service.update_project_completion,
                project_key=project_key,
                completed=request.completed,
                completion_notes=request.completion_notes,
            )
            if updated is None:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Projeto nao encontrado.")
            if any(
                value is not None
                for value in (
                    request.project_name,
                    request.summary,
                    request.status,
                    request.what_is_being_built,
                    request.built_for,
                    request.aliases,
                    request.stage,
                    request.priority,
                    request.blockers,
                    request.next_steps,
                    request.evidence,
                )
            ):
                updated = await run_in_threadpool(
                    memory_service.update_project,
                    project_key=updated.project_key,
                    project_name=request.project_name,
                    summary=request.summary,
                    status=request.status,
                    what_is_being_built=request.what_is_being_built,
                    built_for=request.built_for,
                    aliases=request.aliases,
                    stage=request.stage,
                    priority=request.priority,
                    blockers=request.blockers,
                    next_steps=request.next_steps,
                    evidence=request.evidence,
                )
        else:
            updated = await run_in_threadpool(
                memory_service.update_project,
                project_key=project_key,
                project_name=request.project_name,
                summary=request.summary,
                status=request.status,
                what_is_being_built=request.what_is_being_built,
                built_for=request.built_for,
                aliases=request.aliases,
                stage=request.stage,
                priority=request.priority,
                blockers=request.blockers,
                next_steps=request.next_steps,
                evidence=request.evidence,
            )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    if updated is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Projeto nao encontrado.")
    return _to_project_response(updated)


@router.post("/projects/{project_key}/assist", response_model=ProjectAssistantEditResponse)
async def assist_memory_project_edit(
    project_key: str,
    request: ProjectAssistantEditRequest,
    memory_service: MemoryAnalysisService = Depends(get_memory_analysis_service),
) -> ProjectAssistantEditResponse:
    try:
        updated, assistant_message = await memory_service.edit_project_with_ai(
            project_key=project_key,
            instruction=request.instruction,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    if updated is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Projeto nao encontrado.")
    return ProjectAssistantEditResponse(
        project=_to_project_response(updated),
        assistant_message=assistant_message,
    )


@router.delete("/projects/{project_key}", response_model=SimpleOkResponse)
async def delete_memory_project(
    project_key: str,
    memory_service: MemoryAnalysisService = Depends(get_memory_analysis_service),
) -> SimpleOkResponse:
    deleted = await run_in_threadpool(
        memory_service.delete_project,
        project_key=project_key,
    )
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Projeto nao encontrado.")
    return SimpleOkResponse(ok=True)


@router.get("/groups", response_model=WhatsAppGroupSelectionsListResponse)
async def get_memory_groups(
    store: BancoDeDadosLocalStore = Depends(get_banco_de_dados_local_store),
) -> WhatsAppGroupSelectionsListResponse:
    groups = await run_in_threadpool(store.list_known_groups, user_id=store.default_user_id)
    responses: list[WhatsAppGroupSelectionResponse] = []
    for group in groups:
        last_message_at, message_count, pending_message_count = await run_in_threadpool(
            store.get_known_group_message_stats,
            user_id=store.default_user_id,
            chat_jid=group.chat_jid,
        )
        responses.append(
            _to_group_selection_response(
                group,
                last_message_at=last_message_at,
                message_count=message_count,
                pending_message_count=pending_message_count,
            )
        )
    return WhatsAppGroupSelectionsListResponse(groups=responses)


@router.put("/groups/{chat_jid:path}", response_model=WhatsAppGroupSelectionResponse)
async def update_memory_group_selection(
    chat_jid: str,
    request: UpdateWhatsAppGroupSelectionRequest,
    store: BancoDeDadosLocalStore = Depends(get_banco_de_dados_local_store),
) -> WhatsAppGroupSelectionResponse:
    updated = await run_in_threadpool(
        store.update_known_group_selection,
        user_id=store.default_user_id,
        chat_jid=chat_jid,
        enabled_for_analysis=request.enabled_for_analysis,
    )
    if updated is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Grupo nao encontrado.")
    last_message_at, message_count, pending_message_count = await run_in_threadpool(
        store.get_known_group_message_stats,
        user_id=store.default_user_id,
        chat_jid=updated.chat_jid,
    )
    return _to_group_selection_response(
        updated,
        last_message_at=last_message_at,
        message_count=message_count,
        pending_message_count=pending_message_count,
    )


@router.delete("/database", response_model=SimpleOkResponse)
async def clear_saved_database(
    memory_job_service: MemoryJobService = Depends(get_memory_job_service),
    store: BancoDeDadosLocalStore = Depends(get_banco_de_dados_local_store),
    observer_gateway: ObserverGatewayService = Depends(get_observer_gateway_service),
    agent_gateway: WhatsAppAgentGatewayService = Depends(get_whatsapp_agent_gateway_service),
) -> SimpleOkResponse:
    activity = await memory_job_service.get_activity_snapshot()
    if activity.running_job_id is not None or any(job.status in {"queued", "running"} for job in activity.jobs):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Existe uma analise em andamento ou na fila. Aguarde terminar antes de apagar o banco.",
        )
    try:
        await observer_gateway.reset_observer()
    except Exception:
        pass
    try:
        await agent_gateway.reset_agent()
    except Exception:
        pass
    await run_in_threadpool(store.clear_all_saved_data)
    return SimpleOkResponse()


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
        distinct_contact_count=snapshot.distinct_contact_count,
        inbound_message_count=snapshot.inbound_message_count,
        outbound_message_count=snapshot.outbound_message_count,
        coverage_score=snapshot.coverage_score,
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
        origin_source=project.origin_source if project.origin_source == "manual" else "memory",
        summary=project.summary,
        status=project.status,
        what_is_being_built=project.what_is_being_built,
        built_for=project.built_for,
        aliases=project.aliases,
        stage=project.stage,
        priority=project.priority,
        blockers=project.blockers,
        confidence_score=project.confidence_score,
        next_steps=project.next_steps,
        evidence=project.evidence,
        source_snapshot_id=project.source_snapshot_id,
        last_seen_at=project.last_seen_at,
        last_material_update_at=project.last_material_update_at,
        completion_source=project.completion_source,
        manual_completed_at=project.manual_completed_at,
        manual_completion_notes=project.manual_completion_notes,
        updated_at=project.updated_at,
    )


def _to_person_memory_response(person: PersonMemoryRecord) -> PersonMemoryResponse:
    return PersonMemoryResponse(
        id=person.id,
        person_key=person.person_key,
        contact_name=person.contact_name,
        contact_phone=person.contact_phone,
        chat_jid=person.chat_jid,
        profile_summary=person.profile_summary,
        relationship_type=person.relationship_type,
        relationship_summary=person.relationship_summary,
        salient_facts=person.salient_facts,
        open_loops=person.open_loops,
        recent_topics=person.recent_topics,
        source_snapshot_id=person.source_snapshot_id,
        source_message_count=person.source_message_count,
        last_message_at=person.last_message_at,
        last_analyzed_at=person.last_analyzed_at,
        updated_at=person.updated_at,
    )


def _to_group_selection_response(
    group: KnownGroupRecord,
    *,
    last_message_at: Any,
    message_count: int,
    pending_message_count: int,
) -> WhatsAppGroupSelectionResponse:
    return WhatsAppGroupSelectionResponse(
        chat_jid=group.chat_jid,
        chat_name=group.chat_name,
        enabled_for_analysis=group.enabled_for_analysis,
        last_seen_at=group.last_seen_at,
        last_message_at=last_message_at,
        message_count=message_count,
        pending_message_count=pending_message_count,
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


def _build_live_signature(*parts: Any) -> str:
    return "|".join(_serialize_live_signature_part(part) for part in parts)


def _serialize_live_signature_part(value: Any) -> str:
    if isinstance(value, datetime):
        return value.isoformat()
    if value is None:
        return "-"
    return str(value)


def _to_job_response(job: Any) -> AnalysisJobResponse | None:
    if job is None:
        return None
    progress_percent, live_stage, live_status_text = _resolve_job_live_fields(job)
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
        progress_percent=progress_percent,
        live_stage=live_stage,
        live_status_text=live_status_text,
        started_at=job.started_at,
        finished_at=job.finished_at,
        created_at=job.created_at,
    )


def _resolve_job_live_fields(job: AnalysisJobRecord) -> tuple[int, str | None, str | None]:
    intent = str(job.intent or "improve_memory").strip().lower()
    is_first = intent == "first_analysis"

    if job.status == "queued":
        return (
            12 if is_first else 18,
            "queued",
            "Job registrado no backend e aguardando o worker principal iniciar o processamento.",
        )
    if job.status == "running":
        return (
            64 if is_first else 72,
            "analyzing",
            (
                "Primeira analise em execucao no backend principal."
                if is_first
                else "Atualizacao de memoria em execucao no backend principal."
            ),
        )
    if job.status == "succeeded":
        return 100, "completed", "Backend concluiu a analise e persistiu o resultado final."
    if job.status == "failed":
        return 0, "failed", job.error_text or "A analise falhou antes da persistencia final."
    return 0, None, None
