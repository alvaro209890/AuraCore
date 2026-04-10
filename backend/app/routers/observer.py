from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query

from app.dependencies import get_automation_service, get_observer_gateway_service
from app.schemas import ObserverMessageRefreshResponse, ObserverStatusResponse
from app.services.automation_service import AutomationService
from app.services.observer_gateway import ObserverGatewayError, ObserverGatewayService

router = APIRouter(prefix="/api/observer", tags=["observer"])


@router.post("/connect", response_model=ObserverStatusResponse)
async def connect_observer(
    gateway: ObserverGatewayService = Depends(get_observer_gateway_service),
) -> ObserverStatusResponse:
    try:
        return await gateway.connect_observer()
    except ObserverGatewayError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.post("/reset", response_model=ObserverStatusResponse)
async def reset_observer(
    gateway: ObserverGatewayService = Depends(get_observer_gateway_service),
) -> ObserverStatusResponse:
    try:
        return await gateway.reset_observer()
    except ObserverGatewayError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.post("/messages/refresh", response_model=ObserverMessageRefreshResponse)
async def refresh_observer_messages(
    automation_service: AutomationService = Depends(get_automation_service),
    gateway: ObserverGatewayService = Depends(get_observer_gateway_service),
) -> ObserverMessageRefreshResponse:
    sync_run = await automation_service.start_manual_sync(trigger="manual")
    try:
        status = await gateway.refresh_observer_messages()
    except ObserverGatewayError as exc:
        automation_service.mark_sync_failed(sync_run_id=sync_run.id, error_text=str(exc))
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except Exception as error:
        automation_service.mark_sync_failed(sync_run_id=sync_run.id, error_text=str(error))
        raise
    automation_service.schedule_sync_settle(delay_seconds=30.0)
    return ObserverMessageRefreshResponse(
        status=status,
        message=(
            "Nova sincronizacao do WhatsApp iniciada. O AuraCore vai aguardar o fluxo do observador "
            "assentar, fechar o sync run automaticamente e, se houver lote util, enfileirar sozinho "
            "a primeira analise ou o proximo lote incremental."
        ),
        sync_run_id=sync_run.id,
    )


@router.get("/status", response_model=ObserverStatusResponse)
async def observer_status(
    refresh_qr: bool = Query(default=False),
    gateway: ObserverGatewayService = Depends(get_observer_gateway_service),
) -> ObserverStatusResponse:
    try:
        return await gateway.get_observer_status(refresh_qr=refresh_qr)
    except ObserverGatewayError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
