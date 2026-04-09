from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
import logging
from time import perf_counter
from typing import Literal
from zoneinfo import ZoneInfo

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
        self._important_messages_timezone = ZoneInfo("America/Sao_Paulo")

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
            await self.evaluate_and_schedule(sync_run_id=sync_run.id)
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

        action = "skip"
        should_analyze = False
        reason_code: DecisionReasonCode = "awaiting_first_analysis"
        explanation = "A memoria base ainda nao existe. A primeira analise continua sendo um passo manual unico."
        selected_message_count = memory_status.next_process_message_count
        estimated_total_tokens = 0
        estimated_cost_ceiling_usd = 0.0
        job_plan: FixedAnalysisPlan | None = None

        if memory_status.has_initial_analysis and memory_status.can_run_next_batch:
            job_plan = self.memory_service.plan_next_batch()
            selected_message_count = len(job_plan.source_messages)
            estimated_total_tokens = job_plan.estimated_input_tokens + job_plan.estimated_output_tokens
            estimated_cost_ceiling_usd = job_plan.estimated_cost_ceiling_usd

            if force_analysis and has_pending_job:
                reason_code = "job_already_pending"
                explanation = "Ja existe uma leitura em andamento ou na fila; a sincronizacao manual nao abriu outro lote em paralelo."
            elif not automation_settings.auto_analyze_enabled:
                reason_code = "auto_analyze_disabled"
                explanation = "A automacao de analise esta desligada; o backend registrou o lote disponivel, mas nao o enfileirou."
            elif daily_cost_usd >= automation_settings.daily_budget_usd:
                reason_code = "daily_budget_reached"
                explanation = (
                    f"O custo estimado acumulado hoje ja chegou a US$ {daily_cost_usd:.4f}, acima do teto automatico configurado."
                )
            elif daily_auto_jobs_count >= automation_settings.max_auto_jobs_per_day:
                reason_code = "max_auto_jobs_reached"
                explanation = "O limite diario de jobs automaticos ja foi atingido; este lote ficou aguardando acao manual."
            elif has_pending_auto_job:
                reason_code = "job_already_pending"
                explanation = "Ja existe um job automatico em andamento ou na fila; o sistema nao empilha outro lote em paralelo."
            else:
                action = "queue"
                should_analyze = True
                reason_code = "batch_ready"
                explanation = (
                    f"Existem {memory_status.pending_new_message_count} mensagens novas pendentes. "
                    f"O backend vai processar automaticamente o proximo lote economico de {selected_message_count} mensagens."
                )
        elif memory_status.has_initial_analysis:
            reason_code = "awaiting_next_batch"
            explanation = (
                f"Ainda existem {memory_status.pending_new_message_count} mensagens novas pendentes. "
                f"O proximo processamento automatico so dispara quando a fila chegar a {self.settings.memory_incremental_min_messages}."
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
        return decision, job

    async def enqueue_manual_analysis(
        self,
        *,
        intent: AnalysisIntent,
        target_message_count: int,
        max_lookback_hours: int,
        detail_mode: str,
    ) -> AnalysisJobRecord:
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
        import asyncio
        asyncio.create_task(self.tick())
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
        import asyncio
        asyncio.create_task(self.tick())
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
        import asyncio
        asyncio.create_task(self.tick())
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

        if job.intent == "refine_saved":
            await self._execute_fixed_refinement_job(job=job)
            return self.store.get_analysis_job(job.id)

        if job.max_lookback_hours == 0 and job.intent in {"first_analysis", "improve_memory"}:
            plan = (
                self.memory_service.plan_first_analysis()
                if job.intent == "first_analysis"
                else self.memory_service.plan_next_batch()
            )
            await self._execute_fixed_analysis_job(job=job, plan=plan)
            return self.store.get_analysis_job(job.id)

        preview = await self.memory_service.get_analysis_preview(
            target_message_count=job.target_message_count,
            max_lookback_hours=job.max_lookback_hours,
            detail_mode=job.detail_mode,  # type: ignore[arg-type]
        )
        await self._execute_analysis_job(job=job, preview=preview)
        return self.store.get_analysis_job(job.id)

    async def tick(self) -> AnalysisJobRecord | None:
        await self._maybe_review_important_messages()
        await self.settle_sync_runs()
        return await self.execute_next_job()

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
        recent_jobs = self.store.list_analysis_jobs(user_id=self.settings.default_user_id, limit=20)
        now = datetime.now(UTC)
        stagnant_threshold = timedelta(minutes=15)
        
        pending_jobs = [
            job for job in recent_jobs 
            if job.status in {"queued", "running"} 
            and (now - job.created_at) < stagnant_threshold
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
        important_saved_count = 0
        if outcome.source_messages:
            extract_start = perf_counter()
            try:
                important_saved_count = await self.memory_service.extract_and_store_important_messages(
                    messages=outcome.source_messages,
                    analyzed_at=datetime.now(UTC),
                )
                extract_latency_ms = round((perf_counter() - extract_start) * 1000)
                self.store.create_model_run(
                    user_id=self.settings.default_user_id,
                    job_id=job.id,
                    provider="deepseek",
                    model_name=self.settings.deepseek_model,
                    run_type="important_message_extract",
                    success=True,
                    latency_ms=extract_latency_ms,
                    input_tokens=None,
                    output_tokens=None,
                    reasoning_tokens=None,
                    estimated_cost_usd=None,
                    error_text=None,
                    created_at=datetime.now(UTC),
                )
            except Exception as error:
                extract_latency_ms = round((perf_counter() - extract_start) * 1000)
                self.store.create_model_run(
                    user_id=self.settings.default_user_id,
                    job_id=job.id,
                    provider="deepseek",
                    model_name=self.settings.deepseek_model,
                    run_type="important_message_extract",
                    success=False,
                    latency_ms=extract_latency_ms,
                    input_tokens=None,
                    output_tokens=None,
                    reasoning_tokens=None,
                    estimated_cost_usd=None,
                    error_text=str(error),
                    created_at=datetime.now(UTC),
                )
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
            "analysis_job_done job_id=%s intent=%s selected=%s important_saved=%s",
            job.id,
            job.intent,
            len(outcome.source_message_ids),
            important_saved_count,
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
        important_saved_count = 0
        if outcome.source_messages:
            extract_start = perf_counter()
            try:
                important_saved_count = await self.memory_service.extract_and_store_important_messages(
                    messages=outcome.source_messages,
                    analyzed_at=datetime.now(UTC),
                )
                extract_latency_ms = round((perf_counter() - extract_start) * 1000)
                self.store.create_model_run(
                    user_id=self.settings.default_user_id,
                    job_id=job.id,
                    provider="deepseek",
                    model_name=self.settings.deepseek_model,
                    run_type="important_message_extract",
                    success=True,
                    latency_ms=extract_latency_ms,
                    input_tokens=None,
                    output_tokens=None,
                    reasoning_tokens=None,
                    estimated_cost_usd=None,
                    error_text=None,
                    created_at=datetime.now(UTC),
                )
            except Exception as error:
                extract_latency_ms = round((perf_counter() - extract_start) * 1000)
                self.store.create_model_run(
                    user_id=self.settings.default_user_id,
                    job_id=job.id,
                    provider="deepseek",
                    model_name=self.settings.deepseek_model,
                    run_type="important_message_extract",
                    success=False,
                    latency_ms=extract_latency_ms,
                    input_tokens=None,
                    output_tokens=None,
                    reasoning_tokens=None,
                    estimated_cost_usd=None,
                    error_text=str(error),
                    created_at=datetime.now(UTC),
                )
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
            "fixed_analysis_job_done job_id=%s intent=%s selected=%s important_saved=%s",
            job.id,
            job.intent,
            len(outcome.source_message_ids),
            important_saved_count,
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
        return outcome

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

    async def _maybe_review_important_messages(self) -> None:
        local_now = datetime.now(self._important_messages_timezone)
        review_cutoff_local = local_now.replace(hour=0, minute=0, second=0, microsecond=0)
        review_cutoff = review_cutoff_local.astimezone(UTC)

        start_clock = perf_counter()
        try:
            outcome = await self.memory_service.review_important_messages(
                reviewed_before=review_cutoff,
                limit=120,
            )
        except Exception as error:
            latency_ms = round((perf_counter() - start_clock) * 1000)
            self.store.create_model_run(
                user_id=self.settings.default_user_id,
                job_id=None,
                provider="deepseek",
                model_name=self.settings.deepseek_model,
                run_type="important_message_review",
                success=False,
                latency_ms=latency_ms,
                input_tokens=None,
                output_tokens=None,
                reasoning_tokens=None,
                estimated_cost_usd=None,
                error_text=str(error),
                created_at=datetime.now(UTC),
            )
            return

        if outcome.reviewed_count == 0:
            return

        latency_ms = round((perf_counter() - start_clock) * 1000)
        self.store.create_model_run(
            user_id=self.settings.default_user_id,
            job_id=None,
            provider="deepseek",
            model_name=self.settings.deepseek_model,
            run_type="important_message_review",
            success=True,
            latency_ms=latency_ms,
            input_tokens=None,
            output_tokens=None,
            reasoning_tokens=None,
            estimated_cost_usd=None,
            error_text=None,
            created_at=outcome.reviewed_at or datetime.now(UTC),
        )
