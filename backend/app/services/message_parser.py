from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from uuid import UUID


TEXT_WRAPPER_KEYS = (
    "ephemeralMessage",
    "viewOnceMessage",
    "viewOnceMessageV2",
    "viewOnceMessageV2Extension",
    "documentWithCaptionMessage",
)


@dataclass(slots=True)
class NormalizedMessage:
    id: str
    user_id: UUID
    contact_name: str
    message_text: str
    timestamp: datetime


def normalize_messages(payload: dict[str, Any], default_user_id: UUID) -> list[NormalizedMessage]:
    event_payload = payload.get("data", payload)
    items: list[dict[str, Any]] = []

    if isinstance(event_payload, list):
        items = [item for item in event_payload if isinstance(item, dict)]
    elif isinstance(event_payload, dict):
        items = [event_payload]

    normalized: list[NormalizedMessage] = []
    for item in items:
        message = _normalize_single_message(item, default_user_id)
        if message is not None:
            normalized.append(message)
    return normalized


def _normalize_single_message(item: dict[str, Any], default_user_id: UUID) -> NormalizedMessage | None:
    key = item.get("key")
    if not isinstance(key, dict):
        return None

    if bool(key.get("fromMe")):
        return None

    remote_jid = str(key.get("remoteJid", "")).strip()
    if not remote_jid or _is_group_or_broadcast(remote_jid):
        return None

    message_id = str(key.get("id", "")).strip()
    if not message_id:
        return None

    text = _extract_text(item.get("message"))
    if not text:
        return None

    timestamp = _extract_timestamp(item.get("messageTimestamp"))
    contact_name = str(item.get("pushName") or remote_jid.split("@", maxsplit=1)[0]).strip()

    return NormalizedMessage(
        id=message_id,
        user_id=default_user_id,
        contact_name=contact_name,
        message_text=text,
        timestamp=timestamp,
    )


def _extract_text(message_payload: Any) -> str | None:
    if not isinstance(message_payload, dict):
        return None

    message = _unwrap_message(message_payload)
    if not isinstance(message, dict):
        return None

    conversation = message.get("conversation")
    if isinstance(conversation, str) and conversation.strip():
        return conversation.strip()

    extended_text = message.get("extendedTextMessage")
    if isinstance(extended_text, dict):
        text = extended_text.get("text")
        if isinstance(text, str) and text.strip():
            return text.strip()

    return None


def _unwrap_message(message_payload: dict[str, Any]) -> dict[str, Any]:
    current = message_payload
    visited = 0

    while isinstance(current, dict) and visited < 5:
        for wrapper_key in TEXT_WRAPPER_KEYS:
            wrapper = current.get(wrapper_key)
            if isinstance(wrapper, dict):
                nested = wrapper.get("message")
                current = nested if isinstance(nested, dict) else wrapper
                visited += 1
                break
        else:
            break

    return current


def _extract_timestamp(raw_value: Any) -> datetime:
    if isinstance(raw_value, datetime):
        return raw_value.astimezone(UTC)

    if isinstance(raw_value, str):
        stripped = raw_value.strip()
        if stripped.isdigit():
            raw_value = int(stripped)
        else:
            try:
                return datetime.fromisoformat(stripped.replace("Z", "+00:00")).astimezone(UTC)
            except ValueError:
                return datetime.now(UTC)

    if isinstance(raw_value, (int, float)):
        timestamp_value = float(raw_value)
        if timestamp_value > 1_000_000_000_000:
            timestamp_value /= 1000
        return datetime.fromtimestamp(timestamp_value, tz=UTC)

    return datetime.now(UTC)


def _is_group_or_broadcast(remote_jid: str) -> bool:
    return remote_jid.endswith("@g.us") or remote_jid.endswith("@broadcast")

