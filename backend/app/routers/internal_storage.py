from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Depends
from fastapi.concurrency import run_in_threadpool

from app.dependencies import get_internal_storage_store, require_internal_api_token
from app.schemas import (
    SimpleOkResponse,
    WhatsAppSessionCredsResponse,
    WhatsAppSessionCredsUpsertRequest,
    WhatsAppSessionKeysDeleteRequest,
    WhatsAppSessionKeysLoadRequest,
    WhatsAppSessionKeysLoadResponse,
    WhatsAppSessionKeysUpsertRequest,
)

router = APIRouter(prefix="/api/internal/storage", tags=["internal"])


@router.get("/wa-sessions/{session_id}/creds", response_model=WhatsAppSessionCredsResponse)
async def get_whatsapp_session_creds(
    session_id: str,
    _: None = Depends(require_internal_api_token),
    store = Depends(get_internal_storage_store),
) -> WhatsAppSessionCredsResponse:
    creds = await run_in_threadpool(store.load_whatsapp_session_creds, session_id=session_id)
    return WhatsAppSessionCredsResponse(creds=creds)


@router.put("/wa-sessions/{session_id}/creds", response_model=SimpleOkResponse)
async def put_whatsapp_session_creds(
    session_id: str,
    payload: WhatsAppSessionCredsUpsertRequest,
    _: None = Depends(require_internal_api_token),
    store = Depends(get_internal_storage_store),
) -> SimpleOkResponse:
    await run_in_threadpool(
        store.save_whatsapp_session_creds,
        session_id=session_id,
        creds=payload.creds,
        updated_at=datetime.now(UTC),
    )
    return SimpleOkResponse()


@router.post("/wa-sessions/{session_id}/keys/load", response_model=WhatsAppSessionKeysLoadResponse)
async def load_whatsapp_session_keys(
    session_id: str,
    payload: WhatsAppSessionKeysLoadRequest,
    _: None = Depends(require_internal_api_token),
    store = Depends(get_internal_storage_store),
) -> WhatsAppSessionKeysLoadResponse:
    values = await run_in_threadpool(
        store.load_whatsapp_session_keys,
        session_id=session_id,
        category=payload.category,
        key_ids=payload.ids,
    )
    return WhatsAppSessionKeysLoadResponse(values=values)


@router.put("/wa-sessions/{session_id}/keys", response_model=SimpleOkResponse)
async def put_whatsapp_session_keys(
    session_id: str,
    payload: WhatsAppSessionKeysUpsertRequest,
    _: None = Depends(require_internal_api_token),
    store = Depends(get_internal_storage_store),
) -> SimpleOkResponse:
    await run_in_threadpool(
        store.save_whatsapp_session_keys,
        session_id=session_id,
        category=payload.category,
        values=payload.values,
        updated_at=datetime.now(UTC),
    )
    return SimpleOkResponse()


@router.post("/wa-sessions/{session_id}/keys/delete", response_model=SimpleOkResponse)
async def delete_whatsapp_session_keys(
    session_id: str,
    payload: WhatsAppSessionKeysDeleteRequest,
    _: None = Depends(require_internal_api_token),
    store = Depends(get_internal_storage_store),
) -> SimpleOkResponse:
    await run_in_threadpool(
        store.delete_whatsapp_session_keys,
        session_id=session_id,
        category=payload.category,
        key_ids=payload.ids,
    )
    return SimpleOkResponse()


@router.delete("/wa-sessions/{session_id}", response_model=SimpleOkResponse)
async def clear_whatsapp_session(
    session_id: str,
    _: None = Depends(require_internal_api_token),
    store = Depends(get_internal_storage_store),
) -> SimpleOkResponse:
    await run_in_threadpool(store.clear_whatsapp_session, session_id=session_id)
    return SimpleOkResponse()
