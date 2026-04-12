from __future__ import annotations

import logging

from fastapi import APIRouter, Depends
from fastapi.concurrency import run_in_threadpool

from app.dependencies import (
    get_account_registry,
    get_internal_account,
    get_internal_automation_service,
    get_internal_observer_gateway_service,
    get_internal_service_bundle,
    get_internal_supabase_store,
    get_internal_whatsapp_agent_gateway_service,
)
from app.schemas import (
    GroupMetadataUpdateRequest,
    IngestMessagesRequest,
    IngestMessagesResponse,
    SimpleOkResponse,
)
from app.services.account_registry import AccountRecord, AccountRegistry
from app.services.service_bundle import ServiceBundle
from app.services.supabase_store import IngestedMessageRecord, SupabaseStore

router = APIRouter(prefix="/api/internal/observer", tags=["internal"])
logger = logging.getLogger("auracore.observer_ingest")


@router.post("/messages/ingest", response_model=IngestMessagesResponse)
async def ingest_messages(
    payload: IngestMessagesRequest,
    account: AccountRecord = Depends(get_internal_account),
    registry: AccountRegistry = Depends(get_account_registry),
    bundle: ServiceBundle = Depends(get_internal_service_bundle),
    store: SupabaseStore = Depends(get_internal_supabase_store),
    automation_service = Depends(get_internal_automation_service),
    observer_gateway = Depends(get_internal_observer_gateway_service),
    agent_gateway = Depends(get_internal_whatsapp_agent_gateway_service),
) -> IngestMessagesResponse:
    blocked_contact_phone: str | None = None
    try:
        observer_status = await observer_gateway.get_status()
        blocked_contact_phone = store.normalize_contact_phone(observer_status.owner_number)
        registry.set_observer_owner_phone(
            app_user_id=account.app_user_id,
            phone=observer_status.owner_number,
        )
    except Exception:
        blocked_contact_phone = None
    if not blocked_contact_phone:
        try:
            agent_status = await agent_gateway.get_agent_status()
            blocked_contact_phone = store.normalize_contact_phone(agent_status.owner_number)
        except Exception:
            blocked_contact_phone = None

    normalized_messages, skipped_audio_count = await _build_records(
        payload,
        store,
        blocked_contact_phone,
        bundle,
    )
    save_result = await run_in_threadpool(store.save_ingested_messages, normalized_messages)
    ignored_count = max(0, len(payload.messages) - len(normalized_messages) - skipped_audio_count) + save_result.ignored_count + skipped_audio_count
    if payload.messages:
        logger.info(
            "observer_batch source_events=%s received=%s normalized=%s saved=%s ignored=%s skipped_audio=%s trimmed=%s",
            sorted({(item.source_event or "unknown").strip() for item in payload.messages if (item.source_event or "").strip()}),
            len(payload.messages),
            len(normalized_messages),
            save_result.saved_count,
            ignored_count,
            skipped_audio_count,
            save_result.trimmed_existing_count,
        )
    await run_in_threadpool(
        automation_service.register_ingest_batch,
        accepted_count=save_result.saved_count,
        ignored_count=ignored_count,
        timestamps=[message.timestamp for message in normalized_messages],
    )
    automation_service.schedule_sync_settle()
    return IngestMessagesResponse(accepted_count=save_result.saved_count, ignored_count=ignored_count)


@router.post("/groups/upsert", response_model=SimpleOkResponse)
async def upsert_groups(
    payload: GroupMetadataUpdateRequest,
    store: SupabaseStore = Depends(get_internal_supabase_store),
) -> SimpleOkResponse:
    updated_count = 0
    for item in payload.groups:
        updated = await run_in_threadpool(
            store.upsert_known_group,
            user_id=store.default_user_id,
            chat_jid=item.chat_jid,
            chat_name=item.chat_name,
            seen_at=item.seen_at,
        )
        if updated is not None:
            updated_count += 1
    if payload.groups:
        logger.info("observer_groups_upserted received=%s updated=%s", len(payload.groups), updated_count)
    return SimpleOkResponse()


