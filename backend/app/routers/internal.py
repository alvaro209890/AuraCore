from __future__ import annotations

from fastapi import APIRouter, Header, HTTPException, status

from app.dependencies import get_settings, get_supabase_store
from app.schemas import IngestMessagesRequest, IngestMessagesResponse
from app.services.supabase_store import IngestedMessageRecord, SupabaseStore

router = APIRouter(prefix="/api/internal/observer", tags=["internal"])


@router.post("/messages/ingest", response_model=IngestMessagesResponse)
async def ingest_messages(
    payload: IngestMessagesRequest,
    x_internal_api_token: str | None = Header(default=None),
) -> IngestMessagesResponse:
    settings = get_settings()
    if x_internal_api_token != settings.internal_api_token:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid internal API token.")

    store = get_supabase_store()
    normalized_messages = _build_records(payload, store)
    saved_count = store.save_ingested_messages(normalized_messages)
    ignored_count = max(0, len(payload.messages) - len(normalized_messages))
    return IngestMessagesResponse(accepted_count=saved_count, ignored_count=ignored_count)


def _build_records(payload: IngestMessagesRequest, store: SupabaseStore) -> list[IngestedMessageRecord]:
    records: list[IngestedMessageRecord] = []
    for item in payload.messages:
        message_text = item.message_text.strip()
        contact_phone = item.contact_phone.strip()
        if not message_text or not contact_phone or not store.is_normal_contact_phone(contact_phone):
            continue

        records.append(
            IngestedMessageRecord(
                message_id=item.message_id.strip(),
                user_id=store.default_user_id,
                direction=item.direction,
                contact_name=(item.contact_name or contact_phone).strip(),
                contact_phone=contact_phone,
                message_text=message_text,
                timestamp=item.timestamp,
                source=item.source.strip() or "baileys",
            )
        )
    return records
