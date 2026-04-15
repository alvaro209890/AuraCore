from __future__ import annotations

import ast
import asyncio
import json
import re
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


class DeepSeekProjectEditResult(BaseModel):
    project: DeepSeekProjectMemory
    assistant_message: str = ""


class DeepSeekContactMemoryRefinementResult(BaseModel):
    contact_memories: list[DeepSeekPersonMemory] = Field(default_factory=list)


class DeepSeekAgendaExtractionResult(BaseModel):
    action: str = "none"
    has_schedule_signal: bool = False
    is_explicit_user_intent: bool = False
    titulo: str = ""
    data_inicio: str | None = None
    data_fim: str | None = None
    intencao: str = ""
    confidence: int = Field(default=0, ge=0, le=100)
    missing_fields: list[str] = Field(default_factory=list)


class DeepSeekAgendaConflictResolutionResult(BaseModel):
    decision: Literal[
        "keep_new_cancel_existing",
        "keep_existing_cancel_new",
        "keep_both",
        "clarify",
    ] = "clarify"
    explanation: str = ""
    confidence: int = Field(default=0, ge=0, le=100)


class DeepSeekAssistantSearchPlan(BaseModel):
    needs_retrieval: bool = False
    people_queries: list[str] = Field(default_factory=list)
    project_queries: list[str] = Field(default_factory=list)
    snapshot_queries: list[str] = Field(default_factory=list)
    people_limit: int = 0
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
            project_queries=[],
            snapshot_queries=[],
            people_limit=0,
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
    mood_signals: list[str] = Field(default_factory=list)
    implied_urgency: str = ""
    mentioned_relationships: list[str] = Field(default_factory=list)
    implied_tasks: list[str] = Field(default_factory=list)
    writing_style_hints: str = ""
    explanation: str = ""


class DeepSeekCliAction(BaseModel):
    tool: Literal["pwd", "ls", "cd", "cat", "write", "exec", "find", "head", "tail", "mkdir", "touch", "cp", "mv", "rm", "final"] = "exec"
    path: str = ""
    command: str = ""
    content: str = ""
    mode: Literal["overwrite", "append"] = "overwrite"
    explanation: str = ""


