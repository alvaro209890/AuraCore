from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from time import perf_counter
from typing import Literal

from app.config import Settings
from app.services.memory_service import (
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
    "pruned_messages",
    "new_messages_threshold",
    "stale_memory",
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

    async def evaluate_and_schedule(
        self,
        *,
        sync_run_id: str | None = None,
    ) -> tuple[AutomationDecisionRecord, AnalysisJobRecord | None]:
        automation_settings = self.store.get_automation_settings(self.settings.default_user_id)
        persona = self.memory_service.get_current_persona()
        has_memory = bool(persona.last_analyzed_at or persona.last_snapshot_id)
        intent: AnalysisIntent = "improve_memory" if has_memory else "first_analysis"

        config = self._resolve_config_for_intent(intent=intent, automation_settings=automation_settings)
        preview = await self.memory_service.get_analysis_preview(
            target_message_count=config["target_message_count"],
            max_lookback_hours=config["max_lookback_hours"],
            detail_mode=config["detail_mode"],
        )

        if (
            intent == "improve_memory"
            and preview.should_analyze
            and config["detail_mode"] != "deep"
            and (preview.replaced_message_count > 0 or preview.recommendation_score >= 80)
        ):
            config = {**config, "detail_mode": "deep"}
            preview = await self.memory_service.get_analysis_preview(
                target_message_count=config["target_message_count"],
                max_lookback_hours=config["max_lookback_hours"],
                detail_mode=config["detail_mode"],
            )

        reason_code = self._determine_reason_code(
            preview=preview,
            has_memory=has_memory,
            automation_settings=automation_settings,
            last_analyzed_at=persona.last_analyzed_at,
        )
        daily_cost_usd = self._get_daily_cost_usd()
        daily_auto_jobs_count = self._get_daily_auto_jobs_count()
        recent_jobs = self.store.list_analysis_jobs(user_id=self.settings.default_user_id, limit=20)
        has_pending_auto_job = any(
            job.trigger_source == "automation" and job.status in {"queued", "running"}
            for job in recent_jobs
        )

        action = "queue"
        should_analyze = preview.should_analyze
        explanation = preview.recommendation_summary
        if not automation_settings.auto_analyze_enabled:
            action = "skip"
            should_analyze = False
            reason_code = "auto_analyze_disabled"
            explanation = "A automacao de analise esta desligada; o sistema registrou a oportunidade, mas nao enfileirou job."
        elif daily_cost_usd >= automation_settings.daily_budget_usd:
            action = "skip"
            should_analyze = False
            reason_code = "daily_budget_reached"
            explanation = (
                f"O custo estimado acumulado hoje ja chegou a US$ {daily_cost_usd:.4f}, acima do teto automatico configurado."
            )
        elif daily_auto_jobs_count >= automation_settings.max_auto_jobs_per_day:
            action = "skip"
            should_analyze = False
            reason_code = "max_auto_jobs_reached"
            explanation = "O limite diario de jobs automaticos ja foi atingido; a oportunidade ficou registrada para auditoria."
        elif has_pending_auto_job:
            action = "skip"
            should_analyze = False
            reason_code = "job_already_pending"
            explanation = "Ja existe um job automatico em andamento ou na fila; o sistema nao empilha outro em paralelo."
        elif not preview.should_analyze:
            action = "skip"

        decision = self.store.create_automation_decision(
            user_id=self.settings.default_user_id,
            sync_run_id=sync_run_id,
            intent=intent,
            action=action,
            reason_code=reason_code,
            score=preview.recommendation_score,
            should_analyze=should_analyze,
            available_message_count=preview.available_message_count,
            selected_message_count=preview.selected_message_count,
            new_message_count=preview.new_message_count,
            replaced_message_count=preview.replaced_message_count,
            estimated_total_tokens=preview.estimated_total_tokens,
            estimated_cost_ceiling_usd=preview.estimated_cost_total_ceiling_usd,
            explanation=explanation,
            created_at=datetime.now(UTC),
        )

        if action != "queue":
            return decision, None

        job = self.store.create_analysis_job(
            user_id=self.settings.default_user_id,
            intent=intent,
            status="queued",
            trigger_source="automation",
            decision_id=decision.id,
            sync_run_id=sync_run_id,
            target_message_count=config["target_message_count"],
            max_lookback_hours=config["max_lookback_hours"],
            detail_mode=config["detail_mode"],
            selected_message_count=preview.selected_message_count,
            selected_transcript_chars=preview.selected_transcript_chars,
            estimated_input_tokens=preview.estimated_input_tokens,
            estimated_output_tokens=preview.estimated_output_tokens,
            estimated_cost_floor_usd=preview.estimated_cost_total_floor_usd,
            estimated_cost_ceiling_usd=preview.estimated_cost_total_ceiling_usd,
            created_at=datetime.now(UTC),
        )
        return decision, job

    async def run_manual_analysis(
        self,
        *,
        intent: AnalysisIntent,
        target_message_count: int,
        max_lookback_hours: int,
        detail_mode: str,
    ) -> tuple[AnalysisJobRecord, MemoryAnalysisOutcome]:
        preview = await self.memory_service.get_analysis_preview(
            target_message_count=target_message_count,
            max_lookback_hours=max_lookback_hours,
            detail_mode=detail_mode,  # type: ignore[arg-type]
        )
        started_at = datetime.now(UTC)
        job = self.store.create_analysis_job(
            user_id=self.settings.default_user_id,
            intent=intent,
            status="running",
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
            started_at=started_at,
            created_at=started_at,
        )
        outcome = await self._execute_analysis_job(job=job, preview=preview)
        updated_job = self.store.get_analysis_job(job.id)
        if updated_job is None:
            raise RuntimeError("Manual analysis job disappeared after execution.")
        return updated_job, outcome

    async def run_manual_refinement(self) -> tuple[AnalysisJobRecord, MemoryRefinementOutcome]:
        started_at = datetime.now(UTC)
        job = self.store.create_analysis_job(
            user_id=self.settings.default_user_id,
            intent="refine_saved",
            status="running",
            trigger_source="manual",
            decision_id=None,
            sync_run_id=None,
            target_message_count=0,
            max_lookback_hours=0,
            detail_mode="balanced",
            started_at=started_at,
            created_at=started_at,
        )

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
        updated_job = self.store.get_analysis_job(job.id)
        if updated_job is None:
            raise RuntimeError("Manual refinement job disappeared after execution.")
        return updated_job, outcome

    async def execute_next_job(self) -> AnalysisJobRecord | None:
        job = self.store.claim_next_queued_analysis_job(user_id=self.settings.default_user_id)
        if job is None:
            return None

        preview = await self.memory_service.get_analysis_preview(
            target_message_count=job.target_message_count,
            max_lookback_hours=job.max_lookback_hours,
            detail_mode=job.detail_mode,  # type: ignore[arg-type]
        )
        await self._execute_analysis_job(job=job, preview=preview)
        return self.store.get_analysis_job(job.id)

    async def tick(self) -> AnalysisJobRecord | None:
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

    def _resolve_config_for_intent(
        self,
        *,
        intent: AnalysisIntent,
        automation_settings: AutomationSettingsRecord,
    ) -> dict[str, int | str]:
        if intent == "first_analysis":
            return {
                "target_message_count": min(self.settings.memory_analysis_max_messages, 250),
                "max_lookback_hours": min(self.settings.memory_analysis_max_window_hours, 168),
                "detail_mode": "deep",
            }
        return {
            "target_message_count": min(self.settings.memory_analysis_max_messages, automation_settings.default_target_message_count),
            "max_lookback_hours": min(self.settings.memory_analysis_max_window_hours, automation_settings.default_lookback_hours),
            "detail_mode": automation_settings.default_detail_mode,
        }

    def _determine_reason_code(
        self,
        *,
        preview: MemoryAnalysisPreview,
        has_memory: bool,
        automation_settings: AutomationSettingsRecord,
        last_analyzed_at: datetime | None,
    ) -> DecisionReasonCode:
        if not has_memory:
            return "first_analysis_ready" if preview.selected_message_count >= 40 else "first_analysis_more_signal"
        if preview.replaced_message_count >= automation_settings.pruned_messages_threshold:
            return "pruned_messages"
        if preview.new_message_count >= automation_settings.min_new_messages_threshold:
            return "new_messages_threshold"
        if last_analyzed_at is not None:
            hours_since_last_analysis = max(
                0.0,
                (datetime.now(UTC) - last_analyzed_at).total_seconds() / 3600,
            )
            if hours_since_last_analysis >= automation_settings.stale_hours_threshold and preview.selected_message_count >= 30:
                return "stale_memory"
        return "low_change"

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
        if outcome.source_message_ids:
            processed_at = datetime.now(UTC)
            marked_count = self.store.mark_messages_processed(
                user_id=self.settings.default_user_id,
                message_ids=outcome.source_message_ids,
                processed_at=processed_at,
            )
            if marked_count > 0:
                self.store.delete_messages_by_ids(message_ids=outcome.source_message_ids)
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
