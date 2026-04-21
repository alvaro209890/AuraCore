from __future__ import annotations

from fastapi import APIRouter, Body, Depends, Query

from app.dependencies import get_automation_service, get_banco_de_dados_local_store
from app.schemas import (
    AnalysisJobResponse,
    AutomationDecisionResponse,
    AutomationDecisionsListResponse,
    AutomationJobsListResponse,
    AutomationSettingsResponse,
    AutomationStatusResponse,
    ModelRunResponse,
    UpdateAutomationSettingsRequest,
    WhatsAppSyncRunResponse,
)
from app.services.automation_service import AutomationService
from app.services.banco_de_dados_local_store import (
    AnalysisJobRecord,
    AutomationDecisionRecord,
    AutomationSettingsRecord,
    ModelRunRecord,
    BancoDeDadosLocalStore,
    WhatsAppSyncRunRecord,
)

router = APIRouter(prefix="/api/automation", tags=["automation"])


@router.get("/status", response_model=AutomationStatusResponse)
async def get_automation_status(
    automation_service: AutomationService = Depends(get_automation_service),
) -> AutomationStatusResponse:
    snapshot = await automation_service.get_status_snapshot()
    return AutomationStatusResponse(
        settings=_to_settings_response(snapshot.settings),
        sync_runs=[_to_sync_run_response(sync_run) for sync_run in snapshot.sync_runs],
        decisions=[_to_decision_response(decision) for decision in snapshot.decisions],
        jobs=[_to_job_response(job) for job in snapshot.jobs],
        model_runs=[_to_model_run_response(run) for run in snapshot.model_runs],
        daily_cost_usd=snapshot.daily_cost_usd,
        daily_auto_jobs_count=snapshot.daily_auto_jobs_count,
        queued_jobs_count=snapshot.queued_jobs_count,
        running_job_id=snapshot.running_job_id,
    )


@router.get("/jobs", response_model=AutomationJobsListResponse)
async def list_automation_jobs(
    limit: int = Query(default=12, ge=1, le=50),
    store: BancoDeDadosLocalStore = Depends(get_banco_de_dados_local_store),
) -> AutomationJobsListResponse:
    jobs = store.list_analysis_jobs(user_id=store.default_user_id, limit=limit)
    return AutomationJobsListResponse(jobs=[_to_job_response(job) for job in jobs])


@router.get("/decisions", response_model=AutomationDecisionsListResponse)
async def list_automation_decisions(
    limit: int = Query(default=10, ge=1, le=50),
    store: BancoDeDadosLocalStore = Depends(get_banco_de_dados_local_store),
) -> AutomationDecisionsListResponse:
    decisions = store.list_automation_decisions(user_id=store.default_user_id, limit=limit)
    return AutomationDecisionsListResponse(decisions=[_to_decision_response(decision) for decision in decisions])


@router.get("/settings", response_model=AutomationSettingsResponse)
async def get_automation_settings(
    store: BancoDeDadosLocalStore = Depends(get_banco_de_dados_local_store),
) -> AutomationSettingsResponse:
    settings = store.get_automation_settings(store.default_user_id)
    return _to_settings_response(settings)


@router.put("/settings", response_model=AutomationSettingsResponse)
async def update_automation_settings(
    request: UpdateAutomationSettingsRequest = Body(...),
    store: BancoDeDadosLocalStore = Depends(get_banco_de_dados_local_store),
) -> AutomationSettingsResponse:
    settings = store.update_automation_settings(
        user_id=store.default_user_id,
        auto_sync_enabled=request.auto_sync_enabled,
        auto_analyze_enabled=request.auto_analyze_enabled,
        auto_refine_enabled=request.auto_refine_enabled,
        min_new_messages_threshold=request.min_new_messages_threshold,
        stale_hours_threshold=request.stale_hours_threshold,
        pruned_messages_threshold=request.pruned_messages_threshold,
        default_detail_mode=request.default_detail_mode,
        default_target_message_count=request.default_target_message_count,
        default_lookback_hours=request.default_lookback_hours,
        daily_budget_usd=request.daily_budget_usd,
        max_auto_jobs_per_day=request.max_auto_jobs_per_day,
    )
    return _to_settings_response(settings)


@router.post("/tick", response_model=AutomationStatusResponse)
async def run_automation_tick(
    automation_service: AutomationService = Depends(get_automation_service),
) -> AutomationStatusResponse:
    await automation_service.tick()
    snapshot = await automation_service.get_status_snapshot()
    return AutomationStatusResponse(
        settings=_to_settings_response(snapshot.settings),
        sync_runs=[_to_sync_run_response(sync_run) for sync_run in snapshot.sync_runs],
        decisions=[_to_decision_response(decision) for decision in snapshot.decisions],
        jobs=[_to_job_response(job) for job in snapshot.jobs],
        model_runs=[_to_model_run_response(run) for run in snapshot.model_runs],
        daily_cost_usd=snapshot.daily_cost_usd,
        daily_auto_jobs_count=snapshot.daily_auto_jobs_count,
        queued_jobs_count=snapshot.queued_jobs_count,
        running_job_id=snapshot.running_job_id,
    )


def _to_settings_response(settings: AutomationSettingsRecord) -> AutomationSettingsResponse:
    return AutomationSettingsResponse(
        user_id=str(settings.user_id),
        auto_sync_enabled=settings.auto_sync_enabled,
        auto_analyze_enabled=settings.auto_analyze_enabled,
        auto_refine_enabled=settings.auto_refine_enabled,
        min_new_messages_threshold=settings.min_new_messages_threshold,
        stale_hours_threshold=settings.stale_hours_threshold,
        pruned_messages_threshold=settings.pruned_messages_threshold,
        default_detail_mode=settings.default_detail_mode,
        default_target_message_count=settings.default_target_message_count,
        default_lookback_hours=settings.default_lookback_hours,
        daily_budget_usd=settings.daily_budget_usd,
        max_auto_jobs_per_day=settings.max_auto_jobs_per_day,
        updated_at=settings.updated_at,
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


def _to_decision_response(decision: AutomationDecisionRecord) -> AutomationDecisionResponse:
    return AutomationDecisionResponse(
        id=decision.id,
        sync_run_id=decision.sync_run_id,
        intent=decision.intent,
        action=decision.action,
        reason_code=decision.reason_code,
        score=decision.score,
        should_analyze=decision.should_analyze,
        available_message_count=decision.available_message_count,
        selected_message_count=decision.selected_message_count,
        new_message_count=decision.new_message_count,
        replaced_message_count=decision.replaced_message_count,
        estimated_total_tokens=decision.estimated_total_tokens,
        estimated_cost_ceiling_usd=decision.estimated_cost_ceiling_usd,
        explanation=decision.explanation,
        created_at=decision.created_at,
    )


def _to_job_response(job: AnalysisJobRecord) -> AnalysisJobResponse:
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


def _to_model_run_response(run: ModelRunRecord) -> ModelRunResponse:
    return ModelRunResponse(
        id=run.id,
        job_id=run.job_id,
        provider=run.provider,
        model_name=run.model_name,
        run_type=run.run_type,
        success=run.success,
        latency_ms=run.latency_ms,
        input_tokens=run.input_tokens,
        output_tokens=run.output_tokens,
        reasoning_tokens=run.reasoning_tokens,
        estimated_cost_usd=run.estimated_cost_usd,
        error_text=run.error_text,
        created_at=run.created_at,
    )
