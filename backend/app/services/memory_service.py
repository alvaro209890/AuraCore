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
    available_message_count: int
    selected_message_count: int
    new_message_count: int
    replaced_message_count: int
    retained_message_count: int
    retention_limit: int
    estimated_input_tokens: int
    estimated_output_tokens: int
    estimated_total_tokens: int
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
        chat_context = self._build_chat_context()
        deepseek_result = await self.deepseek_service.analyze_memory(
            transcript=transcript,
            current_life_summary=current_summary,
            prior_analyses_context=prior_analyses_context,
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
        chat_context = self._build_chat_context()
        deepseek_result = await self.deepseek_service.analyze_memory(
            transcript=transcript,
            current_life_summary=current_summary,
            prior_analyses_context=prior_analyses_context,
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
        available_message_count = self.store.count_messages_in_window(
            user_id=self.settings.default_user_id,
            window_start=window_start,
            window_end=window_end,
        )
        retained_message_count = self.store.count_messages(self.settings.default_user_id)
        selected_message_count = min(resolved_target_count, available_message_count)
        current_persona = self.get_current_persona()
        retention_state = self.store.get_message_retention_state(self.settings.default_user_id)

        baseline_ingested = current_persona.last_analyzed_ingested_count or 0
        baseline_pruned = current_persona.last_analyzed_pruned_count or 0
        new_message_count = max(0, retention_state.total_direct_ingested_count - baseline_ingested)
        replaced_message_count = max(0, retention_state.total_direct_pruned_count - baseline_pruned)
        estimated_input_tokens, estimated_output_tokens, estimated_total_tokens = self._estimate_token_usage(
            selected_message_count=selected_message_count,
            char_budget=resolved_char_budget,
            detail_mode=detail_mode,
        )
        recommendation_score = self._score_analysis_opportunity(
            persona=current_persona,
            available_message_count=available_message_count,
            selected_message_count=selected_message_count,
            new_message_count=new_message_count,
            replaced_message_count=replaced_message_count,
            estimated_total_tokens=estimated_total_tokens,
        )
        recommendation_label = self._label_for_score(recommendation_score)
        should_analyze = recommendation_score >= 55
        recommendation_summary = await self._build_preview_summary(
            target_message_count=resolved_target_count,
            max_lookback_hours=max_lookback_hours,
            detail_mode=detail_mode,
            available_message_count=available_message_count,
            selected_message_count=selected_message_count,
            new_message_count=new_message_count,
            replaced_message_count=replaced_message_count,
            estimated_total_tokens=estimated_total_tokens,
            recommendation_score=recommendation_score,
            recommendation_label=recommendation_label,
        )

        return MemoryAnalysisPreview(
            target_message_count=resolved_target_count,
            max_lookback_hours=max_lookback_hours,
            detail_mode=detail_mode,
            available_message_count=available_message_count,
            selected_message_count=selected_message_count,
            new_message_count=new_message_count,
            replaced_message_count=replaced_message_count,
            retained_message_count=retained_message_count,
            retention_limit=self.settings.message_retention_max_rows,
            estimated_input_tokens=estimated_input_tokens,
            estimated_output_tokens=estimated_output_tokens,
            estimated_total_tokens=estimated_total_tokens,
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
            "light": 14000,
            "balanced": 26000,
            "deep": 42000,
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
            "light": 72,
            "balanced": 88,
            "deep": 102,
        }[detail_mode]
        transcript_chars = min(char_budget, selected_message_count * average_chars_per_message)
        context_chars = {
            "light": 5200,
            "balanced": 7600,
            "deep": 9800,
        }[detail_mode]
        estimated_input_tokens = max(600, round((transcript_chars + context_chars) / 4))
        estimated_output_tokens = {
            "light": 650,
            "balanced": 850,
            "deep": 1050,
        }[detail_mode]
        return estimated_input_tokens, estimated_output_tokens, estimated_input_tokens + estimated_output_tokens

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
        token_efficiency = max(0.0, 1.0 - min(1.0, estimated_total_tokens / 15000))

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

    async def _build_preview_summary(
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
        recommendation_score: int,
        recommendation_label: str,
    ) -> str:
        if self.groq_service is None:
            return self._build_fallback_preview_summary(
                selected_message_count=selected_message_count,
                new_message_count=new_message_count,
                replaced_message_count=replaced_message_count,
                recommendation_label=recommendation_label,
            )

        try:
            return await self.groq_service.generate_analysis_preview_summary(
                target_message_count=target_message_count,
                max_lookback_hours=max_lookback_hours,
                detail_mode=detail_mode,
                available_message_count=available_message_count,
                selected_message_count=selected_message_count,
                new_message_count=new_message_count,
                replaced_message_count=replaced_message_count,
                estimated_total_tokens=estimated_total_tokens,
                recommendation_score=recommendation_score,
                recommendation_label=recommendation_label,
            )
        except GroqChatError:
            return self._build_fallback_preview_summary(
                selected_message_count=selected_message_count,
                new_message_count=new_message_count,
                replaced_message_count=replaced_message_count,
                recommendation_label=recommendation_label,
            )

    def _build_fallback_preview_summary(
        self,
        *,
        selected_message_count: int,
        new_message_count: int,
        replaced_message_count: int,
        recommendation_label: str,
    ) -> str:
        return (
            f"{recommendation_label}: esta leitura usaria cerca de {selected_message_count} mensagens, "
            f"com {new_message_count} novas desde a ultima consolidacao e {replaced_message_count} ja substituidas pela retencao."
        )
