from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from datetime import datetime
import logging
from time import perf_counter
from typing import Any, Callable, Literal, TypeVar

import httpx
from pydantic import BaseModel, Field

from app.config import Settings


class DeepSeekError(RuntimeError):
    """Raised when DeepSeek cannot complete or return a valid analysis."""


class DeepSeekProjectMemory(BaseModel):
    name: str
    summary: str
    status: str = ""
    what_is_being_built: str = ""
    built_for: str = ""
    next_steps: list[str] = Field(default_factory=list)
    evidence: list[str] = Field(default_factory=list)


class DeepSeekPersonMemory(BaseModel):
    person_key: str
    contact_name: str = ""
    profile_summary: str
    relationship_type: str = ""
    relationship_summary: str = ""
    salient_facts: list[str] = Field(default_factory=list)
    open_loops: list[str] = Field(default_factory=list)
    recent_topics: list[str] = Field(default_factory=list)


class DeepSeekMemoryResult(BaseModel):
    updated_life_summary: str
    window_summary: str
    key_learnings: list[str] = Field(default_factory=list)
    people_and_relationships: list[str] = Field(default_factory=list)
    routine_signals: list[str] = Field(default_factory=list)
    preferences: list[str] = Field(default_factory=list)
    open_questions: list[str] = Field(default_factory=list)
    active_projects: list[DeepSeekProjectMemory] = Field(default_factory=list)
    contact_memories: list[DeepSeekPersonMemory] = Field(default_factory=list)



class DeepSeekMemoryRefinementResult(BaseModel):
    updated_life_summary: str
    active_projects: list[DeepSeekProjectMemory] = Field(default_factory=list)


class DeepSeekProjectMergeResult(BaseModel):
    active_projects: list[DeepSeekProjectMemory] = Field(default_factory=list)


class DeepSeekContactMemoryRefinementResult(BaseModel):
    contact_memories: list[DeepSeekPersonMemory] = Field(default_factory=list)


class DeepSeekImportantMessageCandidate(BaseModel):
    message_id: str
    category: str
    importance_reason: str
    confidence: int = Field(default=0, ge=0, le=100)


class DeepSeekImportantMessagesResult(BaseModel):
    important_messages: list[DeepSeekImportantMessageCandidate] = Field(default_factory=list)


class DeepSeekImportantMessageReviewDecision(BaseModel):
    source_message_id: str
    decision: Literal["keep", "discard"] = "keep"
    review_notes: str
    confidence: int = Field(default=0, ge=0, le=100)


class DeepSeekImportantMessagesReviewResult(BaseModel):
    reviews: list[DeepSeekImportantMessageReviewDecision] = Field(default_factory=list)


class DeepSeekAssistantSearchPlan(BaseModel):
    needs_retrieval: bool = False
    people_queries: list[str] = Field(default_factory=list)
    important_message_queries: list[str] = Field(default_factory=list)
    project_queries: list[str] = Field(default_factory=list)
    snapshot_queries: list[str] = Field(default_factory=list)
    people_limit: int = 0
    important_messages_limit: int = 0
    projects_limit: int = 0
    snapshots_limit: int = 0
    should_include_open_questions: bool = False
    should_include_contact_memory: bool = False
    requires_confirmation: bool = False
    explanation: str = ""

    @classmethod
    def empty(cls) -> "DeepSeekAssistantSearchPlan":
        return cls(
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
            should_include_contact_memory=False,
            requires_confirmation=False,
            explanation="Busca nao necessaria para esta mensagem.",
        )


class DeepSeekAgentMemoryDecision(BaseModel):
    should_update: bool = False
    profile_summary: str = ""
    preferred_tone: str = ""
    preferences: list[str] = Field(default_factory=list)
    objectives: list[str] = Field(default_factory=list)
    durable_facts: list[str] = Field(default_factory=list)
    constraints: list[str] = Field(default_factory=list)
    recurring_instructions: list[str] = Field(default_factory=list)
    explanation: str = ""


ParsedResultT = TypeVar("ParsedResultT")
logger = logging.getLogger("auracore.deepseek")


@dataclass(slots=True)
class DeepSeekPromptPreview:
    system_prompt: str
    user_prompt: str


@dataclass(slots=True)
class DeepSeekPlanningProfile:
    model_name: str
    context_limit_floor_tokens: int
    context_limit_ceiling_tokens: int
    default_output_tokens: int
    maximum_output_tokens: int
    request_output_reserve_tokens: int
    cache_miss_input_price_floor_per_million: float
    cache_miss_input_price_ceiling_per_million: float
    output_price_floor_per_million: float
    output_price_ceiling_per_million: float
    context_note: str
    pricing_note: str


