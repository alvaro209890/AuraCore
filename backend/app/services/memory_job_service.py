from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
import logging
from time import perf_counter
from typing import Literal

from app.config import Settings
from app.services.memory_service import FixedAnalysisPlan, MemoryAnalysisError, MemoryAnalysisService
from app.services.supabase_store import AnalysisJobRecord, ModelRunRecord, SupabaseStore, WhatsAppSyncRunRecord


logger = logging.getLogger("auracore.memory_jobs")
MINIMUM_STALE_ANALYSIS_JOB_THRESHOLD = timedelta(minutes=15)
MAX_SEQUENTIAL_DEEPSEEK_CALLS_PER_ANALYSIS = 6
ANALYSIS_JOB_GRACE_SECONDS = 120


@dataclass(slots=True)
class MemoryActivitySnapshot:
    sync_runs: list[WhatsAppSyncRunRecord]
    jobs: list[AnalysisJobRecord]
    model_runs: list[ModelRunRecord]
    running_job_id: str | None


class MemoryJobService:
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
        self._enqueue_lock = asyncio.Lock()
        self._job_lock = asyncio.Lock()
        self._background_tasks: dict[str, asyncio.Task[None]] = {}

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

    def finalize_manual_sync(self, *, sync_run_id: str) -> WhatsAppSyncRunRecord | None:
        return self.store.finalize_whatsapp_sync_run(
            user_id=self.settings.default_user_id,
            sync_run_id=sync_run_id,
            finished_at=datetime.now(UTC),
        )

    async def get_activity_snapshot(self) -> MemoryActivitySnapshot:
        self._recover_stale_pending_jobs()
        sync_runs = self.store.list_whatsapp_sync_runs(user_id=self.settings.default_user_id, limit=8)
        jobs = self.store.list_analysis_jobs(user_id=self.settings.default_user_id, limit=12)
        model_runs = self.store.list_model_runs(user_id=self.settings.default_user_id, limit=12)
        running_job = next((job for job in jobs if job.status == "running"), None)
        if running_job is None:
            running_job = next((job for job in jobs if job.status == "queued"), None)
        return MemoryActivitySnapshot(
            sync_runs=sync_runs,
            jobs=jobs,
            model_runs=model_runs,
            running_job_id=running_job.id if running_job else None,
        )

    async def execute_manual_analysis(
        self,
        *,
        intent: Literal["first_analysis", "improve_memory"] | None = None,
    ) -> AnalysisJobRecord:
        async with self._enqueue_lock:
            self._ensure_no_pending_job()
            status = self.memory_service.get_memory_status()
            resolved_intent = intent or ("improve_memory" if status.has_initial_analysis else "first_analysis")
            plan = (
                self.memory_service.plan_first_analysis()
                if resolved_intent == "first_analysis"
                else self.memory_service.plan_next_batch()
            )
            created_at = datetime.now(UTC)
            job = self.store.create_analysis_job(
                user_id=self.settings.default_user_id,
                intent=plan.intent,
                status="queued",
                trigger_source="manual",
                decision_id=None,
                sync_run_id=None,
                target_message_count=len(plan.source_messages),
                max_lookback_hours=0,
                detail_mode="deep" if plan.intent == "first_analysis" else "balanced",
                selected_message_count=len(plan.source_messages),
                selected_transcript_chars=plan.selected_transcript_chars,
                estimated_input_tokens=plan.estimated_input_tokens,
                estimated_output_tokens=plan.estimated_output_tokens,
                estimated_cost_floor_usd=plan.estimated_cost_floor_usd,
                estimated_cost_ceiling_usd=plan.estimated_cost_ceiling_usd,
                created_at=created_at,
            )
            task = asyncio.create_task(
                self._run_fixed_plan_job(job_id=job.id, plan=plan),
                name=f"manual-memory-job:{job.id}",
            )
            self._background_tasks[job.id] = task
            task.add_done_callback(lambda _: self._background_tasks.pop(job.id, None))
            refreshed_job = self.store.get_analysis_job(job.id)
            if refreshed_job is None:
                raise RuntimeError("Manual memory job disappeared after creation.")
            return refreshed_job

    def _ensure_no_pending_job(self) -> None:
        self._recover_stale_pending_jobs()
        recent_jobs = self.store.list_analysis_jobs(user_id=self.settings.default_user_id, limit=20)
        now = datetime.now(UTC)
        stagnant_threshold = self._analysis_job_stale_threshold()
        pending_jobs = [
            job
            for job in recent_jobs
            if job.status in {"queued", "running"}
            and (
                now - (job.started_at if job.status == "running" and job.started_at else job.created_at)
            ) < stagnant_threshold
        ]
        if pending_jobs:
            raise MemoryAnalysisError(
                "Ja existe uma analise manual em fila ou em execucao. Aguarde a conclusao antes de iniciar outra."
            )

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
                    "Job recuperado automaticamente apos ficar travado sem conclusao "
                    f"por mais de {int(threshold.total_seconds() // 60)} minutos."
                ),
                finished_at=now,
            )
            logger.warning("stale_memory_job_recovered job_id=%s intent=%s", job.id, job.intent)

    async def _run_fixed_plan_job(
        self,
        *,
        job_id: str,
        plan: FixedAnalysisPlan,
    ) -> None:
        async with self._job_lock:
            started_at = datetime.now(UTC)
            source_message_ids = [message.message_id for message in plan.source_messages]
            self.store.update_analysis_job(
                job_id=job_id,
                status="running",
                started_at=started_at,
                error_text=None,
            )
            self.store.mark_messages_analysis_started(
                user_id=self.settings.default_user_id,
                message_ids=source_message_ids,
                job_id=job_id,
                started_at=started_at,
            )

            start_clock = perf_counter()
            try:
                outcome = await self.memory_service.execute_fixed_analysis_plan(plan)
            except Exception as error:
                latency_ms = round((perf_counter() - start_clock) * 1000)
                self.store.release_messages_from_analysis(
                    user_id=self.settings.default_user_id,
                    message_ids=source_message_ids,
                )
                self.store.update_analysis_job(
                    job_id=job_id,
                    status="failed",
                    error_text=str(error),
                    finished_at=datetime.now(UTC),
                )
                self.store.create_model_run(
                    user_id=self.settings.default_user_id,
                    job_id=job_id,
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
                logger.exception("manual_memory_job_failed job_id=%s intent=%s", job_id, plan.intent)
                return

            latency_ms = round((perf_counter() - start_clock) * 1000)
            finished_at = datetime.now(UTC)
            final_message_ids = outcome.source_message_ids or source_message_ids
            self.store.mark_messages_analyzed(
                user_id=self.settings.default_user_id,
                message_ids=final_message_ids,
                job_id=job_id,
                started_at=started_at,
                analyzed_at=finished_at,
            )
            if plan.intent == "first_analysis":
                self.store.set_observer_history_cutoff(
                    user_id=self.settings.default_user_id,
                    cutoff_at=started_at,
                )
                self.store.mark_messages_baseline_skipped_before_timestamp(
                    user_id=self.settings.default_user_id,
                    cutoff_at=started_at,
                    exclude_message_ids=final_message_ids,
                    job_id=job_id,
                    started_at=started_at,
                    analyzed_at=finished_at,
                )

            self.store.update_analysis_job(
                job_id=job_id,
                status="succeeded",
                selected_message_count=len(final_message_ids) or len(plan.source_messages),
                selected_transcript_chars=outcome.selected_transcript_chars or plan.selected_transcript_chars,
                snapshot_id=outcome.snapshot.id,
                finished_at=finished_at,
                error_text=None,
            )
            self.store.save_analysis_job_messages(job_id=job_id, message_ids=final_message_ids)
            self.store.create_model_run(
                user_id=self.settings.default_user_id,
                job_id=job_id,
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
                created_at=finished_at,
            )
            logger.info(
                "manual_memory_job_done job_id=%s intent=%s selected=%s",
                job_id,
                plan.intent,
                len(final_message_ids),
            )
