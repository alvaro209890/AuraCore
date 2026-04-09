from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

import httpx

from app.config import Settings


class GroqChatError(RuntimeError):
    """Raised when Groq chat completion fails or returns an invalid payload."""


@dataclass(slots=True)
class GroqPreviewDecision:
    score: int
    label: str
    should_analyze: bool
    summary: str


class GroqChatService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    async def generate_reply(
        self,
        *,
        user_message: str,
        current_life_summary: str,
        recent_snapshots_context: str,
        recent_projects_context: str,
        recent_chat_context: str,
        interaction_mode: str = "contextual",
    ) -> str:
        if not self.settings.groq_api_key:
            raise GroqChatError("GROQ_API_KEY nao configurada na Render.")

        headers = {
            "Authorization": f"Bearer {self.settings.groq_api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": self.settings.groq_model,
            "temperature": 0.35,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "Voce e o AuraCore, um segundo cerebro digital pessoal. Responda sempre em portugues do "
                        "Brasil. Sua funcao e ser extremamente util para o dono deste numero, usando o contexto "
                        "persistido sobre sua rotina, seus projetos, suas preferencias e sua forma de agir. "
                        "Se faltar contexto, diga isso com clareza em vez de inventar. Seja direto, pessoal e "
                        "pratico, sem soar generico. Responda como uma IA que ja conhece o dono, seus padroes de "
                        "decisao e suas frentes ativas, mas sem fingir certeza quando a memoria estiver incompleta. "
                        "Nao transforme cumprimentos simples em um relatorio sobre a vida do dono. "
                        "Nao abra a resposta listando fatos antigos, projetos, gastos ou historicos que nao foram pedidos. "
                        "Use a memoria como apoio silencioso: so traga lembrancas quando elas ajudarem diretamente a resposta atual."
                    ),
                },
                {
                    "role": "user",
                    "content": self._build_prompt(
                        user_message=user_message,
                        current_life_summary=current_life_summary,
                        recent_snapshots_context=recent_snapshots_context,
                        recent_projects_context=recent_projects_context,
                        recent_chat_context=recent_chat_context,
                        interaction_mode=interaction_mode,
                    ),
                },
            ],
        }

        async with httpx.AsyncClient(
            base_url=self.settings.normalized_groq_api_base_url,
            timeout=self.settings.groq_timeout_seconds,
        ) as client:
            response = await client.post("/chat/completions", headers=headers, json=payload)

        if response.status_code >= 400:
            detail = response.text.strip() or "Unexpected Groq error."
            raise GroqChatError(f"Groq request failed ({response.status_code}): {detail}")

        data = response.json()
        content = self._extract_content(data)
        if not content.strip():
            raise GroqChatError("Groq retornou uma resposta vazia.")
        return content.strip()

    async def classify_analysis_preview(
        self,
        *,
        target_message_count: int,
        max_lookback_hours: int,
        detail_mode: str,
        available_message_count: int,
        selected_message_count: int,
        new_message_count: int,
        replaced_message_count: int,
        estimated_total_tokens: int,
        stack_max_message_capacity: int,
        estimated_cost_total_ceiling_usd: float,
        fallback_score: int,
        fallback_label: str,
    ) -> GroqPreviewDecision:
        if not self.settings.groq_api_key:
            raise GroqChatError("GROQ_API_KEY nao configurada na Render.")

        headers = {
            "Authorization": f"Bearer {self.settings.groq_api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": self.settings.groq_model,
            "temperature": 0.1,
            "max_tokens": 120,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "Voce classifica se vale a pena rodar uma nova analise de memoria. "
                        "Responda somente em JSON valido com as chaves score, label, should_analyze e summary. "
                        "score deve ser um inteiro de 0 a 100. "
                        "label deve ser exatamente um destes valores: "
                        "Alta vantagem, Vale rodar, Pode esperar um pouco, Ganho baixo agora. "
                        "should_analyze deve ser boolean. "
                        "summary deve estar em portugues do Brasil, sem markdown, em no maximo duas frases curtas. "
                        "Use apenas os numeros recebidos. Nao invente contexto das mensagens."
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        f"Configuracao: alvo {target_message_count} mensagens, alcance {max_lookback_hours}h, modo {detail_mode}. "
                        f"Disponiveis: {available_message_count}. Selecionadas: {selected_message_count}. "
                        f"Novas desde a ultima analise: {new_message_count}. Substituidas pela retencao: {replaced_message_count}. "
                        f"Tokens estimados do DeepSeek: {estimated_total_tokens}. "
                        f"Teto real desta stack no perfil atual: {stack_max_message_capacity} mensagens. "
                        f"Custo estimado mais conservador desta leitura: ate US$ {estimated_cost_total_ceiling_usd:.4f}. "
                        "Regras de decisao: "
                        "score alto quando houver volume relevante de mensagens novas, substituicoes pela retencao, boa cobertura e custo aceitavel; "
                        "score baixo quando houver pouco material novo ou ganho fraco. "
                        f"Referencias heuristicas atuais: {fallback_score}/100 ({fallback_label}). "
                        "should_analyze deve ser true quando a sua propria classificacao justificar rodar agora."
                    ),
                },
            ],
        }

        async with httpx.AsyncClient(
            base_url=self.settings.normalized_groq_api_base_url,
            timeout=self.settings.groq_timeout_seconds,
        ) as client:
            response = await client.post("/chat/completions", headers=headers, json=payload)

        if response.status_code >= 400:
            detail = response.text.strip() or "Unexpected Groq error."
            raise GroqChatError(f"Groq request failed ({response.status_code}): {detail}")

        data = response.json()
        content = self._extract_content(data)
        if not content.strip():
            raise GroqChatError("Groq retornou um payload vazio para o preview.")
        return self._parse_preview_decision(
            content,
            fallback_score=fallback_score,
            fallback_label=fallback_label,
        )

    def _build_prompt(
        self,
        *,
        user_message: str,
        current_life_summary: str,
        recent_snapshots_context: str,
        recent_projects_context: str,
        recent_chat_context: str,
        interaction_mode: str,
    ) -> str:
        return f"""
Contexto consolidado do dono:
{current_life_summary.strip() or "(ainda sem resumo consolidado)"}

Projetos e frentes conhecidos:
{recent_projects_context.strip() or "(nenhum projeto consolidado ainda)"}

Analises recentes da memoria:
{recent_snapshots_context.strip() or "(nenhum snapshot recente)"}

Historico recente desta conversa:
{recent_chat_context.strip() or "(sem conversa anterior nesta thread)"}

Mensagem atual do dono:
{user_message.strip()}

Modo de interacao:
{interaction_mode}

Regras:
- Responda primeiro ao que o dono acabou de dizer, de forma natural.
- Responda como uma IA pessoal que ja conhece o dono e seus projetos.
- Use o resumo consolidado para adaptar tom, prioridade e praticidade da resposta.
- Priorize contexto pessoal e de trabalho realmente presente no material acima, mas so mencione isso quando for relevante.
- Se a pergunta tocar em um projeto conhecido, conecte a resposta ao estado atual desse projeto.
- Se o dono estiver pedindo ajuda operacional, priorize a resposta mais acionavel e mais curta primeiro.
- Se houver incerteza ou memoria incompleta, assuma isso explicitamente.
- Em cumprimentos, mensagens curtas ou aberturas vagas, responda em 1 ou 2 frases curtas e pergunte como ajudar.
- Nao enumere fatos antigos sem convite explicito.
- Evite hiperfoco em um unico tema so porque ele apareceu na memoria.
- Evite respostas genéricas, longas demais ou com floreio.
- Nao use markdown fences.
""".strip()

    def _extract_content(self, payload: dict[str, Any]) -> str:
        choices = payload.get("choices")
        if not isinstance(choices, list) or not choices:
            raise GroqChatError("Groq returned no choices.")

        first_choice = choices[0] if isinstance(choices[0], dict) else {}
        message = first_choice.get("message") if isinstance(first_choice, dict) else {}
        if not isinstance(message, dict):
            raise GroqChatError("Groq returned an invalid message payload.")

        content = message.get("content")
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            text_parts: list[str] = []
            for chunk in content:
                if not isinstance(chunk, dict):
                    continue
                text = chunk.get("text")
                if isinstance(text, str) and text.strip():
                    text_parts.append(text.strip())
            return "\n".join(text_parts).strip()

        raise GroqChatError("Groq returned an empty content payload.")

    def _parse_preview_decision(
        self,
        content: str,
        *,
        fallback_score: int,
        fallback_label: str,
    ) -> GroqPreviewDecision:
        cleaned = content.strip()
        if cleaned.startswith("```"):
            cleaned = cleaned.strip("`")
            if "\n" in cleaned:
                cleaned = cleaned.split("\n", 1)[1]
            if cleaned.endswith("```"):
                cleaned = cleaned[:-3]
            cleaned = cleaned.strip()

        try:
            payload = json.loads(cleaned)
        except json.JSONDecodeError as exc:
            raise GroqChatError("Groq retornou JSON invalido para o preview.") from exc

        if not isinstance(payload, dict):
            raise GroqChatError("Groq retornou um payload inesperado para o preview.")

        score = payload.get("score")
        try:
            resolved_score = int(score)
        except (TypeError, ValueError):
            resolved_score = fallback_score
        resolved_score = max(0, min(100, resolved_score))

        raw_label = payload.get("label")
        resolved_label = self._normalize_preview_label(
            raw_label if isinstance(raw_label, str) else fallback_label,
            score=resolved_score,
        )

        raw_should_analyze = payload.get("should_analyze")
        resolved_should_analyze = (
            raw_should_analyze
            if isinstance(raw_should_analyze, bool)
            else resolved_score >= 55
        )

        summary = str(payload.get("summary") or "").strip()
        if not summary:
            raise GroqChatError("Groq retornou um resumo vazio no preview.")

        return GroqPreviewDecision(
            score=resolved_score,
            label=resolved_label,
            should_analyze=resolved_should_analyze,
            summary=summary,
        )

    def _normalize_preview_label(self, value: str, *, score: int) -> str:
        normalized = value.strip().lower()
        if "alta" in normalized:
            return "Alta vantagem"
        if "vale" in normalized or "rodar" in normalized:
            return "Vale rodar"
        if "esper" in normalized:
            return "Pode esperar um pouco"
        if "ganho" in normalized or "baixo" in normalized:
            return "Ganho baixo agora"
        if score >= 78:
            return "Alta vantagem"
        if score >= 55:
            return "Vale rodar"
        if score >= 32:
            return "Pode esperar um pouco"
        return "Ganho baixo agora"
