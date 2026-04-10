from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
import logging
from math import ceil
import re
from typing import Literal
from uuid import uuid4

from app.config import Settings
from app.services.deepseek_service import (
    DeepSeekContactMemoryRefinementResult,
    DeepSeekMemoryResult,
    DeepSeekProjectMemory,
    DeepSeekProjectMergeResult,
    DeepSeekService,
)
from app.services.groq_service import GroqChatService
from app.services.supabase_store import (
    AutomationSettingsRecord,
    ChatMessageRecord,
    ImportantMessageRecord,
    ImportantMessageReviewSeed,
    ImportantMessageSeed,
    MemorySnapshotRecord,
    MessageRetentionStateRecord,
    PersonMemoryRecord,
    PersonMemorySeed,
    PersonaRecord,
    ProjectMemoryRecord,
    ProjectMemorySeed,
    StoredMessageRecord,
    SupabaseStore,
)


class MemoryAnalysisError(RuntimeError):
    """Raised when a memory analysis request cannot be completed."""


logger = logging.getLogger("auracore.memory_analysis")


@dataclass(slots=True)
class MemoryAnalysisOutcome:
    persona: PersonaRecord
    snapshot: MemorySnapshotRecord
    projects: list[ProjectMemoryRecord]
    important_messages_saved_count: int = 0
    source_message_ids: list[str] = field(default_factory=list)
    source_messages: list[StoredMessageRecord] = field(default_factory=list)
    selected_transcript_chars: int = 0


@dataclass(slots=True)
class MemoryRefinementOutcome:
    persona: PersonaRecord
    projects: list[ProjectMemoryRecord]


@dataclass(slots=True)
class ImportantMessagesReviewOutcome:
    reviewed_count: int
    kept_count: int
    discarded_count: int
    reviewed_at: datetime | None = None


@dataclass(slots=True)
class MemoryAnalysisPreview:
    target_message_count: int
    max_lookback_hours: int
    detail_mode: Literal["light", "balanced", "deep"]
    deepseek_model: str
    available_message_count: int
    selected_message_count: int
    new_message_count: int
    replaced_message_count: int
    retained_message_count: int
    retention_limit: int
    current_char_budget: int
    selected_transcript_chars: int
    selected_transcript_tokens: int
    average_selected_message_chars: int
    average_selected_message_tokens: int
    estimated_prompt_context_tokens: int
    model_context_limit_floor_tokens: int
    model_context_limit_ceiling_tokens: int
    safe_input_budget_floor_tokens: int
    safe_input_budget_ceiling_tokens: int
    remaining_input_headroom_floor_tokens: int
    remaining_input_headroom_ceiling_tokens: int
    model_default_output_tokens: int
    model_max_output_tokens: int
    request_output_reserve_tokens: int
    estimated_reasoning_tokens: int
    planner_message_capacity: int
    stack_max_message_capacity: int
    model_message_capacity_floor: int
    model_message_capacity_ceiling: int
    estimated_input_tokens: int
    estimated_output_tokens: int
    estimated_total_tokens: int
    estimated_cost_input_floor_usd: float
    estimated_cost_input_ceiling_usd: float
    estimated_cost_output_floor_usd: float
    estimated_cost_output_ceiling_usd: float
    estimated_cost_total_floor_usd: float
    estimated_cost_total_ceiling_usd: float
    documentation_context_note: str
    documentation_pricing_note: str
    recommendation_score: int
    recommendation_label: str
    recommendation_summary: str
    should_analyze: bool


@dataclass(slots=True)
class MemoryStatus:
    has_initial_analysis: bool
    last_analyzed_at: datetime | None
    new_messages_after_first_analysis: int
    first_analysis_limit: int
    incremental_batch_size: int
    incremental_min_messages: int

    @property
    def pending_new_message_count(self) -> int:
        return self.new_messages_after_first_analysis

    @property
    def next_process_message_count(self) -> int:
        limit = self.first_analysis_limit if not self.has_initial_analysis else self.incremental_batch_size
        return min(self.pending_new_message_count, max(0, limit))

    @property
    def can_run_next_batch(self) -> bool:
        if self.pending_new_message_count <= 0 or self.next_process_message_count <= 0:
            return False
        if not self.has_initial_analysis:
            return True
        return self.pending_new_message_count >= self.incremental_min_messages


@dataclass(slots=True)
class FixedAnalysisPlan:
    intent: Literal["first_analysis", "improve_memory"]
    source_messages: list[StoredMessageRecord]
    transcript: str
    conversation_context: str
    people_memory_context: str
    window_hours: int
    window_start: datetime
    window_end: datetime
    selected_transcript_chars: int
    estimated_input_tokens: int
    estimated_output_tokens: int
    estimated_reasoning_tokens: int
    estimated_cost_floor_usd: float
    estimated_cost_ceiling_usd: float


