from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Literal
from uuid import uuid4

from app.config import Settings
from app.services.deepseek_service import DeepSeekMemoryResult, DeepSeekService
from app.services.groq_service import GroqChatError, GroqChatService
from app.services.supabase_store import (
    ChatMessageRecord,
    MemorySnapshotRecord,
    MessageRetentionStateRecord,
    PersonaRecord,
    ProjectMemoryRecord,
    ProjectMemorySeed,
    StoredMessageRecord,
    SupabaseStore,
)


class MemoryAnalysisError(RuntimeError):
    """Raised when a memory analysis request cannot be completed."""


@dataclass(slots=True)
class MemoryAnalysisOutcome:
    persona: PersonaRecord
    snapshot: MemorySnapshotRecord
    projects: list[ProjectMemoryRecord]


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

        current_persona = self.store.get_persona(self.settings.default_user_id)
        current_summary = current_persona.life_summary if current_persona else ""
        prior_analyses_context = self._build_prior_analyses_context()
        project_context = self._build_project_context(
            self.store.list_project_memories(
                self.settings.default_user_id,
                limit=max(1, self.settings.chat_context_projects),
            )
        )
        chat_context = self._build_chat_context()
        deepseek_result = await self.deepseek_service.analyze_memory(
            transcript=transcript,
            current_life_summary=current_summary,
            prior_analyses_context=prior_analyses_context,
            project_context=project_context,
            chat_context=chat_context,
            window_hours=window_hours,
            window_start=window_start,
            window_end=window_end,
            source_message_count=len(included_messages),
        )

        snapshot = self._build_snapshot(
            result=deepseek_result,
            window_hours=window_hours,
            window_start=window_start,
            window_end=window_end,
            source_message_count=len(included_messages),
            created_at=window_end,
        )
        persona = self.store.persist_memory_analysis(
            snapshot=snapshot,
            updated_life_summary=deepseek_result.updated_life_summary,
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
        return MemoryAnalysisOutcome(persona=persona, snapshot=snapshot, projects=projects)

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

        current_persona = self.store.get_persona(self.settings.default_user_id)
        current_summary = current_persona.life_summary if current_persona else ""
        prior_analyses_context = self._build_prior_analyses_context()
        project_context = self._build_project_context(
            self.store.list_project_memories(
                self.settings.default_user_id,
                limit=max(1, self.settings.chat_context_projects),
            )
        )
        chat_context = self._build_chat_context()
        deepseek_result = await self.deepseek_service.analyze_memory(
            transcript=transcript,
            current_life_summary=current_summary,
            prior_analyses_context=prior_analyses_context,
            project_context=project_context,
            chat_context=chat_context,
            window_hours=max_lookback_hours,
            window_start=window_start,
            window_end=window_end,
            source_message_count=len(included_messages),
        )

        snapshot = self._build_snapshot(
            result=deepseek_result,
            window_hours=max_lookback_hours,
            window_start=window_start,
            window_end=window_end,
            source_message_count=len(included_messages),
            created_at=window_end,
        )
        persona = self.store.persist_memory_analysis(
            snapshot=snapshot,
            updated_life_summary=deepseek_result.updated_life_summary,
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
        return MemoryAnalysisOutcome(persona=persona, snapshot=snapshot, projects=projects)

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
        retention_state = self.store.get_message_retention_state(self.settings.default_user_id)

        baseline_ingested = current_persona.last_analyzed_ingested_count or 0
        baseline_pruned = current_persona.last_analyzed_pruned_count or 0
        new_message_count = max(0, retention_state.total_direct_ingested_count - baseline_ingested)
        replaced_message_count = max(0, retention_state.total_direct_pruned_count - baseline_pruned)
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
        prompt_preview = self.deepseek_service.build_analysis_prompt_preview(
            transcript=transcript,
            current_life_summary=current_persona.life_summary,
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
        planning_profile = self.deepseek_service.get_planning_profile()
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
        ) = await self._classify_preview_recommendation(
            target_message_count=resolved_target_count,
            max_lookback_hours=max_lookback_hours,
            detail_mode=detail_mode,
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
            retention_limit=self.settings.message_retention_max_rows,
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
        return self.store.get_persona(self.settings.default_user_id) or PersonaRecord(
            user_id=self.settings.default_user_id,
            life_summary="",
            last_analyzed_at=None,
            last_snapshot_id=None,
            last_analyzed_ingested_count=None,
            last_analyzed_pruned_count=None,
        )

    def list_snapshots(self, *, limit: int = 20) -> list[MemorySnapshotRecord]:
        return self.store.list_memory_snapshots(self.settings.default_user_id, limit=limit)

    def list_projects(self, *, limit: int = 8) -> list[ProjectMemoryRecord]:
        return self.store.list_project_memories(self.settings.default_user_id, limit=limit)

    async def refine_saved_memory(self) -> MemoryRefinementOutcome:
        current_persona = self.get_current_persona()
        snapshots = self.store.list_memory_snapshots(self.settings.default_user_id, limit=max(1, self.settings.memory_analysis_context_snapshots))
        projects = self.store.list_project_memories(self.settings.default_user_id, limit=max(1, self.settings.chat_context_projects))

        if not current_persona.life_summary.strip() and not snapshots and not projects:
            raise MemoryAnalysisError(
                "Ainda nao ha memoria suficiente salva no Supabase para refinar. Rode ao menos uma analise primeiro."
            )

        refined = await self.deepseek_service.refine_saved_memory(
            current_life_summary=current_persona.life_summary,
            prior_analyses_context=self._build_prior_analyses_context_from_snapshots(snapshots),
            project_context=self._build_project_context(projects),
            chat_context=self._build_chat_context(),
        )

        refined_at = datetime.now(UTC)
        persona = self.store.update_persona_summary(
            user_id=self.settings.default_user_id,
            updated_life_summary=refined.updated_life_summary,
            analyzed_at=refined_at,
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
        return MemoryRefinementOutcome(persona=persona, projects=updated_projects)

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
        thread = self.store.get_or_create_chat_thread(user_id=self.settings.default_user_id)
        messages = self.store.list_chat_messages(
            thread.id,
            limit=max(1, min(self.settings.chat_max_history_messages, 12)),
        )
        return self._build_chat_context_from_messages(messages)

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

    def _render_message_line(self, message: StoredMessageRecord) -> str:
        timestamp = message.timestamp.astimezone(UTC).strftime("%Y-%m-%d %H:%M")
        speaker = message.contact_name.strip() or message.contact_phone or "Contato"
        direction = "user->contact" if message.direction == "outbound" else "contact->user"
        text = " ".join(message.message_text.split())
        return f"[{timestamp} UTC] {direction} | {speaker}: {text}"

    def _resolve_char_budget(self, detail_mode: Literal["light", "balanced", "deep"]) -> int:
        presets = {
            "light": 18000,
            "balanced": 36000,
            "deep": 60000,
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

    async def _classify_preview_recommendation(
        self,
        *,
        target_message_count: int,
        max_lookback_hours: int,
        detail_mode: Literal["light", "balanced", "deep"],
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
        fallback_should_analyze = fallback_score >= 55
        fallback_summary = self._build_fallback_preview_summary(
            selected_message_count=selected_message_count,
            new_message_count=new_message_count,
            replaced_message_count=replaced_message_count,
            stack_max_message_capacity=stack_max_message_capacity,
            estimated_cost_total_ceiling_usd=estimated_cost_total_ceiling_usd,
            recommendation_label=fallback_label,
        )
        if self.groq_service is None:
            return (
                fallback_score,
                fallback_label,
                fallback_should_analyze,
                fallback_summary,
            )

        try:
            decision = await self.groq_service.classify_analysis_preview(
                target_message_count=target_message_count,
                max_lookback_hours=max_lookback_hours,
                detail_mode=detail_mode,
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
            return (
                decision.score,
                decision.label,
                decision.should_analyze,
                decision.summary,
            )
        except GroqChatError:
            return (
                fallback_score,
                fallback_label,
                fallback_should_analyze,
                fallback_summary,
            )

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