class DeepSeekService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    async def analyze_memory(
        self,
        *,
        transcript: str,
        conversation_context: str,
        people_memory_context: str,
        current_life_summary: str,
        prior_analyses_context: str,
        project_context: str,
        chat_context: str,
        open_questions_context: str,
        intent: str = "improve_memory",
        window_hours: int,
        window_start: datetime,
        window_end: datetime,
        source_message_count: int,
        contains_group_messages: bool = False,
        max_output_tokens: int | None = None,
    ) -> DeepSeekMemoryResult:
        prompt_preview = self.build_analysis_prompt_preview(
            transcript=transcript,
            conversation_context=conversation_context,
            people_memory_context=people_memory_context,
            current_life_summary=current_life_summary,
            prior_analyses_context=prior_analyses_context,
            project_context=project_context,
            chat_context=chat_context,
            open_questions_context=open_questions_context,
            intent=intent,
            window_hours=window_hours,
            window_start=window_start,
            window_end=window_end,
            source_message_count=source_message_count,
            contains_group_messages=contains_group_messages,
        )
        payload = self._build_completion_payload(
            system_prompt=prompt_preview.system_prompt,
            user_prompt=prompt_preview.user_prompt,
            max_tokens=max_output_tokens or self._analysis_max_output_tokens(intent=intent),
        )

        return await self._request_parsed_completion(
            payload=payload,
            parser=self._parse_result,
            validator=self._validate_analysis_result,
            operation="analyze_memory",
        )

    async def refine_saved_memory(
        self,
        *,
        current_life_summary: str,
        prior_analyses_context: str,
        project_context: str,
        chat_context: str,
    ) -> DeepSeekMemoryRefinementResult:
        prompt_preview = self.build_refinement_prompt_preview(
            current_life_summary=current_life_summary,
            prior_analyses_context=prior_analyses_context,
            project_context=project_context,
            chat_context=chat_context,
        )
        payload = self._build_completion_payload(
            system_prompt=prompt_preview.system_prompt,
            user_prompt=prompt_preview.user_prompt,
            max_tokens=self._refinement_max_output_tokens(),
        )

        return await self._request_parsed_completion(
            payload=payload,
            parser=self._parse_refinement_result,
            validator=self._validate_refinement_result,
            operation="refine_saved_memory",
        )

    async def refine_contact_memories(
        self,
        *,
        current_life_summary: str,
        project_context: str,
        contact_memories_block: str,
    ) -> DeepSeekContactMemoryRefinementResult:
        payload = self._build_completion_payload(
            system_prompt=(
                "Voce revisa perfis de contatos salvos no AuraCore para alinha-los a nova fase da vida do dono. "
                "Retorne apenas JSON valido. Nao mude o person_key. Atualize os resumos de perfil e relacao, e remova "
                "fatos marcantes, pendencias ou topicos que perderam completamente a relevancia para o contexto atual do dono."
            ),
            user_prompt=self._build_contact_refinement_prompt(
                current_life_summary=current_life_summary,
                project_context=project_context,
                contact_memories_block=contact_memories_block,
            ),
            max_tokens=6000 if self._is_reasoning_model() else 3000,
        )

        return await self._request_parsed_completion(
            payload=payload,
            parser=self._parse_contact_refinement_result,
            validator=self._validate_contact_refinement_result,
            operation="refine_contact_memories",
        )

    async def merge_projects_incrementally(
        self,
        *,
        current_life_summary: str,
        current_project_context: str,
        candidate_projects_block: str,
        recent_window_summary: str,
        conversation_context: str,
    ) -> DeepSeekProjectMergeResult:
        payload = self._build_completion_payload(
            system_prompt=(
                "Voce reconcilia projetos ativos do AuraCore. Sua funcao e combinar os projetos ja salvos "
                "com novos sinais vindos da analise recente e devolver uma lista canonica, curta e sem duplicatas. "
                "Retorne apenas JSON valido."
            ),
            user_prompt=self._build_project_merge_prompt(
                current_life_summary=current_life_summary,
                current_project_context=current_project_context,
                candidate_projects_block=candidate_projects_block,
                recent_window_summary=recent_window_summary,
                conversation_context=conversation_context,
            ),
            max_tokens=5000 if self._is_reasoning_model() else 2400,
        )
        return await self._request_parsed_completion(
            payload=payload,
            parser=self._parse_project_merge_result,
            validator=self._validate_project_merge_result,
            operation="merge_projects_incrementally",
        )

    async def extract_important_messages(
        self,
        *,
        messages_block: str,
        allowed_message_ids: list[str],
        current_life_summary: str,
        project_context: str,
    ) -> DeepSeekImportantMessagesResult:
        payload = self._build_completion_payload(
            system_prompt=(
                "Voce e o classificador de memoria duravel do AuraCore. Sua funcao e escolher apenas mensagens "
                "que merecem sair da fila operacional curta e entrar em um cofre de referencia futura. "
                "Retorne apenas JSON valido. Seja conservador: prefira perder algo marginal a salvar ruido."
            ),
            user_prompt=self._build_important_messages_prompt(
                messages_block=messages_block,
                current_life_summary=current_life_summary,
                project_context=project_context,
            ),
            max_tokens=4000 if self._is_reasoning_model() else 2200,
        )
        allowed_ids = set(allowed_message_ids)
        return await self._request_parsed_completion(
            payload=payload,
            parser=self._parse_important_messages_result,
            validator=lambda parsed: self._validate_important_messages_result(parsed, allowed_message_ids=allowed_ids),
            operation="extract_important_messages",
        )

    async def review_important_messages(
        self,
        *,
        important_messages_block: str,
        allowed_message_ids: list[str],
        current_life_summary: str,
        project_context: str,
    ) -> DeepSeekImportantMessagesReviewResult:
        payload = self._build_completion_payload(
            system_prompt=(
                "Voce revisa o cofre de mensagens importantes do AuraCore. Sua funcao e decidir o que continua "
                "util para consultas futuras e o que ja virou ruido, sem inventar fatos. Retorne apenas JSON valido."
            ),
            user_prompt=self._build_important_messages_review_prompt(
                important_messages_block=important_messages_block,
                current_life_summary=current_life_summary,
                project_context=project_context,
            ),
            max_tokens=5000 if self._is_reasoning_model() else 2600,
        )
        allowed_ids = set(allowed_message_ids)
        return await self._request_parsed_completion(
            payload=payload,
            parser=self._parse_important_messages_review_result,
            validator=lambda parsed: self._validate_important_messages_review_result(parsed, allowed_message_ids=allowed_ids),
            operation="review_important_messages",
        )

    async def synthesize_memory_analyses(
        self,
        *,
        partial_analyses_block: str,
        conversation_context: str,
        current_life_summary: str,
        prior_analyses_context: str,
        project_context: str,
        chat_context: str,
        open_questions_context: str,
        intent: str = "first_analysis",
        window_hours: int,
        window_start: datetime,
        window_end: datetime,
        source_message_count: int,
        partial_analysis_count: int,
        contains_group_messages: bool = False,
    ) -> DeepSeekMemoryResult:
        payload = self._build_completion_payload(
            system_prompt=(
                "Voce consolida varias leituras parciais da mesma janela do AuraCore em uma unica memoria final. "
                "Sua funcao e unir as analises sem perder sinal, remover duplicatas, preservar prudencia e "
                "retornar apenas JSON valido no mesmo schema da analise principal."
            ),
            user_prompt=self._build_memory_synthesis_prompt(
                partial_analyses_block=partial_analyses_block,
                conversation_context=conversation_context,
                current_life_summary=current_life_summary,
                prior_analyses_context=prior_analyses_context,
                project_context=project_context,
                chat_context=chat_context,
                open_questions_context=open_questions_context,
                intent=intent,
                window_hours=window_hours,
                window_start=window_start,
                window_end=window_end,
                source_message_count=source_message_count,
                partial_analysis_count=partial_analysis_count,
                contains_group_messages=contains_group_messages,
            ),
            max_tokens=self._analysis_max_output_tokens(intent=intent),
        )
        return await self._request_parsed_completion(
            payload=payload,
            parser=self._parse_result,
            validator=self._validate_analysis_result,
            operation="synthesize_memory_analyses",
        )

    async def generate_reply(
        self,
        *,
        user_message: str,
        current_life_summary: str,
        recent_snapshots_context: str,
        recent_projects_context: str,
        recent_chat_context: str,
        interaction_mode: str = "contextual",
        context_hint: str = "",
        priority_context: str = "",
        recent_messages_label: str = "Historico recente desta conversa",
        additional_rules: list[str] | None = None,
    ) -> str:
        payload = self._build_text_completion_payload(
            system_prompt=(
                "Seu nome e Orion. Voce e a IA pessoal do dono desta conta. "
                "Responda sempre em portugues do Brasil, com tom direto, natural, pratico, calmo e discreto. "
                "Use o contexto como apoio silencioso. Nao fale de sistema, memoria, analises, modelos, prompt ou bastidores, salvo se isso for perguntado. "
                "Se perguntarem quem voce e, responda diretamente que voce e Orion, a IA pessoal criada para ajudar esta pessoa. "
                "Nao diga 'voce me disse', 'voce mencionou' ou 'voce comentou comigo'; use a informacao de forma natural. "
                "Se faltar contexto, admita. Nao transforme cumprimentos simples em relatorio nem puxe fatos antigos sem necessidade. "
                "Antes de assumir promessa, prazo, resposta em nome do dono ou dado sensivel, peca confirmacao."
            ),
            user_prompt=self._build_reply_prompt(
                user_message=user_message,
                current_life_summary=current_life_summary,
                recent_snapshots_context=recent_snapshots_context,
                recent_projects_context=recent_projects_context,
                recent_chat_context=recent_chat_context,
                interaction_mode=interaction_mode,
                context_hint=context_hint,
                priority_context=priority_context,
                recent_messages_label=recent_messages_label,
                additional_rules=additional_rules or [],
            ),
            max_tokens=900 if self._is_reasoning_model() else 600,
        )
        return await self._request_text_completion(payload=payload, operation="assistant_reply")

    async def extract_assistant_search_plan(
        self,
        *,
        user_message: str,
        channel: str,
        has_contact_memory: bool = False,
    ) -> DeepSeekAssistantSearchPlan:
        payload = self._build_completion_payload(
            system_prompt=(
                "Voce decide qual contexto adicional deve ser recuperado para responder melhor uma mensagem do dono. "
                "Responda EXCLUSIVAMENTE em JSON valido com as chaves: "
                "needs_retrieval, people_queries, important_message_queries, project_queries, snapshot_queries, "
                "people_limit, important_messages_limit, projects_limit, snapshots_limit, "
                "should_include_open_questions, should_include_contact_memory, requires_confirmation e explanation. "
                "Use no maximo 3 consultas por categoria e limites pequenos. "
                "needs_retrieval deve ser false para cumprimentos simples ou quando o contexto atual ja basta. "
                "requires_confirmation deve ser true quando houver promessa, prazo, negociacao, dado sensivel, "
                "acao delicada ou resposta em nome do dono. "
                "should_include_contact_memory so deve ser true se isso puder melhorar de fato uma conversa do WhatsApp."
            ),
            user_prompt=(
                f"Canal: {channel}\n"
                f"Memoria propria do contato disponivel: {'sim' if has_contact_memory else 'nao'}\n"
                f"Mensagem do dono:\n{user_message.strip()}"
            ),
            max_tokens=800 if self._is_reasoning_model() else 420,
        )
        return await self._request_parsed_completion(
            payload=payload,
            parser=self._parse_assistant_search_plan,
            validator=self._validate_assistant_search_plan,
            operation="assistant_search_plan",
        )

    async def extract_agent_memory(
        self,
        *,
        user_message: str,
        existing_memory_context: str = "",
    ) -> DeepSeekAgentMemoryDecision:
        payload = self._build_completion_payload(
            system_prompt=(
                "Voce extrai memoria duravel a partir de uma mensagem enviada pelo proprio dono ao assistente no WhatsApp. "
                "Considere apenas preferencias, tom desejado, objetivos, fatos duraveis, restricoes e instrucoes recorrentes "
                "que possam melhorar conversas futuras com esse mesmo dono. "
                "Ignore cumprimentos, recados efemeros e pedidos que so fazem sentido nesta unica resposta. "
                "Responda EXCLUSIVAMENTE em JSON valido com as chaves should_update, profile_summary, preferred_tone, "
                "preferences, objectives, durable_facts, constraints, recurring_instructions e explanation. "
                "Se nada for duravel, retorne should_update=false e listas vazias."
            ),
            user_prompt=(
                "Memoria atual deste contato no agente:\n"
                f"{existing_memory_context.strip() or '(sem memoria propria ainda)'}\n\n"
                "Nova mensagem do dono:\n"
                f"{user_message.strip()}"
            ),
            max_tokens=1000 if self._is_reasoning_model() else 500,
        )
        return await self._request_parsed_completion(
            payload=payload,
            parser=self._parse_agent_memory_decision,
            validator=self._validate_agent_memory_decision,
            operation="agent_memory_extract",
        )

    def build_analysis_prompt_preview(
        self,
        *,
        transcript: str,
        conversation_context: str,
        people_memory_context: str,
        current_life_summary: str,
        prior_analyses_context: str,
        project_context: str,
        chat_context: str,
        open_questions_context: str,
        intent: str = "improve_memory",
        window_hours: int,
        window_start: datetime,
        window_end: datetime,
        source_message_count: int,
        contains_group_messages: bool = False,
    ) -> DeepSeekPromptPreview:
        is_first_analysis = intent == "first_analysis"
        return DeepSeekPromptPreview(
            system_prompt=(
                "Voce e o analista principal de memoria do AuraCore. Sua funcao e transformar conversas "
                "privadas em portugues do Brasil em uma memoria altamente util sobre o dono do numero. "
                "Retorne apenas JSON valido e estritamente aderente ao schema pedido. Nunca invente fatos. "
                "Priorize sinais sobre identidade, forma de agir, criterio de decisao, ritmo, projetos, "
                "responsabilidades e tensoes reais do dono. Quando algo for incerto, trate como sinal ou "
                "hipotese nas listas, sem afirmar como certeza no resumo consolidado."
                + (
                    " Esta leitura mistura conversas diretas e grupos selecionados do WhatsApp. Em mensagens "
                    "de grupo, atribua falas, opinioes, pedidos, promessas e fatos ao participante correto "
                    "antes de inferir algo sobre o dono."
                    if contains_group_messages and not is_first_analysis
                    else ""
                )
                + (
                    " Esta e a primeira analise salva do dono. Prefira cobertura ampla e conservadora: "
                    "menos conviccao, menos projetos, menos inferencias psicologicas e mais lacunas explicitas."
                    if is_first_analysis
                    else ""
                )
            ),
            user_prompt=self._build_prompt(
                transcript=transcript,
                conversation_context=conversation_context,
                people_memory_context=people_memory_context,
                current_life_summary=current_life_summary,
                prior_analyses_context=prior_analyses_context,
                project_context=project_context,
                chat_context=chat_context,
                open_questions_context=open_questions_context,
                intent=intent,
                window_hours=window_hours,
                window_start=window_start,
                window_end=window_end,
                source_message_count=source_message_count,
                contains_group_messages=contains_group_messages,
            ),
        )

    def build_refinement_prompt_preview(
        self,
        *,
        current_life_summary: str,
        prior_analyses_context: str,
        project_context: str,
        chat_context: str,
    ) -> DeepSeekPromptPreview:
        return DeepSeekPromptPreview(
            system_prompt=(
                "Voce revisa memorias privadas em portugues para melhorar a qualidade do perfil salvo do "
                "dono do numero. Retorne apenas JSON valido e estritamente aderente ao schema pedido. "
                "Nunca invente fatos. Remova exageros, refine hipoteses fracas, fortaleça padroes "
                "recorrentes e deixe a memoria mais util para um assistente pessoal futuro."
            ),
            user_prompt=self._build_refinement_prompt(
                current_life_summary=current_life_summary,
                prior_analyses_context=prior_analyses_context,
                project_context=project_context,
                chat_context=chat_context,
            ),
        )

    def get_planning_profile(self, *, intent: str = "improve_memory") -> DeepSeekPlanningProfile:
        output_reserve_tokens = self._analysis_max_output_tokens(intent=intent)
        if self._is_reasoning_model():
            return DeepSeekPlanningProfile(
                model_name=self.settings.deepseek_model,
                context_limit_floor_tokens=64000,
                context_limit_ceiling_tokens=128000,
                default_output_tokens=32000,
                maximum_output_tokens=64000,
                request_output_reserve_tokens=output_reserve_tokens,
                cache_miss_input_price_floor_per_million=0.28,
                cache_miss_input_price_ceiling_per_million=0.55,
                output_price_floor_per_million=0.42,
                output_price_ceiling_per_million=2.19,
                context_note=(
                    "Planner usa piso conservador de 64K de contexto por causa de divergencia entre paginas "
                    "oficiais do DeepSeek; a tela tambem mostra o teto de 128K citado em Models & Pricing."
                ),
                pricing_note=(
                    "Faixa de custo usa cache miss e combina os dois precos oficiais visiveis hoje para "
                    "deepseek-reasoner: Models & Pricing e pricing-details-usd."
                ),
            )

        return DeepSeekPlanningProfile(
            model_name=self.settings.deepseek_model,
            context_limit_floor_tokens=64000,
            context_limit_ceiling_tokens=128000,
            default_output_tokens=4000,
            maximum_output_tokens=8000,
            request_output_reserve_tokens=output_reserve_tokens,
            cache_miss_input_price_floor_per_million=0.28,
            cache_miss_input_price_ceiling_per_million=0.55,
            output_price_floor_per_million=0.42,
            output_price_ceiling_per_million=2.19,
            context_note="Planner usa a mesma faixa conservadora de contexto para nao superestimar capacidade.",
            pricing_note="Faixa de custo segue os precos oficiais visiveis na documentacao atual do DeepSeek.",
        )

    def _build_prompt(
        self,
        *,
        transcript: str,
        conversation_context: str,
        people_memory_context: str,
        current_life_summary: str,
        prior_analyses_context: str,
        project_context: str,
        chat_context: str,
        open_questions_context: str,
        intent: str,
        window_hours: int,
        window_start: datetime,
        window_end: datetime,
        source_message_count: int,
        contains_group_messages: bool = False,
    ) -> str:
        previous_summary = current_life_summary.strip() or "(memoria consolidada ainda vazia)"
        previous_analyses = prior_analyses_context.strip() or "(nenhuma analise anterior relevante)"
        recent_chat_context = chat_context.strip() or "(nenhuma conversa relevante com a IA salva ainda)"
        prioritized_open_questions = open_questions_context.strip() or "(nenhuma lacuna prioritaria registrada)"
        is_first_analysis = intent == "first_analysis"
        intro = (
            "Analise a janela abaixo de conversas diretas e monte a primeira base de memoria do usuario."
            if is_first_analysis
            else (
                "Analise a janela abaixo de conversas do WhatsApp e atualize a memoria do usuario."
                if contains_group_messages
                else "Analise a janela abaixo de conversas diretas e atualize a memoria do usuario."
            )
        )
        bootstrap_rules = """
- Esta e a primeira analise persistida do dono; trate a memoria como bootstrap inicial, nao como retrato definitivo.
- Em updated_life_summary, seja prudente: prefira descrever direcoes gerais e responsabilidades visiveis em vez de interpretar demais a personalidade.
- Em active_projects, mantenha no maximo 4 itens e inclua apenas frentes que tenham sinais repetidos, impacto operacional ou evidencia concreta.
- Use open_questions para registrar duvidas importantes que precisarao de mais conversa futura em vez de fechar conclusoes cedo demais.
- Se houver conflito entre um sinal forte mas isolado e o restante do contexto, reduza a forca da afirmacao e explicite a incerteza nas listas.
""".strip()
        return f"""
{intro}

Janela em horas: {window_hours}
Inicio da janela (UTC): {window_start.isoformat()}
Fim da janela (UTC): {window_end.isoformat()}
Mensagens incluidas: {source_message_count}

Resumo consolidado atual:
{previous_summary}

Analises anteriores relevantes:
{previous_analyses}

Projetos e frentes ja consolidados:
{project_context.strip() or "(nenhum projeto consolidado ainda)"}

Conversas recentes com a IA pessoal:
{recent_chat_context}

Lacunas prioritarias para esta leitura:
{prioritized_open_questions}

Contexto por conversa do WhatsApp:
{conversation_context.strip() or "(nenhum agrupamento adicional de conversa disponivel)"}

Memorias ja consolidadas por pessoa destas conversas:
{people_memory_context.strip() or "(nenhuma memoria por pessoa consolidada ainda para estes contatos)"}

Transcricao da conversa:
{transcript}

Retorne um JSON com exatamente estes campos:
- updated_life_summary: string
- window_summary: string
- key_learnings: string[]
- people_and_relationships: string[]
- routine_signals: string[]
- preferences: string[]
- open_questions: string[]
- active_projects: {{ name: string, summary: string, status: string, what_is_being_built: string, built_for: string, next_steps: string[], evidence: string[] }}[]
- contact_memories: {{ person_key: string, contact_name: string, profile_summary: string, relationship_type: string, relationship_summary: string, salient_facts: string[], open_loops: string[], recent_topics: string[] }}[]

Formato esperado do JSON:
{{
  "updated_life_summary": "string",
  "window_summary": "string",
  "key_learnings": ["string"],
  "people_and_relationships": ["string"],
  "routine_signals": ["string"],
  "preferences": ["string"],
  "open_questions": ["string"],
  "active_projects": [
    {{
      "name": "string",
      "summary": "string",
      "status": "string",
      "what_is_being_built": "string",
      "built_for": "string",
      "next_steps": ["string"],
      "evidence": ["string"]
    }}
  ],
  "contact_memories": [
    {{
      "person_key": "string",
      "contact_name": "string",
      "profile_summary": "string",
      "relationship_type": "partner|family|friend|work|client|service|acquaintance|other|unknown",
      "relationship_summary": "string",
      "salient_facts": ["string"],
      "open_loops": ["string"],
      "recent_topics": ["string"]
    }}
  ]
}}

Regras:
- updated_life_summary deve ser cumulativo e integrar o resumo atual com esta janela.
- Em updated_life_summary, descreva principalmente: quem o dono parece ser, como trabalha e decide, quais frentes estao mais vivas agora e quais tensoes ou prioridades estao guiando o momento.
- Use as analises anteriores como contexto, mas corrija ou refine o que parecer fraco, incompleto ou contraditorio.
- Use tambem os projetos ja salvos para manter continuidade entre leituras e evitar perder o fio de frentes recorrentes.
- Considere tambem o que o dono conversou com a IA no chat para entender melhor prioridades, projetos e como ele pensa.
- Leia o bloco de lacunas prioritarias antes da transcricao e tente responder, reduzir ou recalibrar essas perguntas usando apenas o historico salvo e a janela atual.
- Leia primeiro o bloco de contexto por conversa para entender quem e cada contato, o peso de cada conversa e a relacao mais provavel com o dono.
- Leia tambem as memorias ja consolidadas por pessoa antes de atualizar os contatos desta janela.
- Diferencie sinais sobre o dono dos fatos que pertencem ao contato; nao transforme caracteristicas do contato em caracteristicas do dono.
- Use a direcao das mensagens para separar o que o dono afirma, pede, decide ou promete do que esta sendo dito pelos contatos.
- Quando houver grupos, separe o contexto do grupo do contexto da pessoa: nao atribua ao dono fatos, opinioes ou planos que pertencem a outro participante.
- Quando houver grupos, use o nome do grupo e o participante para entender se algo foi dito pelo dono, por outra pessoa ou pelo grupo como contexto coletivo.
- Procure entender como o dono do numero age, fala, decide, trabalha, se relaciona e organiza a rotina.
- Priorize sinais comportamentais e estruturais do dono do numero, nao apenas um inventario de contatos.
- Nunca trate o proprio dono do numero como se fosse um contato separado. Se a conversa parecer ser com o proprio dono, nao crie contact_memories nem cite essa pessoa como destinatario de projeto.
- Ao citar pessoas e relacoes, infira quem parece ser cada conversa no contexto da vida do dono, sem inventar vinculos que nao tenham apoio no historico.
- Preencha active_projects apenas com projetos, trabalhos, produtos, operacoes ou frentes reais que parecam recorrentes ou importantes para o dono.
- Em cada item de active_projects, explicite o que esta sendo desenvolvido e para quem a entrega, sistema ou servico parece ser direcionado.
- Em active_projects, use no maximo 6 itens e descarte assuntos soltos sem continuidade.
- So use nomes de pessoas em active_projects, built_for, evidence, people_and_relationships ou contact_memories quando o nome estiver explicitamente no texto das mensagens ou ja estiver sustentado pela memoria anterior da mesma person_key. Nomes que aparecem apenas no rotulo tecnico da conversa nao bastam.
- Mantenha updated_life_summary factual, claro, conciso e util para um assistente pessoal futuro. Dê mais peso ao que aparece repetido, ao que tem impacto operacional e ao que altera o comportamento do dono.
- Use os campos de lista para aprendizados concretos, padroes de comportamento e sinais incertos.
- Se a evidencia for fraca, trate como hipotese e nao como fato consolidado.
- Em open_questions, carregue as lacunas anteriores que continuarem sem resposta, remova as que foram resolvidas e reescreva as restantes de modo mais especifico e operacional.
- Quando uma lacuna antiga parecer respondida, transforme a resposta em key_learnings, people_and_relationships, routine_signals ou preferences em vez de repetir a mesma duvida.
- Preencha contact_memories apenas com pessoas que realmente aparecem nesta janela.
- Em cada item de contact_memories, person_key deve copiar exatamente um person_key presente no bloco de contexto por conversa.
- Em contact_memories, profile_summary deve resumir quem e essa pessoa no contexto do dono; relationship_summary deve resumir a dinamica atual entre dono e contato.
- Em contact_memories, relationship_type deve escolher exatamente um destes tipos canonicos: partner, family, friend, work, client, service, acquaintance, other ou unknown.
- Em contact_memories, use as memorias anteriores por pessoa para atualizar de forma cumulativa e sem repetir o que ja existe.
- Em contact_memories, mantenha no maximo 6 fatos, 5 pendencias e 5 topicos por pessoa.
- Nao mencione que voce e uma IA.
- Nao inclua markdown fences.
{bootstrap_rules if is_first_analysis else ""}
""".strip()

    def _build_refinement_prompt(
        self,
        *,
        current_life_summary: str,
        prior_analyses_context: str,
        project_context: str,
        chat_context: str,
    ) -> str:
        return f"""
Refine a memoria consolidada abaixo usando apenas o que ja foi salvo no banco local do AuraCore.

Resumo consolidado atual:
{current_life_summary.strip() or "(memoria consolidada vazia)"}

Snapshots e analises anteriores:
{prior_analyses_context.strip() or "(nenhum snapshot salvo ainda)"}

Projetos e frentes salvos:
{project_context.strip() or "(nenhum projeto salvo ainda)"}

Conversas recentes com a IA pessoal:
{chat_context.strip() or "(nenhuma conversa relevante com a IA salva ainda)"}

Retorne um JSON com exatamente estes campos:
- updated_life_summary: string
- active_projects: {{ name: string, summary: string, status: string, what_is_being_built: string, built_for: string, next_steps: string[], evidence: string[] }}[]

Formato esperado do JSON:
{{
  "updated_life_summary": "string",
  "active_projects": [
    {{
      "name": "string",
      "summary": "string",
      "status": "string",
      "what_is_being_built": "string",
      "built_for": "string",
      "next_steps": ["string"],
      "evidence": ["string"]
    }}
  ]
}}

Regras:
- O objetivo e melhorar a memoria do dono, nao repetir tudo do mesmo jeito.
- Corrija contradicoes, reduza ruido e deixe o resumo mais preciso sobre como o dono age, decide, trabalha e se organiza.
- Dê prioridade a tracos duraveis, responsabilidades recorrentes, projetos reais, estilo de decisao e preferencia operacional.
- Considere o que o dono revelou ou pediu no chat com a IA para reforcar prioridades reais e estado de projetos.
- Se algo estiver fraco ou pouco sustentado, enfraqueça ou remova em vez de inventar complemento.
- Em active_projects, mantenha so projetos realmente importantes e atuais.
- Sempre preencha, quando possivel, o que esta sendo desenvolvido e para quem cada projeto e direcionado.
- Nao inclua markdown fences.
""".strip()

    def _build_memory_synthesis_prompt(
        self,
        *,
        partial_analyses_block: str,
        conversation_context: str,
        current_life_summary: str,
        prior_analyses_context: str,
        project_context: str,
        chat_context: str,
        open_questions_context: str,
        intent: str,
        window_hours: int,
        window_start: datetime,
        window_end: datetime,
        source_message_count: int,
        partial_analysis_count: int,
        contains_group_messages: bool = False,
    ) -> str:
        is_first_analysis = intent == "first_analysis"
        return f"""
Consolide varias leituras parciais da mesma janela de mensagens em uma unica memoria final do dono.

Janela em horas: {window_hours}
Inicio da janela (UTC): {window_start.isoformat()}
Fim da janela (UTC): {window_end.isoformat()}
Mensagens totais incluidas: {source_message_count}
Analises parciais recebidas: {partial_analysis_count}

Resumo consolidado atual:
{current_life_summary.strip() or "(memoria consolidada ainda vazia)"}

Analises anteriores relevantes:
{prior_analyses_context.strip() or "(nenhuma analise anterior relevante)"}

Projetos e frentes ja consolidados:
{project_context.strip() or "(nenhum projeto consolidado ainda)"}

Conversas recentes com a IA pessoal:
{chat_context.strip() or "(nenhuma conversa relevante com a IA salva ainda)"}

Lacunas prioritarias para esta leitura:
{open_questions_context.strip() or "(nenhuma lacuna prioritaria registrada)"}

Contexto resumido por conversa do WhatsApp:
{conversation_context.strip() or "(nenhum agrupamento adicional de conversa disponivel)"}

Analises parciais da mesma janela:
{partial_analyses_block.strip() or "(nenhuma analise parcial disponivel)"}

Retorne um JSON com exatamente estes campos:
- updated_life_summary: string
- window_summary: string
- key_learnings: string[]
- people_and_relationships: string[]
- routine_signals: string[]
- preferences: string[]
- open_questions: string[]
- active_projects: {{ name: string, summary: string, status: string, what_is_being_built: string, built_for: string, next_steps: string[], evidence: string[] }}[]
- contact_memories: {{ person_key: string, contact_name: string, profile_summary: string, relationship_summary: string, salient_facts: string[], open_loops: string[], recent_topics: string[] }}[]

Formato esperado do JSON:
{{
  "updated_life_summary": "string",
  "window_summary": "string",
  "key_learnings": ["string"],
  "people_and_relationships": ["string"],
  "routine_signals": ["string"],
  "preferences": ["string"],
  "open_questions": ["string"],
  "active_projects": [
    {{
      "name": "string",
      "summary": "string",
      "status": "string",
      "what_is_being_built": "string",
      "built_for": "string",
      "next_steps": ["string"],
      "evidence": ["string"]
    }}
  ],
  "contact_memories": [
    {{
      "person_key": "string",
      "contact_name": "string",
      "profile_summary": "string",
      "relationship_type": "partner|family|friend|work|client|service|acquaintance|other|unknown",
      "relationship_summary": "string",
      "salient_facts": ["string"],
      "open_loops": ["string"],
      "recent_topics": ["string"]
    }}
  ]
}}

Regras:
- Trate as analises parciais como partes complementares da mesma janela, nao como pessoas diferentes nem periodos independentes.
- Una duplicatas entre listas, projetos e contatos.
- Dê mais peso ao que aparece repetido em mais de uma parcial ou com evidencia mais concreta.
- Se houver conflito entre parciais, prefira a versao mais prudente e mais bem sustentada.
- Quando houver mensagens de grupo nas parciais, mantenha a atribuicao correta por participante e nao colapse o grupo inteiro como se fosse uma pessoa unica.
- Nunca transforme o proprio dono em contato separado nem atribua a ele o papel de destinatario de um projeto.
- So use nomes de pessoas se eles aparecerem explicitamente no texto das mensagens ou vierem sustentados pela memoria anterior da mesma person_key.
- updated_life_summary deve refletir a janela completa, nao a media mecanica das parciais.
- window_summary deve resumir a janela completa em alto nivel.
- Em active_projects, mantenha poucos projetos fortes, com no maximo 6 itens.
- Em contact_memories, mantenha apenas pessoas realmente relevantes na janela completa.
- Em open_questions, preserve apenas lacunas que continuarem abertas apos unir as parciais.
- Nao inclua markdown fences.
{"- Esta e a primeira analise persistida do dono; mantenha cobertura ampla, prudente e conservadora." if is_first_analysis else ""}
""".strip()

    def _build_project_merge_prompt(
        self,
        *,
        current_life_summary: str,
        current_project_context: str,
        candidate_projects_block: str,
        recent_window_summary: str,
        conversation_context: str,
    ) -> str:
        return f"""
Reconcile os projetos ativos do dono com base no que ja existe salvo e nos novos sinais da leitura mais recente.

Resumo atual da vida do dono:
{current_life_summary.strip() or "(memoria consolidada ainda vazia)"}

Projetos atualmente salvos:
{current_project_context.strip() or "(nenhum projeto salvo ainda)"}

Projetos detectados na leitura mais recente:
{candidate_projects_block.strip() or "(nenhum projeto novo detectado na ultima leitura)"}

Resumo da janela mais recente:
{recent_window_summary.strip() or "(sem resumo da janela)"}

Contexto resumido das conversas recentes:
{conversation_context.strip() or "(sem contexto adicional de conversa)"}

Retorne um JSON com exatamente este formato:
{{
  "active_projects": [
    {{
      "name": "string",
      "summary": "string",
      "status": "string",
      "what_is_being_built": "string",
      "built_for": "string",
      "next_steps": ["string"],
      "evidence": ["string"]
    }}
  ]
}}

Regras:
- A saida deve ser a lista canonica atual de projetos ativos do dono.
- Una projetos duplicados ou muito parecidos em um unico item mais claro.
- Remova projetos que parecem antigos, fracos, resolvidos ou sem continuidade real.
- Nao invente projeto novo se o sinal estiver fraco.
- Prefira poucos projetos fortes a muitos projetos vagos.
- Sempre que possivel, explique o que esta sendo construido e para quem.
- Nunca trate o proprio dono como cliente, contato ou publico do projeto.
- So mantenha nomes de pessoas se eles estiverem explicitamente citados no texto das mensagens ou sustentados por memoria anterior confiavel.
- Mantenha no maximo 8 projetos.
- Nao inclua markdown fences.
""".strip()

    def _build_contact_refinement_prompt(
        self,
        *,
        current_life_summary: str,
        project_context: str,
        contact_memories_block: str,
    ) -> str:
        return f"""
Reavale a lista de contatos do dono com base no panorama mais recente da sua vida e projetos.

Resumo atual da vida do dono:
{current_life_summary.strip() or "(memoria consolidada ainda vazia)"}

Projetos recentes:
{project_context.strip() or "(nenhum projeto consolidado ainda)"}

Lista de contatos para refinar:
{contact_memories_block.strip() or "(nenhum contato)"}

Retorne um JSON com exatamente este formato:
{{
  "contact_memories": [
    {{
      "person_key": "string",
      "contact_name": "string",
      "profile_summary": "string",
      "relationship_summary": "string",
      "salient_facts": ["string"],
      "open_loops": ["string"],
      "recent_topics": ["string"]
    }}
  ]
}}

Regras:
- Retorne a lista completando TODOS os contatos recebidos.
- Nao altere o 'person_key' ou 'contact_name' atual.
- Analise o 'profile_summary' e o 'relationship_summary' de cada contato em relacao ao resumo da vida do dono. Ajuste o texto para ser conciso e focado em como esse contato ajuda, interfere ou se encaixa na vida do dono hoje.
- Preencha relationship_type com exatamente um destes tipos canonicos: partner, family, friend, work, client, service, acquaintance, other ou unknown.
- Em 'salient_facts', 'open_loops' e 'recent_topics', elimine tudo o que for muito antigo, ja finalizado, obsoleto ou irrelevante (ex: "tem consulta", "vai mandar comprovante", conversas menores).
- Deixe apenas os tracos mais importantes de longo prazo da pessoa ou dinamica na rotina.
- Mantenha descricoes neutras e baseadas em fatos.
- Nao inclua markdown fences.
""".strip()

    def _build_important_messages_prompt(
        self,
        *,
        messages_block: str,
        current_life_summary: str,
        project_context: str,
    ) -> str:
        return f"""
Selecione apenas as mensagens que precisam entrar em uma tabela separada de memoria duravel.

Resumo consolidado atual:
{current_life_summary.strip() or "(memoria consolidada ainda vazia)"}

Projetos atuais:
{project_context.strip() or "(nenhum projeto consolidado ainda)"}

Mensagens candidatas:
{messages_block.strip() or "(nenhuma mensagem disponivel)"}

Categorias permitidas:
- credential
- access
- project
- money
- client
- deadline
- document
- risk
- other

Retorne um JSON com exatamente este formato:
{{
  "important_messages": [
    {{
      "message_id": "string",
      "category": "credential|access|project|money|client|deadline|document|risk|other",
      "importance_reason": "string",
      "confidence": 0
    }}
  ]
}}

Regras:
- Selecione somente mensagens com valor futuro reutilizavel.
- Sao importantes: senhas, logins, acessos, chaves, dados de projeto, clientes, dinheiro, cobrancas, valores, prazos, contratos, compromissos relevantes, riscos operacionais e fatos centrais de trabalho.
- Nao salve conversa casual, cumprimento, piada, pequenas confirmacoes, combinados ja triviais ou ruido.
- Codigos temporarios, OTPs e recados que vencem rapido tendem a nao ser memoria duravel; descarte salvo forte justificativa.
- importance_reason deve dizer por que essa mensagem merece sobreviver ao lote operacional curto.
- confidence deve ir de 0 a 100.
- Nao repita message_id.
- Se nada merecer ser salvo, retorne important_messages vazio.
- Nao inclua markdown fences.
""".strip()

    def _build_important_messages_review_prompt(
        self,
        *,
        important_messages_block: str,
        current_life_summary: str,
        project_context: str,
    ) -> str:
        return f"""
Revise o cofre de mensagens importantes abaixo e decida o que continua util.

Resumo consolidado atual:
{current_life_summary.strip() or "(memoria consolidada ainda vazia)"}

Projetos atuais:
{project_context.strip() or "(nenhum projeto consolidado ainda)"}

Mensagens importantes ativas:
{important_messages_block.strip() or "(nenhuma mensagem importante ativa)"}

Retorne um JSON com exatamente este formato:
{{
  "reviews": [
    {{
      "source_message_id": "string",
      "decision": "keep|discard",
      "review_notes": "string",
      "confidence": 0
    }}
  ]
}}

Regras:
- keep quando a mensagem ainda tiver valor operacional ou historico reutilizavel.
- discard quando a informacao ja estiver obsoleta, resolvida, vencida, substituida, duplicada ou sem valor futuro claro.
- Senhas, acessos e configuracoes permanentes podem continuar uteis; codigos temporarios e combinados pontuais costumam ser descartados.
- Projetos e dinheiro devem ficar se ainda ajudam a entender compromissos, contexto de trabalho, clientes, valores ou riscos.
- review_notes deve explicar a decisao de forma curta e objetiva.
- confidence deve ir de 0 a 100.
- Cubra todos os IDs relevantes; se estiver em duvida, prefira keep.
- Nao inclua markdown fences.
""".strip()

    def _extract_content(self, payload: dict[str, Any]) -> str:
        choices = payload.get("choices")
        if not isinstance(choices, list) or not choices:
            raise DeepSeekError("DeepSeek returned no choices.")

        first_choice = choices[0] if isinstance(choices[0], dict) else {}
        message = first_choice.get("message") if isinstance(first_choice, dict) else {}
        if not isinstance(message, dict):
            raise DeepSeekError("DeepSeek returned an invalid message payload.")

        content = message.get("content")
        if not isinstance(content, str) or not content.strip():
            raise DeepSeekError("DeepSeek returned an empty content payload.")

        return content.strip()

    def _build_completion_payload(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        max_tokens: int,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "model": self.settings.deepseek_model,
            "response_format": {"type": "json_object"},
            "max_tokens": max_tokens,
            "messages": [
                {
                    "role": "system",
                    "content": system_prompt,
                },
                {
                    "role": "user",
                    "content": user_prompt,
                },
            ],
        }
        if not self._is_reasoning_model():
            payload["temperature"] = 0.2
        return payload

    def _build_text_completion_payload(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        max_tokens: int,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "model": self.settings.deepseek_model,
            "max_tokens": max_tokens,
            "messages": [
                {
                    "role": "system",
                    "content": system_prompt,
                },
                {
                    "role": "user",
                    "content": user_prompt,
                },
            ],
        }
        if not self._is_reasoning_model():
            payload["temperature"] = 0.35
        return payload

    async def _request_parsed_completion(
        self,
        *,
        payload: dict[str, Any],
        parser: Callable[[str], ParsedResultT],
        validator: Callable[[ParsedResultT], None],
        operation: str,
    ) -> ParsedResultT:
        self._ensure_configured()
        last_error: DeepSeekError | None = None
        logger.info("deepseek_operation_start operation=%s model=%s", operation, self.settings.deepseek_model)
        for attempt in range(1, 3):
            data = await self._post_completion(payload, operation=operation, attempt=attempt)
            try:
                content = self._extract_content(data)
                parsed = parser(content)
                validator(parsed)
                logger.info("deepseek_operation_done operation=%s attempt=%s", operation, attempt)
                return parsed
            except DeepSeekError as exc:
                last_error = exc
                logger.warning(
                    "deepseek_operation_invalid_response operation=%s attempt=%s detail=%s",
                    operation,
                    attempt,
                    str(exc),
                )
        raise last_error or DeepSeekError("DeepSeek returned an invalid structured response.")

    async def _request_text_completion(
        self,
        *,
        payload: dict[str, Any],
        operation: str,
    ) -> str:
        self._ensure_configured()
        last_error: DeepSeekError | None = None
        logger.info("deepseek_operation_start operation=%s model=%s", operation, self.settings.deepseek_model)
        for attempt in range(1, 3):
            data = await self._post_completion(payload, operation=operation, attempt=attempt)
            try:
                content = self._extract_content(data)
                if not content.strip():
                    raise DeepSeekError("DeepSeek retornou uma resposta vazia.")
                logger.info("deepseek_operation_done operation=%s attempt=%s", operation, attempt)
                return content.strip()
            except DeepSeekError as exc:
                last_error = exc
                logger.warning(
                    "deepseek_operation_invalid_response operation=%s attempt=%s detail=%s",
                    operation,
                    attempt,
                    str(exc),
                )
        raise last_error or DeepSeekError("DeepSeek returned an invalid text response.")

    async def _post_completion(self, payload: dict[str, Any], *, operation: str, attempt: int) -> dict[str, Any]:
        self._ensure_configured()
        headers = {
            "Authorization": f"Bearer {self.settings.deepseek_api_key}",
            "Content-Type": "application/json",
        }
        messages = payload.get("messages")
        system_prompt_chars = 0
        user_prompt_chars = 0
        if isinstance(messages, list):
            for message in messages:
                if not isinstance(message, dict):
                    continue
                role = str(message.get("role", ""))
                content = str(message.get("content", ""))
                if role == "system":
                    system_prompt_chars += len(content)
                elif role == "user":
                    user_prompt_chars += len(content)
        start_clock = perf_counter()
        request_timeout = httpx.Timeout(
            connect=min(10.0, self.settings.deepseek_timeout_seconds),
            read=self.settings.deepseek_timeout_seconds,
            write=min(30.0, max(10.0, self.settings.deepseek_timeout_seconds)),
            pool=min(10.0, self.settings.deepseek_timeout_seconds),
        )
        hard_timeout_seconds = self.settings.deepseek_timeout_seconds + 5.0
        logger.info(
            "deepseek_request_start operation=%s attempt=%s model=%s timeout_seconds=%s system_prompt_chars=%s user_prompt_chars=%s",
            operation,
            attempt,
            self.settings.deepseek_model,
            self.settings.deepseek_timeout_seconds,
            system_prompt_chars,
            user_prompt_chars,
        )
        try:
            async with httpx.AsyncClient(
                base_url=self.settings.normalized_deepseek_api_base_url,
                timeout=request_timeout,
                trust_env=False,
            ) as client:
                response = await asyncio.wait_for(
                    client.post("/chat/completions", headers=headers, json=payload),
                    timeout=hard_timeout_seconds,
                )
        except asyncio.TimeoutError as exc:
            latency_ms = round((perf_counter() - start_clock) * 1000)
            logger.error(
                "deepseek_request_timeout operation=%s attempt=%s timeout_kind=hard latency_ms=%s",
                operation,
                attempt,
                latency_ms,
            )
            raise DeepSeekError(
                f"DeepSeek excedeu o timeout duro de {hard_timeout_seconds:.0f}s em {operation}."
            ) from exc
        except httpx.TimeoutException as exc:
            latency_ms = round((perf_counter() - start_clock) * 1000)
            logger.error(
                "deepseek_request_timeout operation=%s attempt=%s timeout_kind=%s latency_ms=%s detail=%s",
                operation,
                attempt,
                exc.__class__.__name__,
                latency_ms,
                str(exc),
            )
            raise DeepSeekError(
                f"DeepSeek excedeu o timeout HTTP ({exc.__class__.__name__}) em {operation}: {exc}"
            ) from exc
        except httpx.HTTPError as exc:
            latency_ms = round((perf_counter() - start_clock) * 1000)
            logger.error(
                "deepseek_request_transport_error operation=%s attempt=%s error_kind=%s latency_ms=%s detail=%s",
                operation,
                attempt,
                exc.__class__.__name__,
                latency_ms,
                str(exc),
            )
            raise DeepSeekError(
                f"Falha de transporte ao chamar DeepSeek em {operation} ({exc.__class__.__name__}): {exc}"
            ) from exc

        latency_ms = round((perf_counter() - start_clock) * 1000)
        logger.info(
            "deepseek_request_done operation=%s attempt=%s status_code=%s latency_ms=%s",
            operation,
            attempt,
            response.status_code,
            latency_ms,
        )

        if response.status_code >= 400:
            detail = response.text.strip() or "Unexpected DeepSeek error."
            raise DeepSeekError(f"DeepSeek request failed ({response.status_code}): {detail}")

        try:
            return response.json()
        except json.JSONDecodeError as exc:
            raise DeepSeekError(f"DeepSeek retornou JSON HTTP invalido em {operation}: {exc}") from exc

    def _ensure_configured(self) -> None:
        if not self.settings.deepseek_api_key:
            raise DeepSeekError("DEEPSEEK_API_KEY nao configurada no backend local.")

    def _validate_analysis_result(self, parsed: DeepSeekMemoryResult) -> None:
        if not parsed.updated_life_summary.strip():
            raise DeepSeekError("DeepSeek returned an empty consolidated memory.")
        if not parsed.window_summary.strip():
            raise DeepSeekError("DeepSeek returned an empty window summary.")
        for person in parsed.contact_memories:
            if not person.person_key.strip():
                raise DeepSeekError("DeepSeek returned a contact memory without person_key.")
            if not person.profile_summary.strip():
                raise DeepSeekError("DeepSeek returned a contact memory without profile_summary.")
            person.relationship_type = self._normalize_relationship_type(person.relationship_type)

    def _validate_refinement_result(self, parsed: DeepSeekMemoryRefinementResult) -> None:
        if not parsed.updated_life_summary.strip():
            raise DeepSeekError("DeepSeek retornou uma memoria refinada vazia.")

    def _validate_project_merge_result(self, parsed: DeepSeekProjectMergeResult) -> None:
        for project in parsed.active_projects:
            if not project.name.strip():
                raise DeepSeekError("DeepSeek retornou um projeto reconciliado sem nome.")
            if not project.summary.strip():
                raise DeepSeekError("DeepSeek retornou um projeto reconciliado sem resumo.")

    def _validate_contact_refinement_result(self, parsed: DeepSeekContactMemoryRefinementResult) -> None:
        for person in parsed.contact_memories:
            if not person.person_key.strip():
                raise DeepSeekError("DeepSeek retornou um contato refinado sem person_key.")
            if not person.profile_summary.strip():
                raise DeepSeekError("DeepSeek retornou um contato refinado sem profile_summary.")
            person.relationship_type = self._normalize_relationship_type(person.relationship_type)

    def _validate_important_messages_result(
        self,
        parsed: DeepSeekImportantMessagesResult,
        *,
        allowed_message_ids: set[str],
    ) -> None:
        for item in parsed.important_messages:
            if item.message_id not in allowed_message_ids:
                raise DeepSeekError("DeepSeek retornou um message_id fora da selecao enviada.")
            if not item.category.strip():
                raise DeepSeekError("DeepSeek retornou uma mensagem importante sem categoria.")
            if not item.importance_reason.strip():
                raise DeepSeekError("DeepSeek retornou uma mensagem importante sem justificativa.")

    def _validate_important_messages_review_result(
        self,
        parsed: DeepSeekImportantMessagesReviewResult,
        *,
        allowed_message_ids: set[str],
    ) -> None:
        for item in parsed.reviews:
            if item.source_message_id not in allowed_message_ids:
                raise DeepSeekError("DeepSeek retornou um source_message_id invalido na revisao.")
            if not item.review_notes.strip():
                raise DeepSeekError("DeepSeek retornou uma revisao sem review_notes.")

    def _validate_assistant_search_plan(self, parsed: DeepSeekAssistantSearchPlan) -> None:
        parsed.people_limit = max(0, min(6, parsed.people_limit))
        parsed.important_messages_limit = max(0, min(6, parsed.important_messages_limit))
        parsed.projects_limit = max(0, min(6, parsed.projects_limit))
        parsed.snapshots_limit = max(0, min(6, parsed.snapshots_limit))
        parsed.people_queries = parsed.people_queries[:3]
        parsed.important_message_queries = parsed.important_message_queries[:3]
        parsed.project_queries = parsed.project_queries[:3]
        parsed.snapshot_queries = parsed.snapshot_queries[:3]

    def _validate_agent_memory_decision(self, parsed: DeepSeekAgentMemoryDecision) -> None:
        parsed.profile_summary = parsed.profile_summary.strip()
        parsed.preferred_tone = parsed.preferred_tone.strip()
        parsed.explanation = parsed.explanation.strip()
        parsed.preferences = parsed.preferences[:12]
        parsed.objectives = parsed.objectives[:12]
        parsed.durable_facts = parsed.durable_facts[:12]
        parsed.constraints = parsed.constraints[:12]
        parsed.recurring_instructions = parsed.recurring_instructions[:12]

    def _is_reasoning_model(self) -> bool:
        return "reasoner" in self.settings.deepseek_model.strip().lower()

    def _analysis_max_output_tokens(self, *, intent: str = "improve_memory") -> int:
        if self._is_reasoning_model():
            if intent == "first_analysis":
                return 14000
            return 12000
        return 5000

    def _refinement_max_output_tokens(self) -> int:
        return 8000 if self._is_reasoning_model() else 3500

    def _parse_result(self, content: str) -> DeepSeekMemoryResult:
        raw = self._parse_json_dict(
            content,
            error_message="DeepSeek returned invalid JSON output.",
            shape_error_message="DeepSeek returned a JSON payload in an unexpected shape.",
        )
        return DeepSeekMemoryResult(
            updated_life_summary=self._as_text(raw.get("updated_life_summary")),
            window_summary=self._as_text(raw.get("window_summary")),
            key_learnings=self._as_string_list(raw.get("key_learnings")),
            people_and_relationships=self._as_string_list(raw.get("people_and_relationships")),
            routine_signals=self._as_string_list(raw.get("routine_signals")),
            preferences=self._as_string_list(raw.get("preferences")),
            open_questions=self._as_string_list(raw.get("open_questions")),
            active_projects=self._as_projects(raw.get("active_projects")),
            contact_memories=self._as_person_memories(raw.get("contact_memories")),
        )

    def _parse_refinement_result(self, content: str) -> DeepSeekMemoryRefinementResult:
        raw = self._parse_json_dict(
            content,
            error_message="DeepSeek retornou JSON invalido no refinamento da memoria.",
            shape_error_message="DeepSeek retornou um payload inesperado no refinamento da memoria.",
        )
        return DeepSeekMemoryRefinementResult(
            updated_life_summary=self._as_text(raw.get("updated_life_summary")),
            active_projects=self._as_projects(raw.get("active_projects")),
        )

    def _parse_project_merge_result(self, content: str) -> DeepSeekProjectMergeResult:
        raw = self._parse_json_dict(
            content,
            error_message="DeepSeek retornou JSON invalido na reconciliacao de projetos.",
            shape_error_message="DeepSeek retornou um payload inesperado na reconciliacao de projetos.",
        )
        return DeepSeekProjectMergeResult(
            active_projects=self._as_projects(raw.get("active_projects")),
        )

    def _parse_contact_refinement_result(self, content: str) -> DeepSeekContactMemoryRefinementResult:
        raw = self._parse_json_dict(
            content,
            error_message="DeepSeek retornou JSON invalido no refinamento de contatos.",
            shape_error_message="DeepSeek retornou um payload inesperado no refinamento de contatos.",
        )
        return DeepSeekContactMemoryRefinementResult(
            contact_memories=self._as_person_memories(raw.get("contact_memories")),
        )

    def _parse_important_messages_result(self, content: str) -> DeepSeekImportantMessagesResult:
        raw = self._parse_json_dict(
            content,
            error_message="DeepSeek retornou JSON invalido na selecao de mensagens importantes.",
            shape_error_message="DeepSeek retornou um payload inesperado na selecao de mensagens importantes.",
        )
        return DeepSeekImportantMessagesResult(
            important_messages=self._as_important_messages(raw.get("important_messages")),
        )

    def _parse_important_messages_review_result(self, content: str) -> DeepSeekImportantMessagesReviewResult:
        raw = self._parse_json_dict(
            content,
            error_message="DeepSeek retornou JSON invalido na revisao das mensagens importantes.",
            shape_error_message="DeepSeek retornou um payload inesperado na revisao das mensagens importantes.",
        )

        return DeepSeekImportantMessagesReviewResult(
            reviews=self._as_important_message_reviews(raw.get("reviews")),
        )

    def _parse_assistant_search_plan(self, content: str) -> DeepSeekAssistantSearchPlan:
        raw = self._parse_json_dict(
            content,
            error_message="DeepSeek retornou JSON invalido para o plano de busca do assistente.",
            shape_error_message="DeepSeek retornou um payload inesperado para o plano de busca do assistente.",
        )

        def _limit(value: Any, default: int) -> int:
            try:
                resolved = int(value)
            except (TypeError, ValueError):
                resolved = default
            return max(0, min(6, resolved))

        people_queries = self._as_string_list(raw.get("people_queries"))[:3]
        important_queries = self._as_string_list(raw.get("important_message_queries"))[:3]
        project_queries = self._as_string_list(raw.get("project_queries"))[:3]
        snapshot_queries = self._as_string_list(raw.get("snapshot_queries"))[:3]

        return DeepSeekAssistantSearchPlan(
            needs_retrieval=bool(raw.get("needs_retrieval")),
            people_queries=people_queries,
            important_message_queries=important_queries,
            project_queries=project_queries,
            snapshot_queries=snapshot_queries,
            people_limit=_limit(raw.get("people_limit"), 2 if people_queries else 0),
            important_messages_limit=_limit(raw.get("important_messages_limit"), 3 if important_queries else 0),
            projects_limit=_limit(raw.get("projects_limit"), 2 if project_queries else 0),
            snapshots_limit=_limit(raw.get("snapshots_limit"), 2 if snapshot_queries else 0),
            should_include_open_questions=bool(raw.get("should_include_open_questions")),
            should_include_contact_memory=bool(raw.get("should_include_contact_memory")),
            requires_confirmation=bool(raw.get("requires_confirmation")),
            explanation=self._as_text(raw.get("explanation")),
        )

    def _parse_agent_memory_decision(self, content: str) -> DeepSeekAgentMemoryDecision:
        raw = self._parse_json_dict(
            content,
            error_message="DeepSeek retornou JSON invalido para a memoria do agente.",
            shape_error_message="DeepSeek retornou um payload inesperado para a memoria do agente.",
        )

        return DeepSeekAgentMemoryDecision(
            should_update=bool(raw.get("should_update")),
            profile_summary=self._as_text(raw.get("profile_summary")),
            preferred_tone=self._as_text(raw.get("preferred_tone")),
            preferences=self._as_string_list(raw.get("preferences")),
            objectives=self._as_string_list(raw.get("objectives")),
            durable_facts=self._as_string_list(raw.get("durable_facts")),
            constraints=self._as_string_list(raw.get("constraints")),
            recurring_instructions=self._as_string_list(raw.get("recurring_instructions")),
            explanation=self._as_text(raw.get("explanation")),
        )

    def _build_reply_prompt(
        self,
        *,
        user_message: str,
        current_life_summary: str,
        recent_snapshots_context: str,
        recent_projects_context: str,
        recent_chat_context: str,
        interaction_mode: str,
        context_hint: str = "",
        priority_context: str = "",
        recent_messages_label: str = "Historico recente desta conversa",
        additional_rules: list[str] | None = None,
    ) -> str:
        priority_context_block = ""
        if priority_context.strip():
            priority_context_block = (
                "Contexto prioritario desta conversa:\n"
                f"{priority_context.strip()}\n\n"
            )
        extra_context_block = ""
        if context_hint.strip():
            extra_context_block = (
                "Contexto adicional relevante:\n"
                f"{context_hint.strip()}"
            )
        extra_rules = "\n".join(
            f"- {rule.strip()}"
            for rule in (additional_rules or [])
            if isinstance(rule, str) and rule.strip()
        )
        return f"""
{priority_context_block}Contexto consolidado do dono:
{current_life_summary.strip() or "(ainda sem resumo consolidado)"}

Projetos e frentes conhecidos:
{recent_projects_context.strip() or "(nenhum projeto consolidado ainda)"}

Analises recentes da memoria:
{recent_snapshots_context.strip() or "(nenhum snapshot recente)"}

{recent_messages_label.strip() or "Historico recente desta conversa"}:
{recent_chat_context.strip() or "(sem conversa anterior nesta thread)"}

Mensagem atual do dono:
{user_message.strip()}

Modo de interacao:
{interaction_mode}

{extra_context_block}

Regras:
- Responda primeiro ao que o dono acabou de dizer, de forma natural.
- Use o resumo consolidado para adaptar tom, prioridade e praticidade da resposta.
- Priorize contexto pessoal e de trabalho realmente presente no material acima, mas so mencione isso quando for relevante.
- Se a pergunta tocar em um projeto conhecido, conecte a resposta ao estado atual desse projeto.
- Se o dono estiver pedindo ajuda operacional, priorize a resposta mais acionavel e mais curta primeiro.
- Se houver incerteza ou memoria incompleta, assuma isso explicitamente.
- Em cumprimentos, mensagens curtas ou aberturas vagas, responda em 1 ou 2 frases curtas e pergunte como ajudar.
- Se o pedido envolver promessa, compromisso, prazo, resposta em nome do dono ou dado sensivel, confirme antes de tratar isso como decidido.
- Nao enumere fatos antigos sem convite explicito.
- Evite hiperfoco em um unico tema so porque ele apareceu na memoria.
- Evite respostas genéricas, longas demais ou com floreio.
- Nao use markdown fences.
{extra_rules}
""".strip()

    def _parse_json_dict(
        self,
        content: str,
        *,
        error_message: str,
        shape_error_message: str,
    ) -> dict[str, Any]:
        normalized_content = content.strip()
        if normalized_content.startswith("```"):
            normalized_content = normalized_content.strip("`")
            normalized_content = normalized_content.replace("json", "", 1).strip()

        try:
            raw = json.loads(normalized_content)
        except json.JSONDecodeError as exc:
            raise DeepSeekError(error_message) from exc

        if not isinstance(raw, dict):
            raise DeepSeekError(shape_error_message)
        return raw

    def _as_text(self, value: Any) -> str:
        if value is None:
            return ""
        if isinstance(value, str):
            return value.strip()
        return str(value).strip()

    def _as_int(self, value: Any) -> int:
        try:
            return int(value)
        except (TypeError, ValueError):
            return 0

    def _as_string_list(self, value: Any) -> list[str]:
        if not isinstance(value, list):
            return []

        items: list[str] = []
        for item in value:
            if item is None:
                continue
            if isinstance(item, str):
                text = item.strip()
            else:
                text = json.dumps(item, ensure_ascii=True).strip()
            if text:
                items.append(text)
        return items

    def _as_projects(self, value: Any) -> list[DeepSeekProjectMemory]:
        if not isinstance(value, list):
            return []

        projects: list[DeepSeekProjectMemory] = []
        for item in value:
            if not isinstance(item, dict):
                continue
            project = DeepSeekProjectMemory(
                name=self._as_text(item.get("name")),
                summary=self._as_text(item.get("summary")),
                status=self._as_text(item.get("status")),
                what_is_being_built=self._as_text(item.get("what_is_being_built")),
                built_for=self._as_text(item.get("built_for")),
                next_steps=self._as_string_list(item.get("next_steps")),
                evidence=self._as_string_list(item.get("evidence")),
            )
            if project.name and project.summary:
                projects.append(project)
        return projects[:6]

    def _as_person_memories(self, value: Any) -> list[DeepSeekPersonMemory]:
        if not isinstance(value, list):
            return []

        items: list[DeepSeekPersonMemory] = []
        seen_keys: set[str] = set()
        for item in value:
            if not isinstance(item, dict):
                continue
            person_key = self._as_text(item.get("person_key"))
            if not person_key or person_key in seen_keys:
                continue
            memory = DeepSeekPersonMemory(
                person_key=person_key,
                contact_name=self._as_text(item.get("contact_name")),
                profile_summary=self._as_text(item.get("profile_summary")),
                relationship_type=self._normalize_relationship_type(self._as_text(item.get("relationship_type"))),
                relationship_summary=self._as_text(item.get("relationship_summary")),
                salient_facts=self._as_string_list(item.get("salient_facts"))[:6],
                open_loops=self._as_string_list(item.get("open_loops"))[:5],
                recent_topics=self._as_string_list(item.get("recent_topics"))[:5],
            )
            if memory.profile_summary:
                items.append(memory)
                seen_keys.add(person_key)
        return items[:24]

    def _normalize_relationship_type(self, value: str) -> str:
        normalized = (value or "").strip().lower().replace("-", "_").replace(" ", "_")
        allowed = {
            "partner",
            "family",
            "friend",
            "work",
            "client",
            "service",
            "acquaintance",
            "other",
            "unknown",
        }
        return normalized if normalized in allowed else "unknown"

    def _as_important_messages(self, value: Any) -> list[DeepSeekImportantMessageCandidate]:
        if not isinstance(value, list):
            return []

        items: list[DeepSeekImportantMessageCandidate] = []
        seen_ids: set[str] = set()
        for item in value:
            if not isinstance(item, dict):
                continue
            message_id = self._as_text(item.get("message_id"))
            if not message_id or message_id in seen_ids:
                continue
            candidate = DeepSeekImportantMessageCandidate(
                message_id=message_id,
                category=self._normalize_importance_category(self._as_text(item.get("category"))),
                importance_reason=self._as_text(item.get("importance_reason")),
                confidence=max(0, min(100, self._as_int(item.get("confidence")))),
            )
            if candidate.category and candidate.importance_reason:
                items.append(candidate)
                seen_ids.add(message_id)
        return items[:32]

    def _as_important_message_reviews(self, value: Any) -> list[DeepSeekImportantMessageReviewDecision]:
        if not isinstance(value, list):
            return []

        items: list[DeepSeekImportantMessageReviewDecision] = []
        seen_ids: set[str] = set()
        for item in value:
            if not isinstance(item, dict):
                continue
            source_message_id = self._as_text(item.get("source_message_id"))
            if not source_message_id or source_message_id in seen_ids:
                continue
            decision_text = self._as_text(item.get("decision")).lower()
            decision: Literal["keep", "discard"] = "discard" if decision_text == "discard" else "keep"
            review = DeepSeekImportantMessageReviewDecision(
                source_message_id=source_message_id,
                decision=decision,
                review_notes=self._as_text(item.get("review_notes")),
                confidence=max(0, min(100, self._as_int(item.get("confidence")))),
            )
            if review.review_notes:
                items.append(review)
                seen_ids.add(source_message_id)
        return items[:80]

    def _normalize_importance_category(self, value: str) -> str:
        normalized = value.strip().lower()
        if normalized in {"credential", "access", "project", "money", "client", "deadline", "document", "risk", "other"}:
            return normalized
        return "other"
