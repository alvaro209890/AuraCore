from __future__ import annotations

import logging

from fastapi import APIRouter, Header, HTTPException, status
from fastapi.concurrency import run_in_threadpool

from app.dependencies import (
    get_memory_job_service,
    get_settings,
    get_supabase_store,
    get_whatsapp_agent_gateway_service,
)
from app.schemas import IngestMessagesRequest, IngestMessagesResponse
from app.services.memory_job_service import MemoryJobService
from app.services.supabase_store import IngestedMessageRecord, SupabaseStore

router = APIRouter(prefix="/api/internal/observer", tags=["internal"])
logger = logging.getLogger("auracore.observer_ingest")


@router.post("/messages/ingest", response_model=IngestMessagesResponse)
async def ingest_messages(
    payload: IngestMessagesRequest,
    x_internal_api_token: str | None = Header(default=None),
) -> IngestMessagesResponse:
    settings = get_settings()
    if x_internal_api_token != settings.internal_api_token:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid internal API token.")

    store = get_supabase_store()
    memory_job_service = get_memory_job_service()
    blocked_contact_phone: str | None = None
    try:
        agent_gateway = get_whatsapp_agent_gateway_service()
        agent_status = await agent_gateway.get_agent_status()
        blocked_contact_phone = store.normalize_contact_phone(agent_status.owner_number)
    except Exception:
        blocked_contact_phone = None

    normalized_messages = _build_records(payload, store, blocked_contact_phone)
    save_result = await run_in_threadpool(store.save_ingested_messages, normalized_messages)
    ignored_count = max(0, len(payload.messages) - len(normalized_messages)) + save_result.ignored_count
    if payload.messages:
        logger.info(
            "observer_batch source_events=%s received=%s normalized=%s saved=%s ignored=%s trimmed=%s",
            sorted({(item.source_event or "unknown").strip() for item in payload.messages if (item.source_event or "").strip()}),
            len(payload.messages),
            len(normalized_messages),
            save_result.saved_count,
            ignored_count,
            save_result.trimmed_existing_count,
        )
    await run_in_threadpool(
        memory_job_service.register_ingest_batch,
        accepted_count=save_result.saved_count,
        ignored_count=ignored_count,
        timestamps=[message.timestamp for message in normalized_messages],
    )
    return IngestMessagesResponse(accepted_count=save_result.saved_count, ignored_count=ignored_count)


def _build_records(
    payload: IngestMessagesRequest,
    store: SupabaseStore,
    blocked_contact_phone: str | None,
) -> list[IngestedMessageRecord]:
    records: list[IngestedMessageRecord] = []
    for item in payload.messages:
        message_text = item.message_text.strip()
        chat_jid = item.chat_jid.strip()
        contact_phone = item.contact_phone.strip()
        if (
            not message_text
            or not chat_jid
            or not store.is_direct_chat_jid(chat_jid)
            or not contact_phone
            or not store.is_normal_contact_phone(contact_phone)
        ):
            continue
        normalized_phone = store.normalize_contact_phone(contact_phone)
        if blocked_contact_phone and normalized_phone and store.phone_matches(normalized_phone, blocked_contact_phone):
            continue

        records.append(
            IngestedMessageRecord(
                message_id=item.message_id.strip(),
                user_id=store.default_user_id,
                direction=item.direction,
                contact_name=(item.contact_name or contact_phone).strip(),
                contact_name_source=(item.contact_name_source or "unknown").strip() or "unknown",
                chat_jid=chat_jid,
                contact_phone=normalized_phone or contact_phone,
                message_text=message_text,
                timestamp=item.timestamp,
                source=item.source.strip() or "baileys",
                source_event=(item.source_event or "").strip() or None,
            )
        )
    return records
