from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from app.dependencies import get_automation_service, get_observer_gateway_service
from app.schemas import ObserverMessageRefreshResponse, ObserverStatusResponse
from app.services.automation_service import AutomationService
from app.services.observer_gateway import ObserverGatewayService

router = APIRouter(prefix="/api/observer", tags=["observer"])


@router.post("/connect", response_model=ObserverStatusResponse)
async def connect_observer(
    gateway: ObserverGatewayService = Depends(get_observer_gateway_service),
) -> ObserverStatusResponse:
    return await gateway.connect_observer()


@router.post("/reset", response_model=ObserverStatusResponse)
async def reset_observer(
    gateway: ObserverGatewayService = Depends(get_observer_gateway_service),
) -> ObserverStatusResponse:
    return await gateway.reset_observer()


@router.post("/messages/refresh", response_model=ObserverMessageRefreshResponse)
async def refresh_observer_messages(
    automation_service: AutomationService = Depends(get_automation_service),
    gateway: ObserverGatewayService = Depends(get_observer_gateway_service),
) -> ObserverMessageRefreshResponse:
    sync_run = await automation_service.start_manual_sync(trigger="manual")
    try:
        status = await gateway.refresh_observer_messages()
    except Exception as error:
        automation_service.mark_sync_failed(sync_run_id=sync_run.id, error_text=str(error))
        raise
    await automation_service.finalize_manual_sync_and_queue_refresh(sync_run_id=sync_run.id)
    return ObserverMessageRefreshResponse(
        status=status,
        message=(
            "Nova sincronizacao do WhatsApp iniciada. O AuraCore vai reler apenas chats diretos "
            "e manter no Supabase somente as mensagens mais novas dentro do limite operacional da memoria. "
            "Depois disso, a atualizacao do resumo do dono entra automaticamente na fila."
        ),
        sync_run_id=sync_run.id,
    )


@router.get("/status", response_model=ObserverStatusResponse)
async def observer_status(
    refresh_qr: bool = Query(default=False),
    gateway: ObserverGatewayService = Depends(get_observer_gateway_service),
) -> ObserverStatusResponse:
    return await gateway.get_observer_status(refresh_qr=refresh_qr)
