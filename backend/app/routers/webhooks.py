from __future__ import annotations

import logging
from json import JSONDecodeError
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, status

from app.dependencies import get_settings, get_supabase_store
from app.schemas import WebhookAckResponse
from app.services.message_parser import normalize_messages
from app.services.supabase_store import SupabaseStore

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/webhooks", tags=["webhooks"])

EVENT_MESSAGES_UPSERT = "messages-upsert"
EVENT_CONNECTION_UPDATE = "connection-update"


@router.post("/evolution/{webhook_token}/{event_slug}", response_model=WebhookAckResponse)
async def evolution_webhook(
    webhook_token: str,
    event_slug: str,
    request: Request,
    store: SupabaseStore = Depends(get_supabase_store),
) -> WebhookAckResponse:
    settings = get_settings()
    if webhook_token != settings.webhook_secret:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid webhook token.")

    try:
        payload = await request.json()
    except JSONDecodeError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Webhook payload must be valid JSON.",
        ) from exc

    if not isinstance(payload, dict):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Webhook payload must be a JSON object.")

    if event_slug == EVENT_MESSAGES_UPSERT:
        messages = normalize_messages(payload, default_user_id=settings.default_user_id)
        saved_count = store.save_messages(messages)
        ignored_count = max(0, len(_candidate_items(payload)) - len(messages))
        return WebhookAckResponse(
            event="MESSAGES_UPSERT",
            accepted_count=saved_count,
            ignored_count=ignored_count,
        )

    if event_slug == EVENT_CONNECTION_UPDATE:
        logger.info("Evolution connection update received: %s", _extract_connection_state(payload))
        return WebhookAckResponse(event="CONNECTION_UPDATE", accepted_count=1, ignored_count=0)

    logger.info("Ignoring unsupported Evolution webhook event slug: %s", event_slug)
    return WebhookAckResponse(event=event_slug.upper().replace("-", "_"), accepted_count=0, ignored_count=1)


def _candidate_items(payload: dict[str, Any]) -> list[dict[str, Any]]:
    event_payload = payload.get("data", payload)
    if isinstance(event_payload, list):
        return [item for item in event_payload if isinstance(item, dict)]
    if isinstance(event_payload, dict):
        return [event_payload]
    return []


def _extract_connection_state(payload: dict[str, Any]) -> str:
    event_payload = payload.get("data", payload)
    if isinstance(event_payload, dict):
        state = event_payload.get("state")
        if state:
            return str(state)
        instance = event_payload.get("instance")
        if isinstance(instance, dict) and instance.get("state"):
            return str(instance["state"])
    return "unknown"