class MemoryAnalysisService:
    def __init__(
        self,
        *,
        settings: Settings,
        store: SupabaseStore,
        deepseek_service: DeepSeekService,
        groq_service: GroqChatService | None = None,
    ) -> None:
        self.settings = settings
        self.store = store
        self.deepseek_service = deepseek_service
        self.groq_service = groq_service

    def get_memory_status(self) -> MemoryStatus:
        persona = self.get_current_persona()
        has_initial_analysis = bool(persona.last_analyzed_at or persona.last_snapshot_id)
        pending_new_message_count = self.store.count_pending_messages(self.settings.default_user_id)
        return MemoryStatus(
            has_initial_analysis=has_initial_analysis,
            last_analyzed_at=persona.last_analyzed_at,
            new_messages_after_first_analysis=pending_new_message_count,
            first_analysis_limit=self._resolve_first_analysis_limit(),
            incremental_batch_size=self._resolve_incremental_batch_size(),
            incremental_min_messages=self._resolve_incremental_min_messages(),
        )

    def plan_first_analysis(self) -> FixedAnalysisPlan:
        return self._build_fixed_analysis_plan(mode="first_analysis")

    def plan_next_batch(self) -> FixedAnalysisPlan:
        return self._build_fixed_analysis_plan(mode="incremental_batch")

    async def analyze_first_pending_messages(self) -> tuple[FixedAnalysisPlan, MemoryAnalysisOutcome]:
        plan = self.plan_first_analysis()
        return plan, await self._analyze_fixed_plan(plan)

    async def analyze_next_pending_batch(self) -> tuple[FixedAnalysisPlan, MemoryAnalysisOutcome]:
        plan = self.plan_next_batch()
        return plan, await self._analyze_fixed_plan(plan)

    async def execute_fixed_analysis_plan(self, plan: FixedAnalysisPlan) -> MemoryAnalysisOutcome:
        return await self._analyze_fixed_plan(plan)

    async def analyze_window(self, *, window_hours: int) -> MemoryAnalysisOutcome:
        if window_hours > self.settings.memory_analysis_max_window_hours:
            raise MemoryAnalysisError(
                f"A janela maxima de analise e de {self.settings.memory_analysis_max_window_hours} horas."
            )

        window_end = datetime.now(UTC)
        window_start = window_end - timedelta(hours=window_hours)
        messages = self.store.list_messages_in_window(
            user_id=self.settings.default_user_id,
            window_start=window_start,
            window_end=window_end,
        )
        if not messages:
            raise MemoryAnalysisError(
                "Nenhuma mensagem foi encontrada nessa janela. Se acabou de conectar o WhatsApp, "
                "use 'Resetar sessao' e leia o QR novamente para puxar o historico inicial."
            )

        transcript, included_messages = self._build_transcript(messages)
        if not transcript.strip() or not included_messages:
            raise MemoryAnalysisError("Essa janela nao contem mensagens textuais analisaveis.")

        current_persona = self.get_current_persona()
        current_summary = self._build_persona_context(current_persona)
        prior_analyses_context = self._build_prior_analyses_context()
        project_context = self._build_project_context(
            self.store.list_project_memories(
                self.settings.default_user_id,
                limit=max(1, self.settings.chat_context_projects),
            )
        )
        chat_context = self._build_chat_context()
        conversation_context = self._build_conversation_context(included_messages)
        people_memory_context = self._build_people_memory_context(included_messages)
        deepseek_result = await self.deepseek_service.analyze_memory(
            transcript=transcript,
            conversation_context=conversation_context,
            people_memory_context=people_memory_context,
            current_life_summary=current_summary,
            prior_analyses_context=prior_analyses_context,
            project_context=project_context,
            chat_context=chat_context,
            intent="improve_memory" if current_persona.last_analyzed_at else "first_analysis",
            window_hours=window_hours,
            window_start=window_start,
            window_end=window_end,
            source_message_count=len(included_messages),
        )

        effective_life_summary = self._resolve_effective_life_summary(
            deepseek_result.updated_life_summary,
            fallback_summary=current_summary,
        )

        snapshot = self._build_snapshot(
            result=deepseek_result,
            window_hours=window_hours,
            window_start=window_start,
            window_end=window_end,
            source_message_count=len(included_messages),
            created_at=window_end,
        )
        structural_strengths, structural_routines, structural_preferences, structural_open_questions = (
            self._build_structural_profile_from_snapshots(
                [
                    snapshot,
                    *self.store.list_memory_snapshots(
                        self.settings.default_user_id,
                        limit=max(1, self.settings.memory_analysis_context_snapshots + 7),
                    ),
                ]
            )
        )
        persona = self.store.persist_memory_analysis(
            snapshot=snapshot,
            updated_life_summary=effective_life_summary,
            analyzed_at=window_end,
            structural_strengths=structural_strengths,
            structural_routines=structural_routines,
            structural_preferences=structural_preferences,
            structural_open_questions=structural_open_questions,
        )
        self._persist_person_memories(
            messages=included_messages,
            deepseek_result=deepseek_result,
            source_snapshot_id=snapshot.id,
            analyzed_at=window_end,
        )
        projects = self.store.upsert_project_memories(
            user_id=self.settings.default_user_id,
            source_snapshot_id=snapshot.id,
            projects=[
                ProjectMemorySeed(
                    project_name=project.name,
                    summary=project.summary,
                    status=project.status,
                    what_is_being_built=project.what_is_being_built,
                    built_for=project.built_for,
                    next_steps=project.next_steps,
                    evidence=project.evidence,
                )
                for project in deepseek_result.active_projects
            ],
            observed_at=window_end,
        )
        return MemoryAnalysisOutcome(
            persona=persona,
            snapshot=snapshot,
            projects=projects,
            source_message_ids=[message.message_id for message in included_messages],
            source_messages=included_messages,
            selected_transcript_chars=len(transcript),
        )

    async def analyze_selection(
        self,
        *,
        target_message_count: int,
        max_lookback_hours: int,
        detail_mode: Literal["light", "balanced", "deep"],
    ) -> MemoryAnalysisOutcome:
        if max_lookback_hours > self.settings.memory_analysis_max_window_hours:
            raise MemoryAnalysisError(
                f"O alcance maximo de leitura e de {self.settings.memory_analysis_max_window_hours} horas."
            )

        resolved_target_count = max(20, min(target_message_count, self.settings.memory_analysis_max_messages))
        resolved_char_budget = self._resolve_char_budget(detail_mode)

        window_end = datetime.now(UTC)
        window_start = window_end - timedelta(hours=max_lookback_hours)
        messages = self.store.list_messages_in_window(
            user_id=self.settings.default_user_id,
            window_start=window_start,
            window_end=window_end,
        )
        if not messages:
            raise MemoryAnalysisError(
                "Nenhuma mensagem foi encontrada nesse alcance. Se acabou de conectar o WhatsApp, "
                "use 'Resetar sessao' e leia o QR novamente para puxar o historico inicial."
            )

        transcript, included_messages = self._build_transcript(
            messages,
            max_messages=resolved_target_count,
            char_budget=resolved_char_budget,
        )
        if not transcript.strip() or not included_messages:
            raise MemoryAnalysisError("As configuracoes escolhidas nao produziram mensagens textuais analisaveis.")

        current_persona = self.get_current_persona()
        current_summary = self._build_persona_context(current_persona)
        prior_analyses_context = self._build_prior_analyses_context()
        project_context = self._build_project_context(
            self.store.list_project_memories(
                self.settings.default_user_id,
                limit=max(1, self.settings.chat_context_projects),
            )
        )
        chat_context = self._build_chat_context()
        conversation_context = self._build_conversation_context(included_messages)
        people_memory_context = self._build_people_memory_context(included_messages)
        deepseek_result = await self.deepseek_service.analyze_memory(
            transcript=transcript,
            conversation_context=conversation_context,
            people_memory_context=people_memory_context,
            current_life_summary=current_summary,
            prior_analyses_context=prior_analyses_context,
            project_context=project_context,
            chat_context=chat_context,
            intent="improve_memory" if current_persona.last_analyzed_at else "first_analysis",
            window_hours=max_lookback_hours,
            window_start=window_start,
            window_end=window_end,
            source_message_count=len(included_messages),
        )

        effective_life_summary = self._resolve_effective_life_summary(
            deepseek_result.updated_life_summary,
            fallback_summary=current_summary,
        )

        snapshot = self._build_snapshot(
            result=deepseek_result,
            window_hours=max_lookback_hours,
            window_start=window_start,
            window_end=window_end,
            source_message_count=len(included_messages),
            created_at=window_end,
        )
        structural_strengths, structural_routines, structural_preferences, structural_open_questions = (
            self._build_structural_profile_from_snapshots(
                [
                    snapshot,
                    *self.store.list_memory_snapshots(
                        self.settings.default_user_id,
                        limit=max(1, self.settings.memory_analysis_context_snapshots + 7),
                    ),
                ]
            )
        )
        persona = self.store.persist_memory_analysis(
            snapshot=snapshot,
            updated_life_summary=effective_life_summary,
            analyzed_at=window_end,
            structural_strengths=structural_strengths,
            structural_routines=structural_routines,
            structural_preferences=structural_preferences,
            structural_open_questions=structural_open_questions,
        )
        self._persist_person_memories(
            messages=included_messages,
            deepseek_result=deepseek_result,
            source_snapshot_id=snapshot.id,
            analyzed_at=window_end,
        )
        projects = self.store.upsert_project_memories(
            user_id=self.settings.default_user_id,
            source_snapshot_id=snapshot.id,
            projects=[
                ProjectMemorySeed(
                    project_name=project.name,
                    summary=project.summary,
                    status=project.status,
                    what_is_being_built=project.what_is_being_built,
                    built_for=project.built_for,
                    next_steps=project.next_steps,
                    evidence=project.evidence,
                )
                for project in deepseek_result.active_projects
            ],
            observed_at=window_end,
        )
        return MemoryAnalysisOutcome(
            persona=persona,
            snapshot=snapshot,
            projects=projects,
            source_message_ids=[message.message_id for message in included_messages],
            source_messages=included_messages,
            selected_transcript_chars=len(transcript),
        )

    async def get_analysis_preview(
        self,
        *,
        target_message_count: int,
        max_lookback_hours: int,
        detail_mode: Literal["light", "balanced", "deep"],
    ) -> MemoryAnalysisPreview:
        if max_lookback_hours > self.settings.memory_analysis_max_window_hours:
            raise MemoryAnalysisError(
                f"O alcance maximo de leitura e de {self.settings.memory_analysis_max_window_hours} horas."
            )

        resolved_target_count = max(20, min(target_message_count, self.settings.memory_analysis_max_messages))
        resolved_char_budget = self._resolve_char_budget(detail_mode)
        window_end = datetime.now(UTC)
        window_start = window_end - timedelta(hours=max_lookback_hours)
        messages = self.store.list_messages_in_window(
            user_id=self.settings.default_user_id,
            window_start=window_start,
            window_end=window_end,
        )
        available_message_count = len(messages)
        retained_message_count = self.store.count_messages(self.settings.default_user_id)
        current_persona = self.get_current_persona()
        automation_settings = self.store.get_automation_settings(self.settings.default_user_id)
        has_memory = current_persona.last_analyzed_at is not None or bool(current_persona.last_snapshot_id)
        resolved_intent = "improve_memory" if has_memory else "first_analysis"
        new_message_count, replaced_message_count = self._resolve_message_deltas_since_last_analysis(current_persona)
        transcript, included_messages = self._build_transcript(
            messages,
            max_messages=resolved_target_count,
            char_budget=resolved_char_budget,
        )
        selected_message_count = len(included_messages)
        selected_transcript_chars = len(transcript)
        selected_transcript_tokens = self._estimate_text_tokens(transcript)
        average_selected_message_chars = round(selected_transcript_chars / selected_message_count) if selected_message_count else 0
        average_selected_message_tokens = round(selected_transcript_tokens / selected_message_count) if selected_message_count else 0

        prior_analyses_context = self._build_prior_analyses_context()
        project_context = self._build_project_context(
            self.store.list_project_memories(
                self.settings.default_user_id,
                limit=max(1, self.settings.chat_context_projects),
            )
        )
        chat_context = self._build_chat_context()
        conversation_context = self._build_conversation_context(included_messages)
        people_memory_context = self._build_people_memory_context(included_messages)
        prompt_preview = self.deepseek_service.build_analysis_prompt_preview(
            transcript=transcript,
            conversation_context=conversation_context,
            people_memory_context=people_memory_context,
            current_life_summary=self._build_persona_context(current_persona),
            prior_analyses_context=prior_analyses_context,
            project_context=project_context,
            chat_context=chat_context,
            window_hours=max_lookback_hours,
            window_start=window_start,
            window_end=window_end,
            source_message_count=selected_message_count,
        )
        estimated_input_tokens = self._estimate_text_tokens(prompt_preview.system_prompt) + self._estimate_text_tokens(prompt_preview.user_prompt)
        estimated_prompt_context_tokens = max(0, estimated_input_tokens - selected_transcript_tokens)
        planning_profile = self.deepseek_service.get_planning_profile(intent=resolved_intent)
        safe_input_budget_floor_tokens = max(
            0,
            planning_profile.context_limit_floor_tokens - planning_profile.request_output_reserve_tokens,
        )
        safe_input_budget_ceiling_tokens = max(
            0,
            planning_profile.context_limit_ceiling_tokens - planning_profile.request_output_reserve_tokens,
        )
        remaining_input_headroom_floor_tokens = max(0, safe_input_budget_floor_tokens - estimated_input_tokens)
        remaining_input_headroom_ceiling_tokens = max(0, safe_input_budget_ceiling_tokens - estimated_input_tokens)
        model_message_capacity_floor, model_message_capacity_ceiling = self._estimate_model_message_capacities(
            average_message_tokens=average_selected_message_tokens,
            estimated_prompt_context_tokens=estimated_prompt_context_tokens,
            safe_input_budget_floor_tokens=safe_input_budget_floor_tokens,
            safe_input_budget_ceiling_tokens=safe_input_budget_ceiling_tokens,
        )
        planner_message_capacity, stack_max_message_capacity = self._estimate_stack_message_capacities(
            average_message_chars=average_selected_message_chars,
            model_message_capacity_floor=model_message_capacity_floor,
            current_char_budget=resolved_char_budget,
        )
        estimated_reasoning_tokens, estimated_output_tokens = self._estimate_output_usage(
            estimated_input_tokens=estimated_input_tokens,
            detail_mode=detail_mode,
            output_reserve_tokens=planning_profile.request_output_reserve_tokens,
        )
        (
            estimated_cost_input_floor_usd,
            estimated_cost_input_ceiling_usd,
            estimated_cost_output_floor_usd,
            estimated_cost_output_ceiling_usd,
            estimated_cost_total_floor_usd,
            estimated_cost_total_ceiling_usd,
        ) = self._estimate_cost_range_usd(
            input_tokens=estimated_input_tokens,
            output_tokens=estimated_output_tokens,
            input_price_floor_per_million=planning_profile.cache_miss_input_price_floor_per_million,
            input_price_ceiling_per_million=planning_profile.cache_miss_input_price_ceiling_per_million,
            output_price_floor_per_million=planning_profile.output_price_floor_per_million,
            output_price_ceiling_per_million=planning_profile.output_price_ceiling_per_million,
        )
        estimated_total_tokens = estimated_input_tokens + estimated_output_tokens
        fallback_score = self._score_analysis_opportunity(
            persona=current_persona,
            available_message_count=available_message_count,
            selected_message_count=selected_message_count,
            new_message_count=new_message_count,
            replaced_message_count=replaced_message_count,
            estimated_total_tokens=estimated_total_tokens,
        )
        fallback_label = self._label_for_score(fallback_score)
        (
            recommendation_score,
            recommendation_label,
            should_analyze,
            recommendation_summary,
        ) = self._build_rule_based_recommendation(
            automation_settings=automation_settings,
            persona=current_persona,
            has_memory=has_memory,
            available_message_count=available_message_count,
            selected_message_count=selected_message_count,
            new_message_count=new_message_count,
            replaced_message_count=replaced_message_count,
            estimated_total_tokens=estimated_total_tokens,
            stack_max_message_capacity=stack_max_message_capacity,
            estimated_cost_total_ceiling_usd=estimated_cost_total_ceiling_usd,
            fallback_score=fallback_score,
            fallback_label=fallback_label,
        )

        return MemoryAnalysisPreview(
            target_message_count=resolved_target_count,
            max_lookback_hours=max_lookback_hours,
            detail_mode=detail_mode,
            deepseek_model=planning_profile.model_name,
            available_message_count=available_message_count,
            selected_message_count=selected_message_count,
            new_message_count=new_message_count,
            replaced_message_count=replaced_message_count,
            retained_message_count=retained_message_count,
            retention_limit=self.store.first_analysis_queue_limit,
            current_char_budget=resolved_char_budget,
            selected_transcript_chars=selected_transcript_chars,
            selected_transcript_tokens=selected_transcript_tokens,
            average_selected_message_chars=average_selected_message_chars,
            average_selected_message_tokens=average_selected_message_tokens,
            estimated_prompt_context_tokens=estimated_prompt_context_tokens,
            model_context_limit_floor_tokens=planning_profile.context_limit_floor_tokens,
            model_context_limit_ceiling_tokens=planning_profile.context_limit_ceiling_tokens,
            safe_input_budget_floor_tokens=safe_input_budget_floor_tokens,
            safe_input_budget_ceiling_tokens=safe_input_budget_ceiling_tokens,
            remaining_input_headroom_floor_tokens=remaining_input_headroom_floor_tokens,
            remaining_input_headroom_ceiling_tokens=remaining_input_headroom_ceiling_tokens,
            model_default_output_tokens=planning_profile.default_output_tokens,
            model_max_output_tokens=planning_profile.maximum_output_tokens,
            request_output_reserve_tokens=planning_profile.request_output_reserve_tokens,
            estimated_reasoning_tokens=estimated_reasoning_tokens,
            planner_message_capacity=planner_message_capacity,
            stack_max_message_capacity=stack_max_message_capacity,
            model_message_capacity_floor=model_message_capacity_floor,
            model_message_capacity_ceiling=model_message_capacity_ceiling,
            estimated_input_tokens=estimated_input_tokens,
            estimated_output_tokens=estimated_output_tokens,
            estimated_total_tokens=estimated_total_tokens,
            estimated_cost_input_floor_usd=estimated_cost_input_floor_usd,
            estimated_cost_input_ceiling_usd=estimated_cost_input_ceiling_usd,
            estimated_cost_output_floor_usd=estimated_cost_output_floor_usd,
            estimated_cost_output_ceiling_usd=estimated_cost_output_ceiling_usd,
            estimated_cost_total_floor_usd=estimated_cost_total_floor_usd,
            estimated_cost_total_ceiling_usd=estimated_cost_total_ceiling_usd,
            documentation_context_note=planning_profile.context_note,
            documentation_pricing_note=planning_profile.pricing_note,
            recommendation_score=recommendation_score,
            recommendation_label=recommendation_label,
            recommendation_summary=recommendation_summary,
            should_analyze=should_analyze,
        )

    def get_current_persona(self) -> PersonaRecord:
        persona = self.store.get_persona(self.settings.default_user_id)
        if persona is None:
            return PersonaRecord(
                user_id=self.settings.default_user_id,
                life_summary="",
                last_analyzed_at=None,
                last_snapshot_id=None,
                last_analyzed_ingested_count=None,
                last_analyzed_pruned_count=None,
                structural_strengths=[],
                structural_routines=[],
                structural_preferences=[],
                structural_open_questions=[],
            )

        needs_structural_backfill = not (
            persona.structural_strengths
            and persona.structural_routines
            and persona.structural_preferences
            and persona.structural_open_questions
        )
        if not needs_structural_backfill:
            return persona

        snapshots = self.store.list_memory_snapshots(self.settings.default_user_id, limit=8)
        if not snapshots:
            return persona

        (
            computed_strengths,
            computed_routines,
            computed_preferences,
            computed_open_questions,
        ) = self._build_structural_profile_from_snapshots(snapshots)
        next_strengths = persona.structural_strengths or computed_strengths
        next_routines = persona.structural_routines or computed_routines
        next_preferences = persona.structural_preferences or computed_preferences
        next_open_questions = persona.structural_open_questions or computed_open_questions

        if (
            next_strengths == persona.structural_strengths
            and next_routines == persona.structural_routines
            and next_preferences == persona.structural_preferences
            and next_open_questions == persona.structural_open_questions
        ):
            return persona

        return self.store.update_persona_structural_profile(
            user_id=self.settings.default_user_id,
            structural_strengths=next_strengths,
            structural_routines=next_routines,
            structural_preferences=next_preferences,
            structural_open_questions=next_open_questions,
            updated_at=datetime.now(UTC),
        )

    def _resolve_message_deltas_since_last_analysis(self, persona: PersonaRecord) -> tuple[int, int]:
        pending_count = self.store.count_pending_messages(self.settings.default_user_id)
        retention_state = self.store.get_message_retention_state(self.settings.default_user_id)
        baseline_ingested = persona.last_analyzed_ingested_count
        baseline_pruned = persona.last_analyzed_pruned_count
        baseline_missing_or_stale = (
            baseline_ingested is None
            or baseline_ingested > retention_state.total_direct_ingested_count
        )
        if (persona.last_analyzed_at or persona.last_snapshot_id) and baseline_missing_or_stale:
            return pending_count, 0

        replaced_message_count = (
            max(0, retention_state.total_direct_pruned_count - baseline_pruned)
            if baseline_pruned is not None and baseline_pruned <= retention_state.total_direct_pruned_count
            else 0
        )
        return pending_count, replaced_message_count

    def _count_new_messages_since_last_analysis(self, persona: PersonaRecord) -> int:
        new_message_count, _ = self._resolve_message_deltas_since_last_analysis(persona)
        return new_message_count

    def _resolve_first_analysis_limit(self) -> int:
        return max(
            40,
            min(
                self.store.first_analysis_queue_limit,
                self.settings.memory_analysis_max_messages,
            ),
        )

    def _resolve_incremental_batch_size(self) -> int:
        return max(
            8,
            min(
                self.settings.memory_incremental_batch_size,
                self.settings.memory_analysis_max_messages,
                self.settings.message_retention_max_rows,
            ),
        )

    def _resolve_incremental_min_messages(self) -> int:
        return max(6, min(self.settings.memory_incremental_min_messages, self._resolve_incremental_batch_size()))

    def _resolve_fixed_plan_char_budget(self, mode: Literal["first_analysis", "incremental_batch"]) -> int:
        target = 28000 if mode == "first_analysis" else 14000
        return min(self.settings.memory_analysis_max_chars, target)

    def _select_balanced_messages(
        self,
        messages: list[StoredMessageRecord],
        *,
        max_messages: int,
        prefer_recent: bool,
    ) -> list[StoredMessageRecord]:
        if not messages:
            return []

        ordered = sorted(messages, key=lambda message: message.timestamp, reverse=prefer_recent)
        groups: dict[str, list[StoredMessageRecord]] = {}
        for message in ordered:
            person_key = self.store.build_person_key(
                contact_phone=message.contact_phone,
                chat_jid=message.chat_jid,
                contact_name=message.contact_name,
            )
            groups.setdefault(person_key, []).append(message)

        ordered_keys = sorted(
            groups.keys(),
            key=lambda key: groups[key][0].timestamp,
            reverse=prefer_recent,
        )
        offsets = {key: 0 for key in ordered_keys}
        selected: list[StoredMessageRecord] = []

        while len(selected) < max_messages:
            progressed = False
            for key in ordered_keys:
                index = offsets[key]
                group = groups[key]
                if index >= len(group):
                    continue
                selected.append(group[index])
                offsets[key] = index + 1
                progressed = True
                if len(selected) >= max_messages:
                    break
            if not progressed:
                break

        return sorted(selected, key=lambda message: message.timestamp)

    def _build_persona_context(self, persona: PersonaRecord) -> str:
        sections: list[str] = []
        if persona.life_summary.strip():
            sections.append(persona.life_summary.strip())
        if persona.structural_strengths:
            sections.append("Forcas recorrentes:\n- " + "\n- ".join(persona.structural_strengths[:6]))
        if persona.structural_routines:
            sections.append("Rotina recorrente:\n- " + "\n- ".join(persona.structural_routines[:6]))
        if persona.structural_preferences:
            sections.append("Preferencias operacionais:\n- " + "\n- ".join(persona.structural_preferences[:6]))
        if persona.structural_open_questions:
            sections.append("Lacunas ainda abertas:\n- " + "\n- ".join(persona.structural_open_questions[:5]))
        return "\n\n".join(section for section in sections if section).strip()

    def _resolve_effective_life_summary(self, raw_summary: str, *, fallback_summary: str) -> str:
        normalized_summary = str(raw_summary or "").strip()
        if normalized_summary:
            return normalized_summary
        return str(fallback_summary or "").strip()

    def _build_structural_profile_from_snapshots(
        self,
        snapshots: list[MemorySnapshotRecord],
    ) -> tuple[list[str], list[str], list[str], list[str]]:
        recent_snapshots = snapshots[:8]
        return (
            self._rank_snapshot_signal_lines(
                recent_snapshots,
                extractor=lambda snapshot: [*snapshot.key_learnings, *snapshot.people_and_relationships],
                limit=8,
                minimum_score=3,
            ),
            self._rank_snapshot_signal_lines(
                recent_snapshots,
                extractor=lambda snapshot: snapshot.routine_signals,
                limit=8,
                minimum_score=3,
            ),
            self._rank_snapshot_signal_lines(
                recent_snapshots,
                extractor=lambda snapshot: snapshot.preferences,
                limit=8,
                minimum_score=3,
            ),
            self._rank_snapshot_signal_lines(
                recent_snapshots,
                extractor=lambda snapshot: snapshot.open_questions,
                limit=6,
                minimum_score=6,
            ),
        )

    def _rank_snapshot_signal_lines(
        self,
        snapshots: list[MemorySnapshotRecord],
        *,
        extractor,
        limit: int,
        minimum_score: int,
    ) -> list[str]:
        if not snapshots:
            return []

        score_by_key: dict[str, int] = {}
        value_by_key: dict[str, str] = {}
        latest_keys: set[str] = set()

        for index, snapshot in enumerate(snapshots):
            weight = max(1, 8 - index)
            if index == 0:
                weight += 3
            elif index == 1:
                weight += 1

            raw_items = extractor(snapshot)
            cleaned_items: list[str] = []
            for item in raw_items:
                text = " ".join(str(item).split()).strip()
                if text:
                    cleaned_items.append(text)

            if index == 0:
                latest_keys = {item.casefold() for item in cleaned_items}

            for position, item in enumerate(cleaned_items[:8]):
                key = item.casefold()
                score_by_key[key] = score_by_key.get(key, 0) + max(1, weight - (position // 2))
                value_by_key.setdefault(key, item)

        ranked = sorted(
            score_by_key.items(),
            key=lambda item: (-item[1], value_by_key[item[0]].casefold()),
        )

        selected: list[str] = []
        for key, score in ranked:
            if key not in latest_keys and score < minimum_score:
                continue
            selected.append(value_by_key[key])
            if len(selected) >= limit:
                break
        return selected

    def _build_fixed_analysis_plan(
        self,
        *,
        mode: Literal["first_analysis", "incremental_batch"],
    ) -> FixedAnalysisPlan:
        status = self.get_memory_status()
        pending_count = status.new_messages_after_first_analysis

        if mode == "first_analysis":
            if status.has_initial_analysis:
                raise MemoryAnalysisError("A primeira analise ja foi concluida. Use o processamento por lotes daqui para frente.")
            if pending_count <= 0:
                raise MemoryAnalysisError("Ainda nao ha mensagens novas para a primeira analise.")
            candidate_messages = self.store.list_pending_messages(
                user_id=self.settings.default_user_id,
                limit=min(
                    self.settings.message_retention_max_rows,
                    max(self._resolve_first_analysis_limit() * 4, min(pending_count, self._resolve_first_analysis_limit() * 8)),
                ),
                newest_first=True,
            )
            # Prioriza mensagens que tenham texto útil
            textual_candidates = [m for m in candidate_messages if m.message_text.strip()]
            
            if not textual_candidates and pending_count > 0:
                raise MemoryAnalysisError(
                    f"Encontrei {pending_count} mensagens pendentes, mas nenhuma delas contém texto analisável (apenas imagens, áudios ou figurinhas)."
                )

            selected_messages = self._select_balanced_messages(
                textual_candidates,
                max_messages=min(self._resolve_first_analysis_limit(), len(textual_candidates)),
                prefer_recent=True,
            )
            intent: Literal["first_analysis", "improve_memory"] = "first_analysis"
            detail_mode: Literal["light", "balanced", "deep"] = "deep"
        else:
            if not status.has_initial_analysis:
                raise MemoryAnalysisError("A primeira analise ainda nao foi feita. Rode-a antes de processar lotes incrementais.")
            if pending_count <= 0:
                raise MemoryAnalysisError("Ainda nao ha mensagens novas pendentes para atualizar a memoria.")
            candidate_messages = self.store.list_pending_messages(
                user_id=self.settings.default_user_id,
                limit=min(
                    self.settings.message_retention_max_rows,
                    max(self._resolve_incremental_batch_size() * 4, min(pending_count, self._resolve_incremental_batch_size() * 8)),
                ),
                newest_first=False,
            )
            # Prioriza mensagens que tenham texto útil
            textual_candidates = [m for m in candidate_messages if m.message_text.strip()]
            
            if not textual_candidates and pending_count > 0:
                raise MemoryAnalysisError(
                    f"Existem mensagens pendentes ({pending_count}), mas nenhuma delas possui texto útil para o processamento incremental."
                )

            selected_messages = self._select_balanced_messages(
                textual_candidates,
                max_messages=min(self._resolve_incremental_batch_size(), len(textual_candidates)),
                prefer_recent=False,
            )
            intent = "improve_memory"
            detail_mode = "balanced"

        selected_messages = [message for message in selected_messages if message.message_text.strip()]
        if not selected_messages:
            raise MemoryAnalysisError("Nao encontrei mensagens textuais analisaveis na fila operacional.")

        transcript, selected_messages = self._build_transcript(
            selected_messages,
            max_messages=len(selected_messages),
            char_budget=self._resolve_fixed_plan_char_budget(mode),
        )
        conversation_context = self._build_conversation_context(selected_messages)
        people_memory_context = self._build_people_memory_context(selected_messages)
        window_start = selected_messages[0].timestamp
        window_end = selected_messages[-1].timestamp
        window_hours = max(1, ceil(max(0.0, (window_end - window_start).total_seconds()) / 3600))
        current_persona = self.get_current_persona()
        prior_analyses_context = self._build_prior_analyses_context()
        project_context = self._build_project_context(
            self.store.list_project_memories(
                self.settings.default_user_id,
                limit=max(1, self.settings.chat_context_projects),
            )
        )
        chat_context = self._build_chat_context()
        prompt_preview = self.deepseek_service.build_analysis_prompt_preview(
            transcript=transcript,
            conversation_context=conversation_context,
            people_memory_context=people_memory_context,
            current_life_summary=self._build_persona_context(current_persona),
            prior_analyses_context=prior_analyses_context,
            project_context=project_context,
            chat_context=chat_context,
            window_hours=window_hours,
            window_start=window_start,
            window_end=window_end,
            source_message_count=len(selected_messages),
        )
        estimated_input_tokens = self._estimate_text_tokens(prompt_preview.system_prompt) + self._estimate_text_tokens(prompt_preview.user_prompt)
        planning_profile = self.deepseek_service.get_planning_profile(intent=intent)
        estimated_reasoning_tokens, estimated_output_tokens = self._estimate_output_usage(
            estimated_input_tokens=estimated_input_tokens,
            detail_mode=detail_mode,
            output_reserve_tokens=planning_profile.request_output_reserve_tokens,
        )
        (
            _estimated_cost_input_floor_usd,
            _estimated_cost_input_ceiling_usd,
            _estimated_cost_output_floor_usd,
            _estimated_cost_output_ceiling_usd,
            estimated_cost_total_floor_usd,
            estimated_cost_total_ceiling_usd,
        ) = self._estimate_cost_range_usd(
            input_tokens=estimated_input_tokens,
            output_tokens=estimated_output_tokens,
            input_price_floor_per_million=planning_profile.cache_miss_input_price_floor_per_million,
            input_price_ceiling_per_million=planning_profile.cache_miss_input_price_ceiling_per_million,
            output_price_floor_per_million=planning_profile.output_price_floor_per_million,
            output_price_ceiling_per_million=planning_profile.output_price_ceiling_per_million,
        )
        return FixedAnalysisPlan(
            intent=intent,
            source_messages=selected_messages,
            transcript=transcript,
            conversation_context=conversation_context,
            people_memory_context=people_memory_context,
            window_hours=window_hours,
            window_start=window_start,
            window_end=window_end,
            selected_transcript_chars=len(transcript),
            estimated_input_tokens=estimated_input_tokens,
            estimated_output_tokens=estimated_output_tokens,
            estimated_reasoning_tokens=estimated_reasoning_tokens,
            estimated_cost_floor_usd=estimated_cost_total_floor_usd,
            estimated_cost_ceiling_usd=estimated_cost_total_ceiling_usd,
        )

    async def _analyze_fixed_plan(self, plan: FixedAnalysisPlan) -> MemoryAnalysisOutcome:
        current_persona = self.get_current_persona()
        prior_analyses_context = self._build_prior_analyses_context()
        existing_projects = self.store.list_project_memories(
            self.settings.default_user_id,
            limit=max(1, self.settings.chat_context_projects),
        )
        project_context = self._build_project_context(existing_projects)
        chat_context = self._build_chat_context()
        deepseek_result = await self.deepseek_service.analyze_memory(
            transcript=plan.transcript,
            conversation_context=plan.conversation_context,
            people_memory_context=plan.people_memory_context,
            current_life_summary=self._build_persona_context(current_persona),
            prior_analyses_context=prior_analyses_context,
            project_context=project_context,
            chat_context=chat_context,
            intent=plan.intent,
            window_hours=plan.window_hours,
            window_start=plan.window_start,
            window_end=plan.window_end,
            source_message_count=len(plan.source_messages),
        )

        analyzed_at = datetime.now(UTC)
        effective_life_summary = self._resolve_effective_life_summary(
            deepseek_result.updated_life_summary,
            fallback_summary=self._build_persona_context(current_persona),
        )
        snapshot = self._build_snapshot(
            result=deepseek_result,
            window_hours=plan.window_hours,
            window_start=plan.window_start,
            window_end=plan.window_end,
            source_message_count=len(plan.source_messages),
            created_at=analyzed_at,
        )
        merged_project_seeds = await self._merge_project_seeds_incrementally(
            updated_life_summary=effective_life_summary,
            existing_projects=existing_projects,
            candidate_projects=deepseek_result.active_projects,
            window_summary=deepseek_result.window_summary,
            conversation_context=plan.conversation_context,
        )
        important_message_seeds = await self._extract_important_message_seeds(
            messages=plan.source_messages,
            current_life_summary=effective_life_summary,
            project_context=self._build_project_seed_context(merged_project_seeds),
        )
        structural_strengths, structural_routines, structural_preferences, structural_open_questions = (
            self._build_structural_profile_from_snapshots(
                [
                    snapshot,
                    *self.store.list_memory_snapshots(
                        self.settings.default_user_id,
                        limit=max(1, self.settings.memory_analysis_context_snapshots + 7),
                    ),
                ]
            )
        )
        persona = self.store.persist_memory_analysis(
            snapshot=snapshot,
            updated_life_summary=effective_life_summary,
            analyzed_at=analyzed_at,
            structural_strengths=structural_strengths,
            structural_routines=structural_routines,
            structural_preferences=structural_preferences,
            structural_open_questions=structural_open_questions,
        )
        self._persist_person_memories(
            messages=plan.source_messages,
            deepseek_result=deepseek_result,
            source_snapshot_id=snapshot.id,
            analyzed_at=analyzed_at,
        )
        projects = self.store.upsert_project_memories(
            user_id=self.settings.default_user_id,
            source_snapshot_id=snapshot.id,
            projects=merged_project_seeds,
            observed_at=analyzed_at,
        )
        important_saved_count = self.store.upsert_important_messages(
            user_id=self.settings.default_user_id,
            messages=important_message_seeds,
            saved_at=analyzed_at,
        )
        return MemoryAnalysisOutcome(
            persona=persona,
            snapshot=snapshot,
            projects=projects,
            important_messages_saved_count=important_saved_count,
            source_message_ids=[message.message_id for message in plan.source_messages],
            source_messages=plan.source_messages,
            selected_transcript_chars=plan.selected_transcript_chars,
        )

    def _persist_person_memories(
        self,
        *,
        messages: list[StoredMessageRecord],
        deepseek_result: DeepSeekMemoryResult,
        source_snapshot_id: str | None,
        analyzed_at: datetime,
    ) -> list[PersonMemoryRecord]:
        grouped_messages = self._group_messages_by_person(messages)
        if not grouped_messages or not deepseek_result.contact_memories:
            return []

        seeds: list[PersonMemorySeed] = []
        for person in deepseek_result.contact_memories:
            grouped = grouped_messages.get(person.person_key)
            if not grouped:
                continue
            last_message = grouped[-1]
            seeds.append(
                PersonMemorySeed(
                    person_key=person.person_key,
                    contact_name=person.contact_name.strip() or last_message.contact_name,
                    contact_phone=last_message.contact_phone,
                    chat_jid=last_message.chat_jid,
                    profile_summary=person.profile_summary,
                    relationship_summary=person.relationship_summary,
                    salient_facts=person.salient_facts,
                    open_loops=person.open_loops,
                    recent_topics=person.recent_topics,
                    source_message_count=len(grouped),
                    window_start=grouped[0].timestamp,
                    window_end=grouped[-1].timestamp,
                )
            )

        if not seeds:
            return []

        return self.store.upsert_person_memories(
            user_id=self.settings.default_user_id,
            source_snapshot_id=source_snapshot_id,
            people=seeds,
            observed_at=analyzed_at,
        )

    async def _merge_project_seeds_incrementally(
        self,
        *,
        updated_life_summary: str,
        existing_projects: list[ProjectMemoryRecord],
        candidate_projects: list[DeepSeekProjectMemory],
        window_summary: str,
        conversation_context: str,
    ) -> list[ProjectMemorySeed]:
        if not existing_projects and not candidate_projects:
            return []
        merged_result = await self.deepseek_service.merge_projects_incrementally(
            current_life_summary=updated_life_summary,
            current_project_context=self._build_project_context(existing_projects),
            candidate_projects_block=self._build_candidate_projects_block(candidate_projects),
            recent_window_summary=window_summary,
            conversation_context=conversation_context,
        )
        seeds = self._project_memory_seeds_from_deepseek(
            merged_result.active_projects if merged_result.active_projects else candidate_projects,
        )
        return seeds[:8]

    async def _extract_important_message_seeds(
        self,
        *,
        messages: list[StoredMessageRecord],
        current_life_summary: str,
        project_context: str,
    ) -> list[ImportantMessageSeed]:
        candidates = [message for message in messages if message.message_text.strip()]
        if not candidates:
            return []

        messages_block = self._build_important_messages_block(candidates)
        if not messages_block:
            return []

        logger.info("important_extract_start candidates=%s", len(candidates))
        result = await self.deepseek_service.extract_important_messages(
            messages_block=messages_block,
            allowed_message_ids=[message.message_id for message in candidates],
            current_life_summary=current_life_summary,
            project_context=project_context,
        )

        message_by_id = {message.message_id: message for message in candidates}
        seeds: list[ImportantMessageSeed] = []
        low_confidence_count = 0
        for candidate in result.important_messages:
            source = message_by_id.get(candidate.message_id)
            if source is None:
                continue
            if candidate.confidence < 55:
                low_confidence_count += 1
                continue
            seeds.append(
                ImportantMessageSeed(
                    source_message_id=source.message_id,
                    contact_name=source.contact_name,
                    contact_phone=source.contact_phone,
                    direction=source.direction,
                    message_text=source.message_text,
                    message_timestamp=source.timestamp,
                    category=candidate.category,
                    importance_reason=candidate.importance_reason,
                    confidence=candidate.confidence,
                )
            )

        fallback_used = False
        if not seeds:
            seeds = self._build_heuristic_important_message_seeds(candidates)
            fallback_used = bool(seeds)

        logger.info(
            "important_extract_done candidates=%s model_candidates=%s low_confidence=%s saved=%s fallback_used=%s",
            len(candidates),
            len(result.important_messages),
            low_confidence_count,
            len(seeds),
            fallback_used,
        )
        return seeds

    def _project_memory_seeds_from_deepseek(
        self,
        projects: list[DeepSeekProjectMemory],
    ) -> list[ProjectMemorySeed]:
        return [
            ProjectMemorySeed(
                project_name=project.name,
                summary=project.summary,
                status=project.status,
                what_is_being_built=project.what_is_being_built,
                built_for=project.built_for,
                next_steps=project.next_steps,
                evidence=project.evidence,
            )
            for project in projects
            if project.name.strip() and project.summary.strip()
        ]

    def _build_project_seed_context(self, projects: list[ProjectMemorySeed]) -> str:
        if not projects:
            return ""
        lines: list[str] = []
        for project in projects[:8]:
            lines.extend(
                [
                    f"- Projeto: {project.project_name}",
                    f"  Resumo: {project.summary or '(sem resumo)'}",
                    f"  Status: {project.status or '(sem status)'}",
                    f"  Construindo: {project.what_is_being_built or '(nao especificado)'}",
                    f"  Para quem: {project.built_for or '(nao especificado)'}",
                    f"  Proximos passos: {'; '.join(project.next_steps) if project.next_steps else '(nenhum)'}",
                    f"  Evidencias: {'; '.join(project.evidence) if project.evidence else '(nenhuma)'}",
                ]
            )
        return "\n".join(lines)

    def _build_candidate_projects_block(self, projects: list[DeepSeekProjectMemory]) -> str:
        if not projects:
            return ""
        lines: list[str] = []
        for project in projects[:8]:
            lines.extend(
                [
                    f"- Projeto detectado: {project.name}",
                    f"  Resumo: {project.summary or '(sem resumo)'}",
                    f"  Status: {project.status or '(sem status)'}",
                    f"  Construindo: {project.what_is_being_built or '(nao especificado)'}",
                    f"  Para quem: {project.built_for or '(nao especificado)'}",
                    f"  Proximos passos: {'; '.join(project.next_steps) if project.next_steps else '(nenhum)'}",
                    f"  Evidencias: {'; '.join(project.evidence) if project.evidence else '(nenhuma)'}",
                ]
            )
        return "\n".join(lines)

    def list_snapshots(self, *, limit: int = 20) -> list[MemorySnapshotRecord]:
        return self.store.list_memory_snapshots(self.settings.default_user_id, limit=limit)

    def list_projects(self, *, limit: int = 8) -> list[ProjectMemoryRecord]:
        return self.store.list_project_memories(self.settings.default_user_id, limit=limit)

    def list_important_messages(self, *, limit: int = 80) -> list[ImportantMessageRecord]:
        return self.store.list_important_messages(self.settings.default_user_id, limit=limit)

    async def extract_and_store_important_messages(
        self,
        *,
        messages: list[StoredMessageRecord],
        analyzed_at: datetime | None = None,
    ) -> int:
        current_persona = self.get_current_persona()
        seeds = await self._extract_important_message_seeds(
            messages=messages,
            current_life_summary=self._build_persona_context(current_persona),
            project_context=self._build_project_context(
                self.store.list_project_memories(
                    self.settings.default_user_id,
                    limit=max(1, self.settings.chat_context_projects),
                )
            ),
        )
        return self.store.upsert_important_messages(
            user_id=self.settings.default_user_id,
            messages=seeds,
            saved_at=analyzed_at or datetime.now(UTC),
        )

    def _build_heuristic_important_message_seeds(
        self,
        messages: list[StoredMessageRecord],
    ) -> list[ImportantMessageSeed]:
        patterns: list[tuple[str, re.Pattern[str], str, int]] = [
            ("money", re.compile(r"\b(?:r\$\s?\d+|\d+[,.]?\d*\s?(?:reais|pix|boleto|pagamento|cobran[çc]a|transfer[êe]ncia))\b", re.IGNORECASE), "Possivel combinacao financeira ou cobranca relevante.", 72),
            ("deadline", re.compile(r"\b(?:amanh[ãa]|hoje|prazo|vence|vencimento|at[ée]|\d{1,2}/\d{1,2}(?:/\d{2,4})?)\b", re.IGNORECASE), "Possivel prazo, vencimento ou data combinada.", 69),
            ("access", re.compile(r"\b(?:senha|c[oó]digo|token|login|acesso|2fa|autentica[cç][aã]o)\b", re.IGNORECASE), "Possivel informacao de acesso ou autenticacao.", 78),
            ("document", re.compile(r"\b(?:cpf|cnpj|rg|passaporte|contrato|comprovante|nota fiscal|documento)\b", re.IGNORECASE), "Possivel documento ou dado formal importante.", 74),
            ("address", re.compile(r"\b(?:endere[cç]o|rua|avenida|av\.?|bairro|cep|apartamento|apto|casa)\b", re.IGNORECASE), "Possivel endereco ou local relevante.", 67),
            ("commitment", re.compile(r"\b(?:reuni[aã]o|consulta|compromisso|agenda|marcado|hor[aá]rio|horario)\b", re.IGNORECASE), "Possivel compromisso ou horario combinado.", 66),
        ]

        seeds_by_message_id: dict[str, ImportantMessageSeed] = {}
        for message in messages:
            normalized_text = " ".join(message.message_text.split()).strip()
            if len(normalized_text) < 12:
                continue
            for category, pattern, reason, confidence in patterns:
                if not pattern.search(normalized_text):
                    continue
                seeds_by_message_id[message.message_id] = ImportantMessageSeed(
                    source_message_id=message.message_id,
                    contact_name=message.contact_name,
                    contact_phone=message.contact_phone,
                    direction=message.direction,
                    message_text=message.message_text,
                    message_timestamp=message.timestamp,
                    category=category,
                    importance_reason=f"heuristic_fallback: {reason}",
                    confidence=confidence,
                )
                break
        return list(seeds_by_message_id.values())

    async def review_important_messages(
        self,
        *,
        reviewed_before: datetime,
        limit: int = 120,
    ) -> ImportantMessagesReviewOutcome:
        pending_messages = self.store.list_important_messages_pending_review(
            user_id=self.settings.default_user_id,
            reviewed_before=reviewed_before,
            limit=limit,
        )
        if not pending_messages:
            return ImportantMessagesReviewOutcome(
                reviewed_count=0,
                kept_count=0,
                discarded_count=0,
                reviewed_at=None,
            )

        current_persona = self.get_current_persona()
        project_context = self._build_project_context(
            self.store.list_project_memories(
                self.settings.default_user_id,
                limit=max(1, self.settings.chat_context_projects),
            )
        )
        review_result = await self.deepseek_service.review_important_messages(
            important_messages_block=self._build_saved_important_messages_block(pending_messages),
            allowed_message_ids=[message.source_message_id for message in pending_messages],
            current_life_summary=self._build_persona_context(current_persona),
            project_context=project_context,
        )

        review_by_id = {review.source_message_id: review for review in review_result.reviews}
        review_seeds: list[ImportantMessageReviewSeed] = []
        for message in pending_messages:
            review = review_by_id.get(message.source_message_id)
            if review is None:
                review_seeds.append(
                    ImportantMessageReviewSeed(
                        source_message_id=message.source_message_id,
                        decision="keep",
                        review_notes="Mantida por seguranca porque a revisao nao devolveu decisao explicita para este item.",
                        confidence=40,
                    )
                )
                continue
            review_seeds.append(
                ImportantMessageReviewSeed(
                    source_message_id=review.source_message_id,
                    decision=review.decision,
                    review_notes=review.review_notes,
                    confidence=review.confidence,
                )
            )

        reviewed_at = datetime.now(UTC)
        kept_count, discarded_count = self.store.apply_important_message_reviews(
            user_id=self.settings.default_user_id,
            reviews=review_seeds,
            reviewed_at=reviewed_at,
        )
        return ImportantMessagesReviewOutcome(
            reviewed_count=len(review_seeds),
            kept_count=kept_count,
            discarded_count=discarded_count,
            reviewed_at=reviewed_at,
        )

    async def refine_saved_memory(self) -> MemoryRefinementOutcome:
        current_persona = self.get_current_persona()
        snapshots = self.store.list_memory_snapshots(self.settings.default_user_id, limit=max(1, self.settings.memory_analysis_context_snapshots))
        projects = self.store.list_project_memories(self.settings.default_user_id, limit=max(1, self.settings.chat_context_projects))

        if not current_persona.life_summary.strip() and not snapshots and not projects:
            raise MemoryAnalysisError(
                "Ainda nao ha memoria suficiente salva no banco local para refinar. Rode ao menos uma analise primeiro."
            )

        # Passo 1: Refinamento da Persona e Projetos
        refined = await self.deepseek_service.refine_saved_memory(
            current_life_summary=self._build_persona_context(current_persona),
            prior_analyses_context=self._build_prior_analyses_context_from_snapshots(snapshots),
            project_context=self._build_project_context(projects),
            chat_context=self._build_chat_context(),
        )

        refined_at = datetime.now(UTC)
        effective_life_summary = self._resolve_effective_life_summary(
            refined.updated_life_summary,
            fallback_summary=self._build_persona_context(current_persona),
        )
        structural_strengths, structural_routines, structural_preferences, structural_open_questions = (
            self._build_structural_profile_from_snapshots(snapshots)
        )
        persona = self.store.update_persona_summary(
            user_id=self.settings.default_user_id,
            updated_life_summary=effective_life_summary,
            analyzed_at=refined_at,
            structural_strengths=structural_strengths,
            structural_routines=structural_routines,
            structural_preferences=structural_preferences,
            structural_open_questions=structural_open_questions,
        )
        updated_projects = self.store.upsert_project_memories(
            user_id=self.settings.default_user_id,
            source_snapshot_id=persona.last_snapshot_id,
            projects=[
                ProjectMemorySeed(
                    project_name=project.name,
                    summary=project.summary,
                    status=project.status,
                    what_is_being_built=project.what_is_being_built,
                    built_for=project.built_for,
                    next_steps=project.next_steps,
                    evidence=project.evidence,
                )
                for project in refined.active_projects
            ],
            observed_at=refined_at,
        )

        # Passo 2: Refinamento dos Contatos (Pessoas)
        contact_records = self.store.list_person_memories(self.settings.default_user_id, limit=24)
        if contact_records:
            contact_block = self._build_contact_memories_block(contact_records)
            refined_contacts = await self.deepseek_service.refine_contact_memories(
                current_life_summary=self._build_persona_context(persona),
                project_context=self._build_project_context(updated_projects),
                contact_memories_block=contact_block,
            )
            
            contact_seeds: list[PersonMemorySeed] = []
            for c_record in contact_records:
                for c_refined in refined_contacts.contact_memories:
                    if c_refined.person_key == c_record.person_key:
                        contact_seeds.append(
                            PersonMemorySeed(
                                person_key=c_record.person_key,
                                contact_name=c_record.contact_name,
                                contact_phone=c_record.contact_phone,
                                chat_jid=c_record.chat_jid,
                                profile_summary=c_refined.profile_summary,
                                relationship_summary=c_refined.relationship_summary,
                                salient_facts=c_refined.salient_facts,
                                open_loops=c_refined.open_loops,
                                recent_topics=c_refined.recent_topics,
                                source_message_count=c_record.source_message_count,
                                window_start=None,
                                window_end=None,
                            )
                        )
                        break
            
            if contact_seeds:
                self.store.upsert_person_memories(
                    user_id=self.settings.default_user_id,
                    source_snapshot_id=persona.last_snapshot_id,
                    people=contact_seeds,
                    observed_at=refined_at,
                )

        # Passo 3: Refinamento do Cofre (Mensagens Importantes)
        await self.review_important_messages(reviewed_before=datetime.now(UTC), limit=80)

        return MemoryRefinementOutcome(persona=persona, projects=updated_projects)

    def _build_contact_memories_block(self, memories: list[PersonMemoryRecord]) -> str:
        if not memories:
            return ""

        sections: list[str] = []
        for memory in memories:
            lines = [
                f"- person_key: {memory.person_key}",
                f"  Contato: {memory.contact_name}",
            ]
            if memory.profile_summary:
                lines.append(f"  Quem e: {memory.profile_summary}")
            if memory.relationship_summary:
                lines.append(f"  Relacao com o dono: {memory.relationship_summary}")
            if memory.salient_facts:
                lines.append(f"  Fatos marcantes: {'; '.join(memory.salient_facts[:6])}")
            if memory.open_loops:
                lines.append(f"  Pendencias abertas: {'; '.join(memory.open_loops[:5])}")
            if memory.recent_topics:
                lines.append(f"  Topicos recentes: {'; '.join(memory.recent_topics[:5])}")

            sections.append("\n".join(lines))

        return "\n\n".join(sections)

    def _build_prior_analyses_context(self) -> str:
        limit = max(0, self.settings.memory_analysis_context_snapshots)
        if limit == 0:
            return ""

        snapshots = self.store.list_memory_snapshots(self.settings.default_user_id, limit=limit)
        return self._build_prior_analyses_context_from_snapshots(snapshots)

    def _build_prior_analyses_context_from_snapshots(self, snapshots: list[MemorySnapshotRecord]) -> str:
        if not snapshots:
            return ""

        sections: list[str] = []
        current_size = 0
        char_budget = max(1000, self.settings.memory_analysis_snapshot_context_chars)

        for snapshot in reversed(snapshots):
            lines = [
                f"- Analise de {snapshot.window_hours}h em {snapshot.created_at.astimezone(UTC).strftime('%Y-%m-%d %H:%M UTC')}",
                f"  Resumo da janela: {snapshot.window_summary}",
            ]
            if snapshot.key_learnings:
                lines.append(f"  Aprendizados: {'; '.join(snapshot.key_learnings[:4])}")
            if snapshot.people_and_relationships:
                lines.append(f"  Pessoas e relacoes: {'; '.join(snapshot.people_and_relationships[:4])}")
            if snapshot.routine_signals:
                lines.append(f"  Rotina: {'; '.join(snapshot.routine_signals[:4])}")
            if snapshot.preferences:
                lines.append(f"  Preferencias: {'; '.join(snapshot.preferences[:4])}")

            section = "\n".join(lines)
            projected_size = current_size + len(section) + 2
            if sections and projected_size > char_budget:
                break
            sections.append(section)
            current_size = projected_size

        return "\n\n".join(sections)

    def _build_project_context(self, projects: list[ProjectMemoryRecord]) -> str:
        if not projects:
            return ""

        sections: list[str] = []
        current_size = 0
        char_budget = max(1000, self.settings.memory_analysis_snapshot_context_chars)

        for project in projects:
            lines = [
                f"- Projeto: {project.project_name}",
                f"  Resumo: {project.summary}",
            ]
            if project.status:
                lines.append(f"  Status: {project.status}")
            if project.what_is_being_built:
                lines.append(f"  O que esta sendo desenvolvido: {project.what_is_being_built}")
            if project.built_for:
                lines.append(f"  Para quem: {project.built_for}")
            if project.next_steps:
                lines.append(f"  Proximos passos: {'; '.join(project.next_steps[:4])}")
            if project.evidence:
                lines.append(f"  Evidencias: {'; '.join(project.evidence[:4])}")

            section = "\n".join(lines)
            projected_size = current_size + len(section) + 2
            if sections and projected_size > char_budget:
                break
            sections.append(section)
            current_size = projected_size

        return "\n\n".join(sections)

    def _build_chat_context(self) -> str:
        threads = self.store.list_chat_threads(user_id=self.settings.default_user_id, limit=4)
        if not threads:
            threads = [self.store.get_or_create_chat_thread(user_id=self.settings.default_user_id)]

        sections: list[str] = []
        current_size = 0
        char_budget = max(1000, self.settings.memory_analysis_snapshot_context_chars)
        per_thread_limit = max(1, min(self.settings.chat_max_history_messages, 6))

        for thread in threads:
            messages = self.store.list_chat_messages(thread.id, limit=per_thread_limit)
            section_body = self._build_chat_context_from_messages(messages)
            if not section_body:
                continue

            section = f"[{thread.title}]\n{section_body}"
            projected_size = current_size + len(section) + 2
            if sections and projected_size > char_budget:
                break
            sections.append(section)
            current_size = projected_size

        return "\n\n".join(sections)

    def _build_chat_context_from_messages(self, messages: list[ChatMessageRecord]) -> str:
        if not messages:
            return ""

        sections: list[str] = []
        current_size = 0
        char_budget = max(1000, self.settings.memory_analysis_snapshot_context_chars)

        for message in messages:
            role = "Dono" if message.role == "user" else "AuraCore"
            line = f"- {role}: {message.content}"
            projected_size = current_size + len(line) + 1
            if sections and projected_size > char_budget:
                break
            sections.append(line)
            current_size = projected_size

        return "\n".join(sections)

    def _group_messages_by_person(self, messages: list[StoredMessageRecord]) -> dict[str, list[StoredMessageRecord]]:
        groups: dict[str, list[StoredMessageRecord]] = {}
        for message in messages:
            person_key = self.store.build_person_key(
                contact_phone=message.contact_phone,
                chat_jid=message.chat_jid,
                contact_name=message.contact_name,
            )
            groups.setdefault(person_key, []).append(message)
        return groups

    def _build_people_memory_context(self, messages: list[StoredMessageRecord]) -> str:
        grouped_messages = self._group_messages_by_person(messages)
        if not grouped_messages:
            return ""

        memories = self.store.list_person_memories_by_keys(
            user_id=self.settings.default_user_id,
            person_keys=list(grouped_messages.keys()),
        )
        if not memories:
            return ""

        memory_by_key = {memory.person_key: memory for memory in memories}
        sections: list[str] = []
        current_size = 0
        char_budget = max(1200, min(5000, self.settings.memory_analysis_snapshot_context_chars))

        for person_key, grouped in grouped_messages.items():
            memory = memory_by_key.get(person_key)
            if memory is None:
                continue
            contact_name = memory.contact_name or grouped[-1].contact_name or grouped[-1].contact_phone or "Contato"
            lines = [
                f"- person_key: {person_key}",
                f"  Contato: {contact_name}",
            ]
            if memory.contact_phone or memory.chat_jid:
                lines.append(f"  Identificador: {memory.contact_phone or memory.chat_jid}")
            if memory.last_analyzed_at:
                lines.append(
                    f"  Ultima atualizacao: {memory.last_analyzed_at.astimezone(UTC).strftime('%Y-%m-%d %H:%M UTC')}"
                )
            if memory.profile_summary:
                lines.append(f"  Quem e: {memory.profile_summary}")
            if memory.relationship_summary:
                lines.append(f"  Relacao com o dono: {memory.relationship_summary}")
            if memory.salient_facts:
                lines.append(f"  Fatos marcantes: {'; '.join(memory.salient_facts[:6])}")
            if memory.open_loops:
                lines.append(f"  Pendencias abertas: {'; '.join(memory.open_loops[:5])}")
            if memory.recent_topics:
                lines.append(f"  Topicos recentes: {'; '.join(memory.recent_topics[:5])}")

            section = "\n".join(lines)
            projected_size = current_size + len(section) + 2
            if sections and projected_size > char_budget:
                break
            sections.append(section)
            current_size = projected_size

        return "\n\n".join(sections)

    def _build_conversation_context(self, messages: list[StoredMessageRecord]) -> str:
        if not messages:
            return ""

        groups: dict[str, dict[str, object]] = {}
        for message in messages:
            key = self.store.build_person_key(
                contact_phone=message.contact_phone,
                chat_jid=message.chat_jid,
                contact_name=message.contact_name,
            )
            group = groups.get(key)
            if group is None:
                group = {
                    "person_key": key,
                    "contact_name": message.contact_name.strip() or message.contact_phone or "Contato",
                    "contact_phone": message.contact_phone,
                    "chat_jid": message.chat_jid,
                    "inbound_count": 0,
                    "outbound_count": 0,
                    "first_timestamp": message.timestamp,
                    "last_timestamp": message.timestamp,
                    "samples": [],
                }
                groups[key] = group

            if message.direction == "outbound":
                group["outbound_count"] = int(group["outbound_count"]) + 1
            else:
                group["inbound_count"] = int(group["inbound_count"]) + 1

            if message.timestamp < group["first_timestamp"]:
                group["first_timestamp"] = message.timestamp
            if message.timestamp > group["last_timestamp"]:
                group["last_timestamp"] = message.timestamp

            samples = group["samples"]
            if isinstance(samples, list) and len(samples) < 2:
                direction_label = "Dono -> contato" if message.direction == "outbound" else "Contato -> dono"
                samples.append(f"{direction_label}: {self._summarize_message_text(message.message_text, 140)}")

        ordered_groups = sorted(
            groups.values(),
            key=lambda group: (
                -(int(group["inbound_count"]) + int(group["outbound_count"])),
                group["last_timestamp"],
            ),
        )

        sections: list[str] = []
        current_size = 0
        char_budget = max(1200, min(5000, self.settings.memory_analysis_snapshot_context_chars))

        for group in ordered_groups[:12]:
            total_messages = int(group["inbound_count"]) + int(group["outbound_count"])
            lines = [
                f"- person_key: {group['person_key']}",
                f"  Conversa: {group['contact_name']}",
                f"  Identificador: {group['contact_phone'] or group['chat_jid'] or 'indisponivel'}",
                (
                    f"  Volume: {total_messages} mensagens "
                    f"({int(group['inbound_count'])} recebidas, {int(group['outbound_count'])} enviadas)"
                ),
                (
                    "  Janela: "
                    f"{group['first_timestamp'].astimezone(UTC).strftime('%Y-%m-%d %H:%M UTC')} ate "
                    f"{group['last_timestamp'].astimezone(UTC).strftime('%Y-%m-%d %H:%M UTC')}"
                ),
            ]
            samples = group["samples"]
            if isinstance(samples, list) and samples:
                lines.append(f"  Sinais recentes: {'; '.join(samples)}")

            section = "\n".join(lines)
            projected_size = current_size + len(section) + 2
            if sections and projected_size > char_budget:
                break
            sections.append(section)
            current_size = projected_size

        return "\n\n".join(sections)

    def _build_snapshot(
        self,
        *,
        result: DeepSeekMemoryResult,
        window_hours: int,
        window_start: datetime,
        window_end: datetime,
        source_message_count: int,
        created_at: datetime,
    ) -> MemorySnapshotRecord:
        return MemorySnapshotRecord(
            id=str(uuid4()),
            user_id=self.settings.default_user_id,
            window_hours=window_hours,
            window_start=window_start,
            window_end=window_end,
            source_message_count=source_message_count,
            window_summary=result.window_summary,
            key_learnings=result.key_learnings,
            people_and_relationships=result.people_and_relationships,
            routine_signals=result.routine_signals,
            preferences=result.preferences,
            open_questions=result.open_questions,
            created_at=created_at,
        )

    def _build_transcript(
        self,
        messages: list[StoredMessageRecord],
        *,
        max_messages: int | None = None,
        char_budget: int | None = None,
    ) -> tuple[str, list[StoredMessageRecord]]:
        resolved_max_messages = max(1, min(max_messages or self.settings.memory_analysis_max_messages, self.settings.memory_analysis_max_messages))
        selected_messages = messages[-resolved_max_messages:]

        lines_reversed: list[str] = []
        selected_reversed: list[StoredMessageRecord] = []
        resolved_char_budget = max(1000, min(char_budget or self.settings.memory_analysis_max_chars, self.settings.memory_analysis_max_chars))
        current_size = 0

        for message in reversed(selected_messages):
            line = self._render_message_line(message)
            projected_size = current_size + len(line) + 1
            if lines_reversed and projected_size > resolved_char_budget:
                break
            lines_reversed.append(line)
            selected_reversed.append(message)
            current_size = projected_size

        if not lines_reversed and selected_messages:
            first_line = self._render_message_line(selected_messages[-1])
            lines_reversed.append(first_line[:resolved_char_budget])
            selected_reversed.append(selected_messages[-1])

        lines = list(reversed(lines_reversed))
        selected = list(reversed(selected_reversed))
        return "\n".join(lines), selected

    def _build_full_transcript(self, messages: list[StoredMessageRecord]) -> str:
        return "\n".join(self._render_message_line(message) for message in messages if message.message_text.strip())

    def _render_message_line(self, message: StoredMessageRecord) -> str:
        timestamp = message.timestamp.astimezone(UTC).strftime("%Y-%m-%d %H:%M")
        contact = message.contact_name.strip() or message.contact_phone or "Contato"
        direction = f"Dono -> {contact}" if message.direction == "outbound" else f"{contact} -> Dono"
        text = " ".join(message.message_text.split())
        return f"[{timestamp} UTC] {direction}: {text}"

    def _summarize_message_text(self, text: str, max_length: int) -> str:
        normalized = " ".join(text.split()).strip()
        if len(normalized) <= max_length:
            return normalized
        return f"{normalized[: max(0, max_length - 3)].rstrip()}..."

    def _build_important_messages_block(self, messages: list[StoredMessageRecord]) -> str:
        lines: list[str] = []
        for message in messages:
            text = " ".join(message.message_text.split())
            if not text:
                continue
            timestamp = message.timestamp.astimezone(UTC).strftime("%Y-%m-%d %H:%M")
            speaker = message.contact_name.strip() or message.contact_phone or "Contato"
            direction = "outbound" if message.direction == "outbound" else "inbound"
            lines.append(
                f"- message_id={message.message_id} | {timestamp} UTC | {direction} | contato={speaker} | texto={text}"
            )
        return "\n".join(lines)

    def _build_saved_important_messages_block(self, messages: list[ImportantMessageRecord]) -> str:
        lines: list[str] = []
        for message in messages:
            text = " ".join(message.message_text.split())
            if not text:
                continue
            timestamp = message.message_timestamp.astimezone(UTC).strftime("%Y-%m-%d %H:%M")
            reviewed_at = (
                message.last_reviewed_at.astimezone(UTC).strftime("%Y-%m-%d %H:%M UTC")
                if message.last_reviewed_at
                else "never"
            )
            lines.append(
                f"- source_message_id={message.source_message_id} | categoria={message.category} | {timestamp} UTC | "
                f"contato={message.contact_name} | confianca={message.confidence} | motivo={message.importance_reason} | "
                f"ultima_revisao={reviewed_at} | texto={text}"
            )
        return "\n".join(lines)

    def _resolve_char_budget(self, detail_mode: Literal["light", "balanced", "deep"]) -> int:
        presets = {
            "light": 10000,
            "balanced": 18000,
            "deep": 30000,
        }
        return min(self.settings.memory_analysis_max_chars, presets[detail_mode])

    def _estimate_token_usage(
        self,
        *,
        selected_message_count: int,
        char_budget: int,
        detail_mode: Literal["light", "balanced", "deep"],
    ) -> tuple[int, int, int]:
        average_chars_per_message = {
            "light": 74,
            "balanced": 92,
            "deep": 110,
        }[detail_mode]
        transcript_chars = min(char_budget, selected_message_count * average_chars_per_message)
        context_chars = {
            "light": 6200,
            "balanced": 9200,
            "deep": 13200,
        }[detail_mode]
        estimated_input_tokens = max(600, round((transcript_chars + context_chars) / 4))
        estimated_output_tokens = {
            "light": 700,
            "balanced": 920,
            "deep": 1180,
        }[detail_mode]
        return estimated_input_tokens, estimated_output_tokens, estimated_input_tokens + estimated_output_tokens

    def _estimate_text_tokens(self, text: str) -> int:
        if not text:
            return 0

        estimated_tokens = 0.0
        for char in text:
            codepoint = ord(char)
            if 0x3400 <= codepoint <= 0x9FFF:
                estimated_tokens += 0.6
            else:
                estimated_tokens += 0.3
        return max(1, round(estimated_tokens))

    def _estimate_model_message_capacities(
        self,
        *,
        average_message_tokens: int,
        estimated_prompt_context_tokens: int,
        safe_input_budget_floor_tokens: int,
        safe_input_budget_ceiling_tokens: int,
    ) -> tuple[int, int]:
        if average_message_tokens <= 0:
            return 0, 0

        usable_floor_tokens = max(0, safe_input_budget_floor_tokens - estimated_prompt_context_tokens)
        usable_ceiling_tokens = max(0, safe_input_budget_ceiling_tokens - estimated_prompt_context_tokens)
        return (
            usable_floor_tokens // average_message_tokens,
            usable_ceiling_tokens // average_message_tokens,
        )

    def _estimate_stack_message_capacities(
        self,
        *,
        average_message_chars: int,
        model_message_capacity_floor: int,
        current_char_budget: int,
    ) -> tuple[int, int]:
        if average_message_chars <= 0:
            return 0, 0

        planner_char_capacity = current_char_budget // average_message_chars
        stack_char_capacity = self.settings.memory_analysis_max_chars // average_message_chars
        planner_message_capacity = min(
            self.settings.memory_analysis_max_messages,
            planner_char_capacity,
            model_message_capacity_floor,
        )
        stack_max_message_capacity = min(
            self.settings.memory_analysis_max_messages,
            stack_char_capacity,
            model_message_capacity_floor,
        )
        return planner_message_capacity, stack_max_message_capacity

    def _estimate_output_usage(
        self,
        *,
        estimated_input_tokens: int,
        detail_mode: Literal["light", "balanced", "deep"],
        output_reserve_tokens: int,
    ) -> tuple[int, int]:
        final_answer_tokens = {
            "light": 760,
            "balanced": 1080,
            "deep": 1460,
        }[detail_mode]
        reasoning_multiplier = {
            "light": 0.24,
            "balanced": 0.38,
            "deep": 0.52,
        }[detail_mode]
        reasoning_floor = {
            "light": 900,
            "balanced": 1450,
            "deep": 2200,
        }[detail_mode]

        resolved_final_answer_tokens = min(output_reserve_tokens, final_answer_tokens)
        reasoning_cap = max(0, output_reserve_tokens - resolved_final_answer_tokens)
        estimated_reasoning_tokens = min(
            reasoning_cap,
            max(reasoning_floor, round(estimated_input_tokens * reasoning_multiplier)),
        )
        estimated_output_tokens = min(
            output_reserve_tokens,
            resolved_final_answer_tokens + estimated_reasoning_tokens,
        )
        return estimated_reasoning_tokens, estimated_output_tokens

    def _estimate_cost_range_usd(
        self,
        *,
        input_tokens: int,
        output_tokens: int,
        input_price_floor_per_million: float,
        input_price_ceiling_per_million: float,
        output_price_floor_per_million: float,
        output_price_ceiling_per_million: float,
    ) -> tuple[float, float, float, float, float, float]:
        input_cost_floor = round((input_tokens / 1_000_000) * input_price_floor_per_million, 6)
        input_cost_ceiling = round((input_tokens / 1_000_000) * input_price_ceiling_per_million, 6)
        output_cost_floor = round((output_tokens / 1_000_000) * output_price_floor_per_million, 6)
        output_cost_ceiling = round((output_tokens / 1_000_000) * output_price_ceiling_per_million, 6)
        total_cost_floor = round(input_cost_floor + output_cost_floor, 6)
        total_cost_ceiling = round(input_cost_ceiling + output_cost_ceiling, 6)
        return (
            input_cost_floor,
            input_cost_ceiling,
            output_cost_floor,
            output_cost_ceiling,
            total_cost_floor,
            total_cost_ceiling,
        )

    def _score_analysis_opportunity(
        self,
        *,
        persona: PersonaRecord,
        available_message_count: int,
        selected_message_count: int,
        new_message_count: int,
        replaced_message_count: int,
        estimated_total_tokens: int,
    ) -> int:
        if available_message_count <= 0 or selected_message_count <= 0:
            return 0

        freshness_ratio = min(1.0, new_message_count / max(selected_message_count, 1))
        coverage_ratio = min(1.0, available_message_count / max(selected_message_count, 1))
        replacement_ratio = min(1.0, replaced_message_count / max(selected_message_count, 1))
        token_efficiency = max(0.0, 1.0 - min(1.0, estimated_total_tokens / 22000))

        if persona.last_analyzed_at is None:
            staleness_ratio = 1.0
        else:
            hours_since_last_analysis = max(
                0.0,
                (datetime.now(UTC) - persona.last_analyzed_at).total_seconds() / 3600,
            )
            staleness_ratio = min(1.0, hours_since_last_analysis / 48)

        score = round(
            (freshness_ratio * 36)
            + (coverage_ratio * 22)
            + (replacement_ratio * 18)
            + (staleness_ratio * 14)
            + (token_efficiency * 10)
        )

        if selected_message_count < 24:
            score = min(score, 36)
        if persona.last_analyzed_at is None and available_message_count >= 32:
            score = max(score, 74)
        return max(0, min(100, score))

    def _label_for_score(self, score: int) -> str:
        if score >= 78:
            return "Alta vantagem"
        if score >= 55:
            return "Vale rodar"
        if score >= 32:
            return "Pode esperar um pouco"
        return "Ganho baixo agora"

    def _build_rule_based_recommendation(
        self,
        *,
        automation_settings: AutomationSettingsRecord,
        persona: PersonaRecord,
        has_memory: bool,
        available_message_count: int,
        selected_message_count: int,
        new_message_count: int,
        replaced_message_count: int,
        estimated_total_tokens: int,
        stack_max_message_capacity: int,
        estimated_cost_total_ceiling_usd: float,
        fallback_score: int,
        fallback_label: str,
    ) -> tuple[int, str, bool, str]:
        if available_message_count <= 0 or selected_message_count <= 0:
            return (
                0,
                "Sem material",
                False,
                "Ainda nao ha mensagens diretas textuais suficientes nessa janela para justificar leitura.",
            )

        hours_since_last_analysis = None
        if persona.last_analyzed_at is not None:
            hours_since_last_analysis = max(
                0.0,
                (datetime.now(UTC) - persona.last_analyzed_at).total_seconds() / 3600,
            )

        if not has_memory:
            if selected_message_count >= 40:
                score = max(fallback_score, 84)
                label = self._label_for_score(score)
                summary = (
                    f"Ja existem {selected_message_count} mensagens diretas utilizaveis nesta janela. "
                    "Isso e suficiente para montar a primeira base consolidada do dono com o reasoner."
                )
                return score, label, True, summary

            score = min(max(fallback_score, 26), 54)
            label = "Aguardar mais sinal"
            summary = (
                f"Ainda so cabem {selected_message_count} mensagens diretas uteis na leitura. "
                "Para a primeira analise, vale esperar um pouco mais de volume antes de gastar tokens."
            )
            return score, label, False, summary

        if replaced_message_count >= automation_settings.pruned_messages_threshold:
            score = max(fallback_score, 88)
            label = self._label_for_score(score)
            summary = (
                f"{replaced_message_count} mensagens ja ficaram para tras pela retencao. "
                "Vale atualizar a memoria agora para nao perder sinais recentes que mudam o retrato do dono."
            )
            return score, label, True, summary

        if new_message_count >= automation_settings.min_new_messages_threshold:
            score = max(fallback_score, 78)
            label = self._label_for_score(score)
            summary = (
                f"Entraram {new_message_count} mensagens novas desde a ultima consolidacao. "
                "Ja ha ganho suficiente para reler e melhorar a memoria atual."
            )
            return score, label, True, summary

        if (
            hours_since_last_analysis is not None
            and hours_since_last_analysis >= automation_settings.stale_hours_threshold
            and selected_message_count >= 30
        ):
            score = max(fallback_score, 66)
            label = self._label_for_score(score)
            summary = (
                f"A ultima analise ja tem {round(hours_since_last_analysis)}h e a janela atual ainda traz "
                f"{selected_message_count} mensagens diretas aproveitaveis. Vale uma releitura para manter a memoria fresca."
            )
            return score, label, True, summary

        score = min(fallback_score, 48)
        summary = self._build_fallback_preview_summary(
            selected_message_count=selected_message_count,
            new_message_count=new_message_count,
            replaced_message_count=replaced_message_count,
            stack_max_message_capacity=stack_max_message_capacity,
            estimated_cost_total_ceiling_usd=estimated_cost_total_ceiling_usd,
            recommendation_label=fallback_label,
        )
        return score, self._label_for_score(score), False, summary

    def _build_fallback_preview_summary(
        self,
        *,
        selected_message_count: int,
        new_message_count: int,
        replaced_message_count: int,
        stack_max_message_capacity: int,
        estimated_cost_total_ceiling_usd: float,
        recommendation_label: str,
    ) -> str:
        return (
            f"{recommendation_label}: esta leitura usaria cerca de {selected_message_count} mensagens, "
            f"com {new_message_count} novas, {replaced_message_count} ja substituidas pela retencao, "
            f"teto real de {stack_max_message_capacity} mensagens nesta stack e custo estimado ate US$ {estimated_cost_total_ceiling_usd:.4f}."
        )
