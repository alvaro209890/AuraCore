from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
import logging
from time import perf_counter
from typing import Literal

from app.config import Settings
from app.services.memory_service import (
    FixedAnalysisPlan,
    MemoryAnalysisError,
    MemoryAnalysisOutcome,
    MemoryAnalysisPreview,
    MemoryAnalysisService,
    MemoryRefinementOutcome,
)
from app.services.supabase_store import (
    AnalysisJobRecord,
    AutomationDecisionRecord,
    AutomationSettingsRecord,
    ModelRunRecord,
    SupabaseStore,
    WhatsAppSyncRunRecord,
)

AnalysisIntent = Literal["first_analysis", "improve_memory", "refine_saved"]
DecisionReasonCode = Literal[
    "first_analysis_ready",
    "first_analysis_more_signal",
    "awaiting_first_analysis",
    "batch_ready",
    "awaiting_next_batch",
    "pruned_messages",
    "new_messages_threshold",
    "stale_memory",
    "manual_refresh",
    "low_change",
    "auto_analyze_disabled",
    "daily_budget_reached",
    "max_auto_jobs_reached",
    "job_already_pending",
]


@dataclass(slots=True)
class AutomationStatusSnapshot:
    settings: AutomationSettingsRecord
    sync_runs: list[WhatsAppSyncRunRecord]
    decisions: list[AutomationDecisionRecord]
    jobs: list[AnalysisJobRecord]
    model_runs: list[ModelRunRecord]
    daily_cost_usd: float
    daily_auto_jobs_count: int
    queued_jobs_count: int
    running_job_id: str | None


logger = logging.getLogger("auracore.automation")
MINIMUM_STALE_ANALYSIS_JOB_THRESHOLD = timedelta(minutes=15)
MAX_SEQUENTIAL_DEEPSEEK_CALLS_PER_ANALYSIS = 6
ANALYSIS_JOB_GRACE_SECONDS = 120


