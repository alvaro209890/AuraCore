from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
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


ParsedResultT = TypeVar("ParsedResultT")


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
        intent: str = "improve_memory",
        window_hours: int,
        window_start: datetime,
        window_end: datetime,
        source_message_count: int,
    ) -> DeepSeekMemoryResult:
        prompt_preview = self.build_analysis_prompt_preview(
            transcript=transcript,
            conversation_context=conversation_context,
            people_memory_context=people_memory_context,
            current_life_summary=current_life_summary,
            prior_analyses_context=prior_analyses_context,
            project_context=project_context,
            chat_context=chat_context,
            window_hours=window_hours,
            window_start=window_start,
            window_end=window_end,
            source_message_count=source_message_count,
        )
        payload = self._build_completion_payload(
            system_prompt=prompt_preview.system_prompt,
            user_prompt=prompt_preview.user_prompt,
            max_tokens=self._analysis_max_output_tokens(intent=intent),
        )

        return await self._request_parsed_completion(
            payload=payload,
            parser=self._parse_result,
            validator=self._validate_analysis_result,
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
        window_hours: int,
        window_start: datetime,
        window_end: datetime,
        source_message_count: int,
    ) -> DeepSeekPromptPreview:
        return DeepSeekPromptPreview(
            system_prompt=(
                "Voce e o analista principal de memoria do AuraCore. Sua funcao e transformar conversas "
                "privadas em portugues do Brasil em uma memoria altamente util sobre o dono do numero. "
                "Retorne apenas JSON valido e estritamente aderente ao schema pedido. Nunca invente fatos. "
                "Priorize sinais sobre identidade, forma de agir, criterio de decisao, ritmo, projetos, "
                "responsabilidades e tensoes reais do dono. Quando algo for incerto, trate como sinal ou "
                "hipotese nas listas, sem afirmar como certeza no resumo consolidado."
            ),
            user_prompt=self._build_prompt(
                transcript=transcript,
                conversation_context=conversation_context,
                people_memory_context=people_memory_context,
                current_life_summary=current_life_summary,
                prior_analyses_context=prior_analyses_context,
                project_context=project_context,
                chat_context=chat_context,
                window_hours=window_hours,
                window_start=window_start,
                window_end=window_end,
                source_message_count=source_message_count,
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
        window_hours: int,
        window_start: datetime,
        window_end: datetime,
        source_message_count: int,
    ) -> str:
        previous_summary = current_life_summary.strip() or "(memoria consolidada ainda vazia)"
        previous_analyses = prior_analyses_context.strip() or "(nenhuma analise anterior relevante)"
        recent_chat_context = chat_context.strip() or "(nenhuma conversa relevante com a IA salva ainda)"
        return f"""
Analise a janela abaixo de conversas diretas e atualize a memoria do usuario.

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
- Leia primeiro o bloco de contexto por conversa para entender quem e cada contato, o peso de cada conversa e a relacao mais provavel com o dono.
- Leia tambem as memorias ja consolidadas por pessoa antes de atualizar os contatos desta janela.
- Diferencie sinais sobre o dono dos fatos que pertencem ao contato; nao transforme caracteristicas do contato em caracteristicas do dono.
- Use a direcao das mensagens para separar o que o dono afirma, pede, decide ou promete do que esta sendo dito pelos contatos.
- Procure entender como o dono do numero age, fala, decide, trabalha, se relaciona e organiza a rotina.
- Priorize sinais comportamentais e estruturais do dono do numero, nao apenas um inventario de contatos.
- Ao citar pessoas e relacoes, infira quem parece ser cada conversa no contexto da vida do dono, sem inventar vinculos que nao tenham apoio no historico.
- Preencha active_projects apenas com projetos, trabalhos, produtos, operacoes ou frentes reais que parecam recorrentes ou importantes para o dono.
- Em cada item de active_projects, explicite o que esta sendo desenvolvido e para quem a entrega, sistema ou servico parece ser direcionado.
- Em active_projects, use no maximo 6 itens e descarte assuntos soltos sem continuidade.
- Mantenha updated_life_summary factual, claro, conciso e util para um assistente pessoal futuro. Dê mais peso ao que aparece repetido, ao que tem impacto operacional e ao que altera o comportamento do dono.
- Use os campos de lista para aprendizados concretos, padroes de comportamento e sinais incertos.
- Se a evidencia for fraca, trate como hipotese e nao como fato consolidado.
- Preencha contact_memories apenas com pessoas que realmente aparecem nesta janela.
- Em cada item de contact_memories, person_key deve copiar exatamente um person_key presente no bloco de contexto por conversa.
- Em contact_memories, profile_summary deve resumir quem e essa pessoa no contexto do dono; relationship_summary deve resumir a dinamica atual entre dono e contato.
- Em contact_memories, use as memorias anteriores por pessoa para atualizar de forma cumulativa e sem repetir o que ja existe.
- Em contact_memories, mantenha no maximo 6 fatos, 5 pendencias e 5 topicos por pessoa.
- Nao mencione que voce e uma IA.
- Nao inclua markdown fences.
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
Refine a memoria consolidada abaixo usando apenas o que ja foi salvo no Supabase.

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

    async def _request_parsed_completion(
        self,
        *,
        payload: dict[str, Any],
        parser: Callable[[str], ParsedResultT],
        validator: Callable[[ParsedResultT], None],
    ) -> ParsedResultT:
        self._ensure_configured()
        last_error: DeepSeekError | None = None
        for _attempt in range(2):
            data = await self._post_completion(payload)
            try:
                content = self._extract_content(data)
                parsed = parser(content)
                validator(parsed)
                return parsed
            except DeepSeekError as exc:
                last_error = exc
        raise last_error or DeepSeekError("DeepSeek returned an invalid structured response.")

    async def _post_completion(self, payload: dict[str, Any]) -> dict[str, Any]:
        self._ensure_configured()
        headers = {
            "Authorization": f"Bearer {self.settings.deepseek_api_key}",
            "Content-Type": "application/json",
        }

        async with httpx.AsyncClient(
            base_url=self.settings.normalized_deepseek_api_base_url,
            timeout=self.settings.deepseek_timeout_seconds,
        ) as client:
            response = await client.post("/chat/completions", headers=headers, json=payload)

        if response.status_code >= 400:
            detail = response.text.strip() or "Unexpected DeepSeek error."
            raise DeepSeekError(f"DeepSeek request failed ({response.status_code}): {detail}")

        return response.json()

    def _ensure_configured(self) -> None:
        if not self.settings.deepseek_api_key:
            raise DeepSeekError("DEEPSEEK_API_KEY nao configurada na Render.")

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
                relationship_summary=self._as_text(item.get("relationship_summary")),
                salient_facts=self._as_string_list(item.get("salient_facts"))[:6],
                open_loops=self._as_string_list(item.get("open_loops"))[:5],
                recent_topics=self._as_string_list(item.get("recent_topics"))[:5],
            )
            if memory.profile_summary:
                items.append(memory)
                seen_keys.add(person_key)
        return items[:24]

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
