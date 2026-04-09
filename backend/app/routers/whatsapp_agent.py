from __future__ import annotations

from fastapi import APIRouter, Body, Depends, Query

from app.dependencies import get_whatsapp_agent_service
from app.schemas import (
    UpdateWhatsAppAgentSettingsRequest,
    WhatsAppAgentMessagesListResponse,
    WhatsAppAgentSettingsResponse,
    WhatsAppAgentStatusResponse,
    WhatsAppAgentThreadsListResponse,
    WhatsAppAgentWorkspaceResponse,
)
from app.services.whatsapp_agent_service import WhatsAppAgentService

router = APIRouter(prefix="/api/whatsapp-agent", tags=["whatsapp-agent"])


@router.get("/status", response_model=WhatsAppAgentStatusResponse)
async def get_agent_status(
    agent_service: WhatsAppAgentService = Depends(get_whatsapp_agent_service),
) -> WhatsAppAgentStatusResponse:
    return await agent_service.get_status()


@router.post("/connect", response_model=WhatsAppAgentStatusResponse)
async def connect_agent(
    agent_service: WhatsAppAgentService = Depends(get_whatsapp_agent_service),
) -> WhatsAppAgentStatusResponse:
    return await agent_service.connect_agent()


@router.post("/reset", response_model=WhatsAppAgentStatusResponse)
async def reset_agent(
    agent_service: WhatsAppAgentService = Depends(get_whatsapp_agent_service),
) -> WhatsAppAgentStatusResponse:
    return await agent_service.reset_agent()


@router.get("/settings", response_model=WhatsAppAgentSettingsResponse)
async def get_agent_settings(
    agent_service: WhatsAppAgentService = Depends(get_whatsapp_agent_service),
) -> WhatsAppAgentSettingsResponse:
    snapshot = await agent_service.build_workspace()
    return snapshot.settings


@router.put("/settings", response_model=WhatsAppAgentSettingsResponse)
async def update_agent_settings(
    payload: UpdateWhatsAppAgentSettingsRequest = Body(...),
    agent_service: WhatsAppAgentService = Depends(get_whatsapp_agent_service),
) -> WhatsAppAgentSettingsResponse:
    return agent_service.update_settings(auto_reply_enabled=payload.auto_reply_enabled)


@router.get("/workspace", response_model=WhatsAppAgentWorkspaceResponse)
async def get_agent_workspace(
    thread_id: str | None = Query(default=None),
    agent_service: WhatsAppAgentService = Depends(get_whatsapp_agent_service),
) -> WhatsAppAgentWorkspaceResponse:
    snapshot = await agent_service.build_workspace(thread_id=thread_id)
    return WhatsAppAgentWorkspaceResponse(
        status=snapshot.status,
        settings=snapshot.settings,
        observer_status=snapshot.observer_status,
        active_thread_id=snapshot.active_thread_id,
        threads=[_to_thread_response(thread, agent_service) for thread in snapshot.threads],
        messages=[_to_message_response(message) for message in snapshot.messages],
    )


@router.get("/threads", response_model=WhatsAppAgentThreadsListResponse)
async def list_agent_threads(
    limit: int = Query(default=24, ge=1, le=100),
    agent_service: WhatsAppAgentService = Depends(get_whatsapp_agent_service),
) -> WhatsAppAgentThreadsListResponse:
    threads = agent_service.list_threads(limit=limit)
    return WhatsAppAgentThreadsListResponse(
        threads=[_to_thread_response(thread, agent_service) for thread in threads],
    )


@router.get("/messages", response_model=WhatsAppAgentMessagesListResponse)
async def list_agent_messages(
    thread_id: str = Query(...),
    limit: int = Query(default=40, ge=1, le=200),
    agent_service: WhatsAppAgentService = Depends(get_whatsapp_agent_service),
) -> WhatsAppAgentMessagesListResponse:
    messages = agent_service.list_messages(thread_id=thread_id, limit=limit)
    return WhatsAppAgentMessagesListResponse(
        messages=[_to_message_response(message) for message in messages],
    )


def _to_message_response(message) -> dict:
    return {
        "id": message.id,
        "thread_id": message.thread_id,
        "direction": message.direction,
        "role": message.role,
        "whatsapp_message_id": message.whatsapp_message_id,
        "source_inbound_message_id": message.source_inbound_message_id,
        "contact_phone": message.contact_phone,
        "chat_jid": message.chat_jid,
        "content": message.content,
        "message_timestamp": message.message_timestamp,
        "processing_status": message.processing_status,
        "send_status": message.send_status,
        "error_text": message.error_text,
        "response_latency_ms": message.response_latency_ms,
        "model_run_id": message.model_run_id,
        "metadata": message.metadata,
        "created_at": message.created_at,
    }


def _to_thread_response(thread, agent_service: WhatsAppAgentService):
    messages = agent_service.list_messages(thread_id=thread.id, limit=1)
    last_message = messages[-1] if messages else None
    preview = None
    if last_message:
        preview = last_message.content[:84].strip()
        if len(last_message.content) > 84:
            preview = preview.rstrip() + "..."
    return {
        "id": thread.id,
        "contact_name": thread.contact_name,
        "contact_phone": thread.contact_phone,
        "chat_jid": thread.chat_jid,
        "status": thread.status,
        "last_message_preview": preview,
        "last_message_at": thread.last_message_at,
        "last_inbound_at": thread.last_inbound_at,
        "last_outbound_at": thread.last_outbound_at,
        "last_error_at": thread.last_error_at,
        "last_error_text": thread.last_error_text,
        "created_at": thread.created_at,
        "updated_at": thread.updated_at,
    }
