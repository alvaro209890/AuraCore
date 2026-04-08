from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from app.config import Settings
from app.services.deepseek_service import DeepSeekMemoryResult, DeepSeekService
from app.services.supabase_store import (
    MemorySnapshotRecord,
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


class MemoryAnalysisService:
    def __init__(
        self,
        *,
        settings: Settings,
        store: SupabaseStore,
        deepseek_service: DeepSeekService,
    ) -> None:
        self.settings = settings
        self.store = store
        self.deepseek_service = deepseek_service

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
        deepseek_result = await self.deepseek_service.analyze_memory(
            transcript=transcript,
            current_life_summary=current_summary,
            prior_analyses_context=prior_analyses_context,
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
                    next_steps=project.next_steps,
                    evidence=project.evidence,
                )
                for project in deepseek_result.active_projects
            ],
            observed_at=window_end,
        )
        return MemoryAnalysisOutcome(persona=persona, snapshot=snapshot, projects=projects)

    def get_current_persona(self) -> PersonaRecord:
        return self.store.get_persona(self.settings.default_user_id) or PersonaRecord(
            user_id=self.settings.default_user_id,
            life_summary="",
            last_analyzed_at=None,
            last_snapshot_id=None,
        )

    def list_snapshots(self, *, limit: int = 20) -> list[MemorySnapshotRecord]:
        return self.store.list_memory_snapshots(self.settings.default_user_id, limit=limit)

    def list_projects(self, *, limit: int = 8) -> list[ProjectMemoryRecord]:
        return self.store.list_project_memories(self.settings.default_user_id, limit=limit)

    def _build_prior_analyses_context(self) -> str:
        limit = max(0, self.settings.memory_analysis_context_snapshots)
        if limit == 0:
            return ""

        snapshots = self.store.list_memory_snapshots(self.settings.default_user_id, limit=limit)
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

    def _build_transcript(self, messages: list[StoredMessageRecord]) -> tuple[str, list[StoredMessageRecord]]:
        max_messages = max(1, self.settings.memory_analysis_max_messages)
        selected_messages = messages[-max_messages:]

        lines_reversed: list[str] = []
        selected_reversed: list[StoredMessageRecord] = []
        char_budget = max(1000, self.settings.memory_analysis_max_chars)
        current_size = 0

        for message in reversed(selected_messages):
            line = self._render_message_line(message)
            projected_size = current_size + len(line) + 1
            if lines_reversed and projected_size > char_budget:
                break
            lines_reversed.append(line)
            selected_reversed.append(message)
            current_size = projected_size

        if not lines_reversed and selected_messages:
            first_line = self._render_message_line(selected_messages[-1])
            lines_reversed.append(first_line[:char_budget])
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
