from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from app.dependencies import get_observer_gateway_service
from app.schemas import ObserverMessageRefreshResponse, ObserverStatusResponse
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
    gateway: ObserverGatewayService = Depends(get_observer_gateway_service),
) -> ObserverMessageRefreshResponse:
    status = await gateway.refresh_observer_messages()
    return ObserverMessageRefreshResponse(
        status=status,
        message=(
            "Nova sincronizacao do WhatsApp iniciada. O AuraCore vai reler apenas chats diretos "
            "e manter no Supabase somente as mensagens mais novas dentro do limite operacional da memoria."
        ),
    )


@router.get("/status", response_model=ObserverStatusResponse)
async def observer_status(
    refresh_qr: bool = Query(default=False),
    gateway: ObserverGatewayService = Depends(get_observer_gateway_service),
) -> ObserverStatusResponse:
    return await gateway.get_observer_status(refresh_qr=refresh_qr)
