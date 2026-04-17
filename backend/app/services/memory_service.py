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
    DeepSeekError,
    DeepSeekContactMemoryRefinementResult,
    DeepSeekMemoryResult,
    DeepSeekPersonMemory,
    DeepSeekProjectMemory,
    DeepSeekProjectMergeResult,
    DeepSeekService,
)
from app.services.groq_service import GroqChatService
from app.services.supabase_store import (
    AutomationSettingsRecord,
    MemorySnapshotRecord,
    MessageRetentionStateRecord,
    PersonMemoryRecord,
    PersonMemorySeed,
    PersonaRecord,
    ProjectMemoryRecord,
    ProjectMemorySeed,
    StoredMessageRecord,
    SupabaseStore,
    WhatsAppAgentMessageRecord,
)


class MemoryAnalysisError(RuntimeError):
    """Raised when a memory analysis request cannot be completed."""


logger = logging.getLogger("auracore.memory_analysis")

BOOTSTRAP_BUCKET_WEIGHTS: tuple[tuple[str, float], ...] = (
    ("recent", 0.5),
    ("week", 0.3),
    ("older", 0.2),
)

PROJECT_KEYWORD_STOPWORDS: set[str] = {
    "agora",
    "ainda",
    "ajuda",
    "algum",
    "alguma",
    "assim",
    "cliente",
    "coisa",
    "como",
    "com",
    "contato",
    "contra",
    "dados",
    "dela",
    "dele",
    "demandas",
    "depois",
    "dessa",
    "desse",
    "deste",
    "direto",
    "entrega",
    "esse",
    "essa",
    "esta",
    "este",
    "fazer",
    "frente",
    "hoje",
    "isso",
    "item",
    "mais",
    "mesmo",
    "muito",
    "nada",
    "para",
    "pra",
    "pro",
    "porque",
    "projeto",
    "quando",
    "real",
    "sistema",
    "site",
    "sobre",
    "tarefa",
    "tema",
    "tem",
    "tipo",
    "uma",
    "umas",
    "uns",
    "usuario",
}

PROJECT_ACTION_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(
        r"\b(?:preciso|precisamos|vou|vamos|falta|tem que|tenho que|precisa|quero|precisaria)\b[^?!.]{8,160}",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(?:ajustar|alinhar|atualizar|corrigir|definir|documentar|entregar|finalizar|implementar|montar|"
        r"organizar|publicar|refatorar|revisar|resolver|rodar|subir|testar|validar)\b[^?!.]{6,150}",
        re.IGNORECASE,
    ),
)


@dataclass(slots=True)
class MemoryAnalysisOutcome:
    persona: PersonaRecord
    snapshot: MemorySnapshotRecord
    projects: list[ProjectMemoryRecord]
    source_message_ids: list[str] = field(default_factory=list)
    source_messages: list[StoredMessageRecord] = field(default_factory=list)
    selected_transcript_chars: int = 0


@dataclass(slots=True)
class MemoryRefinementOutcome:
    persona: PersonaRecord
    projects: list[ProjectMemoryRecord]


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


@dataclass(slots=True)
class FirstAnalysisChunk:
    source_messages: list[StoredMessageRecord]
    transcript: str
    conversation_context: str
    people_memory_context: str
    window_start: datetime
    window_end: datetime
    selected_transcript_chars: int


@dataclass(slots=True)
class FirstAnalysisSynthesisNode:
    label: str
    source_messages: list[StoredMessageRecord]
    window_start: datetime
    window_end: datetime
    result: DeepSeekMemoryResult


