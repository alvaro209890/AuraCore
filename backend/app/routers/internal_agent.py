from __future__ import annotations

import logging

from fastapi import APIRouter, Depends

from app.dependencies import get_account_registry, get_service_bundle_cache, require_internal_api_token
from app.schemas import WhatsAppAgentInboundMessagesRequest, WhatsAppAgentInboundMessagesResponse
from app.services.account_registry import AccountRegistry
from app.services.service_bundle import ServiceBundleCache

router = APIRouter(prefix="/api/internal/agent", tags=["internal"])
logger = logging.getLogger("auracore.agent_reply")


@router.post("/messages/inbound", response_model=WhatsAppAgentInboundMessagesResponse)
async def ingest_agent_message(
    payload: WhatsAppAgentInboundMessagesRequest,
    _: None = Depends(require_internal_api_token),
    registry: AccountRegistry = Depends(get_account_registry),
    cache: ServiceBundleCache = Depends(get_service_bundle_cache),
) -> WhatsAppAgentInboundMessagesResponse:
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
        "ignored_unmapped_observer",
        "duplicate_message",
        "duplicate_reply",
    }
    for message in payload.messages:
        account = registry.get_account_by_observer_owner_phone(message.contact_phone)
        if account is None:
            ignored += 1
            logger.info(
                "agent_inbound_unmapped contact_phone=%s message_id=%s",
                message.contact_phone,
                message.message_id,
            )
            continue
        response = await cache.get_bundle(account).whatsapp_agent_service.handle_inbound_message(message)
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
