from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
import logging
import math
import re
from typing import Literal, Sequence

from app.config import Settings
from app.services.deepseek_service import DeepSeekAssistantSearchPlan, DeepSeekService
from app.services.supabase_store import (
    ImportantMessageRecord,
    MemorySnapshotRecord,
    PersonMemoryRecord,
    PersonaRecord,
    ProjectMemoryRecord,
    SupabaseStore,
)

logger = logging.getLogger("auracore.assistant_context")

AssistantChannel = Literal["web_chat", "whatsapp_agent"]


@dataclass(slots=True)
class AssistantConversationTurn:
    role: str
    content: str
    created_at: datetime


@dataclass(slots=True)
class AssistantContextPackage:
    current_life_summary: str
    recent_snapshots_context: str
    recent_projects_context: str
    recent_chat_context: str
    interaction_mode: str
    context_hint: str
    priority_context: str
    additional_rules: list[str]


class AssistantContextService:
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

    async def build_reply_context(
        self,
        *,
        user_message: str,
        recent_messages: Sequence[AssistantConversationTurn],
        channel: AssistantChannel,
        context_hint: str | None = None,
        priority_context: str | None = None,
        contact_memory_context: str | None = None,
        additional_rules: Sequence[str] | None = None,
    ) -> AssistantContextPackage:
        persona = self.store.get_persona(self.settings.default_user_id) or PersonaRecord(
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
        projects = self.store.list_project_memories(
            self.settings.default_user_id,
            limit=max(1, self.settings.chat_context_projects),
        )
        snapshots = self.store.list_memory_snapshots(
            self.settings.default_user_id,
            limit=max(1, self.settings.chat_context_snapshots),
        )
        interaction_mode = self._resolve_interaction_mode(user_message)
        light_touch = interaction_mode == "light_touch"
        identity_query = self._is_identity_query(user_message)

        plan = await self._resolve_search_plan(
            user_message=user_message,
            channel=channel,
            interaction_mode=interaction_mode,
            has_contact_memory=bool((contact_memory_context or "").strip()),
        )

        retrieval_sections: list[str] = []
        if not light_touch:
            retrieval_sections = self._build_retrieval_sections(
                persona=persona,
                projects=projects,
                snapshots=snapshots,
                plan=plan,
            )

        effective_priority_parts = [part.strip() for part in (priority_context or "",) if part and part.strip()]
        if identity_query:
            effective_priority_parts.append(
                "O dono perguntou sua identidade. Responda diretamente que seu nome e Orion, que voce e a IA pessoal criada para ajudar essa pessoa, e depois siga a conversa sem cair em saudacao genérica."
            )
        if contact_memory_context and contact_memory_context.strip():
            if channel == "whatsapp_agent" and (not light_touch or plan.should_include_contact_memory):
                effective_priority_parts.append(contact_memory_context.strip())

        merged_hint = "\n\n".join(
            part
            for part in [
                (context_hint or "").strip(),
                *retrieval_sections,
            ]
            if part
        ).strip()
        targeted_context = bool(merged_hint or effective_priority_parts)

        resolved_rules = [
            "Seu nome e Orion. Voce e uma IA pessoal feita para ajudar o dono desta conta.",
            "Quando perguntarem seu nome, quem voce e ou qual sua funcao, responda isso diretamente e com naturalidade. Nao troque isso por uma saudacao generica.",
            "Se o pedido envolver compromisso, prazo, promessa, envio de dado sensivel, instrucoes em nome do dono ou qualquer decisao delicada, confirme antes de assumir isso como resolvido.",
            "Seu estilo deve ser de um assistente altamente competente: calmo, preciso, discreto, pratico e levemente proativo, sem soar teatral.",
            *[rule.strip() for rule in (additional_rules or []) if isinstance(rule, str) and rule.strip()],
        ]
        if plan.requires_confirmation:
            resolved_rules.append(
                "Este pedido parece sensivel. Antes de confirmar qualquer acao, combinacao, promessa ou posicionamento em nome do dono, peca confirmacao explicita."
            )

        logger.info(
            "assistant_context_resolved channel=%s interaction_mode=%s people=%s important=%s projects=%s snapshots=%s include_open_questions=%s include_contact_memory=%s requires_confirmation=%s",
            channel,
            interaction_mode,
            len(plan.people_queries),
            len(plan.important_message_queries),
            len(plan.project_queries),
            len(plan.snapshot_queries),
            plan.should_include_open_questions,
            bool(contact_memory_context and contact_memory_context.strip() and (channel == "whatsapp_agent" and (not light_touch or plan.should_include_contact_memory))),
            plan.requires_confirmation,
        )

        return AssistantContextPackage(
            current_life_summary=(
                ""
                if light_touch
                else self._compact_context_block(
                    self._build_persona_context(persona),
                    char_budget=1100 if targeted_context else 1600,
                    max_lines=14,
                )
            ),
            recent_snapshots_context=(
                ""
                if light_touch
                else self._compact_context_block(
                    self._render_snapshot_context(snapshots),
                    char_budget=900 if targeted_context else 1300,
                    max_lines=12,
                )
            ),
            recent_projects_context=(
                ""
                if light_touch
                else self._compact_context_block(
                    self._build_project_context(projects),
                    char_budget=1400 if targeted_context else 2200,
                    max_lines=18,
                )
            ),
            recent_chat_context=(
                ""
                if light_touch
                else self._compact_context_block(
                    self._build_chat_context(recent_messages),
                    char_budget=900 if targeted_context else 1400,
                    max_lines=12,
                )
            ),
            interaction_mode=interaction_mode,
            context_hint=merged_hint,
            priority_context="\n\n".join(effective_priority_parts).strip(),
            additional_rules=resolved_rules,
        )

    async def _resolve_search_plan(
        self,
        *,
        user_message: str,
        channel: AssistantChannel,
        interaction_mode: str,
        has_contact_memory: bool,
    ) -> DeepSeekAssistantSearchPlan:
        if interaction_mode == "light_touch":
            return DeepSeekAssistantSearchPlan.empty()

        try:
            plan = await self.deepseek_service.extract_assistant_search_plan(
                user_message=user_message,
                channel=channel,
                has_contact_memory=has_contact_memory,
            )
            return plan
        except Exception as error:
            logger.warning("assistant_search_plan_fallback channel=%s error=%s", channel, error)
            return self._fallback_search_plan(user_message=user_message, has_contact_memory=has_contact_memory)

    def _fallback_search_plan(
        self,
        *,
        user_message: str,
        has_contact_memory: bool,
    ) -> DeepSeekAssistantSearchPlan:
        requires_confirmation = self._looks_sensitive(user_message)
        return DeepSeekAssistantSearchPlan(
            needs_retrieval=False,
            people_queries=[],
            important_message_queries=[],
            project_queries=[],
            snapshot_queries=[],
            people_limit=0,
            important_messages_limit=0,
            projects_limit=0,
            snapshots_limit=0,
            should_include_open_questions=False,
            should_include_contact_memory=has_contact_memory and len(user_message.strip()) >= 20,
            requires_confirmation=requires_confirmation,
            explanation="Plano de busca em fallback heuristico.",
        )

    def _build_retrieval_sections(
        self,
        *,
        persona: PersonaRecord,
        projects: list[ProjectMemoryRecord],
        snapshots: list[MemorySnapshotRecord],
        plan: DeepSeekAssistantSearchPlan,
    ) -> list[str]:
        sections: list[str] = []

        if plan.people_queries and plan.people_limit > 0:
            people = self.store.search_person_memories(
                self.settings.default_user_id,
                plan.people_queries,
                limit=max(1, min(8, plan.people_limit * 2)),
            )
            ranked_people = self._rank_people(people, queries=plan.people_queries, limit=plan.people_limit)
            if ranked_people:
                sections.append("Pessoas relevantes:\n" + self._format_search_people(ranked_people))

        if plan.project_queries and plan.projects_limit > 0:
            ranked_projects = self._rank_projects(projects, queries=plan.project_queries, limit=plan.projects_limit)
            if ranked_projects:
                sections.append("Projetos relevantes:\n" + self._format_search_projects(ranked_projects))

        if plan.important_message_queries and plan.important_messages_limit > 0:
            ranked_messages = self._rank_important_messages(
                queries=plan.important_message_queries,
                limit=plan.important_messages_limit,
            )
            if ranked_messages:
                sections.append("Mensagens importantes relevantes:\n" + self._format_search_vault(ranked_messages))

        if plan.snapshot_queries and plan.snapshots_limit > 0:
            ranked_snapshots = self._rank_snapshots(
                snapshots=snapshots,
                queries=plan.snapshot_queries,
                limit=plan.snapshots_limit,
            )
            if ranked_snapshots:
                sections.append("Snapshots relevantes:\n" + self._format_search_snapshots(ranked_snapshots))

        if plan.should_include_open_questions:
            open_questions_block = self._format_open_questions(persona=persona, snapshots=snapshots)
            if open_questions_block:
                sections.append("Lacunas abertas da memoria:\n" + open_questions_block)

        return sections

    def _rank_people(
        self,
        people: Sequence[PersonMemoryRecord],
        *,
        queries: Sequence[str],
        limit: int,
    ) -> list[PersonMemoryRecord]:
        ranked = sorted(
            people,
            key=lambda person: self._score_person(person, queries=queries),
            reverse=True,
        )
        return [person for person in ranked[: max(1, limit)] if self._score_person(person, queries=queries) > 0]

    def _rank_projects(
        self,
        projects: Sequence[ProjectMemoryRecord],
        *,
        queries: Sequence[str],
        limit: int,
    ) -> list[ProjectMemoryRecord]:
        ranked = sorted(
            projects,
            key=lambda project: self._score_project(project, queries=queries),
            reverse=True,
        )
        return [project for project in ranked[: max(1, limit)] if self._score_project(project, queries=queries) > 0]

    def _rank_snapshots(
        self,
        *,
        snapshots: Sequence[MemorySnapshotRecord],
        queries: Sequence[str],
        limit: int,
    ) -> list[MemorySnapshotRecord]:
        ranked = sorted(
            snapshots,
            key=lambda snapshot: self._score_snapshot(snapshot, queries=queries),
            reverse=True,
        )
        return [snapshot for snapshot in ranked[: max(1, limit)] if self._score_snapshot(snapshot, queries=queries) > 0]

    def _rank_important_messages(
        self,
        *,
        queries: Sequence[str],
        limit: int,
    ) -> list[ImportantMessageRecord]:
        candidates = self.store.search_important_messages(
            self.settings.default_user_id,
            list(queries),
            limit=max(10, limit * 4),
        )
        if not candidates:
            candidates = self.store.list_important_messages(self.settings.default_user_id, limit=max(12, limit * 3))

        ranked = sorted(
            candidates,
            key=lambda message: self._score_important_message(message, queries=queries),
            reverse=True,
        )
        return [message for message in ranked[: max(1, limit)] if self._score_important_message(message, queries=queries) > 0]

    def _score_person(self, person: PersonMemoryRecord, *, queries: Sequence[str]) -> float:
        haystack = " ".join(
            [
                person.contact_name,
                person.profile_summary,
                person.relationship_summary,
                " ".join(person.salient_facts),
                " ".join(person.open_loops),
                " ".join(person.recent_topics),
            ]
        )
        score = self._score_text_block(haystack, queries)
        if person.last_message_at:
            score += self._recency_score(person.last_message_at, half_life_days=90)
        return score

    def _score_project(self, project: ProjectMemoryRecord, *, queries: Sequence[str]) -> float:
        haystack = " ".join(
            [
                project.project_name,
                project.summary,
                project.status,
                project.what_is_being_built,
                project.built_for,
                " ".join(project.next_steps),
                " ".join(project.evidence),
            ]
        )
        score = self._score_text_block(haystack, queries)
        if project.last_seen_at:
            score += self._recency_score(project.last_seen_at, half_life_days=60)
        return score

    def _score_snapshot(self, snapshot: MemorySnapshotRecord, *, queries: Sequence[str]) -> float:
        haystack = " ".join(
            [
                snapshot.window_summary,
                " ".join(snapshot.key_learnings),
                " ".join(snapshot.people_and_relationships),
                " ".join(snapshot.preferences),
                " ".join(snapshot.open_questions),
            ]
        )
        score = self._score_text_block(haystack, queries)
        score += self._recency_score(snapshot.created_at, half_life_days=45)
        return score

    def _score_important_message(self, message: ImportantMessageRecord, *, queries: Sequence[str]) -> float:
        haystack = " ".join([message.contact_name, message.message_text, message.importance_reason, message.category])
        relevance = self._score_text_block(haystack, queries)
        recency = self._recency_score(message.message_timestamp, half_life_days=120)
        durability = self._durability_score(message)
        confidence = max(0.0, min(1.0, float(message.confidence) / 100.0)) * 2.5
        return relevance + recency + durability + confidence

    def _score_text_block(self, text: str, queries: Sequence[str]) -> float:
        normalized_text = text.casefold()
        total = 0.0
        for query in queries:
            normalized_query = " ".join(query.casefold().split()).strip()
            if not normalized_query:
                continue
            if normalized_query in normalized_text:
                total += 8.0
            for token in self._tokenize(normalized_query):
                if token and token in normalized_text:
                    total += 1.5
        return total

    def _recency_score(self, timestamp: datetime, *, half_life_days: int) -> float:
        age_days = max(0.0, (datetime.now(UTC) - timestamp.astimezone(UTC)).total_seconds() / 86400)
        return 4.0 * math.exp(-age_days / max(1, half_life_days))

    def _durability_score(self, message: ImportantMessageRecord) -> float:
        category = (message.category or "").casefold()
        reason = (message.importance_reason or "").casefold()
        durable_markers = (
            "prefer",
            "restri",
            "objetiv",
            "contrat",
            "prazo",
            "cliente",
            "acesso",
            "valor",
            "acordo",
            "relacion",
            "identidade",
            "perfil",
            "pagamento",
        )
        if any(marker in category or marker in reason for marker in durable_markers):
            return 3.0
        return 1.0

    def _format_open_questions(
        self,
        *,
        persona: PersonaRecord,
        snapshots: Sequence[MemorySnapshotRecord],
    ) -> str:
        merged_questions = self.store._merge_unique_string_lists(
            persona.structural_open_questions,
            [question for snapshot in snapshots for question in snapshot.open_questions],
            limit=6,
        )
        if not merged_questions:
            return ""
        return "\n".join(f"- {question}" for question in merged_questions)

    def _tokenize(self, text: str) -> list[str]:
        return [token for token in re.split(r"[^a-zA-Z0-9à-ÿ]+", text.casefold()) if len(token) >= 3]

    def _looks_sensitive(self, user_message: str) -> bool:
        normalized = " ".join(user_message.casefold().split())
        sensitive_markers = (
            "manda",
            "envia",
            "responde por mim",
            "fala que eu",
            "combina",
            "fechou",
            "pode confirmar",
            "agenda",
            "promete",
            "negocia",
            "cpf",
            "cnpj",
            "pix",
            "senha",
            "banco",
            "cartao",
            "cartão",
            "valor",
            "preco",
            "preço",
        )
        return any(marker in normalized for marker in sensitive_markers)

    def _resolve_interaction_mode(self, message_text: str) -> str:
        normalized = " ".join(message_text.lower().split()).strip()
        if not normalized:
            return "light_touch"
        if len(normalized) <= 24 and normalized in {
            "oi",
            "ola",
            "olá",
            "opa",
            "bom dia",
            "boa tarde",
            "boa noite",
            "e ai",
            "e aí",
            "salve",
            "fala",
            "oii",
        }:
            return "light_touch"
        if len(normalized) <= 18 and normalized.rstrip("!?.,") in {"oi", "ola", "olá", "opa", "fala"}:
            return "light_touch"
        return "contextual"

    def _is_identity_query(self, message_text: str) -> bool:
        normalized = " ".join(message_text.casefold().split()).strip().rstrip("!?.,")
        identity_markers = (
            "qual seu nome",
            "quem é você",
            "quem e voce",
            "quem é vc",
            "quem e vc",
            "como você se chama",
            "como voce se chama",
            "seu nome",
            "você é quem",
            "voce e quem",
            "o que você é",
            "o que voce e",
            "qual sua função",
            "qual sua funcao",
        )
        return any(marker in normalized for marker in identity_markers)

    def _build_persona_context(self, persona: PersonaRecord) -> str:
        sections: list[str] = []
        if persona.life_summary.strip():
            sections.append(self._summarize_text(persona.life_summary.strip(), 720))
        if persona.structural_strengths:
            sections.append(
                "Forcas recorrentes:\n- "
                + "\n- ".join(self._summarize_items(persona.structural_strengths, item_limit=4, item_chars=120))
            )
        if persona.structural_routines:
            sections.append(
                "Rotina recorrente:\n- "
                + "\n- ".join(self._summarize_items(persona.structural_routines, item_limit=4, item_chars=120))
            )
        if persona.structural_preferences:
            sections.append(
                "Preferencias operacionais:\n- "
                + "\n- ".join(self._summarize_items(persona.structural_preferences, item_limit=4, item_chars=120))
            )
        if persona.structural_open_questions:
            sections.append(
                "Lacunas ainda abertas:\n- "
                + "\n- ".join(self._summarize_items(persona.structural_open_questions, item_limit=4, item_chars=120))
            )
        return "\n\n".join(section for section in sections if section).strip()

    def _render_snapshot_context(self, snapshots: list[MemorySnapshotRecord]) -> str:
        if not snapshots:
            return ""

        parts: list[str] = []
        current_size = 0
        char_budget = min(max(900, self.settings.chat_context_chars // 4), 1600)

        for snapshot in snapshots:
            lines = [
                f"- Snapshot de {snapshot.window_hours}h em {snapshot.created_at.astimezone(UTC).strftime('%d/%m %H:%M UTC')}",
                f"  Resumo: {self._summarize_text(snapshot.window_summary, 220)}",
            ]
            if snapshot.key_learnings:
                lines.append(
                    "  Aprendizados: "
                    + "; ".join(self._summarize_items(snapshot.key_learnings, item_limit=3, item_chars=90))
                )
            section = "\n".join(lines)
            projected = current_size + len(section) + 2
            if parts and projected > char_budget:
                break
            parts.append(section)
            current_size = projected

        return "\n\n".join(parts)

    def _build_project_context(self, projects: list[ProjectMemoryRecord]) -> str:
        if not projects:
            return ""

        parts: list[str] = []
        current_size = 0
        char_budget = min(max(1200, self.settings.chat_context_chars // 3), 2600)

        for project in projects:
            lines = [
                f"- {project.project_name}",
                f"  Resumo: {self._summarize_text(project.summary, 220)}",
            ]
            if project.status:
                lines.append(f"  Status: {self._summarize_text(project.status, 80)}")
            if project.what_is_being_built:
                lines.append(
                    f"  O que esta sendo desenvolvido: {self._summarize_text(project.what_is_being_built, 160)}"
                )
            if project.built_for:
                lines.append(f"  Para quem: {self._summarize_text(project.built_for, 120)}")
            if project.next_steps:
                lines.append(
                    "  Proximos passos: "
                    + "; ".join(self._summarize_items(project.next_steps, item_limit=3, item_chars=90))
                )
            if project.evidence:
                lines.append(
                    "  Evidencias: "
                    + "; ".join(self._summarize_items(project.evidence, item_limit=2, item_chars=90))
                )
            section = "\n".join(lines)
            projected = current_size + len(section) + 2
            if parts and projected > char_budget:
                break
            parts.append(section)
            current_size = projected

        return "\n\n".join(parts)

    def _build_chat_context(self, messages: Sequence[AssistantConversationTurn]) -> str:
        if not messages:
            return ""

        parts: list[str] = []
        current_size = 0
        char_budget = min(max(900, self.settings.chat_context_chars // 4), 1600)

        for message in reversed(messages):
            role_label = "Dono" if message.role == "user" else "Orion"
            line = (
                f"[{message.created_at.astimezone(UTC).strftime('%Y-%m-%d %H:%M UTC')}] "
                f"{role_label}: {self._summarize_text(message.content, 240)}"
            )
            projected = current_size + len(line) + 1
            if parts and projected > char_budget:
                break
            parts.append(line)
            current_size = projected

        return "\n".join(reversed(parts))

    def _compact_context_block(self, text: str, *, char_budget: int, max_lines: int) -> str:
        normalized = str(text or "").strip()
        if not normalized:
            return ""

        lines: list[str] = []
        previous_key: str | None = None
        for raw_line in normalized.splitlines():
            candidate = " ".join(raw_line.split()).strip()
            if not candidate:
                continue
            candidate_key = candidate.casefold()
            if candidate_key == previous_key:
                continue
            lines.append(candidate)
            previous_key = candidate_key
            if len(lines) >= max(1, max_lines):
                break

        compacted = "\n".join(lines) if lines else normalized
        if len(compacted) <= char_budget:
            return compacted
        return compacted[: max(0, char_budget - 16)].rstrip() + " [cortado]"

    def _summarize_text(self, text: str, max_chars: int) -> str:
        normalized = " ".join(str(text or "").split()).strip()
        if len(normalized) <= max_chars:
            return normalized
        return f"{normalized[: max(0, max_chars - 3)].rstrip()}..."

    def _summarize_items(
        self,
        items: Sequence[str],
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
            summarized.append(self._summarize_text(normalized, item_chars))
            if len(summarized) >= max(1, item_limit):
                break
        return summarized

    def _format_search_people(self, people: Sequence[PersonMemoryRecord]) -> str:
        blocks: list[str] = []
        for person in people:
            lines = [f"- Nome: {person.contact_name}"]
            if person.profile_summary:
                lines.append(f"  Quem e: {person.profile_summary}")
            if person.relationship_summary:
                lines.append(f"  Relacao: {person.relationship_summary}")
            if person.salient_facts:
                lines.append(f"  Fatos: {'; '.join(person.salient_facts[:4])}")
            if person.open_loops:
                lines.append(f"  Pontos em aberto: {'; '.join(person.open_loops[:3])}")
            blocks.append("\n".join(lines))
        return "\n\n".join(blocks)

    def _format_search_projects(self, projects: Sequence[ProjectMemoryRecord]) -> str:
        blocks: list[str] = []
        for project in projects:
            lines = [f"- Projeto: {project.project_name}"]
            if project.summary:
                lines.append(f"  Resumo: {project.summary}")
            if project.status:
                lines.append(f"  Status: {project.status}")
            if project.what_is_being_built:
                lines.append(f"  O que esta sendo desenvolvido: {project.what_is_being_built}")
            if project.next_steps:
                lines.append(f"  Proximos passos: {'; '.join(project.next_steps[:3])}")
            blocks.append("\n".join(lines))
        return "\n\n".join(blocks)

    def _format_search_snapshots(self, snapshots: Sequence[MemorySnapshotRecord]) -> str:
        blocks: list[str] = []
        for snapshot in snapshots:
            lines = [
                f"- Snapshot de {snapshot.window_hours}h em {snapshot.created_at.astimezone(UTC).strftime('%d/%m/%Y %H:%M UTC')}",
                f"  Resumo: {snapshot.window_summary}",
            ]
            if snapshot.key_learnings:
                lines.append(f"  Aprendizados: {'; '.join(snapshot.key_learnings[:4])}")
            if snapshot.open_questions:
                lines.append(f"  Lacunas: {'; '.join(snapshot.open_questions[:3])}")
            blocks.append("\n".join(lines))
        return "\n\n".join(blocks)

    def _format_search_vault(self, messages: Sequence[ImportantMessageRecord]) -> str:
        blocks: list[str] = []
        for message in messages:
            date_str = message.message_timestamp.astimezone(UTC).strftime("%d/%m/%Y")
            lines = [
                f"- Mensagem de {message.contact_name} em {date_str}:",
                f"  Conteudo: {message.message_text}",
                f"  Por que e importante: {message.importance_reason}",
            ]
            blocks.append("\n".join(lines))
        return "\n\n".join(blocks)
