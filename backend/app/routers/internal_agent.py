from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, Header, HTTPException, status

from app.dependencies import get_settings, get_whatsapp_agent_service
from app.schemas import WhatsAppAgentInboundMessagesRequest, WhatsAppAgentInboundMessagesResponse
from app.services.whatsapp_agent_service import WhatsAppAgentService

router = APIRouter(prefix="/api/internal/agent", tags=["internal"])
logger = logging.getLogger("auracore.agent_reply")


@router.post("/messages/inbound", response_model=WhatsAppAgentInboundMessagesResponse)
async def ingest_agent_message(
    payload: WhatsAppAgentInboundMessagesRequest,
    x_internal_api_token: str | None = Header(default=None),
    agent_service: WhatsAppAgentService = Depends(get_whatsapp_agent_service),
) -> WhatsAppAgentInboundMessagesResponse:
    settings = get_settings()
    if x_internal_api_token != settings.internal_api_token:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid internal API token.")
    accepted = 0
    ignored = 0
    ignored_actions = {
        "ignored_empty",
        "ignored_non_direct",
        "ignored_invalid_contact",
        "ignored_from_me",
        "ignored_self",
        "ignored_missing_allowlist",
        "ignored_not_allowed",
        "duplicate_message",
        "duplicate_reply",
    }
    for message in payload.messages:
        response = await agent_service.handle_inbound_message(message)
        if response.action in ignored_actions or response.action.startswith("ignored"):
            ignored += 1
        else:
            accepted += 1
    logger.info(
        "agent_inbound_batch accepted=%s ignored=%s total=%s",
        accepted,
        ignored,
        len(payload.messages),
    )
    return WhatsAppAgentInboundMessagesResponse(
        accepted_count=accepted,
        ignored_count=ignored,
    )
