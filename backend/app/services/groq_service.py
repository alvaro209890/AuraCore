from __future__ import annotations

from typing import Any

import httpx

from app.config import Settings


class GroqChatError(RuntimeError):
    """Raised when Groq chat completion fails or returns an invalid payload."""


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
                        "decisao e suas frentes ativas, mas sem fingir certeza quando a memoria estiver incompleta."
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

    async def generate_analysis_preview_summary(
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
        recommendation_score: int,
        recommendation_label: str,
    ) -> str:
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
                        "Voce resume, em portugues do Brasil e em no maximo duas frases curtas, se vale a pena "
                        "rodar uma nova analise de memoria. Use apenas os numeros recebidos. Nao invente contexto "
                        "das mensagens e nao use markdown."
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        f"Configuracao: alvo {target_message_count} mensagens, alcance {max_lookback_hours}h, modo {detail_mode}. "
                        f"Disponiveis: {available_message_count}. Selecionadas: {selected_message_count}. "
                        f"Novas desde a ultima analise: {new_message_count}. Substituidas pela retencao: {replaced_message_count}. "
                        f"Tokens estimados do DeepSeek: {estimated_total_tokens}. "
                        f"Score atual: {recommendation_score}/100 ({recommendation_label})."
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
            raise GroqChatError("Groq retornou um resumo vazio para o preview.")
        return content.strip()

    def _build_prompt(
        self,
        *,
        user_message: str,
        current_life_summary: str,
        recent_snapshots_context: str,
        recent_projects_context: str,
        recent_chat_context: str,
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

Regras:
- Responda como uma IA pessoal que ja conhece o dono e seus projetos.
- Use o resumo consolidado para adaptar tom, prioridade e praticidade da resposta.
- Priorize contexto pessoal e de trabalho realmente presente no material acima.
- Se a pergunta tocar em um projeto conhecido, conecte a resposta ao estado atual desse projeto.
- Se o dono estiver pedindo ajuda operacional, priorize a resposta mais acionavel e mais curta primeiro.
- Se houver incerteza ou memoria incompleta, assuma isso explicitamente.
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