async def _build_records(
    payload: IngestMessagesRequest,
    store: SupabaseStore,
    blocked_contact_phone: str | None,
    bundle: ServiceBundle,
) -> tuple[list[IngestedMessageRecord], int]:
    persona = await run_in_threadpool(store.get_persona, store.default_user_id)
    allow_audio_transcription = bool(persona.last_analyzed_at)
    records: list[IngestedMessageRecord] = []
    skipped_audio_count = 0
    for item in payload.messages:
        message_text = item.message_text.strip()
        chat_jid = item.chat_jid.strip()
        chat_type = str(item.chat_type or "direct").strip().lower()
        audio_data_url = (item.audio_data_url or "").strip()
        is_audio_message = (item.media_type or "").strip().lower() == "audio" or bool(audio_data_url)
        if not chat_jid:
            continue
        if is_audio_message and not message_text:
            if not allow_audio_transcription:
                skipped_audio_count += 1
                continue
            if not audio_data_url:
                skipped_audio_count += 1
                continue
            try:
                transcript = await bundle.groq_service.transcribe_audio_data_url(audio_data_url)
            except Exception as exc:
                skipped_audio_count += 1
                logger.warning(
                    "observer_audio_transcription_failed message_id=%s chat_jid=%s detail=%s",
                    item.message_id,
                    chat_jid,
                    str(exc),
                )
                continue
            transcript = " ".join(transcript.split()).strip()
            if not transcript:
                skipped_audio_count += 1
                continue
            message_text = f"[Audio transcrito] {transcript}"
        elif is_audio_message and audio_data_url and allow_audio_transcription:
            try:
                transcript = await bundle.groq_service.transcribe_audio_data_url(audio_data_url)
            except Exception:
                transcript = ""
            transcript = " ".join(transcript.split()).strip()
            if transcript:
                combined_parts = [message_text, f"[Audio transcrito] {transcript}"]
                message_text = "\n".join(part for part in combined_parts if part)

        if not message_text:
            continue

        if chat_type == "group":
            if not store.is_group_chat_jid(chat_jid):
                continue
            normalized_contact_phone = store.normalize_contact_phone(item.contact_phone)
            normalized_participant_phone = store.normalize_contact_phone(item.participant_phone)
            resolved_contact_name = (
                (item.participant_name or item.contact_name or item.chat_name or item.participant_phone or chat_jid).strip()
            )
            records.append(
                IngestedMessageRecord(
                    message_id=item.message_id.strip(),
                    user_id=store.default_user_id,
                    chat_type="group",
                    chat_name=(item.chat_name or chat_jid).strip(),
                    direction=item.direction,
                    contact_name=resolved_contact_name,
                    contact_name_source=(item.contact_name_source or "unknown").strip() or "unknown",
                    chat_jid=chat_jid,
                    contact_phone=normalized_contact_phone,
                    message_text=message_text,
                    timestamp=item.timestamp,
                    participant_name=(item.participant_name or item.contact_name or "").strip() or None,
                    participant_phone=normalized_participant_phone,
                    participant_jid=(item.participant_jid or "").strip() or None,
                    source=item.source.strip() or "baileys",
                    source_event=(item.source_event or "").strip() or None,
                    media_type=(item.media_type or "").strip() or None,
                )
            )
            continue

        contact_phone = (item.contact_phone or "").strip()
        if (
            not store.is_direct_chat_jid(chat_jid)
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
                chat_type="direct",
                chat_name=(item.chat_name or item.contact_name or contact_phone).strip(),
                direction=item.direction,
                contact_name=(item.contact_name or contact_phone).strip(),
                contact_name_source=(item.contact_name_source or "unknown").strip() or "unknown",
                chat_jid=chat_jid,
                contact_phone=normalized_phone or contact_phone,
                message_text=message_text,
                timestamp=item.timestamp,
                participant_name=None,
                participant_phone=None,
                participant_jid=None,
                source=item.source.strip() or "baileys",
                source_event=(item.source_event or "").strip() or None,
                media_type=(item.media_type or "").strip() or None,
            )
        )
    return records, skipped_audio_count
