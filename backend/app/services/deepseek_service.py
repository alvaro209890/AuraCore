from __future__ import annotations

import json
from datetime import datetime
from typing import Any

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


class DeepSeekMemoryResult(BaseModel):
    updated_life_summary: str
    window_summary: str
    key_learnings: list[str] = Field(default_factory=list)
    people_and_relationships: list[str] = Field(default_factory=list)
    routine_signals: list[str] = Field(default_factory=list)
    preferences: list[str] = Field(default_factory=list)
    open_questions: list[str] = Field(default_factory=list)
    active_projects: list[DeepSeekProjectMemory] = Field(default_factory=list)


class DeepSeekMemoryRefinementResult(BaseModel):
    updated_life_summary: str
    active_projects: list[DeepSeekProjectMemory] = Field(default_factory=list)


class DeepSeekService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    async def analyze_memory(
        self,
        *,
        transcript: str,
        current_life_summary: str,
        prior_analyses_context: str,
        project_context: str,
        chat_context: str,
        window_hours: int,
        window_start: datetime,
        window_end: datetime,
        source_message_count: int,
    ) -> DeepSeekMemoryResult:
        headers = {
            "Authorization": f"Bearer {self.settings.deepseek_api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": self.settings.deepseek_model,
            "temperature": 0.2,
            "response_format": {"type": "json_object"},
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "Voce e o analista principal de memoria do AuraCore. Sua funcao e transformar conversas "
                        "privadas em portugues do Brasil em uma memoria altamente util sobre o dono do numero. "
                        "Responda sempre em portugues do Brasil e retorne apenas JSON valido. Nunca invente fatos. "
                        "Priorize sinais sobre identidade, forma de agir, criterio de decisao, ritmo, projetos, "
                        "responsabilidades e tensoes reais do dono. Quando algo for incerto, trate como sinal ou "
                        "hipotese nas listas, sem afirmar como certeza no resumo consolidado."
                    ),
                },
                {
                    "role": "user",
                    "content": self._build_prompt(
                        transcript=transcript,
                        current_life_summary=current_life_summary,
                        prior_analyses_context=prior_analyses_context,
                        project_context=project_context,
                        chat_context=chat_context,
                        window_hours=window_hours,
                        window_start=window_start,
                        window_end=window_end,
                        source_message_count=source_message_count,
                    ),
                },
            ],
        }

        async with httpx.AsyncClient(
            base_url=self.settings.normalized_deepseek_api_base_url,
            timeout=self.settings.deepseek_timeout_seconds,
        ) as client:
            response = await client.post("/chat/completions", headers=headers, json=payload)

        if response.status_code >= 400:
            detail = response.text.strip() or "Unexpected DeepSeek error."
            raise DeepSeekError(f"DeepSeek request failed ({response.status_code}): {detail}")

        data = response.json()
        content = self._extract_content(data)
        parsed = self._parse_result(content)
        if not parsed.updated_life_summary.strip():
            raise DeepSeekError("DeepSeek returned an empty consolidated memory.")
        if not parsed.window_summary.strip():
            raise DeepSeekError("DeepSeek returned an empty window summary.")

        return parsed

    async def refine_saved_memory(
        self,
        *,
        current_life_summary: str,
        prior_analyses_context: str,
        project_context: str,
        chat_context: str,
    ) -> DeepSeekMemoryRefinementResult:
        headers = {
            "Authorization": f"Bearer {self.settings.deepseek_api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": self.settings.deepseek_model,
            "temperature": 0.2,
            "response_format": {"type": "json_object"},
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "Voce revisa memorias privadas em portugues para melhorar a qualidade do perfil salvo do "
                        "dono do numero. Responda sempre em portugues do Brasil e retorne apenas JSON valido. "
                        "Nunca invente fatos. Remova exageros, refine hipoteses fracas, fortaleça padroes "
                        "recorrentes e deixe a memoria mais util para um assistente pessoal futuro."
                    ),
                },
                {
                    "role": "user",
                    "content": self._build_refinement_prompt(
                        current_life_summary=current_life_summary,
                        prior_analyses_context=prior_analyses_context,
                        project_context=project_context,
                        chat_context=chat_context,
                    ),
                },
            ],
        }

        async with httpx.AsyncClient(
            base_url=self.settings.normalized_deepseek_api_base_url,
            timeout=self.settings.deepseek_timeout_seconds,
        ) as client:
            response = await client.post("/chat/completions", headers=headers, json=payload)

        if response.status_code >= 400:
            detail = response.text.strip() or "Unexpected DeepSeek error."
            raise DeepSeekError(f"DeepSeek request failed ({response.status_code}): {detail}")

        data = response.json()
        content = self._extract_content(data)
        parsed = self._parse_refinement_result(content)
        if not parsed.updated_life_summary.strip():
            raise DeepSeekError("DeepSeek retornou uma memoria refinada vazia.")
        return parsed

    def _build_prompt(
        self,
        *,
        transcript: str,
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

Regras:
- updated_life_summary deve ser cumulativo e integrar o resumo atual com esta janela.
- Em updated_life_summary, descreva principalmente: quem o dono parece ser, como trabalha e decide, quais frentes estao mais vivas agora e quais tensoes ou prioridades estao guiando o momento.
- Use as analises anteriores como contexto, mas corrija ou refine o que parecer fraco, incompleto ou contraditorio.
- Use tambem os projetos ja salvos para manter continuidade entre leituras e evitar perder o fio de frentes recorrentes.
- Considere tambem o que o dono conversou com a IA no chat para entender melhor prioridades, projetos e como ele pensa.
- Procure entender como o dono do numero age, fala, decide, trabalha, se relaciona e organiza a rotina.
- Priorize sinais comportamentais e estruturais do dono do numero, nao apenas um inventario de contatos.
- Preencha active_projects apenas com projetos, trabalhos, produtos, operacoes ou frentes reais que parecam recorrentes ou importantes para o dono.
- Em cada item de active_projects, explicite o que esta sendo desenvolvido e para quem a entrega, sistema ou servico parece ser direcionado.
- Em active_projects, use no maximo 6 itens e descarte assuntos soltos sem continuidade.
- Mantenha updated_life_summary factual, claro, conciso e util para um assistente pessoal futuro. Dê mais peso ao que aparece repetido, ao que tem impacto operacional e ao que altera o comportamento do dono.
- Use os campos de lista para aprendizados concretos, padroes de comportamento e sinais incertos.
- Se a evidencia for fraca, trate como hipotese e nao como fato consolidado.
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

    def _parse_result(self, content: str) -> DeepSeekMemoryResult:
        normalized_content = content.strip()
        if normalized_content.startswith("```"):
            normalized_content = normalized_content.strip("`")
            normalized_content = normalized_content.replace("json", "", 1).strip()

        try:
            raw = json.loads(normalized_content)
        except json.JSONDecodeError as exc:
            raise DeepSeekError("DeepSeek returned invalid JSON output.") from exc

        if not isinstance(raw, dict):
            raise DeepSeekError("DeepSeek returned a JSON payload in an unexpected shape.")

        return DeepSeekMemoryResult(
            updated_life_summary=self._as_text(raw.get("updated_life_summary")),
            window_summary=self._as_text(raw.get("window_summary")),
            key_learnings=self._as_string_list(raw.get("key_learnings")),
            people_and_relationships=self._as_string_list(raw.get("people_and_relationships")),
            routine_signals=self._as_string_list(raw.get("routine_signals")),
            preferences=self._as_string_list(raw.get("preferences")),
            open_questions=self._as_string_list(raw.get("open_questions")),
            active_projects=self._as_projects(raw.get("active_projects")),
        )

    def _parse_refinement_result(self, content: str) -> DeepSeekMemoryRefinementResult:
        normalized_content = content.strip()
        if normalized_content.startswith("```"):
            normalized_content = normalized_content.strip("`")
            normalized_content = normalized_content.replace("json", "", 1).strip()

        try:
            raw = json.loads(normalized_content)
        except json.JSONDecodeError as exc:
            raise DeepSeekError("DeepSeek retornou JSON invalido no refinamento.") from exc

        if not isinstance(raw, dict):
            raise DeepSeekError("DeepSeek retornou um payload inesperado no refinamento.")

        return DeepSeekMemoryRefinementResult(
            updated_life_summary=self._as_text(raw.get("updated_life_summary")),
            active_projects=self._as_projects(raw.get("active_projects")),
        )

    def _as_text(self, value: Any) -> str:
        if value is None:
            return ""
        if isinstance(value, str):
            return value.strip()
        return str(value).strip()

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