class AutomationService:
    def __init__(
        self,
        *,
        settings: Settings,
        store: SupabaseStore,
        memory_service: MemoryAnalysisService,
    ) -> None:
        self.settings = settings
        self.store = store
        self.memory_service = memory_service
        self._tick_lock = asyncio.Lock()
        self._scheduled_tick_task: asyncio.Task[AnalysisJobRecord | None] | None = None
        self._scheduled_settle_task: asyncio.Task[None] | None = None
        self._scheduled_settle_deadline: datetime | None = None

    async def start_manual_sync(self, *, trigger: str = "manual") -> WhatsAppSyncRunRecord:
        started_at = datetime.now(UTC)
        return self.store.create_whatsapp_sync_run(
            user_id=self.settings.default_user_id,
            trigger=trigger,
            started_at=started_at,
        )

    def register_ingest_batch(
        self,
        *,
        accepted_count: int,
        ignored_count: int,
        timestamps: list[datetime],
    ) -> WhatsAppSyncRunRecord | None:
        now = datetime.now(UTC)
        sync_run = self.store.get_latest_running_sync_run(self.settings.default_user_id)
        if sync_run is None:
            sync_run = self.store.create_whatsapp_sync_run(
                user_id=self.settings.default_user_id,
                trigger="auto_ingest",
                started_at=now,
            )
        oldest_message_at = min(timestamps) if timestamps else None
        newest_message_at = max(timestamps) if timestamps else None
        return self.store.touch_latest_running_sync_run(
            user_id=self.settings.default_user_id,
            seen_increment=max(0, accepted_count + ignored_count),
            saved_increment=max(0, accepted_count),
            ignored_increment=max(0, ignored_count),
            oldest_message_at=oldest_message_at,
            newest_message_at=newest_message_at,
            activity_at=now,
        )

    def schedule_sync_settle(self, *, delay_seconds: float = 13.0) -> None:
        proposed_deadline = datetime.now(UTC) + timedelta(seconds=delay_seconds)
        if self._scheduled_settle_task is not None and not self._scheduled_settle_task.done():
            if self._scheduled_settle_deadline is not None and self._scheduled_settle_deadline <= proposed_deadline:
                return
            self._scheduled_settle_task.cancel()

        async def _delayed_tick() -> None:
            try:
                await asyncio.sleep(delay_seconds)
                await self.tick()
            except asyncio.CancelledError:
                return
            except Exception:
                logger.exception("scheduled_sync_settle_failed")
            finally:
                if self._scheduled_settle_task is asyncio.current_task():
                    self._scheduled_settle_task = None
                    self._scheduled_settle_deadline = None

        self._scheduled_settle_task = asyncio.create_task(_delayed_tick(), name="auracore-sync-settle")
        self._scheduled_settle_deadline = proposed_deadline

    def mark_sync_failed(self, *, sync_run_id: str, error_text: str) -> WhatsAppSyncRunRecord | None:
        return self.store.mark_whatsapp_sync_run_failed(
            sync_run_id=sync_run_id,
            error_text=error_text,
            finished_at=datetime.now(UTC),
        )

    async def settle_sync_runs(self) -> list[WhatsAppSyncRunRecord]:
        finalized_runs = self.store.finalize_idle_sync_runs(
            user_id=self.settings.default_user_id,
            idle_before=datetime.now(UTC) - timedelta(seconds=12),
        )
        if not finalized_runs:
            return []

        recent_decisions = self.store.list_automation_decisions(
            user_id=self.settings.default_user_id,
            limit=40,
        )
        seen_sync_ids = {decision.sync_run_id for decision in recent_decisions if decision.sync_run_id}
        for sync_run in finalized_runs:
            if sync_run.id in seen_sync_ids:
                continue
            await self.evaluate_and_schedule(
                sync_run_id=sync_run.id,
                force_analysis=sync_run.trigger == "manual",
                trigger_source="manual_sync" if sync_run.trigger == "manual" else "automation",
            )
        return finalized_runs

    async def finalize_manual_sync_and_queue_refresh(
        self,
        *,
        sync_run_id: str,
    ) -> tuple[WhatsAppSyncRunRecord | None, AnalysisJobRecord | None]:
        finalized_run = self.store.finalize_whatsapp_sync_run(
            user_id=self.settings.default_user_id,
            sync_run_id=sync_run_id,
            finished_at=datetime.now(UTC),
        )
        if finalized_run is None:
            return None, None

        _decision, job = await self.evaluate_and_schedule(
            sync_run_id=sync_run_id,
            force_analysis=finalized_run.trigger == "manual",
            trigger_source="manual_sync" if finalized_run.trigger == "manual" else "automation",
        )
        return finalized_run, job

    async def evaluate_and_schedule(
        self,
        *,
        sync_run_id: str | None = None,
        force_analysis: bool = False,
        trigger_source: str = "automation",
    ) -> tuple[AutomationDecisionRecord, AnalysisJobRecord | None]:
        automation_settings = self.store.get_automation_settings(self.settings.default_user_id)
        memory_status = self.memory_service.get_memory_status()
        intent: AnalysisIntent = "improve_memory" if memory_status.has_initial_analysis else "first_analysis"
        daily_cost_usd = self._get_daily_cost_usd()
        daily_auto_jobs_count = self._get_daily_auto_jobs_count()
        recent_jobs = self.store.list_analysis_jobs(user_id=self.settings.default_user_id, limit=20)
        has_pending_auto_job = any(
            job.trigger_source == "automation" and job.status in {"queued", "running"}
            for job in recent_jobs
        )
        has_pending_job = any(job.status in {"queued", "running"} for job in recent_jobs)
        incremental_threshold = max(
            self.settings.memory_incremental_min_messages,
            automation_settings.min_new_messages_threshold,
        )

        action = "skip"
        should_analyze = False
        reason_code: DecisionReasonCode = "awaiting_first_analysis"
        explanation = "A memoria base ainda nao existe. O backend esta aguardando o primeiro lote util do observador."
        selected_message_count = memory_status.next_process_message_count
        estimated_total_tokens = 0
        estimated_cost_ceiling_usd = 0.0
        job_plan: FixedAnalysisPlan | None = None

        if not memory_status.has_initial_analysis and memory_status.can_run_next_batch:
            try:
                job_plan = self.memory_service.plan_first_analysis()
            except MemoryAnalysisError as error:
                reason_code = "first_analysis_more_signal"
                explanation = str(error)
            else:
                selected_message_count = len(job_plan.source_messages)
                estimated_total_tokens = job_plan.estimated_input_tokens + job_plan.estimated_output_tokens
                estimated_cost_ceiling_usd = job_plan.estimated_cost_ceiling_usd

                if force_analysis and has_pending_job:
                    reason_code = "job_already_pending"
                    explanation = (
                        "Ja existe uma leitura em andamento ou na fila; a sincronizacao manual nao abriu "
                        "outra primeira analise em paralelo."
                    )
                elif not force_analysis and not automation_settings.auto_analyze_enabled:
                    reason_code = "auto_analyze_disabled"
                    explanation = (
                        "A automacao de analise esta desligada; o backend registrou o lote inicial disponivel, "
                        "mas nao o enfileirou."
                    )
                elif not force_analysis and daily_cost_usd >= automation_settings.daily_budget_usd:
                    reason_code = "daily_budget_reached"
                    explanation = (
                        f"O custo estimado acumulado hoje ja chegou a US$ {daily_cost_usd:.4f}, "
                        "acima do teto automatico configurado."
                    )
                elif not force_analysis and daily_auto_jobs_count >= automation_settings.max_auto_jobs_per_day:
                    reason_code = "max_auto_jobs_reached"
                    explanation = (
                        "O limite diario de jobs automaticos ja foi atingido; a primeira analise ficou "
                        "aguardando acao manual."
                    )
                elif not force_analysis and has_pending_auto_job:
                    reason_code = "job_already_pending"
                    explanation = (
                        "Ja existe um job automatico em andamento ou na fila; o sistema nao empilha "
                        "outra primeira analise em paralelo."
                    )
                else:
                    action = "queue"
                    should_analyze = True
                    reason_code = "first_analysis_ready"
                    explanation = (
                        f"O observador fechou um lote inicial com {memory_status.pending_new_message_count} mensagens pendentes. "
                        f"O backend vai montar a primeira memoria usando {selected_message_count} mensagens recentes."
                    )
        elif not memory_status.has_initial_analysis:
            reason_code = "awaiting_first_analysis"
            explanation = (
                "A memoria base ainda nao existe. O backend continua aguardando mensagens diretas textuais "
                "do observador para abrir a primeira analise."
            )
        elif memory_status.can_run_next_batch:
            job_plan = self.memory_service.plan_next_batch()
            selected_message_count = len(job_plan.source_messages)
            estimated_total_tokens = job_plan.estimated_input_tokens + job_plan.estimated_output_tokens
            estimated_cost_ceiling_usd = job_plan.estimated_cost_ceiling_usd

            if force_analysis and has_pending_job:
                reason_code = "job_already_pending"
                explanation = "Ja existe uma leitura em andamento ou na fila; a sincronizacao manual nao abriu outro lote em paralelo."
            elif not force_analysis and not automation_settings.auto_analyze_enabled:
                reason_code = "auto_analyze_disabled"
                explanation = (
                    "A automacao de analise esta desligada; o backend registrou o novo lote disponivel, "
                    "mas nao o enfileirou automaticamente."
                )
            elif not force_analysis and daily_cost_usd >= automation_settings.daily_budget_usd:
                reason_code = "daily_budget_reached"
                explanation = (
                    f"O custo estimado acumulado hoje ja chegou a US$ {daily_cost_usd:.4f}, "
                    "acima do teto automatico configurado."
                )
            elif not force_analysis and daily_auto_jobs_count >= automation_settings.max_auto_jobs_per_day:
                reason_code = "max_auto_jobs_reached"
                explanation = (
                    "O limite diario de jobs automaticos ja foi atingido; o novo lote ficou aguardando "
                    "o proximo ciclo disponivel."
                )
            elif not force_analysis and has_pending_auto_job:
                reason_code = "job_already_pending"
                explanation = (
                    "Ja existe um job automatico em andamento ou na fila; o sistema nao empilha "
                    "outro lote incremental em paralelo."
                )
            elif memory_status.pending_new_message_count < incremental_threshold:
                reason_code = "awaiting_next_batch"
                explanation = (
                    f"Existem {memory_status.pending_new_message_count} mensagens novas pendentes. "
                    f"O backend vai enfileirar a proxima atualizacao automatica quando a conta atingir "
                    f"{incremental_threshold} mensagens novas."
                )
            else:
                action = "queue"
                should_analyze = True
                reason_code = "new_messages_threshold"
                explanation = (
                    f"Existem {memory_status.pending_new_message_count} mensagens novas pendentes. "
                    f"O backend vai atualizar a memoria automaticamente agora e processar um lote economico com "
                    f"{selected_message_count} mensagens."
                )
        elif memory_status.has_initial_analysis:
            reason_code = "awaiting_next_batch"
            explanation = (
                f"Ainda existem {memory_status.pending_new_message_count} mensagens novas pendentes. "
                f"O proximo lote automatico dispara quando a conta atingir {incremental_threshold} mensagens novas."
            )

        decision = self.store.create_automation_decision(
            user_id=self.settings.default_user_id,
            sync_run_id=sync_run_id,
            intent=intent,
            action=action,
            reason_code=reason_code,
            score=100 if action == "queue" else min(90, memory_status.pending_new_message_count * 10),
            should_analyze=should_analyze,
            available_message_count=memory_status.pending_new_message_count,
            selected_message_count=selected_message_count,
            new_message_count=memory_status.pending_new_message_count,
            replaced_message_count=0,
            estimated_total_tokens=estimated_total_tokens,
            estimated_cost_ceiling_usd=estimated_cost_ceiling_usd,
            explanation=explanation,
            created_at=datetime.now(UTC),
        )

        if action != "queue":
            return decision, None

        if job_plan is None:
            return decision, None

        job = self.store.create_analysis_job(
            user_id=self.settings.default_user_id,
            intent=job_plan.intent,
            status="queued",
            trigger_source=trigger_source,
            decision_id=decision.id,
            sync_run_id=sync_run_id,
            target_message_count=len(job_plan.source_messages),
            max_lookback_hours=0,
            detail_mode="balanced",
            selected_message_count=len(job_plan.source_messages),
            selected_transcript_chars=job_plan.selected_transcript_chars,
            estimated_input_tokens=job_plan.estimated_input_tokens,
            estimated_output_tokens=job_plan.estimated_output_tokens,
            estimated_cost_floor_usd=job_plan.estimated_cost_floor_usd,
            estimated_cost_ceiling_usd=job_plan.estimated_cost_ceiling_usd,
            created_at=datetime.now(UTC),
        )
        self._schedule_tick()
        return decision, job

    async def enqueue_manual_analysis(
        self,
        *,
        intent: AnalysisIntent,
        target_message_count: int,
        max_lookback_hours: int,
        detail_mode: str,
    ) -> AnalysisJobRecord:
        if max_lookback_hours == 0 and intent in {"first_analysis", "improve_memory"}:
            plan = (
                self.memory_service.plan_first_analysis()
                if intent == "first_analysis"
                else self.memory_service.plan_next_batch()
            )
            resolved_detail_mode = "deep" if plan.intent == "first_analysis" else "balanced"
            created_at = datetime.now(UTC)
            job = self.store.create_analysis_job(
                user_id=self.settings.default_user_id,
                intent=intent,
                status="queued",
                trigger_source="manual",
                decision_id=None,
                sync_run_id=None,
                target_message_count=len(plan.source_messages),
                max_lookback_hours=0,
                detail_mode=resolved_detail_mode,
                selected_message_count=len(plan.source_messages),
                selected_transcript_chars=plan.selected_transcript_chars,
                estimated_input_tokens=plan.estimated_input_tokens,
                estimated_output_tokens=plan.estimated_output_tokens,
                estimated_cost_floor_usd=plan.estimated_cost_floor_usd,
                estimated_cost_ceiling_usd=plan.estimated_cost_ceiling_usd,
                created_at=created_at,
            )
            self._schedule_tick()
            updated_job = self.store.get_analysis_job(job.id)
            if updated_job is None:
                raise RuntimeError("Manual fixed-plan job disappeared.")
            return updated_job

        preview = await self.memory_service.get_analysis_preview(
            target_message_count=target_message_count,
            max_lookback_hours=max_lookback_hours,
            detail_mode=detail_mode,  # type: ignore[arg-type]
        )
        created_at = datetime.now(UTC)
        job = self.store.create_analysis_job(
            user_id=self.settings.default_user_id,
            intent=intent,
            status="queued",
            trigger_source="manual",
            decision_id=None,
            sync_run_id=None,
            target_message_count=preview.target_message_count,
            max_lookback_hours=preview.max_lookback_hours,
            detail_mode=preview.detail_mode,
            selected_message_count=preview.selected_message_count,
            selected_transcript_chars=preview.selected_transcript_chars,
            estimated_input_tokens=preview.estimated_input_tokens,
            estimated_output_tokens=preview.estimated_output_tokens,
            estimated_cost_floor_usd=preview.estimated_cost_total_floor_usd,
            estimated_cost_ceiling_usd=preview.estimated_cost_total_ceiling_usd,
            created_at=created_at,
        )
        self._schedule_tick()
        updated_job = self.store.get_analysis_job(job.id)
        if updated_job is None:
            raise RuntimeError("Manual analysis job disappeared.")
        return updated_job

    async def enqueue_manual_first_analysis(self) -> AnalysisJobRecord:
        self._ensure_no_pending_job()
        plan = self.memory_service.plan_first_analysis()
        return await self.enqueue_manual_analysis(
            intent="first_analysis",
            target_message_count=len(plan.source_messages),
            max_lookback_hours=0,
            detail_mode="deep",
        )

    async def enqueue_manual_next_batch(self) -> AnalysisJobRecord:
        self._ensure_no_pending_job()
        plan = self.memory_service.plan_next_batch()
        created_at = datetime.now(UTC)
        job = self.store.create_analysis_job(
            user_id=self.settings.default_user_id,
            intent="improve_memory",
            status="queued",
            trigger_source="manual",
            decision_id=None,
            sync_run_id=None,
            target_message_count=len(plan.source_messages),
            max_lookback_hours=0,
            detail_mode="balanced",
            selected_message_count=len(plan.source_messages),
            selected_transcript_chars=plan.selected_transcript_chars,
            estimated_input_tokens=plan.estimated_input_tokens,
            estimated_output_tokens=plan.estimated_output_tokens,
            estimated_cost_floor_usd=plan.estimated_cost_floor_usd,
            estimated_cost_ceiling_usd=plan.estimated_cost_ceiling_usd,
            created_at=created_at,
        )
        self._schedule_tick()
        updated_job = self.store.get_analysis_job(job.id)
        if updated_job is None:
            raise RuntimeError("Manual next batch job disappeared.")
        return updated_job

    async def enqueue_manual_refinement(self) -> AnalysisJobRecord:
        created_at = datetime.now(UTC)
        job = self.store.create_analysis_job(
            user_id=self.settings.default_user_id,
            intent="refine_saved",
            status="queued",
            trigger_source="manual",
            decision_id=None,
            sync_run_id=None,
            target_message_count=0,
            max_lookback_hours=0,
            detail_mode="balanced",
            created_at=created_at,
        )
        self._schedule_tick()
        updated_job = self.store.get_analysis_job(job.id)
        if updated_job is None:
            raise RuntimeError("Manual refinement job disappeared.")
        return updated_job

    async def _execute_fixed_refinement_job(self, job: AnalysisJobRecord) -> None:
        start_clock = perf_counter()
        try:
            outcome = await self.memory_service.refine_saved_memory()
        except Exception as error:
            latency_ms = round((perf_counter() - start_clock) * 1000)
            self.store.update_analysis_job(
                job_id=job.id,
                status="failed",
                error_text=str(error),
                finished_at=datetime.now(UTC),
            )
            self.store.create_model_run(
                user_id=self.settings.default_user_id,
                job_id=job.id,
                provider="deepseek",
                model_name=self.settings.deepseek_model,
                run_type="memory_refine",
                success=False,
                latency_ms=latency_ms,
                input_tokens=None,
                output_tokens=None,
                reasoning_tokens=None,
                estimated_cost_usd=None,
                error_text=str(error),
                created_at=datetime.now(UTC),
            )
            raise

        latency_ms = round((perf_counter() - start_clock) * 1000)
        self.store.update_analysis_job(
            job_id=job.id,
            status="succeeded",
            finished_at=datetime.now(UTC),
        )
        self.store.create_model_run(
            user_id=self.settings.default_user_id,
            job_id=job.id,
            provider="deepseek",
            model_name=self.settings.deepseek_model,
            run_type="memory_refine",
            success=True,
            latency_ms=latency_ms,
            input_tokens=None,
            output_tokens=None,
            reasoning_tokens=None,
            estimated_cost_usd=None,
            error_text=None,
            created_at=datetime.now(UTC),
        )

    async def execute_next_job(self) -> AnalysisJobRecord | None:
        job = self.store.claim_next_queued_analysis_job(user_id=self.settings.default_user_id)
        if job is None:
            return None

        logger.info(
            "analysis_job_started job_id=%s intent=%s trigger=%s target=%s detail_mode=%s",
            job.id,
            job.intent,
            job.trigger_source,
            job.target_message_count,
            job.detail_mode,
        )

        if job.intent == "refine_saved":
            await self._execute_fixed_refinement_job(job=job)
            return self.store.get_analysis_job(job.id)

        if job.max_lookback_hours == 0 and job.intent in {"first_analysis", "improve_memory"}:
            try:
                plan = (
                    self.memory_service.plan_first_analysis()
                    if job.intent == "first_analysis"
                    else self.memory_service.plan_next_batch()
                )
            except Exception as error:
                self.store.update_analysis_job(
                    job_id=job.id,
                    status="failed",
                    error_text=str(error),
                    finished_at=datetime.now(UTC),
                )
                raise
            await self._execute_fixed_analysis_job(job=job, plan=plan)
            return self.store.get_analysis_job(job.id)

        try:
            preview = await self.memory_service.get_analysis_preview(
                target_message_count=job.target_message_count,
                max_lookback_hours=job.max_lookback_hours,
                detail_mode=job.detail_mode,  # type: ignore[arg-type]
            )
        except Exception as error:
            self.store.update_analysis_job(
                job_id=job.id,
                status="failed",
                error_text=str(error),
                finished_at=datetime.now(UTC),
            )
            raise
        await self._execute_analysis_job(job=job, preview=preview)
        return self.store.get_analysis_job(job.id)

    async def tick(self) -> AnalysisJobRecord | None:
        async with self._tick_lock:
            self._recover_stale_pending_jobs()
            finalized_runs = await self.settle_sync_runs()
            if not finalized_runs:
                await self._maybe_schedule_analysis_from_live_backlog()
            return await self.execute_next_job()

    def _schedule_tick(self) -> None:
        if self._scheduled_tick_task is not None and not self._scheduled_tick_task.done():
            return
        task = asyncio.create_task(self.tick(), name="auracore-automation-tick")
        task.add_done_callback(self._handle_scheduled_tick_done)
        self._scheduled_tick_task = task

    def warm_start(self) -> None:
        recovered_jobs = self._requeue_orphaned_running_jobs()
        if recovered_jobs > 0:
            logger.warning("automation_warm_start_requeued_jobs count=%s", recovered_jobs)
        self._schedule_tick()

    def _handle_scheduled_tick_done(self, task: asyncio.Task[AnalysisJobRecord | None]) -> None:
        if self._scheduled_tick_task is task:
            self._scheduled_tick_task = None
        try:
            task.result()
        except asyncio.CancelledError:
            return
        except Exception:
            logger.exception("scheduled_automation_tick_failed")

    def _requeue_orphaned_running_jobs(self) -> int:
        recovered_jobs = 0
        for job in self.store.list_analysis_jobs(user_id=self.settings.default_user_id, limit=20):
            if job.status != "running":
                continue
            self.store.update_analysis_job(
                job_id=job.id,
                status="queued",
                error_text="Job interrompido por reinicio do backend; reenfileirado automaticamente.",
            )
            recovered_jobs += 1
            logger.warning(
                "analysis_job_requeued_after_restart job_id=%s intent=%s trigger=%s",
                job.id,
                job.intent,
                job.trigger_source,
            )
        return recovered_jobs

    def _analysis_job_stale_threshold(self) -> timedelta:
        timeout_based_threshold = timedelta(
            seconds=(
                self.settings.deepseek_timeout_seconds * MAX_SEQUENTIAL_DEEPSEEK_CALLS_PER_ANALYSIS
                + ANALYSIS_JOB_GRACE_SECONDS
            )
        )
        return max(MINIMUM_STALE_ANALYSIS_JOB_THRESHOLD, timeout_based_threshold)

    def _recover_stale_pending_jobs(self) -> None:
        now = datetime.now(UTC)
        threshold = self._analysis_job_stale_threshold()
        for job in self.store.list_analysis_jobs(user_id=self.settings.default_user_id, limit=20):
            if job.status not in {"queued", "running"}:
                continue
            reference_time = job.started_at if job.status == "running" and job.started_at else job.created_at
            if now - reference_time < threshold:
                continue
            self.store.update_analysis_job(
                job_id=job.id,
                status="failed",
                error_text=(
                    "Job recuperado automaticamente apos ficar travado sem conclusao por mais de "
                    f"{int(threshold.total_seconds() // 60)} minutos."
                ),
                finished_at=now,
            )
            logger.warning("stale_analysis_job_recovered job_id=%s intent=%s", job.id, job.intent)

    async def get_status_snapshot(self) -> AutomationStatusSnapshot:
        await self.settle_sync_runs()
        settings = self.store.get_automation_settings(self.settings.default_user_id)
        sync_runs = self.store.list_whatsapp_sync_runs(user_id=self.settings.default_user_id, limit=8)
        decisions = self.store.list_automation_decisions(user_id=self.settings.default_user_id, limit=10)
        jobs = self.store.list_analysis_jobs(user_id=self.settings.default_user_id, limit=12)
        model_runs = self.store.list_model_runs(user_id=self.settings.default_user_id, limit=12)
        queued_jobs_count = sum(1 for job in jobs if job.status == "queued")
        running_job = next((job for job in jobs if job.status == "running"), None)
        return AutomationStatusSnapshot(
            settings=settings,
            sync_runs=sync_runs,
            decisions=decisions,
            jobs=jobs,
            model_runs=model_runs,
            daily_cost_usd=self._get_daily_cost_usd(),
            daily_auto_jobs_count=self._get_daily_auto_jobs_count(),
            queued_jobs_count=queued_jobs_count,
            running_job_id=running_job.id if running_job else None,
        )

    def _ensure_no_pending_job(self) -> None:
        self._recover_stale_pending_jobs()
        recent_jobs = self.store.list_analysis_jobs(user_id=self.settings.default_user_id, limit=20)
        now = datetime.now(UTC)
        stagnant_threshold = self._analysis_job_stale_threshold()
        
        pending_jobs = [
            job for job in recent_jobs 
            if job.status in {"queued", "running"} 
            and (
                now - (job.started_at if job.status == "running" and job.started_at else job.created_at)
            ) < stagnant_threshold
        ]
        
        if pending_jobs:
            raise MemoryAnalysisError(
                "Já existe uma análise em fila ou em processamento. Por favor, aguarde alguns instantes até que ela seja concluída."
            )

    async def _execute_analysis_job(
        self,
        *,
        job: AnalysisJobRecord,
        preview: MemoryAnalysisPreview,
    ) -> MemoryAnalysisOutcome:
        start_clock = perf_counter()
        try:
            outcome = await self.memory_service.analyze_selection(
                target_message_count=job.target_message_count,
                max_lookback_hours=job.max_lookback_hours,
                detail_mode=job.detail_mode,  # type: ignore[arg-type]
            )
        except Exception as error:
            logger.exception("analysis_job_failed job_id=%s intent=%s", job.id, job.intent)
            latency_ms = round((perf_counter() - start_clock) * 1000)
            self.store.update_analysis_job(
                job_id=job.id,
                status="failed",
                error_text=str(error),
                finished_at=datetime.now(UTC),
            )
            self.store.create_model_run(
                user_id=self.settings.default_user_id,
                job_id=job.id,
                provider="deepseek",
                model_name=self.settings.deepseek_model,
                run_type="memory_analyze",
                success=False,
                latency_ms=latency_ms,
                input_tokens=preview.estimated_input_tokens,
                output_tokens=preview.estimated_output_tokens,
                reasoning_tokens=preview.estimated_reasoning_tokens,
                estimated_cost_usd=preview.estimated_cost_total_ceiling_usd,
                error_text=str(error),
                created_at=datetime.now(UTC),
            )
            raise

        latency_ms = round((perf_counter() - start_clock) * 1000)
        self.store.update_analysis_job(
            job_id=job.id,
            status="succeeded",
            selected_message_count=len(outcome.source_message_ids) or preview.selected_message_count,
            selected_transcript_chars=outcome.selected_transcript_chars or preview.selected_transcript_chars,
            snapshot_id=outcome.snapshot.id,
            finished_at=datetime.now(UTC),
        )
        self.store.save_analysis_job_messages(job_id=job.id, message_ids=outcome.source_message_ids)
        if outcome.source_message_ids:
            processed_at = datetime.now(UTC)
            marked_count = self.store.mark_messages_processed(
                user_id=self.settings.default_user_id,
                message_ids=outcome.source_message_ids,
                processed_at=processed_at,
            )
            if marked_count > 0:
                self.store.delete_messages_by_ids(message_ids=outcome.source_message_ids)
        self._finalize_observer_cutoff_if_needed(job)
        logger.info(
            "analysis_job_done job_id=%s intent=%s selected=%s",
            job.id,
            job.intent,
            len(outcome.source_message_ids),
        )
        self.store.create_model_run(
            user_id=self.settings.default_user_id,
            job_id=job.id,
            provider="deepseek",
            model_name=self.settings.deepseek_model,
            run_type="memory_analyze",
            success=True,
            latency_ms=latency_ms,
            input_tokens=preview.estimated_input_tokens,
            output_tokens=preview.estimated_output_tokens,
            reasoning_tokens=preview.estimated_reasoning_tokens,
            estimated_cost_usd=preview.estimated_cost_total_ceiling_usd,
            error_text=None,
            created_at=datetime.now(UTC),
        )
        return outcome

    async def _execute_fixed_analysis_job(
        self,
        *,
        job: AnalysisJobRecord,
        plan: FixedAnalysisPlan,
    ) -> MemoryAnalysisOutcome:
        start_clock = perf_counter()
        try:
            outcome = await self.memory_service.execute_fixed_analysis_plan(plan)
        except Exception as error:
            logger.exception("fixed_analysis_job_failed job_id=%s intent=%s", job.id, job.intent)
            latency_ms = round((perf_counter() - start_clock) * 1000)
            self.store.update_analysis_job(
                job_id=job.id,
                status="failed",
                error_text=str(error),
                finished_at=datetime.now(UTC),
            )
            self.store.create_model_run(
                user_id=self.settings.default_user_id,
                job_id=job.id,
                provider="deepseek",
                model_name=self.settings.deepseek_model,
                run_type="memory_analyze",
                success=False,
                latency_ms=latency_ms,
                input_tokens=plan.estimated_input_tokens,
                output_tokens=plan.estimated_output_tokens,
                reasoning_tokens=plan.estimated_reasoning_tokens,
                estimated_cost_usd=plan.estimated_cost_ceiling_usd,
                error_text=str(error),
                created_at=datetime.now(UTC),
            )
            raise

        latency_ms = round((perf_counter() - start_clock) * 1000)
        self.store.update_analysis_job(
            job_id=job.id,
            status="succeeded",
            selected_message_count=len(outcome.source_message_ids) or len(plan.source_messages),
            selected_transcript_chars=outcome.selected_transcript_chars or plan.selected_transcript_chars,
            snapshot_id=outcome.snapshot.id,
            finished_at=datetime.now(UTC),
        )
        self.store.save_analysis_job_messages(job_id=job.id, message_ids=outcome.source_message_ids)
        if outcome.source_message_ids:
            processed_at = datetime.now(UTC)
            marked_count = self.store.mark_messages_processed(
                user_id=self.settings.default_user_id,
                message_ids=outcome.source_message_ids,
                processed_at=processed_at,
            )
            if marked_count > 0:
                self.store.delete_messages_by_ids(message_ids=outcome.source_message_ids)
        self._finalize_observer_cutoff_if_needed(job)
        logger.info(
            "fixed_analysis_job_done job_id=%s intent=%s selected=%s",
            job.id,
            job.intent,
            len(outcome.source_message_ids),
        )
        self.store.create_model_run(
            user_id=self.settings.default_user_id,
            job_id=job.id,
            provider="deepseek",
            model_name=self.settings.deepseek_model,
            run_type="memory_analyze",
            success=True,
            latency_ms=latency_ms,
            input_tokens=plan.estimated_input_tokens,
            output_tokens=plan.estimated_output_tokens,
            reasoning_tokens=plan.estimated_reasoning_tokens,
            estimated_cost_usd=plan.estimated_cost_ceiling_usd,
            error_text=None,
            created_at=datetime.now(UTC),
        )
        self._schedule_follow_up_evaluation_if_needed()
        return outcome

    def _schedule_follow_up_evaluation_if_needed(self) -> None:
        try:
            status = self.memory_service.get_memory_status()
        except Exception:
            logger.exception("follow_up_memory_status_failed")
            return

        if not status.has_initial_analysis or not status.can_run_next_batch:
            return

        logger.info(
            "follow_up_analysis_waiting_manual pending=%s min_batch=%s",
            status.pending_new_message_count,
            status.incremental_min_messages,
        )

    def _finalize_observer_cutoff_if_needed(self, job: AnalysisJobRecord) -> None:
        if job.intent != "first_analysis":
            return
        cutoff_at = job.started_at or datetime.now(UTC)
        self.store.set_observer_history_cutoff(
            user_id=self.settings.default_user_id,
            cutoff_at=cutoff_at,
        )
        self.store.reconcile_observer_backlog(user_id=self.settings.default_user_id)

    def _get_daily_cost_usd(self) -> float:
        day_start = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
        return self.store.sum_model_run_cost_since(
            user_id=self.settings.default_user_id,
            since=day_start,
        )

    def _get_daily_auto_jobs_count(self) -> int:
        day_start = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
        return self.store.count_analysis_jobs_since(
            user_id=self.settings.default_user_id,
            since=day_start,
            trigger_source="automation",
        )

    async def _maybe_schedule_analysis_from_live_backlog(self) -> None:
        status = self.memory_service.get_memory_status()
        if not status.can_run_next_batch:
            return

        recent_jobs = self.store.list_analysis_jobs(user_id=self.settings.default_user_id, limit=20)
        has_pending_job = any(job.status in {"queued", "running"} for job in recent_jobs)
        if has_pending_job:
            return

        if not status.has_initial_analysis and status.pending_new_message_count >= status.first_analysis_limit:
            logger.info(
                "automation_live_backlog_ready pending=%s limit=%s action=evaluate_first_analysis",
                status.pending_new_message_count,
                status.first_analysis_limit,
            )
            await self.evaluate_and_schedule(trigger_source="automation")
