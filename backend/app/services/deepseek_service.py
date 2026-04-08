from __future__ import annotations

import json
from datetime import datetime
from typing import Any

import httpx
from pydantic import BaseModel, Field

from app.config import Settings


class DeepSeekError(RuntimeError):
    """Raised when DeepSeek cannot complete or return a valid analysis."""


class DeepSeekMemoryResult(BaseModel):
    updated_life_summary: str
    window_summary: str
    key_learnings: list[str] = Field(default_factory=list)
    people_and_relationships: list[str] = Field(default_factory=list)
    routine_signals: list[str] = Field(default_factory=list)
    preferences: list[str] = Field(default_factory=list)
    open_questions: list[str] = Field(default_factory=list)


class DeepSeekService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    async def analyze_memory(
        self,
        *,
        transcript: str,
        current_life_summary: str,
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
                        "You analyze private chat messages to build a memory profile about one user. "
                        "Return only valid JSON. Never invent facts. If something is uncertain, phrase it as a "
                        "possible signal in the lists instead of stating it as a certainty in the life summary."
                    ),
                },
                {
                    "role": "user",
                    "content": self._build_prompt(
                        transcript=transcript,
                        current_life_summary=current_life_summary,
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

    def _build_prompt(
        self,
        *,
        transcript: str,
        current_life_summary: str,
        window_hours: int,
        window_start: datetime,
        window_end: datetime,
        source_message_count: int,
    ) -> str:
        previous_summary = current_life_summary.strip() or "(empty memory so far)"
        return f"""
Analyze the following direct-message conversation window and update the user's memory.

Window hours: {window_hours}
Window start (UTC): {window_start.isoformat()}
Window end (UTC): {window_end.isoformat()}
Messages included: {source_message_count}

Current consolidated life summary:
{previous_summary}

Conversation transcript:
{transcript}

Return a JSON object with exactly these fields:
- updated_life_summary: string
- window_summary: string
- key_learnings: string[]
- people_and_relationships: string[]
- routine_signals: string[]
- preferences: string[]
- open_questions: string[]

Rules:
- updated_life_summary must be cumulative and merge the old summary with this window.
- Keep updated_life_summary factual, concise, and useful for a future personal assistant.
- Use the list fields for concrete learnings and uncertain signals.
- Do not mention that you are an AI.
- Do not include markdown fences.
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

