from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from app.dependencies import get_current_account, get_whatsapp_agent_gateway_service
from app.schemas import GlobalAgentStatusResponse
from app.services.account_registry import AccountRecord
from app.services.observer_gateway import ObserverGatewayError, WhatsAppAgentGatewayService

router = APIRouter(prefix="/api/global-agent", tags=["global-agent"])


@router.get("/status", response_model=GlobalAgentStatusResponse)
async def get_global_agent_status(
    account: AccountRecord = Depends(get_current_account),
    gateway: WhatsAppAgentGatewayService = Depends(get_whatsapp_agent_gateway_service),
) -> GlobalAgentStatusResponse:
    try:
        status = await gateway.get_agent_status()
    except ObserverGatewayError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return _to_global_agent_status(status=status, account=account)


@router.post("/connect", response_model=GlobalAgentStatusResponse)
async def connect_global_agent(
    account: AccountRecord = Depends(get_current_account),
    gateway: WhatsAppAgentGatewayService = Depends(get_whatsapp_agent_gateway_service),
) -> GlobalAgentStatusResponse:
    try:
        status = await gateway.connect_agent()
    except ObserverGatewayError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return _to_global_agent_status(status=status, account=account)


@router.post("/reset", response_model=GlobalAgentStatusResponse)
async def reset_global_agent(
    account: AccountRecord = Depends(get_current_account),
    gateway: WhatsAppAgentGatewayService = Depends(get_whatsapp_agent_gateway_service),
) -> GlobalAgentStatusResponse:
    try:
        status = await gateway.reset_agent()
    except ObserverGatewayError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return _to_global_agent_status(status=status, account=account)


def _to_global_agent_status(
    *,
    status,
    account: AccountRecord,
) -> GlobalAgentStatusResponse:
    return GlobalAgentStatusResponse(
        instance_name=status.instance_name,
        connected=status.connected,
        state=status.state,
        gateway_ready=status.gateway_ready,
        owner_number=status.owner_number,
        qr_code=status.qr_code,
        qr_expires_in_sec=status.qr_expires_in_sec,
        last_seen_at=status.last_seen_at,
        last_error=status.last_error,
        current_username=account.username,
        current_user_observer_phone=account.observer_owner_phone,
    )