class DeepSeekCliPlan(BaseModel):
    summary: str = ""
    explicit_sensitive_request: bool = False
    actions: list[DeepSeekCliAction] = Field(default_factory=list)


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

    async def extract_agenda_signal(
        self,
        *,
        message_text: str,
        reference_now: datetime,
    ) -> DeepSeekAgendaExtractionResult:
        user_prompt = (
            f"Horario de referencia: {reference_now.isoformat()}\n"
            "Analise a mensagem abaixo e retorne exatamente este formato:\n"
            "{\n"
            '  "action": "create|reschedule|cancel|update_reminder|none|clarify",\n'
            '  "has_schedule_signal": true,\n'
            '  "is_explicit_user_intent": false,\n'
            '  "titulo": "string",\n'
            '  "data_inicio": "string|null",\n'
            '  "data_fim": "string|null",\n'
            '  "intencao": "confirmado|tentativo|incerto",\n'
            '  "confidence": 0,\n'
            '  "missing_fields": ["string"]\n'
            "}\n"
            "Marque action=clarify quando houver horario ou compromisso plausivel, mas faltar intencao explicita ou dados suficientes para salvar com seguranca.\n"
            "Marque action=none quando a mensagem nao for sobre agenda.\n"
            "Mensagem:\n"
            f"{message_text.strip()}"
        )
        payload = self._build_completion_payload(
            system_prompt=(
                "Voce extrai sinais de agenda do AuraCore. "
                "Recebera apenas uma mensagem. "
                "Retorne somente JSON valido. "
                "Classifique com conservadorismo. "
                "Use has_schedule_signal=true apenas quando a mensagem realmente estiver marcando, remarcando, cancelando, pedindo lembrete ou confirmando um compromisso. "
                "Nao trate mencoes informativas de horario como compromisso automatico. "
                "Preencha data_inicio e data_fim preferencialmente em ISO 8601. "
                "Em intencao, use apenas confirmado, tentativo ou incerto. "
                "Em action, use apenas create, reschedule, cancel, update_reminder, none ou clarify."
            ),
            user_prompt=user_prompt,
            max_tokens=self._adaptive_max_tokens(
                user_prompt,
                ceiling_reasoning=180,
                ceiling_standard=140,
                floor_reasoning=140,
                floor_standard=110,
                chars_per_step=240,
                step_tokens=10,
                max_steps=4,
            ),
        )
        return await self._request_parsed_completion(
            payload=payload,
            parser=self._parse_agenda_extraction_result,
            validator=self._validate_agenda_extraction_result,
            operation="extract_agenda_signal",
        )

    async def extract_agenda_conflict_resolution(
        self,
        *,
        message_text: str,
        conflict_context: str,
    ) -> DeepSeekAgendaConflictResolutionResult:
        user_prompt = (
            "Contexto do conflito:\n"
            f"{conflict_context.strip()}\n\n"
            "Mensagem do usuario:\n"
            f"{message_text.strip()}\n\n"
            "Retorne exatamente este formato:\n"
            "{\n"
            '  "decision": "keep_new_cancel_existing|keep_existing_cancel_new|keep_both|clarify",\n'
            '  "explanation": "string",\n'
            '  "confidence": 0\n'
            "}"
        )
        payload = self._build_completion_payload(
            system_prompt=(
                "Voce interpreta a resposta do usuario a um alerta de conflito de agenda. "
                "Recebera a mensagem do usuario e o contexto do conflito. "
                "Retorne somente JSON valido. "
                "Identifique se o usuario quer manter o compromisso novo e cancelar o antigo, "
                "manter o antigo e cancelar o novo, manter ambos, ou se ainda precisa de esclarecimento. "
                "Se a mensagem for ambigua, use clarify."
            ),
            user_prompt=user_prompt,
            max_tokens=self._adaptive_max_tokens(
                user_prompt,
                ceiling_reasoning=160,
                ceiling_standard=120,
                floor_reasoning=120,
                floor_standard=90,
                chars_per_step=320,
                step_tokens=12,
                max_steps=4,
            ),
        )
        return await self._request_parsed_completion(
            payload=payload,
            parser=self._parse_agenda_conflict_resolution_result,
            validator=self._validate_agenda_conflict_resolution_result,
            operation="extract_agenda_conflict_resolution",
        )

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
            model_name=self.settings.deepseek_memory_model,
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
        user_prompt = self._build_contact_refinement_prompt(
            current_life_summary=current_life_summary,
            project_context=project_context,
            contact_memories_block=contact_memories_block,
        )
        payload = self._build_completion_payload(
            system_prompt=(
                "Voce revisa perfis de contatos salvos no AuraCore para alinha-los a nova fase da vida do dono. "
                "Retorne apenas JSON valido. Nao mude o person_key. Atualize os resumos de perfil e relacao, e remova "
                "fatos marcantes, pendencias ou topicos que perderam completamente a relevancia para o contexto atual do dono."
            ),
            user_prompt=user_prompt,
            max_tokens=self._adaptive_max_tokens(
                user_prompt,
                ceiling_reasoning=4200,
                ceiling_standard=2200,
                floor_reasoning=2200,
                floor_standard=1200,
                chars_per_step=1800,
                step_tokens=260,
                max_steps=6,
            ),
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
        user_prompt = self._build_project_merge_prompt(
            current_life_summary=current_life_summary,
            current_project_context=current_project_context,
            candidate_projects_block=candidate_projects_block,
            recent_window_summary=recent_window_summary,
            conversation_context=conversation_context,
        )
        payload = self._build_completion_payload(
            system_prompt=(
                "Voce reconcilia projetos ativos do AuraCore. Sua funcao e combinar os projetos ja salvos "
                "com novos sinais vindos da analise recente e devolver uma lista canonica, curta e sem duplicatas. "
                "Retorne apenas JSON valido."
            ),
            user_prompt=user_prompt,
            max_tokens=self._adaptive_max_tokens(
                user_prompt,
                ceiling_reasoning=2000,
                ceiling_standard=1100,
                floor_reasoning=1000,
                floor_standard=600,
                chars_per_step=1200,
                step_tokens=180,
                max_steps=4,
            ),
        )
        return await self._request_parsed_completion(
            payload=payload,
            parser=self._parse_project_merge_result,
            validator=self._validate_project_merge_result,
            operation="merge_projects_incrementally",
        )

    async def edit_project_memory(
        self,
        *,
        current_life_summary: str,
        current_project_context: str,
        target_project_block: str,
        instruction: str,
    ) -> DeepSeekProjectEditResult:
        user_prompt = self._build_project_edit_prompt(
            current_life_summary=current_life_summary,
            current_project_context=current_project_context,
            target_project_block=target_project_block,
            instruction=instruction,
        )
        payload = self._build_completion_payload(
            system_prompt=(
                "Voce edita um unico projeto do AuraCore a partir de uma instrucao do usuario. "
                "Sua funcao e reescrever somente esse projeto com clareza, sem inventar fatos fora do que ja esta no projeto "
                "ou explicitamente pedido na instrucao. Retorne apenas JSON valido."
            ),
            user_prompt=user_prompt,
            max_tokens=self._adaptive_max_tokens(
                user_prompt,
                ceiling_reasoning=2200,
                ceiling_standard=1200,
                floor_reasoning=1000,
                floor_standard=700,
                chars_per_step=1200,
                step_tokens=180,
                max_steps=5,
            ),
        )
        return await self._request_parsed_completion(
            payload=payload,
            parser=self._parse_project_edit_result,
            validator=self._validate_project_edit_result,
            operation="edit_project_memory",
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
        max_output_tokens: int | None = None,
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
            max_tokens=max_output_tokens or self._analysis_max_output_tokens(intent=intent),
            model_name=self.settings.deepseek_memory_model,
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
        user_prompt = self._build_reply_prompt(
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
        )
        payload = self._build_text_completion_payload(
            interaction_mode=interaction_mode,
            system_prompt=(
                "Seu nome e Orion. Voce e a inteligencia artificial pessoal do dono desta conta, "
                "uma presenca constante e confiavel no WhatsApp. Fale sempre em portugues do Brasil."
                "\n\n"
                "Personalidade: voce e proativo sem ser invasivo, empatico sem ser sentimental, "
                "e tem um senso de humor sutil que aparece naturalmente quando o momento permite. "
                "Trate o dono pelo nome ou de forma familiar quando souber. Adapte seu tom: "
                "casual e direto em conversas do dia a dia, mais formal e preciso quando o assunto "
                "for serio (saude, finanças, compromissos, conflitos)."
                "\n\n"
                "Uso de memoria: use o contexto disponivel de forma silenciosa e natural. "
                "Nunca diga 'voce me disse', 'pela minha memoria', 'no contexto' ou frases similares. "
                "Integre informacoes do passado como algo que voce simplesmente sabe, "
                "da mesma forma que um assistente humano que conhece bem a pessoa. "
                "Quando relevante, conecte temas atuais com informacoes anteriores. "
                "Se nao tiver certeza sobre algo, admita — nao invente fatos."
                "\n\n"
                "Ambiguidade: quando a mensagem do dono for vaga ou ambigua, faca uma pergunta "
                "curta e esclarecedora em vez de assumir. Prefira entender antes de responder."
                "\n\n"
                "Identidade: se perguntarem quem voce e, responda de forma direta e natural que "
                "voce e Orion, a IA pessoal criada para ajudar esta pessoa. Nao entre em detalhes "
                "tecnicos salvo se perguntado."
                "\n\n"
                "Proatividade: quando o contexto permitir, faca sugestoes breves e acionaveis. "
                "Se o dono mencionou um projeto ativo e a mensagem tem relacao, conecte os pontos. "
                "Se houver um compromisso na agenda relacionado, mencione de forma natural. "
                "Se algo importante ficou pendente e o assunto ressurgiu, lembre de leve. "
                "Nao transforme proatividade em monologo — 1 frase de sugestao ja basta."
                "\n\n"
                "Inteligencia emocional: perceba o tom emocional da mensagem — frustracao, "
                "ansiedade, entusiasmo, cansaco — e ajuste sua resposta acorde. Ofereça suporte "
                "quando o dono estiver sob pressao, celebre conquistas quando houver progresso, "
                "e seja direto quando o dono parecer objetivo e apressado."
                "\n\n"
                "Limites: nunca fale sobre sistema, banco de dados, modelos, prompts, analises, "
                "memoria artificial ou bastidores tecnicos. Antes de assumir promessa, prazo, "
                "resposta em nome do dono ou dado sensivel, peca confirmacao. "
                "Nao transforme cumprimentos em relatorio. Nao puxe fatos antigos sem necessidade."
            ),
            user_prompt=user_prompt,
            max_tokens=self._adaptive_max_tokens(
                user_prompt,
                ceiling_reasoning=1500,
                ceiling_standard=1100,
                floor_reasoning=500,
                floor_standard=400,
                chars_per_step=1000,
                step_tokens=100,
                max_steps=5,
            ),
        )
        return await self._request_text_completion(payload=payload, operation="assistant_reply")

    async def extract_assistant_search_plan(
        self,
        *,
        user_message: str,
        channel: str,
        has_contact_memory: bool = False,
    ) -> DeepSeekAssistantSearchPlan:
        user_prompt = (
            f"Canal: {channel}\n"
            f"Memoria propria do contato disponivel: {'sim' if has_contact_memory else 'nao'}\n"
            f"Mensagem do dono:\n{user_message.strip()}"
        )
        payload = self._build_completion_payload(
            system_prompt=(
                "Voce decide qual contexto adicional deve ser recuperado para responder melhor uma mensagem do dono. "
                "Responda EXCLUSIVAMENTE em JSON valido com as chaves: "
                "needs_retrieval, people_queries, project_queries, snapshot_queries, "
                "people_limit, projects_limit, snapshots_limit, "
                "should_include_open_questions, should_include_contact_memory, requires_confirmation e explanation. "
                "Use no maximo 3 consultas por categoria e limites pequenos. "
                "needs_retrieval deve ser false para cumprimentos simples ou quando o contexto atual ja basta. "
                "requires_confirmation deve ser true quando houver promessa, prazo, negociacao, dado sensivel, "
                "acao delicada ou resposta em nome do dono. "
                "should_include_contact_memory so deve ser true se isso puder melhorar de fato uma conversa do WhatsApp."
            ),
            user_prompt=user_prompt,
            max_tokens=self._adaptive_max_tokens(
                user_prompt,
                ceiling_reasoning=420,
                ceiling_standard=240,
                floor_reasoning=220,
                floor_standard=140,
                chars_per_step=700,
                step_tokens=50,
                max_steps=4,
            ),
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
        user_prompt = (
            "Memoria atual deste contato no agente:\n"
            f"{existing_memory_context.strip() or '(sem memoria propria ainda)'}\n\n"
            "Nova mensagem do dono:\n"
            f"{user_message.strip()}"
        )
        payload = self._build_completion_payload(
            system_prompt=(
                "Voce extrai memoria duravel e sinais contextuais a partir de uma mensagem enviada pelo proprio dono ao assistente no WhatsApp. "
                "Considere preferencias, tom desejado, objetivos, fatos duraveis, restricoes e instrucoes recorrentes "
                "que possam melhorar conversas futuras com esse mesmo dono. "
                "Alem disso, extraia sinais momentaneos que ajudam na proxima resposta: humor, urgencia, relacoes mencionadas, "
                "tarefas implicitas e pistas sobre o estilo de escrita. "
                "Ignore cumprimentos, recados efemeros e pedidos que so fazem sentido nesta unica resposta. "
                "Responda EXCLUSIVAMENTE em JSON valido com as chaves: should_update, profile_summary, preferred_tone, "
                "preferences, objectives, durable_facts, constraints, recurring_instructions, "
                "mood_signals, implied_urgency, mentioned_relationships, implied_tasks, writing_style_hints e explanation. "
                "mood_signals: sinais de humor/estado emocional (ex: 'apressado', 'frustrado com X', 'animado com Y'). "
                "Detecte tambem dinamica relacional: se o dono confia nesse contato, se cobra, se delega, se e casual. "
                "Observe se o dono muda de tom com este contato especifico — isso informa como responder no futuro. "
                "implied_urgency: nivel de urgencia detectado ('nenhuma', 'moderada', 'alta') com breve justificativa. "
                "mentioned_relationships: nomes ou papeis de terceiros mencionados na mensagem. "
                "implied_tasks: tarefas ou acoes que o dono parece esperar que sejam feitas. "
                "writing_style_hints: pistas sobre como o dono escreve (formal, direto, usa abreviacoes, emocional). "
                "Se nada for duravel, retorne should_update=false e listas vazias."
            ),
            user_prompt=user_prompt,
            max_tokens=self._adaptive_max_tokens(
                user_prompt,
                ceiling_reasoning=560,
                ceiling_standard=320,
                floor_reasoning=260,
                floor_standard=180,
                chars_per_step=700,
                step_tokens=60,
                max_steps=5,
            ),
        )
        return await self._request_parsed_completion(
            payload=payload,
            parser=self._parse_agent_memory_decision,
            validator=self._validate_agent_memory_decision,
            operation="agent_memory_extract",
        )

    async def extract_cli_plan(
        self,
        *,
        user_message: str,
        cwd: str,
        cli_mode_enabled: bool,
    ) -> DeepSeekCliPlan:
        user_prompt = (
            f"Diretorio atual: {cwd.strip()}\n"
            f"Modo CLI ativo: {'sim' if cli_mode_enabled else 'nao'}\n"
            "Mensagem do usuario:\n"
            f"{user_message.strip()}"
        )
        payload = self._build_completion_payload(
            system_prompt=(
                "Voce orquestra um terminal via WhatsApp com as ferramentas pwd, ls, cd, cat, write, exec, find, head, tail, mkdir, touch, cp, mv e rm. "
                "Responda EXCLUSIVAMENTE em JSON valido com as chaves summary, explicit_sensitive_request e actions. "
                "Cada item de actions deve ter: tool, path, command, content, mode e explanation. "
                "Use o menor numero de acoes necessario. "
                "tool=cd so para mudar o diretorio persistente. "
                "tool=ls para listar arquivos. "
                "tool=cat para ler arquivo. "
                "tool=write para criar ou alterar arquivo quando o pedido explicitar conteudo. "
                "tool=exec para comandos shell gerais. "
                "tool=find para localizar arquivos ou texto. "
                "tool=head e tool=tail para ver trechos de arquivo. "
                "tool=mkdir para criar diretorios. "
                "tool=touch para criar arquivo vazio. "
                "tool=cp e tool=mv para copiar ou mover. "
                "tool=rm para remover quando o pedido for explicito. "
                "tool=final apenas se nenhuma ferramenta for necessaria e houver uma resposta curta a enviar. "
                "Marque explicit_sensitive_request=true somente quando o usuario pedir de forma explicita mexer em servicos, systemctl, docker, geoserver, cloudflared, tunnel, tunnel do cloudflare ou processos do sistema. "
                "Nao invente conteudo de arquivo nem comandos que o usuario nao pediu."
            ),
            user_prompt=user_prompt,
            max_tokens=self._adaptive_max_tokens(
                user_prompt,
                ceiling_reasoning=700,
                ceiling_standard=420,
                floor_reasoning=220,
                floor_standard=180,
                chars_per_step=600,
                step_tokens=70,
                max_steps=5,
            ),
        )
        return await self._request_parsed_completion(
            payload=payload,
            parser=self._parse_cli_plan,
            validator=self._validate_cli_plan,
            operation="cli_plan",
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
                + (
                    "\n\nDiretrizes avancadas de analise: "
                    "Detecte padroes comportamentais — como o dono reage sob pressao, se tende a delegar ou executar, "
                    "se prefere decisoes rapidas ou refletidas. Identifique estilos de comunicacao — direto, detalhista, "
                    "visual, pragmatico. Observe sinais emocionais — frustracao, entusiasmo, ceticismo, urgencia — "
                    "e como eles influenciam decisoes. Mapeie preferencias operacionais — horarios de trabalho, "
                    "ferramentas favoritas, aversoes recorrentes, tolerancia a riscos. Infira prioridades implicitas "
                    "pelo que o dono repete, ignora, cobra com mais frequencia ou trata com mais cuidado."
                    if not is_first_analysis
                    else ""
                )
                + (
                    "\n\nCamadas de profundidade esperadas: "
                    "1) Camada factual — o que aconteceu, com quem, quando, qual o resultado visivel. "
                    "2) Camada comportamental — como o dono agiu, qual estrategia de comunicacao usou, como lidou com obstaculos. "
                    "3) Camada emocional — que emocoes transparecem (frustracao, orgulho, ansiedade, satisfacao) e como elas moldaram a acao. "
                    "4) Camada relacional — qual a natureza real de cada vinculo (confianca, dependencia, admiracao, tenso) e como evoluiu. "
                    "5) Camada estratégica — o que o dono realmente prioriza (vs o que diz que prioriza), quais projetos avancam vs estagnam, "
                    "qual e o padrao de decisao quando conflitam."
                    if not is_first_analysis
                    else (
                        "\n\nCamadas esperadas para a primeira analise: "
                        "1) Quem e o dono — responsabilidades, contexto de vida, papeis. "
                        "2) Com quem se relaciona — contatos mais ativos, natureza dos vinculos. "
                        "3) O que faz — projetos visiveis, rotinas, ferramentas. "
                        "4) Como age e decide — estilo de comunicacao, padrao sob pressao. "
                        "5) Lacunas — o que ainda nao da para saber com confianca e precisa de mais conversa."
                    )
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
        planning_model = self.settings.deepseek_memory_model
        output_reserve_tokens = self._analysis_max_output_tokens(intent=intent)
        if self._is_reasoning_model(planning_model):
            return DeepSeekPlanningProfile(
                model_name=planning_model,
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
            model_name=planning_model,
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
- Observe como o dono se comunica com cada contato — formalidade, carinho, cobrancas, paciencia — e registre isso em relationship_summary.
- Detecte emocoes implícitas nas mensagens do dono e como elas moldam decisoes. Frustracao com burocracia, entusiasmo com ideias novas, impaciencia com atrasos — tudo isso informa como um assistente deve responder no futuro.
- Note padroes de repeticao: o que o dono cobra, o que esquece, o que delega, o que faz sozinho. Isso revela prioridades reais vs declaradas.
- Identifique assuntos ou contatos que o dono evita, adia ou menciona de forma evasiva — isso e tao informativo quanto o que ele aborda diretamente.
- Diferencie entre "o dono disse X uma vez" e "o dono consistentemente age como se X fosse verdade". Prefira padroes consistentes nas listas de sinais.
- Se o dono demonstra mudanca de comportamento ou prioridade entre esta janela e as anteriores, destaque isso em key_learnings.
- Detecte contradicoes explicitas: o dono afirmou algo e depois agiu de forma oposta? Isso nao e erro — e sinal de complexidade humana. Registre em key_learnings com contexto: "diz X mas na pratica prioriza Y".
- Avalie confianca de cada sinal: alta (aparece 3+ vezes ou em 2+ contextos diferentes), media (aparece 2 vezes ou com evidencia forte), baixa (aparece 1 vez mas e revelador). Sinais de confianca baixa vao em listas como hipotese, nao no resumo.
- Observe o arco emocional da janela: o dono comecou frustrado e terminou satisfeito? Ou o inverso? Isso importa tanto quanto o conteudo factual.
- Mapeie tomadores de decisao: quando uma escolha depende de alguem externo, quem e? O dono delega, decide sozinho, ou precisa de validacao? Isso define como um assistente deve se posicionar.
- Em active_projects, detecte sinais de ciclo de vida: inicio (exploracao, duvidas), meio (execucao, entregas), fim (conclusao, abandono, pivot). Regresse o status acorde.
- Para cada contato, va alem do superficial: qual e o nivel de confianca do dono nesse contato? O dono busca conselho, da ordens, pede favor, ou divide responsabilidades?
- Se a mesma pessoa aparece em multiplas conversas com tom diferente, isso revela nuance — registre em relationship_summary.
- Em key_learnings, priorize: (1) mudancas de comportamento/prioridade, (2) padroes que se repetem em 2+ conversas, (3) descobertas sobre como o dono opera. Evite listar fatos isolados.
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
- Faca cross-validacao entre snapshots: o que aparece consistente em 2+ analises e sinal forte — o que aparece em apenas 1 pode ser ruido ou contexto momentaneo.
- Padroes recorrentes merecem mais peso no resumo final; sinais isolados merecem ceticismo ou mencao como hipotese.
- Se um projeto sumiu de snapshots recentes, considere que pode estar concluido ou abandonado — atualize o status acorde.
- Se o dono mudou de comportamento entre snapshots (nova rotina, prioridade diferente, contato mais frequente com alguem), destaque isso.
- Nao inclua markdown fences.
- Detecte contradicoes entre snapshots anteriores: se um snapshot diz X e outro diz Y, resolva explicitando a tensao ("em alguns momentos X, mas a tendencia recente sugere Y").
- Sinais com decaimento: o que era relevante 3 snapshots atras mas nao aparece mais? Remova ou enfraqueça progressivamente. Memoria precisa respirar.
- Sinais com aceleracao: o que aparece pela primeira vez mas com alta intensidade ou frequencia? Merece atencao especial mesmo sendo novo.
- Avalie a qualidade da memoria atual: se ha muitas lacunas ainda nao resolvidas, mantenha open_questions no resumo em vez de preencher com suposicoes.
- Projetos devem ter lifecycle real: se o nome e o mesmo mas o contexto mudou completamente, atualize summary e status — nao mantenha o que nao faz mais sentido.
- No resumo final, o assistente do futuro deve conseguir responder: (1) quem e o dono, (2) no que ele esta focado AGORA, (3) como ele toma decisoes, (4) o que ele precisa que o assistente saiba antes de responder.
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
- Detecte padroes entre parciais: o que o dono disse no inicio da janela mudou no final? Isso e uma evolucao, nao uma contradicao — registre em key_learnings.
- Se um tema aparece em 3+ parciais com intensidade, e um pilar da vida atual do dono — merece peso no resumo.
- Se um contato aparece em multiplas parciais com tom consistente, o vinculo e duravel. Se o tom varia, explique a nuance em relationship_summary.
- Resolva conflitos explicitos: se uma parcial diz "projeto X ativo" e outra sugere abandono, avalie qual tem evidencia mais recente e decida explicitamente no status.
- A qualidade final da memoria deve ser maior que a soma das parciais individuais — voce esta vendo o quadro completo que nenhuma parcial viu isoladamente.
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

    def _build_project_edit_prompt(
        self,
        *,
        current_life_summary: str,
        current_project_context: str,
        target_project_block: str,
        instruction: str,
    ) -> str:
        return f"""
Edite apenas o projeto alvo abaixo com base na instrucao do usuario.

Resumo atual da vida do dono:
{current_life_summary.strip() or "(memoria consolidada ainda vazia)"}

Panorama atual dos projetos:
{current_project_context.strip() or "(nenhum projeto salvo ainda)"}

Projeto alvo:
{target_project_block.strip() or "(projeto alvo ausente)"}

Instrucao do usuario:
{instruction.strip()}

Retorne um JSON com exatamente este formato:
{{
  "project": {{
    "name": "string",
    "summary": "string",
    "status": "string",
    "what_is_being_built": "string",
    "built_for": "string",
    "next_steps": ["string"],
    "evidence": ["string"]
  }},
  "assistant_message": "string"
}}

Regras:
- Edite apenas este projeto, sem criar outros.
- Mantenha o resultado coerente com o estado atual do projeto e com a instrucao dada.
- Se a instrucao pedir limpeza, remova ruido, duplicatas e itens vagos.
- Em next_steps e evidence, prefira listas curtas, concretas e sem repeticao.
- Nao invente cliente, escopo ou prova sem sustentacao no projeto atual ou na instrucao do usuario.
- assistant_message deve resumir o que foi alterado em linguagem natural curta.
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
        model_name: str | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "model": (model_name or self.settings.deepseek_model).strip() or self.settings.deepseek_model,
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
        if not self._is_reasoning_model(str(payload.get("model") or "")):
            payload["temperature"] = 0.2
        return payload

    def _build_text_completion_payload(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        max_tokens: int,
        interaction_mode: str | None = None,
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
            payload["temperature"] = self._reply_temperature(interaction_mode)
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
        model_name = str(payload.get("model") or self.settings.deepseek_model)
        logger.info("deepseek_operation_start operation=%s model=%s", operation, model_name)
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
                    "deepseek_operation_invalid_response operation=%s attempt=%s model=%s detail=%s raw_preview=%s",
                    operation,
                    attempt,
                    model_name,
                    str(exc),
                    self._preview_text(content if "content" in locals() else json.dumps(data, ensure_ascii=True)),
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
        model_name = str(payload.get("model") or self.settings.deepseek_model)
        logger.info("deepseek_operation_start operation=%s model=%s", operation, model_name)
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
                    "deepseek_operation_invalid_response operation=%s attempt=%s model=%s detail=%s raw_preview=%s",
                    operation,
                    attempt,
                    model_name,
                    str(exc),
                    self._preview_text(content if "content" in locals() else json.dumps(data, ensure_ascii=True)),
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
        model_name = str(payload.get("model") or self.settings.deepseek_model)
        logger.info(
            "deepseek_request_start operation=%s attempt=%s model=%s timeout_seconds=%s system_prompt_chars=%s user_prompt_chars=%s",
            operation,
            attempt,
            model_name,
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

    def _validate_project_edit_result(self, parsed: DeepSeekProjectEditResult) -> None:
        if not parsed.project.name.strip():
            raise DeepSeekError("DeepSeek retornou um projeto editado sem nome.")
        if not parsed.project.summary.strip():
            raise DeepSeekError("DeepSeek retornou um projeto editado sem resumo.")
        parsed.assistant_message = parsed.assistant_message.strip()

    def _validate_contact_refinement_result(self, parsed: DeepSeekContactMemoryRefinementResult) -> None:
        for person in parsed.contact_memories:
            if not person.person_key.strip():
                raise DeepSeekError("DeepSeek retornou um contato refinado sem person_key.")
            if not person.profile_summary.strip():
                raise DeepSeekError("DeepSeek retornou um contato refinado sem profile_summary.")
            person.relationship_type = self._normalize_relationship_type(person.relationship_type)

    def _validate_agenda_extraction_result(self, parsed: DeepSeekAgendaExtractionResult) -> None:
        parsed.action = parsed.action.strip().lower()
        if parsed.action not in {"create", "reschedule", "cancel", "update_reminder", "none", "clarify"}:
            parsed.action = "none"
        parsed.titulo = parsed.titulo.strip()
        parsed.intencao = parsed.intencao.strip().lower()
        if parsed.intencao not in {"", "confirmado", "tentativo", "incerto"}:
            parsed.intencao = "incerto"
        if parsed.data_inicio is not None:
            parsed.data_inicio = str(parsed.data_inicio).strip() or None
        if parsed.data_fim is not None:
            parsed.data_fim = str(parsed.data_fim).strip() or None
        parsed.missing_fields = [str(item).strip().lower() for item in parsed.missing_fields if str(item).strip()]

    def _validate_agenda_conflict_resolution_result(self, parsed: DeepSeekAgendaConflictResolutionResult) -> None:
        parsed.decision = parsed.decision.strip().lower()
        if parsed.decision not in {
            "keep_new_cancel_existing",
            "keep_existing_cancel_new",
            "keep_both",
            "clarify",
        }:
            parsed.decision = "clarify"
        parsed.explanation = parsed.explanation.strip()

    def _validate_assistant_search_plan(self, parsed: DeepSeekAssistantSearchPlan) -> None:
        parsed.people_limit = max(0, min(6, parsed.people_limit))
        parsed.projects_limit = max(0, min(6, parsed.projects_limit))
        parsed.snapshots_limit = max(0, min(6, parsed.snapshots_limit))
        parsed.people_queries = parsed.people_queries[:3]
        parsed.project_queries = parsed.project_queries[:3]
        parsed.snapshot_queries = parsed.snapshot_queries[:3]

    def _validate_agent_memory_decision(self, parsed: DeepSeekAgentMemoryDecision) -> None:
        parsed.profile_summary = parsed.profile_summary.strip()
        parsed.preferred_tone = parsed.preferred_tone.strip()
        parsed.explanation = parsed.explanation.strip()
        parsed.implied_urgency = parsed.implied_urgency.strip()
        parsed.writing_style_hints = parsed.writing_style_hints.strip()
        parsed.preferences = parsed.preferences[:12]
        parsed.objectives = parsed.objectives[:12]
        parsed.durable_facts = parsed.durable_facts[:12]
        parsed.constraints = parsed.constraints[:12]
        parsed.recurring_instructions = parsed.recurring_instructions[:12]
        parsed.mood_signals = parsed.mood_signals[:8]
        parsed.mentioned_relationships = parsed.mentioned_relationships[:8]
        parsed.implied_tasks = parsed.implied_tasks[:8]

    def _validate_cli_plan(self, parsed: DeepSeekCliPlan) -> None:
        parsed.summary = parsed.summary.strip()
        parsed.actions = parsed.actions[:6]
        normalized_actions: list[DeepSeekCliAction] = []
        for action in parsed.actions:
            tool = action.tool.strip().lower()
            if tool not in {"pwd", "ls", "cd", "cat", "write", "exec", "find", "head", "tail", "mkdir", "touch", "cp", "mv", "rm", "final"}:
                tool = "exec"
            normalized_actions.append(
                DeepSeekCliAction(
                    tool=tool,
                    path=action.path.strip(),
                    command=action.command.strip(),
                    content=action.content,
                    mode="append" if action.mode == "append" else "overwrite",
                    explanation=action.explanation.strip(),
                )
            )
        parsed.actions = normalized_actions

    def _is_reasoning_model(self, model_name: str | None = None) -> bool:
        resolved_model = (model_name or self.settings.deepseek_model).strip().lower()
        return "reasoner" in resolved_model

    def _analysis_max_output_tokens(self, *, intent: str = "improve_memory") -> int:
        if self._is_reasoning_model(self.settings.deepseek_memory_model):
            if intent == "first_analysis":
                return 6400
            return 4200
        return 3400

    def _refinement_max_output_tokens(self) -> int:
        return 3200 if self._is_reasoning_model() else 1500

    def _adaptive_max_tokens(
        self,
        prompt_text: str,
        *,
        ceiling_reasoning: int,
        ceiling_standard: int,
        floor_reasoning: int,
        floor_standard: int,
        chars_per_step: int = 900,
        step_tokens: int = 80,
        max_steps: int = 4,
        model_name: str | None = None,
    ) -> int:
        normalized_prompt = " ".join(str(prompt_text or "").split()).strip()
        prompt_chars = len(normalized_prompt)
        steps = min(max(0, max_steps), max(0, prompt_chars) // max(1, chars_per_step))
        if self._is_reasoning_model(model_name):
            return min(ceiling_reasoning, floor_reasoning + (steps * step_tokens))
        standard_step_tokens = max(12, step_tokens // 2)
        return min(ceiling_standard, floor_standard + (steps * standard_step_tokens))

    def _reply_temperature(self, interaction_mode: str | None = None) -> float:
        mode = (interaction_mode or "contextual").lower()
        if mode == "light_touch":
            return 0.25
        if mode == "agenda":
            return 0.15
        return 0.5

    def _preview_text(self, value: str, *, max_chars: int = 900) -> str:
        normalized = " ".join(str(value or "").split()).strip()
        if len(normalized) <= max_chars:
            return normalized
        return normalized[: max_chars - 3] + "..."

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

    def _parse_project_edit_result(self, content: str) -> DeepSeekProjectEditResult:
        raw = self._parse_json_dict(
            content,
            error_message="DeepSeek retornou JSON invalido na edicao assistida de projeto.",
            shape_error_message="DeepSeek retornou um payload inesperado na edicao assistida de projeto.",
        )
        projects = self._as_projects([raw.get("project")])
        if not projects:
            raise DeepSeekError("DeepSeek nao devolveu um projeto valido na edicao assistida.")
        return DeepSeekProjectEditResult(
            project=projects[0],
            assistant_message=self._as_text(raw.get("assistant_message")),
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

    def _parse_agenda_extraction_result(self, content: str) -> DeepSeekAgendaExtractionResult:
        raw = self._parse_json_dict(
            content,
            error_message="DeepSeek retornou JSON invalido na extracao de agenda.",
            shape_error_message="DeepSeek retornou um payload inesperado na extracao de agenda.",
        )
        return DeepSeekAgendaExtractionResult(
            action=self._as_text(raw.get("action")),
            has_schedule_signal=self._as_bool(raw.get("has_schedule_signal")),
            is_explicit_user_intent=self._as_bool(raw.get("is_explicit_user_intent")),
            titulo=self._as_text(raw.get("titulo")),
            data_inicio=self._as_optional_text(raw.get("data_inicio")),
            data_fim=self._as_optional_text(raw.get("data_fim")),
            intencao=self._as_text(raw.get("intencao")),
            confidence=self._as_confidence(raw.get("confidence")),
            missing_fields=self._as_string_list(raw.get("missing_fields")),
        )

    def _parse_agenda_conflict_resolution_result(self, content: str) -> DeepSeekAgendaConflictResolutionResult:
        raw = self._parse_json_dict(
            content,
            error_message="DeepSeek retornou JSON invalido na resolucao de conflito de agenda.",
            shape_error_message="DeepSeek retornou um payload inesperado na resolucao de conflito de agenda.",
        )
        return DeepSeekAgendaConflictResolutionResult(
            decision=self._as_text(raw.get("decision")),
            explanation=self._as_text(raw.get("explanation")),
            confidence=self._as_confidence(raw.get("confidence")),
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
        project_queries = self._as_string_list(raw.get("project_queries"))[:3]
        snapshot_queries = self._as_string_list(raw.get("snapshot_queries"))[:3]

        return DeepSeekAssistantSearchPlan(
            needs_retrieval=bool(raw.get("needs_retrieval")),
            people_queries=people_queries,
            project_queries=project_queries,
            snapshot_queries=snapshot_queries,
            people_limit=_limit(raw.get("people_limit"), 2 if people_queries else 0),
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
            mood_signals=self._as_string_list(raw.get("mood_signals")),
            implied_urgency=self._as_text(raw.get("implied_urgency")),
            mentioned_relationships=self._as_string_list(raw.get("mentioned_relationships")),
            implied_tasks=self._as_string_list(raw.get("implied_tasks")),
            writing_style_hints=self._as_text(raw.get("writing_style_hints")),
            explanation=self._as_text(raw.get("explanation")),
        )

    def _parse_cli_plan(self, content: str) -> DeepSeekCliPlan:
        raw = self._parse_json_dict(
            content,
            error_message="DeepSeek retornou JSON invalido para o plano da CLI.",
            shape_error_message="DeepSeek retornou um payload inesperado para o plano da CLI.",
        )
        raw_actions = raw.get("actions")
        actions: list[DeepSeekCliAction] = []
        if isinstance(raw_actions, list):
            for item in raw_actions:
                if not isinstance(item, dict):
                    continue
                actions.append(
                    DeepSeekCliAction(
                        tool=self._as_text(item.get("tool")) or "exec",
                        path=self._as_text(item.get("path")),
                        command=self._as_text(item.get("command")),
                        content=self._as_text(item.get("content")),
                        mode="append" if self._as_text(item.get("mode")).strip().lower() == "append" else "overwrite",
                        explanation=self._as_text(item.get("explanation")),
                    )
                )
        return DeepSeekCliPlan(
            summary=self._as_text(raw.get("summary")),
            explicit_sensitive_request=bool(raw.get("explicit_sensitive_request")),
            actions=actions,
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
- Responda primeiro ao que o dono acabou de dizer, de forma natural e direta.
- Antes de responder literalmente, infera a intencao implicita: o que o dono realmente quer saber ou resolver?
- Use o resumo consolidado para adaptar tom, prioridade e praticidade da resposta.
- Priorize contexto pessoal e de trabalho realmente presente no material acima, mas so mencione isso quando for relevante.
- Quando fizer sentido, conecte informacoes do contexto de forma natural, como alguem que conhece bem a pessoa.
- Se a pergunta tocar em um projeto conhecido, conecte a resposta ao estado atual desse projeto.
- Se o dono estiver pedindo ajuda operacional, priorize a resposta mais acionavel e mais curta primeiro.
- Se houver incerteza ou memoria incompleta, assuma isso explicitamente.
- Em cumprimentos, mensagens curtas ou aberturas vagas, responda em 1 ou 2 frases curtas e pergunte como ajudar.
- Se o pedido envolver promessa, compromisso, prazo, resposta em nome do dono ou dado sensivel, confirme antes de tratar isso como decidido.
- Nao enumere fatos antigos sem convite explicito.
- Evite hiperfoco em um unico tema so porque ele apareceu na memoria.
- Seja conciso mas completo — entregue o que e necessario sem enrolacao.
- NUNCA mencione palavras como "memoria", "banco de dados", "contexto", "IA", "modelo", "sistema", "prompt" ou qualquer referencia a seus bastidores tecnicos.
- Quando o dono parecer sob pressao ou frustrado, priorize empatia e solucao rapida antes de detalhes.
- Quando o dono demonstrar entusiasmo ou progresso, reconheça brevemente — isso fortalece a relacao.
- Se houver algo pendente relevante e nao resolvido que se conecta ao assunto atual, mencione de forma sutil (1 frase).
- Proatividade comeco: se voce tiver uma sugestao util, coloque-a no final como opcao, nao como imposicao.
- Se o dono estiver pedindo algo que conflita com algo que ele mesmo disse antes, aponte de forma gentil: "nao tinha ficado X antes? quer que eu ajuste?".
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
        normalized_content = self._normalize_json_content(content)
        raw = self._load_json_object(normalized_content)
        if raw is None:
            repaired_content = self._repair_json_like_content(normalized_content)
            raw = self._load_json_object(repaired_content)
        if raw is None:
            raw = self._parse_python_like_mapping(normalized_content)
        if raw is None:
            raise DeepSeekError(error_message)

        if not isinstance(raw, dict):
            raise DeepSeekError(shape_error_message)
        return raw

    def _normalize_json_content(self, content: str) -> str:
        normalized_content = str(content or "").strip()
        if not normalized_content:
            return normalized_content

        fence_match = re.search(r"```(?:json)?\s*(.*?)```", normalized_content, flags=re.IGNORECASE | re.DOTALL)
        if fence_match:
            normalized_content = fence_match.group(1).strip()

        first_brace = normalized_content.find("{")
        last_brace = normalized_content.rfind("}")
        if first_brace != -1 and last_brace != -1 and last_brace > first_brace:
            normalized_content = normalized_content[first_brace : last_brace + 1]

        normalized_content = re.sub(r",(\s*[}\]])", r"\1", normalized_content)
        return normalized_content.strip()

    def _load_json_object(self, content: str) -> Any | None:
        if not content:
            return None
        try:
            raw = json.loads(content)
        except json.JSONDecodeError:
            return None
        if isinstance(raw, str):
            nested = self._normalize_json_content(raw)
            if nested and nested != content:
                return self._load_json_object(nested)
        return raw

    def _repair_json_like_content(self, content: str) -> str:
        repaired = str(content or "").strip()
        if not repaired:
            return repaired

        replacements = {
            "\u201c": '"',
            "\u201d": '"',
            "\u2018": "'",
            "\u2019": "'",
            "\u00a0": " ",
        }
        for source, target in replacements.items():
            repaired = repaired.replace(source, target)

        repaired = re.sub(r"^\s*//.*$", "", repaired, flags=re.MULTILINE)
        repaired = re.sub(r"/\*.*?\*/", "", repaired, flags=re.DOTALL)
        repaired = re.sub(r",(\s*[}\]])", r"\1", repaired)
        return repaired.strip()

    def _parse_python_like_mapping(self, content: str) -> dict[str, Any] | None:
        candidate = self._repair_json_like_content(content)
        if not candidate:
            return None
        candidate = re.sub(r"\btrue\b", "True", candidate, flags=re.IGNORECASE)
        candidate = re.sub(r"\bfalse\b", "False", candidate, flags=re.IGNORECASE)
        candidate = re.sub(r"\bnull\b", "None", candidate, flags=re.IGNORECASE)
        try:
            raw = ast.literal_eval(candidate)
        except (SyntaxError, ValueError):
            return None
        return raw if isinstance(raw, dict) else None

    def _as_text(self, value: Any) -> str:
        if value is None:
            return ""
        if isinstance(value, str):
            return value.strip()
        return str(value).strip()

    def _as_optional_text(self, value: Any) -> str | None:
        text = self._as_text(value)
        return text or None

    def _as_int(self, value: Any) -> int:
        try:
            return int(value)
        except (TypeError, ValueError):
            return 0

    def _as_confidence(self, value: Any) -> int:
        return max(0, min(100, self._as_int(value)))

    def _as_bool(self, value: Any) -> bool:
        if isinstance(value, bool):
            return value
        if value is None:
            return False
        if isinstance(value, str):
            return value.strip().lower() in {"true", "1", "yes", "sim"}
        return bool(value)

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


    def _normalize_importance_category(self, value: str) -> str:
        normalized = value.strip().lower()
        if normalized in {"credential", "access", "project", "money", "client", "deadline", "document", "risk", "other"}:
            return normalized
        return "other"