@dataclass(slots=True)
class AnalyzeMemoryPromptContext:
    transcript: str
    conversation_context: str
    people_memory_context: str
    current_life_summary: str
    prior_analyses_context: str
    project_context: str
    chat_context: str
    open_questions_context: str


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
        include_groups = self._analysis_includes_groups(has_memory=has_initial_analysis)
        if has_initial_analysis and persona.last_analyzed_at is not None:
            pending_new_message_count = self.store.count_selected_messages_after_timestamp(
                self.settings.default_user_id,
                after_timestamp=persona.last_analyzed_at,
                include_groups=include_groups,
            )
        else:
            pending_new_message_count = self.store.count_pending_messages(
                self.settings.default_user_id,
                include_groups=include_groups,
            )
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
        current_persona = self.get_current_persona()
        include_groups = self._analysis_includes_groups(
            has_memory=bool(current_persona.last_analyzed_at or current_persona.last_snapshot_id)
        )
        messages = self.store.list_messages_in_window(
            user_id=self.settings.default_user_id,
            window_start=window_start,
            window_end=window_end,
            include_groups=include_groups,
        )
        if not messages:
            raise MemoryAnalysisError(
                "Nenhuma mensagem foi encontrada nessa janela. Se acabou de conectar o WhatsApp, "
                "use 'Resetar sessao' e leia o QR novamente para puxar o historico inicial."
            )

        transcript, included_messages = self._build_transcript(messages)
        if not transcript.strip() or not included_messages:
            raise MemoryAnalysisError("Essa janela nao contem mensagens textuais analisaveis.")

        current_summary = self._build_persona_context(current_persona)
        prior_analyses_context = self._build_prior_analyses_context()
        project_context = self._build_project_context(
            self.store.list_project_memories(
                self.settings.default_user_id,
                limit=max(1, self.settings.context_max_projects),
            )
        )
        chat_context = self._build_chat_context()
        open_questions_context = self._build_open_questions_context(current_persona)
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
            open_questions_context=open_questions_context,
            intent="improve_memory" if current_persona.last_analyzed_at else "first_analysis",
            window_hours=window_hours,
            window_start=window_start,
            window_end=window_end,
            source_message_count=len(included_messages),
            contains_group_messages=any(self._is_group_message(message) for message in included_messages),
        )
        if not current_persona.last_analyzed_at:
            deepseek_result = self._stabilize_first_analysis_result(deepseek_result)

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
            source_messages=included_messages,
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
        project_seeds = self._project_memory_seeds_from_deepseek(deepseek_result.active_projects)
        projects = self.store.upsert_project_memories(
            user_id=self.settings.default_user_id,
            source_snapshot_id=snapshot.id,
            projects=project_seeds,
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
        current_persona = self.get_current_persona()
        include_groups = self._analysis_includes_groups(
            has_memory=bool(current_persona.last_analyzed_at or current_persona.last_snapshot_id)
        )
        messages = self.store.list_messages_in_window(
            user_id=self.settings.default_user_id,
            window_start=window_start,
            window_end=window_end,
            include_groups=include_groups,
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

        current_summary = self._build_persona_context(current_persona)
        prior_analyses_context = self._build_prior_analyses_context()
        project_context = self._build_project_context(
            self.store.list_project_memories(
                self.settings.default_user_id,
                limit=max(1, self.settings.context_max_projects),
            )
        )
        chat_context = self._build_chat_context()
        open_questions_context = self._build_open_questions_context(current_persona)
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
            open_questions_context=open_questions_context,
            intent="improve_memory" if current_persona.last_analyzed_at else "first_analysis",
            window_hours=max_lookback_hours,
            window_start=window_start,
            window_end=window_end,
            source_message_count=len(included_messages),
            contains_group_messages=any(self._is_group_message(message) for message in included_messages),
        )
        if not current_persona.last_analyzed_at:
            deepseek_result = self._stabilize_first_analysis_result(deepseek_result)

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
            source_messages=included_messages,
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
        project_seeds = self._project_memory_seeds_from_deepseek(deepseek_result.active_projects)
        projects = self.store.upsert_project_memories(
            user_id=self.settings.default_user_id,
            source_snapshot_id=snapshot.id,
            projects=project_seeds,
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
        current_persona = self.get_current_persona()
        has_memory = current_persona.last_analyzed_at is not None or bool(current_persona.last_snapshot_id)
        messages = self.store.list_messages_in_window(
            user_id=self.settings.default_user_id,
            window_start=window_start,
            window_end=window_end,
            include_groups=self._analysis_includes_groups(has_memory=has_memory),
        )
        available_message_count = len(messages)
        retained_message_count = self.store.count_messages(
            self.settings.default_user_id,
            include_groups=self._analysis_includes_groups(has_memory=has_memory),
        )
        automation_settings = self.store.get_automation_settings(self.settings.default_user_id)
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
                limit=max(1, self.settings.context_max_projects),
            )
        )
        chat_context = self._build_chat_context()
        open_questions_context = self._build_open_questions_context(current_persona)
        conversation_context = self._build_conversation_context(included_messages)
        people_memory_context = self._build_people_memory_context(included_messages)
        prompt_context = self._build_analysis_prompt_context_for_intent(
            AnalyzeMemoryPromptContext(
                transcript=transcript,
                conversation_context=conversation_context,
                people_memory_context=people_memory_context,
                current_life_summary=self._build_persona_context(current_persona),
                prior_analyses_context=prior_analyses_context,
                project_context=project_context,
                chat_context=chat_context,
                open_questions_context=open_questions_context,
            ),
            intent=intent,
        )
        prompt_preview = self.deepseek_service.build_analysis_prompt_preview(
            transcript=prompt_context.transcript,
            conversation_context=prompt_context.conversation_context,
            people_memory_context=prompt_context.people_memory_context,
            current_life_summary=prompt_context.current_life_summary,
            prior_analyses_context=prompt_context.prior_analyses_context,
            project_context=prompt_context.project_context,
            chat_context=prompt_context.chat_context,
            open_questions_context=prompt_context.open_questions_context,
            intent="improve_memory" if current_persona.last_analyzed_at else "first_analysis",
            window_hours=max_lookback_hours,
            window_start=window_start,
            window_end=window_end,
            source_message_count=selected_message_count,
            contains_group_messages=any(self._is_group_message(message) for message in included_messages),
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
        has_memory = persona.last_analyzed_at is not None or bool(persona.last_snapshot_id)
        pending_count = self.store.count_pending_messages(
            self.settings.default_user_id,
            include_groups=self._analysis_includes_groups(has_memory=has_memory),
        )
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
        target = 18000 if mode == "first_analysis" else 9000
        return min(self.settings.memory_analysis_max_chars, target)

    def _resolve_bootstrap_bucket_targets(
        self,
        messages_by_bucket: dict[str, list[StoredMessageRecord]],
        *,
        max_messages: int,
    ) -> dict[str, int]:
        targets = {bucket: 0 for bucket, _weight in BOOTSTRAP_BUCKET_WEIGHTS}
        for bucket, weight in BOOTSTRAP_BUCKET_WEIGHTS:
            if not messages_by_bucket.get(bucket):
                continue
            targets[bucket] = min(len(messages_by_bucket[bucket]), max(1, round(max_messages * weight)))

        allocated = sum(targets.values())
        if allocated > max_messages:
            overflow = allocated - max_messages
            for bucket, _weight in reversed(BOOTSTRAP_BUCKET_WEIGHTS):
                removable = min(overflow, max(0, targets[bucket] - 1))
                targets[bucket] -= removable
                overflow -= removable
                if overflow <= 0:
                    break

        remaining = max_messages - sum(targets.values())
        if remaining > 0:
            for bucket, _weight in BOOTSTRAP_BUCKET_WEIGHTS:
                available = max(0, len(messages_by_bucket.get(bucket, [])) - targets[bucket])
                if available <= 0:
                    continue
                addition = min(remaining, available)
                targets[bucket] += addition
                remaining -= addition
                if remaining <= 0:
                    break

        return targets

    def _select_bootstrap_bucket_messages(
        self,
        messages: list[StoredMessageRecord],
        *,
        target_total: int,
    ) -> list[StoredMessageRecord]:
        if not messages or target_total <= 0:
            return []

        outbound_messages = [message for message in messages if message.direction == "outbound"]
        inbound_messages = [message for message in messages if message.direction != "outbound"]
        outbound_target = min(len(outbound_messages), round(target_total * 0.4))
        if outbound_messages and outbound_target <= 0:
            outbound_target = 1
        inbound_target = max(0, target_total - outbound_target)
        if inbound_messages and inbound_target <= 0:
            inbound_target = 1
        total_target = target_total

        selected = [
            *self._select_balanced_messages(outbound_messages, max_messages=outbound_target, prefer_recent=True),
            *self._select_balanced_messages(inbound_messages, max_messages=inbound_target, prefer_recent=True),
        ]
        selected = self._merge_unique_messages(selected)
        if len(selected) >= total_target:
            return selected[:total_target]

        fallback = self._select_balanced_messages(messages, max_messages=total_target * 2, prefer_recent=True)
        selected = self._merge_unique_messages([*selected, *fallback])
        return selected[:total_target]

    def _select_bootstrap_messages(
        self,
        messages: list[StoredMessageRecord],
        *,
        max_messages: int,
    ) -> list[StoredMessageRecord]:
        if not messages:
            return []

        latest_timestamp = max(message.timestamp for message in messages)
        messages_by_bucket: dict[str, list[StoredMessageRecord]] = {
            "recent": [],
            "week": [],
            "older": [],
        }
        for message in sorted(messages, key=lambda item: item.timestamp, reverse=True):
            age_hours = max(0.0, (latest_timestamp - message.timestamp).total_seconds() / 3600)
            if age_hours <= 24:
                messages_by_bucket["recent"].append(message)
            elif age_hours <= 24 * 7:
                messages_by_bucket["week"].append(message)
            else:
                messages_by_bucket["older"].append(message)

        targets = self._resolve_bootstrap_bucket_targets(messages_by_bucket, max_messages=max_messages)
        selected: list[StoredMessageRecord] = []
        for bucket, _weight in BOOTSTRAP_BUCKET_WEIGHTS:
            selected.extend(
                self._select_bootstrap_bucket_messages(
                    messages_by_bucket.get(bucket, []),
                    target_total=targets[bucket],
                )
            )

        selected = self._merge_unique_messages(selected)
        if len(selected) < max_messages:
            fallback = self._select_balanced_messages(messages, max_messages=max_messages * 2, prefer_recent=True)
            selected = self._merge_unique_messages([*selected, *fallback])

        return sorted(selected[:max_messages], key=lambda message: message.timestamp)

    def _merge_unique_messages(self, messages: list[StoredMessageRecord]) -> list[StoredMessageRecord]:
        seen_ids: set[str] = set()
        unique: list[StoredMessageRecord] = []
        for message in sorted(messages, key=lambda item: item.timestamp):
            if message.message_id in seen_ids:
                continue
            seen_ids.add(message.message_id)
            unique.append(message)
        return unique

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
            bucket_key = self._message_selection_bucket_key(message)
            groups.setdefault(bucket_key, []).append(message)

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
            sections.append(self._summarize_message_text(persona.life_summary.strip(), 1000))
        if persona.structural_strengths:
            sections.append(
                "Forcas recorrentes:\n- "
                + "\n- ".join(self._summarize_list_items(persona.structural_strengths, item_limit=6, item_chars=140))
            )
        if persona.structural_routines:
            sections.append(
                "Rotina recorrente:\n- "
                + "\n- ".join(self._summarize_list_items(persona.structural_routines, item_limit=6, item_chars=140))
            )
        if persona.structural_preferences:
            sections.append(
                "Preferencias operacionais:\n- "
                + "\n- ".join(self._summarize_list_items(persona.structural_preferences, item_limit=6, item_chars=140))
            )
        if persona.structural_open_questions:
            sections.append(
                "Lacunas ainda abertas:\n- "
                + "\n- ".join(self._summarize_list_items(persona.structural_open_questions, item_limit=6, item_chars=140))
            )
        return "\n\n".join(section for section in sections if section).strip()

    def _resolve_effective_life_summary(self, raw_summary: str, *, fallback_summary: str) -> str:
        normalized_summary = str(raw_summary or "").strip()
        if normalized_summary:
            return normalized_summary
        return str(fallback_summary or "").strip()

    def _build_open_questions_context(
        self,
        persona: PersonaRecord,
        snapshots: list[MemorySnapshotRecord] | None = None,
    ) -> str:
        if snapshots is None:
            snapshots = self.store.list_memory_snapshots(
                self.settings.default_user_id,
                limit=max(1, self.settings.memory_analysis_context_snapshots),
            )

        lines: list[str] = []
        seen_keys: set[str] = set()

        for question in persona.structural_open_questions[:6]:
            normalized = " ".join(question.split()).strip()
            if not normalized:
                continue
            key = normalized.casefold()
            if key in seen_keys:
                continue
            seen_keys.add(key)
            lines.append(f"- Prioridade atual: {normalized}")

        for snapshot in snapshots[:4]:
            for question in snapshot.open_questions[:4]:
                normalized = " ".join(question.split()).strip()
                if not normalized:
                    continue
                key = normalized.casefold()
                if key in seen_keys:
                    continue
                seen_keys.add(key)
                lines.append(
                    "- Vista recentemente em "
                    f"{snapshot.created_at.astimezone(UTC).strftime('%Y-%m-%d %H:%M UTC')}: {normalized}"
                )
                if len(lines) >= 8:
                    break
            if len(lines) >= 8:
                break

        return "\n".join(lines)

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
                include_groups=False,
            )
            candidate_messages = self._exclude_owner_messages(candidate_messages)
            # Prioriza mensagens que tenham texto útil
            textual_candidates = [m for m in candidate_messages if m.message_text.strip()]
            
            if not textual_candidates and pending_count > 0:
                raise MemoryAnalysisError(
                    f"Encontrei {pending_count} mensagens pendentes, mas nenhuma delas contém texto analisável (apenas imagens, áudios ou figurinhas)."
                )

            selected_messages = self._select_bootstrap_messages(
                textual_candidates,
                max_messages=min(self._resolve_first_analysis_limit(), len(textual_candidates)),
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
                include_groups=True,
            )
            candidate_messages = self._exclude_owner_messages(candidate_messages)
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
                limit=max(1, self.settings.context_max_projects),
            )
        )
        chat_context = self._build_chat_context()
        open_questions_context = self._build_open_questions_context(current_persona)
        prompt_context = self._build_analysis_prompt_context_for_intent(
            AnalyzeMemoryPromptContext(
                transcript=transcript,
                conversation_context=conversation_context,
                people_memory_context=people_memory_context,
                current_life_summary=self._build_persona_context(current_persona),
                prior_analyses_context=prior_analyses_context,
                project_context=project_context,
                chat_context=chat_context,
                open_questions_context=open_questions_context,
            ),
            intent=intent,
        )
        prompt_preview = self.deepseek_service.build_analysis_prompt_preview(
            transcript=prompt_context.transcript,
            conversation_context=prompt_context.conversation_context,
            people_memory_context=prompt_context.people_memory_context,
            current_life_summary=prompt_context.current_life_summary,
            prior_analyses_context=prompt_context.prior_analyses_context,
            project_context=prompt_context.project_context,
            chat_context=prompt_context.chat_context,
            open_questions_context=prompt_context.open_questions_context,
            intent=intent,
            window_hours=window_hours,
            window_start=window_start,
            window_end=window_end,
            source_message_count=len(selected_messages),
            contains_group_messages=any(self._is_group_message(message) for message in selected_messages),
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
        logger.info(
            "fixed_plan_stage_start stage=analyze_memory intent=%s messages=%s window_start=%s window_end=%s",
            plan.intent,
            len(plan.source_messages),
            plan.window_start.isoformat(),
            plan.window_end.isoformat(),
        )
        current_persona = self.get_current_persona()
        prior_analyses_context = self._build_prior_analyses_context()
        existing_projects = self.store.list_project_memories(
            self.settings.default_user_id,
            limit=max(1, self.settings.context_max_projects),
        )
        prompt_context = AnalyzeMemoryPromptContext(
            transcript=plan.transcript,
            conversation_context=plan.conversation_context,
            people_memory_context=plan.people_memory_context,
            current_life_summary=self._build_persona_context(current_persona),
            prior_analyses_context=prior_analyses_context,
            project_context=self._build_project_context(existing_projects),
            chat_context=self._build_chat_context(),
            open_questions_context=self._build_open_questions_context(current_persona),
        )
        prompt_context = self._build_analysis_prompt_context_for_intent(prompt_context, intent=plan.intent)
        self._log_analysis_prompt_context_sizes(plan=plan, context=prompt_context, stage="primary")
        current_life_summary = prompt_context.current_life_summary
        if self._should_chunk_first_analysis(plan):
            deepseek_result = await self._analyze_first_analysis_in_chunks(
                plan,
                current_life_summary=current_life_summary,
                prior_analyses_context=prior_analyses_context,
                project_context=prompt_context.project_context,
                chat_context=prompt_context.chat_context,
                open_questions_context=prompt_context.open_questions_context,
            )
        else:
            deepseek_result = await self._run_analysis_request_with_fallbacks(
                plan=plan,
                context=prompt_context,
            )
        logger.info(
            "fixed_plan_stage_done stage=analyze_memory intent=%s projects=%s contacts=%s open_questions=%s",
            plan.intent,
            len(deepseek_result.active_projects),
            len(deepseek_result.contact_memories),
            len(deepseek_result.open_questions),
        )
        if plan.intent == "first_analysis":
            deepseek_result = self._stabilize_first_analysis_result(deepseek_result)
            logger.info(
                "fixed_plan_stage_done stage=stabilize_first_analysis intent=%s projects=%s contacts=%s",
                plan.intent,
                len(deepseek_result.active_projects),
                len(deepseek_result.contact_memories),
            )
        deepseek_result = self._sanitize_analysis_result(
            deepseek_result,
            source_messages=plan.source_messages,
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
            source_messages=plan.source_messages,
            created_at=analyzed_at,
        )
        logger.info(
            "fixed_plan_stage_done stage=build_snapshot intent=%s coverage=%s source_messages=%s",
            plan.intent,
            snapshot.coverage_score,
            snapshot.source_message_count,
        )
        logger.info(
            "fixed_plan_stage_start stage=merge_projects intent=%s existing_projects=%s candidate_projects=%s",
            plan.intent,
            len(existing_projects),
            len(deepseek_result.active_projects),
        )
        merged_project_seeds = await self._merge_project_seeds_incrementally(
            intent=plan.intent,
            updated_life_summary=effective_life_summary,
            existing_projects=existing_projects,
            candidate_projects=deepseek_result.active_projects,
            window_summary=deepseek_result.window_summary,
            conversation_context=plan.conversation_context,
            source_messages=plan.source_messages,
        )
        logger.info(
            "fixed_plan_stage_done stage=merge_projects intent=%s merged_projects=%s",
            plan.intent,
            len(merged_project_seeds),
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
        logger.info(
            "fixed_plan_stage_done stage=build_structural_profile intent=%s strengths=%s routines=%s preferences=%s open_questions=%s",
            plan.intent,
            len(structural_strengths),
            len(structural_routines),
            len(structural_preferences),
            len(structural_open_questions),
        )
        logger.info("fixed_plan_stage_start stage=persist_persona intent=%s", plan.intent)
        persona = self.store.persist_memory_analysis(
            snapshot=snapshot,
            updated_life_summary=effective_life_summary,
            analyzed_at=analyzed_at,
            structural_strengths=structural_strengths,
            structural_routines=structural_routines,
            structural_preferences=structural_preferences,
            structural_open_questions=structural_open_questions,
        )
        logger.info(
            "fixed_plan_stage_done stage=persist_persona intent=%s persona_id=%s snapshot_id=%s",
            plan.intent,
            str(persona.user_id),
            snapshot.id,
        )
        logger.info("fixed_plan_stage_start stage=persist_people intent=%s", plan.intent)
        self._persist_person_memories(
            messages=plan.source_messages,
            deepseek_result=deepseek_result,
            source_snapshot_id=snapshot.id,
            analyzed_at=analyzed_at,
        )
        logger.info("fixed_plan_stage_done stage=persist_people intent=%s", plan.intent)
        logger.info("fixed_plan_stage_start stage=persist_projects intent=%s", plan.intent)
        projects = self.store.upsert_project_memories(
            user_id=self.settings.default_user_id,
            source_snapshot_id=snapshot.id,
            projects=merged_project_seeds,
            observed_at=analyzed_at,
        )
        logger.info(
            "fixed_plan_stage_done stage=persist_projects intent=%s project_rows=%s",
            plan.intent,
            len(projects),
        )
        return MemoryAnalysisOutcome(
            persona=persona,
            snapshot=snapshot,
            projects=projects,
            source_message_ids=[message.message_id for message in plan.source_messages],
            source_messages=plan.source_messages,
            selected_transcript_chars=plan.selected_transcript_chars,
        )

    async def _run_analyze_memory_request(
        self,
        *,
        plan: FixedAnalysisPlan,
        context: AnalyzeMemoryPromptContext,
        max_output_tokens: int | None = None,
    ) -> DeepSeekMemoryResult:
        return await self.deepseek_service.analyze_memory(
            transcript=context.transcript,
            conversation_context=context.conversation_context,
            people_memory_context=context.people_memory_context,
            current_life_summary=context.current_life_summary,
            prior_analyses_context=context.prior_analyses_context,
            project_context=context.project_context,
            chat_context=context.chat_context,
            open_questions_context=context.open_questions_context,
            intent=plan.intent,
            window_hours=plan.window_hours,
            window_start=plan.window_start,
            window_end=plan.window_end,
            source_message_count=len(plan.source_messages),
            contains_group_messages=any(self._is_group_message(message) for message in plan.source_messages),
            max_output_tokens=max_output_tokens,
        )

    def _should_retry_analyze_memory_with_compact_context(
        self,
        *,
        plan: FixedAnalysisPlan,
        error: DeepSeekError,
    ) -> bool:
        detail = str(error).strip().lower()
        return (
            "timeout" in detail
            or "timed out" in detail
            or "readtimeout" in detail
            or "invalid json" in detail
            or "invalid structured response" in detail
        )

    def _build_compact_analysis_prompt_context(
        self,
        context: AnalyzeMemoryPromptContext,
    ) -> AnalyzeMemoryPromptContext:
        return AnalyzeMemoryPromptContext(
            transcript=context.transcript,
            conversation_context=self._compact_context_block(context.conversation_context, char_budget=700, max_lines=8),
            people_memory_context=self._compact_context_block(context.people_memory_context, char_budget=520, max_lines=7),
            current_life_summary=self._compact_context_block(context.current_life_summary, char_budget=680, max_lines=8),
            prior_analyses_context=self._compact_context_block(context.prior_analyses_context, char_budget=780, max_lines=9),
            project_context=self._compact_context_block(context.project_context, char_budget=620, max_lines=8),
            chat_context=self._compact_context_block(context.chat_context, char_budget=320, max_lines=4),
            open_questions_context=self._compact_context_block(context.open_questions_context, char_budget=220, max_lines=4),
        )

    def _build_incremental_analysis_prompt_context(
        self,
        context: AnalyzeMemoryPromptContext,
    ) -> AnalyzeMemoryPromptContext:
        return AnalyzeMemoryPromptContext(
            transcript=context.transcript,
            conversation_context=self._compact_context_block(context.conversation_context, char_budget=520, max_lines=6),
            people_memory_context=self._compact_context_block(context.people_memory_context, char_budget=420, max_lines=5),
            current_life_summary=self._compact_context_block(context.current_life_summary, char_budget=620, max_lines=7),
            prior_analyses_context=self._compact_context_block(context.prior_analyses_context, char_budget=520, max_lines=6),
            project_context=self._compact_context_block(context.project_context, char_budget=420, max_lines=5),
            chat_context=self._compact_context_block(context.chat_context, char_budget=160, max_lines=3),
            open_questions_context=self._compact_context_block(context.open_questions_context, char_budget=140, max_lines=2),
        )

    def _build_minimal_analysis_prompt_context(
        self,
        context: AnalyzeMemoryPromptContext,
    ) -> AnalyzeMemoryPromptContext:
        return AnalyzeMemoryPromptContext(
            transcript=context.transcript,
            conversation_context=self._compact_context_block(context.conversation_context, char_budget=220, max_lines=3),
            people_memory_context=self._compact_context_block(context.people_memory_context, char_budget=180, max_lines=3),
            current_life_summary=self._compact_context_block(context.current_life_summary, char_budget=260, max_lines=4),
            prior_analyses_context=self._compact_context_block(context.prior_analyses_context, char_budget=220, max_lines=3),
            project_context=self._compact_context_block(context.project_context, char_budget=200, max_lines=3),
            chat_context=self._compact_context_block(context.chat_context, char_budget=120, max_lines=2),
            open_questions_context=self._compact_context_block(context.open_questions_context, char_budget=120, max_lines=2),
        )

    def _build_analysis_prompt_context_for_intent(
        self,
        context: AnalyzeMemoryPromptContext,
        *,
        intent: Literal["first_analysis", "improve_memory"],
    ) -> AnalyzeMemoryPromptContext:
        if intent == "improve_memory":
            return self._build_incremental_analysis_prompt_context(context)
        return self._build_default_analysis_prompt_context(context)

    def _build_default_analysis_prompt_context(
        self,
        context: AnalyzeMemoryPromptContext,
    ) -> AnalyzeMemoryPromptContext:
        return AnalyzeMemoryPromptContext(
            transcript=context.transcript,
            conversation_context=self._compact_context_block(context.conversation_context, char_budget=760, max_lines=9),
            people_memory_context=self._compact_context_block(context.people_memory_context, char_budget=560, max_lines=7),
            current_life_summary=self._compact_context_block(context.current_life_summary, char_budget=760, max_lines=8),
            prior_analyses_context=self._compact_context_block(context.prior_analyses_context, char_budget=760, max_lines=8),
            project_context=self._compact_context_block(context.project_context, char_budget=620, max_lines=7),
            chat_context=self._compact_context_block(context.chat_context, char_budget=220, max_lines=4),
            open_questions_context=self._compact_context_block(context.open_questions_context, char_budget=160, max_lines=3),
        )

    def _compact_context_block(
        self,
        text: str,
        *,
        char_budget: int,
        max_lines: int,
    ) -> str:
        normalized = str(text or "").strip()
        if not normalized:
            return ""

        compacted_lines: list[str] = []
        previous_key: str | None = None
        for raw_line in normalized.splitlines():
            candidate = " ".join(raw_line.split()).strip()
            if not candidate:
                continue
            candidate_key = candidate.casefold()
            if candidate_key == previous_key:
                continue
            compacted_lines.append(candidate)
            previous_key = candidate_key
            if len(compacted_lines) >= max(1, max_lines):
                break

        compacted = "\n".join(compacted_lines) if compacted_lines else normalized
        return self._truncate_context_block(compacted, char_budget=char_budget)

    def _truncate_context_block(self, text: str, *, char_budget: int) -> str:
        normalized = str(text or "").strip()
        if not normalized or char_budget <= 0 or len(normalized) <= char_budget:
            return normalized

        lines = [line.rstrip() for line in normalized.splitlines()]
        kept: list[str] = []
        current_size = 0
        for line in lines:
            candidate = line.strip()
            if not candidate:
                continue
            extra = len(candidate) + (1 if kept else 0)
            if kept and current_size + extra > char_budget:
                break
            if not kept and len(candidate) > char_budget:
                kept.append(candidate[: max(0, char_budget - 16)].rstrip() + " [cortado]")
                return "\n".join(kept)
            kept.append(candidate)
            current_size += extra

        if not kept:
            return normalized[: max(0, char_budget - 16)].rstrip() + " [cortado]"
        if "\n".join(kept) == normalized:
            return normalized
        return "\n".join(kept) + "\n[contexto reduzido automaticamente]"

    def _compact_analysis_max_output_tokens(self) -> int:
        if "reasoner" in self.settings.deepseek_memory_model.strip().lower():
            return 2600
        return 1800

    def _minimal_analysis_max_output_tokens(self) -> int:
        if "reasoner" in self.settings.deepseek_memory_model.strip().lower():
            return 1800
        return 1400

    def _reduced_window_analysis_max_output_tokens(self) -> int:
        if "reasoner" in self.settings.deepseek_memory_model.strip().lower():
            return 1600
        return 1200

    def _should_retry_analyze_memory_with_reduced_window(
        self,
        *,
        plan: FixedAnalysisPlan,
        error: DeepSeekError,
    ) -> bool:
        return (
            plan.intent == "improve_memory"
            and len(plan.source_messages) > 8
            and self._should_retry_analyze_memory_with_compact_context(plan=plan, error=error)
        )

    def _build_reduced_window_retry_plan(
        self,
        *,
        plan: FixedAnalysisPlan,
    ) -> FixedAnalysisPlan | None:
        if len(plan.source_messages) <= 8:
            return None

        reduced_message_count = max(8, min(12, len(plan.source_messages) // 2))
        reduced_char_budget = max(1600, min(3200, plan.selected_transcript_chars // 2))
        transcript, reduced_messages = self._build_transcript(
            plan.source_messages,
            max_messages=reduced_message_count,
            char_budget=reduced_char_budget,
        )
        if not transcript.strip() or len(reduced_messages) >= len(plan.source_messages):
            return None

        reduced_window_start = reduced_messages[0].timestamp
        reduced_window_end = reduced_messages[-1].timestamp
        reduced_window_hours = max(
            1,
            ceil(max(0.0, (reduced_window_end - reduced_window_start).total_seconds()) / 3600),
        )
        scale = max(0.35, len(reduced_messages) / max(1, len(plan.source_messages)))
        return FixedAnalysisPlan(
            intent=plan.intent,
            source_messages=reduced_messages,
            transcript=transcript,
            conversation_context=self._build_conversation_context(reduced_messages),
            people_memory_context=self._build_people_memory_context(reduced_messages),
            window_hours=reduced_window_hours,
            window_start=reduced_window_start,
            window_end=reduced_window_end,
            selected_transcript_chars=len(transcript),
            estimated_input_tokens=max(200, round(plan.estimated_input_tokens * scale)),
            estimated_output_tokens=max(200, round(plan.estimated_output_tokens * scale)),
            estimated_reasoning_tokens=max(0, round(plan.estimated_reasoning_tokens * scale)),
            estimated_cost_floor_usd=round(plan.estimated_cost_floor_usd * scale, 6),
            estimated_cost_ceiling_usd=round(plan.estimated_cost_ceiling_usd * scale, 6),
        )

    async def _run_analysis_request_with_fallbacks(
        self,
        *,
        plan: FixedAnalysisPlan,
        context: AnalyzeMemoryPromptContext,
    ) -> DeepSeekMemoryResult:
        try:
            return await self._run_analyze_memory_request(
                plan=plan,
                context=context,
            )
        except DeepSeekError as exc:
            if not self._should_retry_analyze_memory_with_compact_context(plan=plan, error=exc):
                raise
            compact_context = self._build_compact_analysis_prompt_context(context)
            compact_max_output_tokens = self._compact_analysis_max_output_tokens()
            logger.warning(
                "fixed_plan_stage_retry stage=analyze_memory intent=%s reason=compact_context_retry "
                "compact_max_output_tokens=%s error=%s",
                plan.intent,
                compact_max_output_tokens,
                str(exc),
            )
            self._log_analysis_prompt_context_sizes(plan=plan, context=compact_context, stage="compact_retry")
            try:
                return await self._run_analyze_memory_request(
                    plan=plan,
                    context=compact_context,
                    max_output_tokens=compact_max_output_tokens,
                )
            except DeepSeekError as compact_exc:
                if not self._should_retry_analyze_memory_with_compact_context(plan=plan, error=compact_exc):
                    raise
                minimal_context = self._build_minimal_analysis_prompt_context(context)
                minimal_max_output_tokens = self._minimal_analysis_max_output_tokens()
                logger.warning(
                    "fixed_plan_stage_retry stage=analyze_memory intent=%s reason=minimal_context_retry "
                    "minimal_max_output_tokens=%s error=%s",
                    plan.intent,
                    minimal_max_output_tokens,
                    str(compact_exc),
                )
                self._log_analysis_prompt_context_sizes(plan=plan, context=minimal_context, stage="minimal_retry")
                try:
                    return await self._run_analyze_memory_request(
                        plan=plan,
                        context=minimal_context,
                        max_output_tokens=minimal_max_output_tokens,
                    )
                except DeepSeekError as minimal_exc:
                    if not self._should_retry_analyze_memory_with_reduced_window(plan=plan, error=minimal_exc):
                        raise
                    reduced_plan = self._build_reduced_window_retry_plan(plan=plan)
                    if reduced_plan is None:
                        raise
                    reduced_context = self._build_minimal_analysis_prompt_context(
                        AnalyzeMemoryPromptContext(
                            transcript=reduced_plan.transcript,
                            conversation_context=reduced_plan.conversation_context,
                            people_memory_context=reduced_plan.people_memory_context,
                            current_life_summary=context.current_life_summary,
                            prior_analyses_context=context.prior_analyses_context,
                            project_context=context.project_context,
                            chat_context=context.chat_context,
                            open_questions_context=context.open_questions_context,
                        )
                    )
                    reduced_max_output_tokens = self._reduced_window_analysis_max_output_tokens()
                    logger.warning(
                        "fixed_plan_stage_retry stage=analyze_memory intent=%s reason=reduced_window_retry "
                        "message_count=%s transcript_chars=%s reduced_max_output_tokens=%s error=%s",
                        reduced_plan.intent,
                        len(reduced_plan.source_messages),
                        reduced_plan.selected_transcript_chars,
                        reduced_max_output_tokens,
                        str(minimal_exc),
                    )
                    self._log_analysis_prompt_context_sizes(
                        plan=reduced_plan,
                        context=reduced_context,
                        stage="reduced_window_retry",
                    )
                    return await self._run_analyze_memory_request(
                        plan=reduced_plan,
                        context=reduced_context,
                        max_output_tokens=reduced_max_output_tokens,
                    )

    async def _run_first_analysis_synthesis_with_fallbacks(
        self,
        *,
        partial_analyses_block: str,
        conversation_context: str,
        current_life_summary: str,
        prior_analyses_context: str,
        project_context: str,
        chat_context: str,
        open_questions_context: str,
        window_hours: int,
        window_start: datetime,
        window_end: datetime,
        source_message_count: int,
        partial_analysis_count: int,
        contains_group_messages: bool,
    ) -> DeepSeekMemoryResult:
        try:
            return await self.deepseek_service.synthesize_memory_analyses(
                partial_analyses_block=partial_analyses_block,
                conversation_context=conversation_context,
                current_life_summary=current_life_summary,
                prior_analyses_context=prior_analyses_context,
                project_context=project_context,
                chat_context=chat_context,
                open_questions_context=open_questions_context,
                intent="first_analysis",
                window_hours=window_hours,
                window_start=window_start,
                window_end=window_end,
                source_message_count=source_message_count,
                partial_analysis_count=partial_analysis_count,
                contains_group_messages=contains_group_messages,
            )
        except DeepSeekError as exc:
            detail = str(exc).strip().lower()
            if not any(token in detail for token in ("timeout", "timed out", "readtimeout")):
                raise
            logger.warning(
                "first_analysis_synthesis_retry reason=compact_context_retry error=%s",
                str(exc),
            )
            return await self.deepseek_service.synthesize_memory_analyses(
                partial_analyses_block=self._truncate_context_block(partial_analyses_block, char_budget=2600),
                conversation_context=self._compact_context_block(conversation_context, char_budget=900, max_lines=10),
                current_life_summary=self._compact_context_block(current_life_summary, char_budget=700, max_lines=8),
                prior_analyses_context=self._compact_context_block(prior_analyses_context, char_budget=650, max_lines=8),
                project_context=self._compact_context_block(project_context, char_budget=700, max_lines=8),
                chat_context=self._compact_context_block(chat_context, char_budget=260, max_lines=4),
                open_questions_context=self._compact_context_block(open_questions_context, char_budget=180, max_lines=4),
                intent="first_analysis",
                window_hours=window_hours,
                window_start=window_start,
                window_end=window_end,
                source_message_count=source_message_count,
                partial_analysis_count=partial_analysis_count,
                contains_group_messages=contains_group_messages,
                max_output_tokens=self._minimal_analysis_max_output_tokens(),
            )

    def _log_analysis_prompt_context_sizes(
        self,
        *,
        plan: FixedAnalysisPlan,
        context: AnalyzeMemoryPromptContext,
        stage: str,
    ) -> None:
        logger.info(
            "fixed_plan_prompt_context intent=%s stage=%s transcript_chars=%s conversation_chars=%s "
            "people_chars=%s persona_chars=%s prior_chars=%s project_chars=%s chat_chars=%s open_questions_chars=%s",
            plan.intent,
            stage,
            len(context.transcript),
            len(context.conversation_context),
            len(context.people_memory_context),
            len(context.current_life_summary),
            len(context.prior_analyses_context),
            len(context.project_context),
            len(context.chat_context),
            len(context.open_questions_context),
        )

    def _should_chunk_first_analysis(self, plan: FixedAnalysisPlan) -> bool:
        if plan.intent != "first_analysis":
            return False
        trigger_messages = max(2, self.settings.memory_first_analysis_chunk_trigger_messages)
        return len(plan.source_messages) > trigger_messages

    async def _analyze_first_analysis_in_chunks(
        self,
        plan: FixedAnalysisPlan,
        *,
        current_life_summary: str,
        prior_analyses_context: str,
        project_context: str,
        chat_context: str,
        open_questions_context: str,
    ) -> DeepSeekMemoryResult:
        chunks = self._build_first_analysis_chunks(plan.source_messages)
        if len(chunks) <= 1:
            single_chunk = chunks[0] if chunks else FirstAnalysisChunk(
                source_messages=plan.source_messages,
                transcript=plan.transcript,
                conversation_context=plan.conversation_context,
                people_memory_context=plan.people_memory_context,
                window_start=plan.window_start,
                window_end=plan.window_end,
                selected_transcript_chars=plan.selected_transcript_chars,
            )
            single_chunk_context = self._build_default_analysis_prompt_context(
                AnalyzeMemoryPromptContext(
                    transcript=single_chunk.transcript,
                    conversation_context=single_chunk.conversation_context,
                    people_memory_context=single_chunk.people_memory_context,
                    current_life_summary=current_life_summary,
                    prior_analyses_context=prior_analyses_context,
                    project_context=project_context,
                    chat_context=chat_context,
                    open_questions_context=open_questions_context,
                )
            )
            return await self._run_analysis_request_with_fallbacks(
                plan=plan,
                context=single_chunk_context,
            )

        logger.info(
            "first_analysis_chunking_enabled total_messages=%s total_chars=%s chunk_count=%s chunk_size=%s chunk_char_budget=%s",
            len(plan.source_messages),
            plan.selected_transcript_chars,
            len(chunks),
            self.settings.memory_first_analysis_chunk_size,
            self.settings.memory_first_analysis_chunk_char_budget,
        )

        partial_nodes: list[FirstAnalysisSynthesisNode] = []
        for index, chunk in enumerate(chunks, start=1):
            chunk_context = self._build_default_analysis_prompt_context(
                AnalyzeMemoryPromptContext(
                    transcript=chunk.transcript,
                    conversation_context=chunk.conversation_context,
                    people_memory_context=chunk.people_memory_context,
                    current_life_summary=current_life_summary,
                    prior_analyses_context=prior_analyses_context,
                    project_context=project_context,
                    chat_context=chat_context,
                    open_questions_context=open_questions_context,
                )
            )
            logger.info(
                "first_analysis_chunk_start chunk=%s/%s messages=%s chars=%s window_start=%s window_end=%s",
                index,
                len(chunks),
                len(chunk.source_messages),
                chunk.selected_transcript_chars,
                chunk.window_start.isoformat(),
                chunk.window_end.isoformat(),
            )
            chunk_plan = FixedAnalysisPlan(
                intent="first_analysis",
                source_messages=chunk.source_messages,
                transcript=chunk.transcript,
                conversation_context=chunk.conversation_context,
                people_memory_context=chunk.people_memory_context,
                window_hours=max(1, ceil((chunk.window_end - chunk.window_start).total_seconds() / 3600)),
                window_start=chunk.window_start,
                window_end=chunk.window_end,
                selected_transcript_chars=chunk.selected_transcript_chars,
                estimated_input_tokens=plan.estimated_input_tokens,
                estimated_output_tokens=plan.estimated_output_tokens,
                estimated_reasoning_tokens=plan.estimated_reasoning_tokens,
                estimated_cost_floor_usd=plan.estimated_cost_floor_usd,
                estimated_cost_ceiling_usd=plan.estimated_cost_ceiling_usd,
            )
            partial = await self._run_analysis_request_with_fallbacks(
                plan=chunk_plan,
                context=chunk_context,
            )
            logger.info(
                "first_analysis_chunk_done chunk=%s/%s projects=%s contacts=%s open_questions=%s",
                index,
                len(chunks),
                len(partial.active_projects),
                len(partial.contact_memories),
                len(partial.open_questions),
            )
            partial_nodes.append(
                FirstAnalysisSynthesisNode(
                    label=f"chunk-{index}",
                    source_messages=chunk.source_messages,
                    window_start=chunk.window_start,
                    window_end=chunk.window_end,
                    result=partial,
                )
            )

        return await self._synthesize_first_analysis_nodes_hierarchically(
            nodes=partial_nodes,
            plan=plan,
            current_life_summary=current_life_summary,
            prior_analyses_context=prior_analyses_context,
            project_context=project_context,
            chat_context=chat_context,
            open_questions_context=open_questions_context,
        )

    def _build_first_analysis_chunks(self, messages: list[StoredMessageRecord]) -> list[FirstAnalysisChunk]:
        if not messages:
            return []

        chunk_size = max(8, self.settings.memory_first_analysis_chunk_size)
        char_budget = max(1500, min(self.settings.memory_first_analysis_chunk_char_budget, 4200, self.settings.memory_analysis_max_chars))
        ordered_messages = sorted(messages, key=lambda message: message.timestamp)
        chunks: list[FirstAnalysisChunk] = []

        start_index = 0
        while start_index < len(ordered_messages):
            raw_slice = ordered_messages[start_index : start_index + chunk_size]
            transcript, selected_messages = self._build_transcript(
                raw_slice,
                max_messages=len(raw_slice),
                char_budget=char_budget,
            )
            if not transcript.strip() or not selected_messages:
                start_index += len(raw_slice) or 1
                continue

            chunks.append(
                FirstAnalysisChunk(
                    source_messages=selected_messages,
                    transcript=transcript,
                    conversation_context=self._build_conversation_context(selected_messages),
                    people_memory_context=self._build_people_memory_context(selected_messages),
                    window_start=selected_messages[0].timestamp,
                    window_end=selected_messages[-1].timestamp,
                    selected_transcript_chars=len(transcript),
                )
            )
            start_index += len(raw_slice)

        return chunks

    async def _synthesize_first_analysis_nodes_hierarchically(
        self,
        *,
        nodes: list[FirstAnalysisSynthesisNode],
        plan: FixedAnalysisPlan,
        current_life_summary: str,
        prior_analyses_context: str,
        project_context: str,
        chat_context: str,
        open_questions_context: str,
    ) -> DeepSeekMemoryResult:
        if not nodes:
            raise MemoryAnalysisError("Nenhum bloco de sintese foi gerado para a primeira analise.")

        if len(nodes) == 1:
            logger.info(
                "first_analysis_chunk_synthesis_done levels=%s final_nodes=%s projects=%s contacts=%s open_questions=%s",
                0,
                1,
                len(nodes[0].result.active_projects),
                len(nodes[0].result.contact_memories),
                len(nodes[0].result.open_questions),
            )
            return nodes[0].result

        level = 1
        group_size = max(2, self.settings.memory_first_analysis_synthesis_group_size)
        current_nodes = nodes

        while len(current_nodes) > 1:
            logger.info(
                "first_analysis_synthesis_level_start level=%s node_count=%s group_size=%s",
                level,
                len(current_nodes),
                group_size,
            )
            next_nodes: list[FirstAnalysisSynthesisNode] = []
            group_count = ceil(len(current_nodes) / group_size)

            for group_index, group_start in enumerate(range(0, len(current_nodes), group_size), start=1):
                group = current_nodes[group_start : group_start + group_size]
                if len(group) == 1:
                    logger.info(
                        "first_analysis_synthesis_group_passthrough level=%s group=%s/%s label=%s",
                        level,
                        group_index,
                        group_count,
                        group[0].label,
                    )
                    next_nodes.append(group[0])
                    continue

                merged_messages = self._merge_unique_messages(
                    [message for node in group for message in node.source_messages]
                )
                group_window_start = min(node.window_start for node in group)
                group_window_end = max(node.window_end for node in group)
                group_conversation_context = self._build_conversation_context(merged_messages)
                partial_analyses_block = self._build_partial_analyses_block(group)
                synthesis_context = self._build_default_analysis_prompt_context(
                    AnalyzeMemoryPromptContext(
                        transcript="",
                        conversation_context=group_conversation_context,
                        people_memory_context="",
                        current_life_summary=current_life_summary,
                        prior_analyses_context=prior_analyses_context,
                        project_context=project_context,
                        chat_context=chat_context,
                        open_questions_context=open_questions_context,
                    )
                )
                logger.info(
                    "first_analysis_synthesis_group_start level=%s group=%s/%s node_count=%s messages=%s window_start=%s window_end=%s",
                    level,
                    group_index,
                    group_count,
                    len(group),
                    len(merged_messages),
                    group_window_start.isoformat(),
                    group_window_end.isoformat(),
                )
                synthesized = await self._run_first_analysis_synthesis_with_fallbacks(
                    partial_analyses_block=partial_analyses_block,
                    conversation_context=synthesis_context.conversation_context,
                    current_life_summary=synthesis_context.current_life_summary,
                    prior_analyses_context=synthesis_context.prior_analyses_context,
                    project_context=synthesis_context.project_context,
                    chat_context=synthesis_context.chat_context,
                    open_questions_context=synthesis_context.open_questions_context,
                    window_hours=max(1, ceil((group_window_end - group_window_start).total_seconds() / 3600)),
                    window_start=group_window_start,
                    window_end=group_window_end,
                    source_message_count=len(merged_messages),
                    partial_analysis_count=len(group),
                    contains_group_messages=any(self._is_group_message(message) for message in merged_messages),
                )
                next_label = f"synthesis-l{level}-g{group_index}"
                logger.info(
                    "first_analysis_synthesis_group_done level=%s group=%s/%s label=%s projects=%s contacts=%s open_questions=%s",
                    level,
                    group_index,
                    group_count,
                    next_label,
                    len(synthesized.active_projects),
                    len(synthesized.contact_memories),
                    len(synthesized.open_questions),
                )
                next_nodes.append(
                    FirstAnalysisSynthesisNode(
                        label=next_label,
                        source_messages=merged_messages,
                        window_start=group_window_start,
                        window_end=group_window_end,
                        result=synthesized,
                    )
                )

            current_nodes = next_nodes
            level += 1

        final_result = current_nodes[0].result
        logger.info(
            "first_analysis_chunk_synthesis_done levels=%s final_nodes=%s projects=%s contacts=%s open_questions=%s",
            level - 1,
            len(current_nodes),
            len(final_result.active_projects),
            len(final_result.contact_memories),
            len(final_result.open_questions),
        )
        return final_result

    def _build_partial_analyses_block(
        self,
        nodes: list[FirstAnalysisSynthesisNode],
    ) -> str:
        sections: list[str] = []
        current_size = 0
        char_budget = min(max(1800, self.settings.memory_analysis_max_chars // 4), 4200)
        for index, node in enumerate(nodes, start=1):
            result = node.result
            project_lines = [
                (
                    f"  - nome={project.name}; status={project.status or 'indefinido'}; "
                    f"resumo={self._summarize_message_text(project.summary, 120)}; "
                    f"construindo={self._summarize_message_text(project.what_is_being_built, 90)}; "
                    f"para={self._summarize_message_text(project.built_for, 80)}; "
                    f"proximos={'; '.join(self._summarize_list_items(project.next_steps, item_limit=3, item_chars=70)) or 'nenhum'}"
                )
                for project in result.active_projects[:4]
            ]
            contact_lines = [
                (
                    f"  - person_key={person.person_key}; contato={person.contact_name}; "
                    f"perfil={self._summarize_message_text(person.profile_summary, 90)}; "
                    f"relacao={self._summarize_message_text(person.relationship_summary, 90)}; "
                    f"fatos={'; '.join(self._summarize_list_items(person.salient_facts, item_limit=3, item_chars=70)) or 'nenhum'}; "
                    f"pendencias={'; '.join(self._summarize_list_items(person.open_loops, item_limit=3, item_chars=70)) or 'nenhuma'}; "
                    f"topicos={'; '.join(self._summarize_list_items(person.recent_topics, item_limit=3, item_chars=70)) or 'nenhum'}"
                )
                for person in result.contact_memories[:5]
            ]
            section_lines = [
                f"### Parcial {index} ({node.label})",
                (
                    "Janela: "
                    f"{node.window_start.astimezone(UTC).strftime('%Y-%m-%d %H:%M UTC')} ate "
                    f"{node.window_end.astimezone(UTC).strftime('%Y-%m-%d %H:%M UTC')}"
                ),
                f"Mensagens: {len(node.source_messages)}",
                f"Resumo consolidado parcial: {self._summarize_message_text(result.updated_life_summary, 180)}",
                f"Resumo da janela parcial: {self._summarize_message_text(result.window_summary, 160)}",
                f"Aprendizados: {'; '.join(self._summarize_list_items(result.key_learnings, item_limit=4, item_chars=90)) or 'nenhum'}",
                f"Pessoas e relacoes: {'; '.join(self._summarize_list_items(result.people_and_relationships, item_limit=4, item_chars=90)) or 'nenhum'}",
                f"Rotina: {'; '.join(self._summarize_list_items(result.routine_signals, item_limit=4, item_chars=90)) or 'nenhum'}",
                f"Preferencias: {'; '.join(self._summarize_list_items(result.preferences, item_limit=4, item_chars=90)) or 'nenhuma'}",
                f"Lacunas: {'; '.join(self._summarize_list_items(result.open_questions, item_limit=4, item_chars=90)) or 'nenhuma'}",
                "Projetos detectados:",
                *(project_lines or ["  - nenhum"]),
                "Contatos detectados:",
                *(contact_lines or ["  - nenhum"]),
            ]
            section = "\n".join(section_lines)
            projected_size = current_size + len(section) + 2
            if sections and projected_size > char_budget:
                break
            sections.append(section)
            current_size = projected_size
        return "\n\n".join(sections)

    def _get_observer_owner_phone(self) -> str | None:
        return self.store.get_whatsapp_session_owner_phone(session_id=f"{self.settings.default_user_id}:observer")

    def _is_owner_direct_message(
        self,
        message: StoredMessageRecord,
        *,
        owner_phone: str | None = None,
    ) -> bool:
        if self._is_group_message(message):
            return False
        resolved_owner_phone = owner_phone or self._get_observer_owner_phone()
        if not resolved_owner_phone or not message.contact_phone:
            return False
        return self.store.phone_matches(message.contact_phone, resolved_owner_phone)

    def _exclude_owner_messages(self, messages: list[StoredMessageRecord]) -> list[StoredMessageRecord]:
        owner_phone = self._get_observer_owner_phone()
        if not owner_phone:
            return messages

        filtered = [message for message in messages if not self._is_owner_direct_message(message, owner_phone=owner_phone)]
        removed_count = len(messages) - len(filtered)
        if removed_count > 0:
            logger.info("owner_messages_filtered removed=%s remaining=%s", removed_count, len(filtered))
        return filtered

    def _is_named_person_label(self, value: str | None) -> bool:
        text = (value or "").strip()
        if not text:
            return False
        if text.lower() in {"contato", "participante", "grupo"}:
            return False
        if self.store.is_normal_contact_phone(text):
            return False
        return bool(re.search(r"[A-Za-zÀ-ÿ]", text))

    def _text_mentions_name(self, text: str, name: str) -> bool:
        if not text.strip() or not name.strip():
            return False
        pattern = re.compile(rf"(?<!\w){re.escape(name.strip())}(?!\w)", re.IGNORECASE)
        return pattern.search(text) is not None

    def _build_project_name_replacements(self, messages: list[StoredMessageRecord]) -> dict[str, str]:
        candidate_names: set[str] = set()
        explicit_names: set[str] = set()

        for message in messages:
            if self._is_owner_direct_message(message):
                continue
            name = self._message_person_name(message).strip()
            if not self._is_named_person_label(name):
                continue
            candidate_names.add(name)
            if self._text_mentions_name(message.message_text, name):
                explicit_names.add(name)

        return {name: "o contato" for name in candidate_names if name not in explicit_names}

    def _sanitize_project_text(self, value: str, replacements: dict[str, str]) -> str:
        text = " ".join(value.split()).strip()
        if not text or not replacements:
            return text

        sanitized = text
        for original, replacement in replacements.items():
            sanitized = re.sub(
                rf"(?<!\w){re.escape(original)}(?!\w)",
                replacement,
                sanitized,
                flags=re.IGNORECASE,
            )

        return re.sub(r"\s{2,}", " ", sanitized).strip(" ,;")

    def _sanitize_project_string_list(self, values: list[str], replacements: dict[str, str], *, limit: int) -> list[str]:
        sanitized: list[str] = []
        for value in values:
            cleaned = self._sanitize_project_text(value, replacements)
            if cleaned:
                sanitized.append(cleaned)
        return sanitized[:limit]

    def _normalize_project_match_text(self, value: str | None) -> str:
        normalized = re.sub(r"[^0-9a-zà-ÿ]+", " ", str(value or "").casefold())
        return " ".join(normalized.split()).strip()

    def _extract_project_keywords(self, project: DeepSeekProjectMemory) -> list[str]:
        keywords: list[str] = []
        seen: set[str] = set()
        for raw_value in [
            project.name,
            project.summary,
            project.status,
            project.what_is_being_built,
            project.built_for,
            *project.next_steps,
            *project.evidence,
        ]:
            for token in self._normalize_project_match_text(raw_value).split():
                if len(token) < 4 or token in PROJECT_KEYWORD_STOPWORDS or token.isdigit():
                    continue
                if token in seen:
                    continue
                seen.add(token)
                keywords.append(token)
        return keywords[:14]

    def _select_project_support_messages(
        self,
        *,
        project: DeepSeekProjectMemory,
        source_messages: list[StoredMessageRecord],
        limit: int = 4,
    ) -> list[StoredMessageRecord]:
        normalized_name = self._normalize_project_match_text(project.name)
        name_tokens = [token for token in normalized_name.split() if len(token) >= 4]
        keywords = self._extract_project_keywords(project)
        scored: list[tuple[int, datetime, StoredMessageRecord]] = []
        seen_messages: set[str] = set()

        for message in source_messages:
            text = self._normalize_project_match_text(message.message_text)
            if not text:
                continue
            score = 0
            if normalized_name and normalized_name in text:
                score += 8
            score += sum(2 for token in name_tokens if token in text)
            score += sum(1 for token in keywords if token not in name_tokens and token in text)
            if score <= 0:
                continue
            if message.direction == "outbound":
                score += 1
            if len(text) >= 80:
                score += 1
            message_key = text[:220]
            if message_key in seen_messages:
                continue
            seen_messages.add(message_key)
            scored.append((score, message.timestamp, message))

        scored.sort(key=lambda item: (item[0], item[1]), reverse=True)
        return [message for _, _, message in scored[: max(1, limit)]]

    def _project_message_snippet(self, message: StoredMessageRecord) -> str:
        snippet = self._summarize_message_text(message.message_text, 150)
        if not snippet:
            return ""
        prefix = "Dono" if message.direction == "outbound" else "Mensagem"
        return f"{prefix}: {snippet}"

    def _is_weak_project_text(self, value: str | None, *, min_chars: int = 28) -> bool:
        normalized = " ".join(str(value or "").split()).strip()
        if len(normalized) < min_chars:
            return True
        lowered = normalized.casefold()
        generic_prefixes = (
            "projeto ativo",
            "frente ativa",
            "tema recorrente",
            "demanda em andamento",
            "assunto em aberto",
            "projeto em andamento",
            "frente em andamento",
        )
        if lowered.startswith(generic_prefixes):
            return True
        return len(set(self._normalize_project_match_text(normalized).split())) < 4

    def _extract_project_action_candidate(self, text: str) -> str | None:
        compact = " ".join(text.split()).strip(" .,:;")
        if len(compact) < 12 or len(compact) > 180 or "?" in compact:
            return None
        for pattern in PROJECT_ACTION_PATTERNS:
            match = pattern.search(compact)
            if match:
                action = " ".join(match.group(0).split()).strip(" .,:;")
                if len(action) >= 12:
                    return action
        return None

    def _merge_project_next_steps(
        self,
        *,
        project: DeepSeekProjectMemory,
        support_messages: list[StoredMessageRecord],
    ) -> list[str]:
        merged: list[str] = []
        seen: set[str] = set()
        for item in project.next_steps:
            cleaned = " ".join(item.split()).strip(" .,:;")
            if not cleaned:
                continue
            key = cleaned.casefold()
            if key in seen:
                continue
            seen.add(key)
            merged.append(cleaned)

        for message in support_messages:
            if message.direction != "outbound":
                continue
            candidate = self._extract_project_action_candidate(message.message_text)
            if not candidate:
                continue
            key = candidate.casefold()
            if key in seen:
                continue
            seen.add(key)
            merged.append(candidate)
            if len(merged) >= 4:
                break

        return merged[:4]

    def _compose_project_summary(
        self,
        *,
        project: DeepSeekProjectMemory,
        what_is_being_built: str,
        next_steps: list[str],
        evidence: list[str],
    ) -> str:
        clauses: list[str] = []
        if what_is_being_built:
            clauses.append(what_is_being_built.rstrip("."))
        elif evidence:
            raw_evidence = evidence[0].split(":", 1)[-1].strip()
            clauses.append(f"Frente recorrente ligada a {raw_evidence.rstrip('.')}")
        if project.built_for.strip():
            clauses.append(f"Direcionado para {project.built_for.strip().rstrip('.')}")
        if project.status.strip():
            clauses.append(f"Status percebido: {project.status.strip().rstrip('.')}")
        if next_steps:
            clauses.append(f"Proximo passo mais concreto: {next_steps[0].rstrip('.')}")
        summary = ". ".join(clause for clause in clauses if clause).strip(" .")
        if not summary:
            return ""
        return self._summarize_message_text(summary + ".", 240)

    def _project_has_minimum_detail(self, project: DeepSeekProjectMemory) -> bool:
        strong_signals = 0
        if not self._is_weak_project_text(project.summary, min_chars=36):
            strong_signals += 1
        if not self._is_weak_project_text(project.what_is_being_built, min_chars=24):
            strong_signals += 1
        if project.built_for.strip():
            strong_signals += 1
        if len(project.next_steps) >= 1:
            strong_signals += 1
        if len(project.evidence) >= 2:
            strong_signals += 1
        return strong_signals >= 2

    def _refine_project_candidate(
        self,
        *,
        project: DeepSeekProjectMemory,
        source_messages: list[StoredMessageRecord],
    ) -> DeepSeekProjectMemory | None:
        support_messages = self._select_project_support_messages(project=project, source_messages=source_messages)
        evidence = self._sanitize_project_string_list(project.evidence, {}, limit=8)
        for message in support_messages:
            snippet = self._project_message_snippet(message)
            if snippet and snippet.casefold() not in {item.casefold() for item in evidence}:
                evidence.append(snippet)
            if len(evidence) >= 4:
                break

        what_is_being_built = project.what_is_being_built.strip()
        if self._is_weak_project_text(what_is_being_built, min_chars=24):
            if not self._is_weak_project_text(project.summary, min_chars=36):
                what_is_being_built = self._summarize_message_text(project.summary, 160)
            elif support_messages:
                what_is_being_built = self._summarize_message_text(support_messages[0].message_text, 160)

        next_steps = self._merge_project_next_steps(project=project, support_messages=support_messages)
        summary = project.summary.strip()
        if self._is_weak_project_text(summary, min_chars=36):
            summary = self._compose_project_summary(
                project=project,
                what_is_being_built=what_is_being_built,
                next_steps=next_steps,
                evidence=evidence,
            )

        refined = project.model_copy(
            update={
                "summary": summary,
                "what_is_being_built": what_is_being_built,
                "next_steps": next_steps,
                "evidence": evidence[:4],
            }
        )
        if not refined.name.strip() or not refined.summary.strip():
            return None
        if not self._project_has_minimum_detail(refined):
            return None
        return refined

    def _sanitize_project_candidates(
        self,
        projects: list[DeepSeekProjectMemory],
        *,
        source_messages: list[StoredMessageRecord],
    ) -> list[DeepSeekProjectMemory]:
        replacements = self._build_project_name_replacements(source_messages)
        if not projects:
            return []

        sanitized_projects: list[DeepSeekProjectMemory] = []
        seen_names: set[str] = set()
        for project in projects:
            sanitized_project = DeepSeekProjectMemory(
                name=self._sanitize_project_text(project.name, replacements),
                summary=self._sanitize_project_text(project.summary, replacements),
                status=self._sanitize_project_text(project.status, replacements),
                what_is_being_built=self._sanitize_project_text(project.what_is_being_built, replacements),
                built_for=self._sanitize_project_text(project.built_for, replacements),
                next_steps=self._sanitize_project_string_list(project.next_steps, replacements, limit=6),
                evidence=self._sanitize_project_string_list(project.evidence, replacements, limit=8),
            )
            refined_project = self._refine_project_candidate(
                project=sanitized_project,
                source_messages=source_messages,
            )
            if refined_project is None:
                continue
            dedupe_key = refined_project.name.casefold()
            if dedupe_key in seen_names:
                continue
            seen_names.add(dedupe_key)
            sanitized_projects.append(refined_project)

        if replacements:
            logger.info(
                "project_names_sanitized replacements=%s projects_in=%s projects_out=%s",
                sorted(replacements.keys()),
                len(projects),
                len(sanitized_projects),
            )
        return sanitized_projects[:6]

    def _sanitize_analysis_result(
        self,
        result: DeepSeekMemoryResult,
        *,
        source_messages: list[StoredMessageRecord],
    ) -> DeepSeekMemoryResult:
        filtered_messages = self._exclude_owner_messages(source_messages)
        grouped_messages = self._group_messages_by_person(filtered_messages)
        replacements = self._build_project_name_replacements(filtered_messages)
        sanitized_contacts = self._sanitize_contact_memories(
            result.contact_memories,
            grouped_messages=grouped_messages,
        )

        return DeepSeekMemoryResult(
            updated_life_summary=self._sanitize_project_text(result.updated_life_summary, replacements),
            window_summary=self._sanitize_project_text(result.window_summary, replacements),
            key_learnings=self._sanitize_project_string_list(result.key_learnings, replacements, limit=12),
            people_and_relationships=self._sanitize_project_string_list(result.people_and_relationships, replacements, limit=12),
            routine_signals=self._sanitize_project_string_list(result.routine_signals, replacements, limit=12),
            preferences=self._sanitize_project_string_list(result.preferences, replacements, limit=12),
            open_questions=self._sanitize_project_string_list(result.open_questions, replacements, limit=12),
            active_projects=self._sanitize_project_candidates(
                result.active_projects,
                source_messages=filtered_messages,
            ),
            contact_memories=sanitized_contacts[:24],
        )

    def _sanitize_contact_memories(
        self,
        contacts: list[DeepSeekPersonMemory],
        *,
        grouped_messages: dict[str, list[StoredMessageRecord]],
    ) -> list[DeepSeekPersonMemory]:
        if not contacts or not grouped_messages:
            return []

        normalized_name_to_keys: dict[str, list[str]] = {}
        for person_key, messages in grouped_messages.items():
            last_message = messages[-1]
            candidate_names = {
                self._normalize_contact_lookup_name(self._message_person_name(last_message)),
                self._normalize_contact_lookup_name(self._message_conversation_label(last_message)),
            }
            for candidate in candidate_names:
                if not candidate:
                    continue
                normalized_name_to_keys.setdefault(candidate, []).append(person_key)

        sanitized: list[DeepSeekPersonMemory] = []
        seen_keys: set[str] = set()
        for person in contacts:
            resolved_key = person.person_key if person.person_key in grouped_messages else None
            if resolved_key is None:
                normalized_contact_name = self._normalize_contact_lookup_name(person.contact_name)
                candidate_keys = normalized_name_to_keys.get(normalized_contact_name, [])
                if len(candidate_keys) == 1:
                    resolved_key = candidate_keys[0]
            if resolved_key is None or resolved_key in seen_keys:
                continue

            grouped = grouped_messages[resolved_key]
            last_message = grouped[-1]
            resolved_name = person.contact_name.strip()
            if self._contact_name_is_generic(resolved_name):
                resolved_name = self._message_person_name(last_message)
            sanitized.append(
                DeepSeekPersonMemory(
                    person_key=resolved_key,
                    contact_name=resolved_name,
                    profile_summary=person.profile_summary,
                    relationship_type=person.relationship_type,
                    relationship_summary=person.relationship_summary,
                    salient_facts=person.salient_facts,
                    open_loops=person.open_loops,
                    recent_topics=person.recent_topics,
                )
            )
            seen_keys.add(resolved_key)

        return sanitized

    def _normalize_contact_lookup_name(self, value: str | None) -> str:
        normalized = " ".join(str(value or "").split()).strip().casefold()
        return normalized

    def _contact_name_is_generic(self, value: str | None) -> bool:
        normalized = self._normalize_contact_lookup_name(value)
        return normalized in {"", "contato", "o contato", "a contato", "pessoa", "unknown"}

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

        owner_phone = self._get_observer_owner_phone()
        seeds: list[PersonMemorySeed] = []
        for person in deepseek_result.contact_memories:
            grouped = grouped_messages.get(person.person_key)
            if not grouped:
                continue
            last_message = grouped[-1]
            if self._is_owner_direct_message(last_message, owner_phone=owner_phone):
                continue
            seeds.append(
                PersonMemorySeed(
                    person_key=person.person_key,
                    contact_name=person.contact_name.strip() or self._message_person_name(last_message),
                    contact_phone=self._message_person_phone(last_message),
                    chat_jid=self._message_person_jid(last_message),
                    profile_summary=person.profile_summary,
                    relationship_type=person.relationship_type,
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
        intent: Literal["first_analysis", "improve_memory"],
        updated_life_summary: str,
        existing_projects: list[ProjectMemoryRecord],
        candidate_projects: list[DeepSeekProjectMemory],
        window_summary: str,
        conversation_context: str,
        source_messages: list[StoredMessageRecord],
    ) -> list[ProjectMemorySeed]:
        sanitized_candidates = self._sanitize_project_candidates(
            candidate_projects,
            source_messages=source_messages,
        )
        if not existing_projects and not sanitized_candidates:
            logger.info("merge_projects_skipped reason=no_existing_and_no_candidates")
            return []
        if intent == "improve_memory" and not sanitized_candidates:
            logger.info(
                "merge_projects_skipped reason=no_incremental_candidates existing=%s",
                len(existing_projects),
            )
            return []
        merged_result = await self.deepseek_service.merge_projects_incrementally(
            current_life_summary=updated_life_summary,
            current_project_context=self._build_project_context(existing_projects),
            candidate_projects_block=self._build_candidate_projects_block(sanitized_candidates),
            recent_window_summary=window_summary,
            conversation_context=conversation_context,
        )
        seeds = self._project_memory_seeds_from_deepseek(
            self._sanitize_project_candidates(
                merged_result.active_projects if merged_result.active_projects else sanitized_candidates,
                source_messages=source_messages,
            ),
        )
        logger.info(
            "merge_projects_result existing=%s candidates=%s merged=%s",
            len(existing_projects),
            len(sanitized_candidates),
            len(seeds),
        )
        return seeds[:8]

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

    def list_relations(self, *, limit: int = 80) -> list[PersonMemoryRecord]:
        return self.store.list_person_memories(self.settings.default_user_id, limit=limit)

    def update_relation(
        self,
        *,
        contact_name: str,
        new_contact_name: str | None = None,
        relationship_type: str | None = None,
    ) -> PersonMemoryRecord | None:
        return self.store.update_person_memory(
            user_id=self.settings.default_user_id,
            contact_name=contact_name,
            new_contact_name=new_contact_name,
            relationship_type=relationship_type,
            updated_at=datetime.now(UTC),
        )

    def update_project_completion(
        self,
        *,
        project_key: str,
        completed: bool,
        completion_notes: str = "",
    ) -> ProjectMemoryRecord | None:
        return self.store.update_project_manual_completion(
            user_id=self.settings.default_user_id,
            project_key=project_key,
            completed=completed,
            completion_notes=completion_notes,
            changed_at=datetime.now(UTC),
        )

    def update_project(
        self,
        *,
        project_key: str,
        project_name: str | None = None,
        summary: str | None = None,
        status: str | None = None,
        what_is_being_built: str | None = None,
        built_for: str | None = None,
        next_steps: list[str] | None = None,
        evidence: list[str] | None = None,
    ) -> ProjectMemoryRecord | None:
        return self.store.update_project_memory(
            user_id=self.settings.default_user_id,
            project_key=project_key,
            project_name=project_name,
            summary=summary,
            status=status,
            what_is_being_built=what_is_being_built,
            built_for=built_for,
            next_steps=next_steps,
            evidence=evidence,
            updated_at=datetime.now(UTC),
        )

    def create_project(
        self,
        *,
        project_name: str,
        summary: str,
        status: str = "",
        what_is_being_built: str = "",
        built_for: str = "",
        next_steps: list[str] | None = None,
        evidence: list[str] | None = None,
    ) -> ProjectMemoryRecord:
        return self.store.create_project_memory(
            user_id=self.settings.default_user_id,
            project_name=project_name,
            summary=summary,
            status=status,
            what_is_being_built=what_is_being_built,
            built_for=built_for,
            next_steps=next_steps or [],
            evidence=evidence or [],
            created_at=datetime.now(UTC),
        )

    async def edit_project_with_ai(
        self,
        *,
        project_key: str,
        instruction: str,
    ) -> tuple[ProjectMemoryRecord | None, str]:
        current_persona = self.get_current_persona()
        projects = self.store.list_project_memories(self.settings.default_user_id, limit=max(8, self.settings.context_max_projects))
        target_project = next((project for project in projects if project.project_key == project_key), None)
        if target_project is None:
            return None, ""

        project_context = self._build_project_context(projects)
        target_project_block = self._build_project_context([target_project])
        result = await self.deepseek_service.edit_project_memory(
            current_life_summary=self._build_persona_context(current_persona),
            current_project_context=project_context,
            target_project_block=target_project_block,
            instruction=instruction,
        )
        updated = self.store.update_project_memory(
            user_id=self.settings.default_user_id,
            project_key=project_key,
            project_name=result.project.name,
            summary=result.project.summary,
            status=result.project.status,
            what_is_being_built=result.project.what_is_being_built,
            built_for=result.project.built_for,
            next_steps=result.project.next_steps,
            evidence=result.project.evidence,
            updated_at=datetime.now(UTC),
        )
        return updated, (result.assistant_message or "Projeto atualizado com ajuda da IA.")

    def delete_project(
        self,
        *,
        project_key: str,
    ) -> bool:
        return self.store.delete_project_memory(
            user_id=self.settings.default_user_id,
            project_key=project_key,
        )

    async def refine_saved_memory(self) -> MemoryRefinementOutcome:
        current_persona = self.get_current_persona()
        snapshots = self.store.list_memory_snapshots(self.settings.default_user_id, limit=max(1, self.settings.memory_analysis_context_snapshots))
        projects = self.store.list_project_memories(self.settings.default_user_id, limit=max(1, self.settings.context_max_projects))

        if not current_persona.life_summary.strip() and not snapshots and not projects:
            raise MemoryAnalysisError(
                "Ainda nao ha memoria suficiente salva no banco local para refinar. Rode ao menos uma analise primeiro."
            )

        # Passo 1: Refinamento da Persona e Projetos
        refinement_context = self._build_default_analysis_prompt_context(
            AnalyzeMemoryPromptContext(
                transcript="",
                conversation_context="",
                people_memory_context="",
                current_life_summary=self._build_persona_context(current_persona),
                prior_analyses_context=self._build_prior_analyses_context_from_snapshots(snapshots),
                project_context=self._build_project_context(projects),
                chat_context=self._build_chat_context(),
                open_questions_context="",
            )
        )
        refined = await self.deepseek_service.refine_saved_memory(
            current_life_summary=refinement_context.current_life_summary,
            prior_analyses_context=refinement_context.prior_analyses_context,
            project_context=refinement_context.project_context,
            chat_context=refinement_context.chat_context,
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
                                relationship_type=c_refined.relationship_type,
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
            if memory.relationship_type:
                lines.append(f"  Tipo de relacao: {memory.relationship_type}")
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
        char_budget = min(max(900, self.settings.memory_analysis_snapshot_context_chars // 4), 2000)

        for snapshot in reversed(snapshots):
            lines = [
                f"- Analise de {snapshot.window_hours}h em {snapshot.created_at.astimezone(UTC).strftime('%Y-%m-%d %H:%M UTC')}",
                f"  Resumo da janela: {self._summarize_message_text(snapshot.window_summary, 180)}",
            ]
            if snapshot.key_learnings:
                lines.append(
                    "  Aprendizados: "
                    + "; ".join(self._summarize_list_items(snapshot.key_learnings, item_limit=2, item_chars=84))
                )
            if snapshot.people_and_relationships:
                lines.append(
                    "  Pessoas e relacoes: "
                    + "; ".join(self._summarize_list_items(snapshot.people_and_relationships, item_limit=2, item_chars=84))
                )
            if snapshot.routine_signals:
                lines.append(
                    "  Rotina: "
                    + "; ".join(self._summarize_list_items(snapshot.routine_signals, item_limit=2, item_chars=84))
                )
            if snapshot.preferences:
                lines.append(
                    "  Preferencias: "
                    + "; ".join(self._summarize_list_items(snapshot.preferences, item_limit=2, item_chars=84))
                )
            if snapshot.open_questions:
                lines.append(
                    "  Lacunas abertas: "
                    + "; ".join(self._summarize_list_items(snapshot.open_questions, item_limit=2, item_chars=84))
                )

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
        char_budget = min(max(1100, self.settings.memory_analysis_snapshot_context_chars // 4), 2200)

        for project in projects:
            lines = [
                f"- Projeto: {project.project_name}",
                f"  Resumo: {self._summarize_message_text(project.summary, 180)}",
            ]
            if project.status:
                lines.append(f"  Status: {self._summarize_message_text(project.status, 70)}")
            if project.what_is_being_built:
                lines.append(
                    f"  O que esta sendo desenvolvido: {self._summarize_message_text(project.what_is_being_built, 120)}"
                )
            if project.built_for:
                lines.append(f"  Para quem: {self._summarize_message_text(project.built_for, 90)}")
            if project.next_steps:
                lines.append(
                    "  Proximos passos: "
                    + "; ".join(self._summarize_list_items(project.next_steps, item_limit=2, item_chars=76))
                )
            if project.evidence:
                lines.append(
                    "  Evidencias: "
                    + "; ".join(self._summarize_list_items(project.evidence, item_limit=2, item_chars=76))
                )
            if project.completion_source == "manual" and project.manual_completed_at is not None:
                lines.append(
                    f"  Atualizacao manual do usuario: marcado como concluido em {project.manual_completed_at.isoformat()}"
                )
                if project.manual_completion_notes.strip():
                    lines.append(
                        f"  Observacao manual: {self._summarize_message_text(project.manual_completion_notes.strip(), 110)}"
                    )

            section = "\n".join(lines)
            projected_size = current_size + len(section) + 2
            if sections and projected_size > char_budget:
                break
            sections.append(section)
            current_size = projected_size

        return "\n\n".join(sections)

    def _build_chat_context(self) -> str:
        sections: list[str] = []
        current_size = 0
        char_budget = min(max(800, self.settings.memory_analysis_snapshot_context_chars // 5), 1300)

        owner_phone = self.store.get_whatsapp_session_owner_phone(
            session_id=f"{self.settings.default_user_id}:observer"
        )
        if owner_phone:
            owner_whatsapp_messages = self.store.list_whatsapp_agent_messages_for_contact(
                user_id=self.settings.default_user_id,
                contact_phone=owner_phone,
                limit=max(8, self.settings.context_max_history_messages),
            )
            owner_whatsapp_section = self._build_owner_whatsapp_chat_context(owner_whatsapp_messages)
            if owner_whatsapp_section:
                section = "[WhatsApp do proprio dono com Orion]\n" + owner_whatsapp_section
                current_size += len(section) + 2
                sections.append(section)

        return "\n\n".join(sections)

    def _build_owner_whatsapp_chat_context(self, messages: list[WhatsAppAgentMessageRecord]) -> str:
        if not messages:
            return ""

        sections: list[str] = []
        current_size = 0
        char_budget = min(max(720, self.settings.memory_analysis_snapshot_context_chars // 5), 1300)

        for message in messages:
            content = " ".join(message.content.split()).strip()
            if not content:
                continue
            role = "Dono" if message.role == "user" or message.direction == "inbound" else "Orion"
            line = (
                f"- {role} ({self._owner_whatsapp_message_channel_label(message)}): "
                f"{self._summarize_message_text(content, 180)}"
            )
            projected_size = current_size + len(line) + 1
            if sections and projected_size > char_budget:
                break
            sections.append(line)
            current_size = projected_size

        return "\n".join(sections)

    def _owner_whatsapp_message_channel_label(self, message: WhatsAppAgentMessageRecord) -> str:
        metadata = message.metadata if isinstance(message.metadata, dict) else {}
        cli_mode = bool(metadata.get("cli_mode_enabled")) or str(message.processing_status).startswith("cli_")
        if not cli_mode:
            return "WhatsApp"
        qualifier = "WhatsApp CLI"
        if metadata.get("admin_actor") and metadata.get("server_operator"):
            qualifier = "WhatsApp CLI admin servidor"
        cwd = str(metadata.get("cli_cwd") or "").strip()
        if cwd:
            return f"{qualifier} cwd={self._summarize_message_text(cwd, 70)}"
        return qualifier

    def _analysis_includes_groups(self, *, has_memory: bool) -> bool:
        return has_memory

    def _is_group_message(self, message: StoredMessageRecord) -> bool:
        return str(message.chat_type or "").strip().lower() == "group"

    def _message_person_key(self, message: StoredMessageRecord) -> str | None:
        if self._is_group_message(message):
            if message.direction == "outbound":
                return None
            return self.store.build_person_key(
                contact_phone=message.participant_phone,
                chat_jid=message.participant_jid,
                contact_name=message.participant_name or message.contact_name,
            )
        return self.store.build_person_key(
            contact_phone=message.contact_phone,
            chat_jid=message.chat_jid,
            contact_name=message.contact_name,
        )

    def _message_person_name(self, message: StoredMessageRecord) -> str:
        if self._is_group_message(message):
            return (
                (message.participant_name or "").strip()
                or message.contact_name.strip()
                or message.participant_phone
                or message.participant_jid
                or "Participante"
            )
        return message.contact_name.strip() or message.contact_phone or "Contato"

    def _message_person_phone(self, message: StoredMessageRecord) -> str | None:
        if self._is_group_message(message):
            return message.participant_phone if message.direction != "outbound" else None
        return message.contact_phone

    def _message_person_jid(self, message: StoredMessageRecord) -> str | None:
        if self._is_group_message(message):
            return message.participant_jid if message.direction != "outbound" else None
        return message.chat_jid

    def _message_conversation_key(self, message: StoredMessageRecord) -> str:
        if self._is_group_message(message):
            chat_jid = (message.chat_jid or message.chat_name or "grupo").strip().lower()
            return f"group:{chat_jid}"
        return "direct:" + self.store.build_person_key(
            contact_phone=message.contact_phone,
            chat_jid=message.chat_jid,
            contact_name=message.contact_name,
        )

    def _message_conversation_label(self, message: StoredMessageRecord) -> str:
        if self._is_group_message(message):
            return (message.chat_name or "").strip() or message.chat_jid or "Grupo"
        return message.contact_name.strip() or message.contact_phone or "Contato"

    def _message_selection_bucket_key(self, message: StoredMessageRecord) -> str:
        if self._is_group_message(message):
            return self._message_conversation_key(message)
        return self._message_person_key(message) or self._message_conversation_key(message)

    def _message_speaker_label(self, message: StoredMessageRecord) -> str:
        if message.direction == "outbound":
            return "Dono"
        return self._message_person_name(message)

    def _group_messages_by_person(self, messages: list[StoredMessageRecord]) -> dict[str, list[StoredMessageRecord]]:
        groups: dict[str, list[StoredMessageRecord]] = {}
        for message in messages:
            person_key = self._message_person_key(message)
            if person_key is None:
                continue
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
        char_budget = min(max(1100, self.settings.memory_analysis_snapshot_context_chars // 3), 2200)

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
            if memory.relationship_type:
                lines.append(f"  Tipo de relacao: {memory.relationship_type}")
            if memory.profile_summary:
                lines.append(f"  Quem e: {self._summarize_message_text(memory.profile_summary, 140)}")
            if memory.relationship_summary:
                lines.append(f"  Relacao com o dono: {self._summarize_message_text(memory.relationship_summary, 140)}")
            if memory.salient_facts:
                lines.append(
                    "  Fatos marcantes: "
                    + "; ".join(self._summarize_list_items(memory.salient_facts, item_limit=3, item_chars=72))
                )
            if memory.open_loops:
                lines.append(
                    "  Pendencias abertas: "
                    + "; ".join(self._summarize_list_items(memory.open_loops, item_limit=3, item_chars=72))
                )
            if memory.recent_topics:
                lines.append(
                    "  Topicos recentes: "
                    + "; ".join(self._summarize_list_items(memory.recent_topics, item_limit=3, item_chars=72))
                )

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
            key = self._message_conversation_key(message)
            group = groups.get(key)
            is_group = self._is_group_message(message)
            if group is None:
                group = {
                    "conversation_key": key,
                    "conversation_label": self._message_conversation_label(message),
                    "chat_type": "group" if is_group else "direct",
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
                if is_group:
                    speaker = self._message_speaker_label(message)
                    direction_label = "Dono -> grupo" if message.direction == "outbound" else f"{speaker} -> grupo"
                else:
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
        char_budget = min(max(1200, self.settings.memory_analysis_snapshot_context_chars // 3), 2400)

        for group in ordered_groups[:8]:
            total_messages = int(group["inbound_count"]) + int(group["outbound_count"])
            lines = [
                f"- conversation_key: {group['conversation_key']}",
                f"  Conversa: {group['conversation_label']}",
                f"  Tipo: {'grupo' if group['chat_type'] == 'group' else 'direta'}",
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
        source_messages: list[StoredMessageRecord] | None = None,
        created_at: datetime,
    ) -> MemorySnapshotRecord:
        (
            distinct_contact_count,
            inbound_message_count,
            outbound_message_count,
            coverage_score,
        ) = self._compute_snapshot_coverage(source_messages or [], window_hours=window_hours)
        return MemorySnapshotRecord(
            id=str(uuid4()),
            user_id=self.settings.default_user_id,
            window_hours=window_hours,
            window_start=window_start,
            window_end=window_end,
            source_message_count=source_message_count,
            distinct_contact_count=distinct_contact_count,
            inbound_message_count=inbound_message_count,
            outbound_message_count=outbound_message_count,
            coverage_score=coverage_score,
            window_summary=result.window_summary,
            key_learnings=result.key_learnings,
            people_and_relationships=result.people_and_relationships,
            routine_signals=result.routine_signals,
            preferences=result.preferences,
            open_questions=result.open_questions,
            created_at=created_at,
        )

    def _compute_snapshot_coverage(
        self,
        messages: list[StoredMessageRecord],
        *,
        window_hours: int,
    ) -> tuple[int, int, int, int]:
        if not messages:
            return 0, 0, 0, 0

        contact_keys = {
            self._message_person_key(message) or self._message_conversation_key(message)
            for message in messages
        }
        inbound_message_count = sum(1 for message in messages if message.direction != "outbound")
        outbound_message_count = sum(1 for message in messages if message.direction == "outbound")
        total_messages = max(1, len(messages))
        first_analysis_limit = max(1, self._resolve_first_analysis_limit())
        contact_score = min(35, len(contact_keys) * 5)
        volume_score = min(25, round((total_messages / first_analysis_limit) * 25))
        outbound_ratio = outbound_message_count / total_messages
        balance_score = round(max(0.0, 1.0 - (abs(outbound_ratio - 0.4) / 0.4)) * 20)
        window_score = min(20, round(min(1.0, window_hours / 72) * 20))
        coverage_score = max(0, min(100, contact_score + volume_score + balance_score + window_score))
        return len(contact_keys), inbound_message_count, outbound_message_count, coverage_score

    def _stabilize_first_analysis_result(self, result: DeepSeekMemoryResult) -> DeepSeekMemoryResult:
        unique_projects: list[DeepSeekProjectMemory] = []
        seen_project_names: set[str] = set()
        for project in result.active_projects:
            project_name = " ".join(project.name.split()).strip()
            if len(project_name) < 3:
                continue
            project_key = project_name.casefold()
            if project_key in seen_project_names:
                continue
            if not self._project_has_minimum_detail(project):
                continue
            seen_project_names.add(project_key)
            unique_projects.append(project)
            if len(unique_projects) >= 4:
                break

        return result.model_copy(
            update={
                "updated_life_summary": result.updated_life_summary.strip(),
                "window_summary": result.window_summary.strip(),
                "key_learnings": result.key_learnings[:6],
                "people_and_relationships": result.people_and_relationships[:6],
                "routine_signals": result.routine_signals[:6],
                "preferences": result.preferences[:6],
                "open_questions": result.open_questions[:6],
                "active_projects": unique_projects,
                "contact_memories": result.contact_memories[:8],
            }
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
        text = " ".join(message.message_text.split())
        if self._is_group_message(message):
            group_label = self._message_conversation_label(message)
            speaker = self._message_speaker_label(message)
            direction = (
                f"Dono -> Grupo {group_label}"
                if message.direction == "outbound"
                else f"{speaker} -> Grupo {group_label}"
            )
            return f"[{timestamp} UTC] {direction}: {text}"
        contact = self._message_conversation_label(message)
        direction = f"Dono -> {contact}" if message.direction == "outbound" else f"{contact} -> Dono"
        return f"[{timestamp} UTC] {direction}: {text}"

    def _summarize_message_text(self, text: str, max_length: int) -> str:
        normalized = " ".join(text.split()).strip()
        if len(normalized) <= max_length:
            return normalized
        return f"{normalized[: max(0, max_length - 3)].rstrip()}..."

    def _summarize_list_items(
        self,
        items: list[str] | tuple[str, ...],
        *,
        item_limit: int,
        item_chars: int,
    ) -> list[str]:
        summarized: list[str] = []
        seen: set[str] = set()
        for item in items:
            normalized = " ".join(str(item or "").split()).strip()
            if not normalized:
                continue
            key = normalized.casefold()
            if key in seen:
                continue
            seen.add(key)
            summarized.append(self._summarize_message_text(normalized, item_chars))
            if len(summarized) >= max(1, item_limit):
                break
        return summarized

    def _resolve_char_budget(self, detail_mode: Literal["light", "balanced", "deep"]) -> int:
        presets = {
            "light": 8500,
            "balanced": 14500,
            "deep": 22500,
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
            "light": 5000,
            "balanced": 7600,
            "deep": 10200,
        }[detail_mode]
        estimated_input_tokens = max(600, round((transcript_chars + context_chars) / 4))
        estimated_output_tokens = {
            "light": 620,
            "balanced": 820,
            "deep": 1040,
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
                "Ainda nao ha mensagens textuais suficientes nessa janela para justificar leitura.",
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
                    "Isso e suficiente para montar a primeira base consolidada do dono com o DeepSeek Chat."
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
                f"{selected_message_count} mensagens aproveitaveis. Vale uma releitura para manter a memoria fresca."
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
