from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query

from app.dependencies import get_account_registry, get_automation_service, get_current_account, get_observer_gateway_service
from app.schemas import ObserverMessageRefreshResponse, ObserverStatusResponse
from app.services.account_registry import AccountRecord, AccountRegistry
from app.services.automation_service import AutomationService
from app.services.observer_gateway import ObserverGatewayError, ObserverGatewayService

router = APIRouter(prefix="/api/observer", tags=["observer"])


@router.post("/connect", response_model=ObserverStatusResponse)
async def connect_observer(
    account: AccountRecord = Depends(get_current_account),
    registry: AccountRegistry = Depends(get_account_registry),
    gateway: ObserverGatewayService = Depends(get_observer_gateway_service),
) -> ObserverStatusResponse:
    try:
        status = await gateway.connect_observer()
    except ObserverGatewayError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    _sync_observer_owner_phone(registry=registry, account=account, status=status)
    return status


@router.post("/reset", response_model=ObserverStatusResponse)
async def reset_observer(
    account: AccountRecord = Depends(get_current_account),
    registry: AccountRegistry = Depends(get_account_registry),
    gateway: ObserverGatewayService = Depends(get_observer_gateway_service),
) -> ObserverStatusResponse:
    try:
        status = await gateway.reset_observer()
    except ObserverGatewayError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    _sync_observer_owner_phone(registry=registry, account=account, status=status)
    return status


@router.post("/messages/refresh", response_model=ObserverMessageRefreshResponse)
async def refresh_observer_messages(
    account: AccountRecord = Depends(get_current_account),
    registry: AccountRegistry = Depends(get_account_registry),
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
    _sync_observer_owner_phone(registry=registry, account=account, status=status)
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
    account: AccountRecord = Depends(get_current_account),
    registry: AccountRegistry = Depends(get_account_registry),
    gateway: ObserverGatewayService = Depends(get_observer_gateway_service),
) -> ObserverStatusResponse:
    try:
        status = await gateway.get_observer_status(refresh_qr=refresh_qr)
    except ObserverGatewayError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    _sync_observer_owner_phone(registry=registry, account=account, status=status)
    return status


def _sync_observer_owner_phone(
    *,
    registry: AccountRegistry,
    account: AccountRecord,
    status: ObserverStatusResponse,
) -> None:
    try:
        registry.set_observer_owner_phone(
            app_user_id=account.app_user_id,
            phone=status.owner_number,
        )
    except Exception:
        # Observer status should still be returned even if the registry sync fails.
        return
