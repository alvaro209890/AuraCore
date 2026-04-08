from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from app.dependencies import get_observer_gateway_service
from app.schemas import ObserverStatusResponse
from app.services.observer_gateway import ObserverGatewayService

router = APIRouter(prefix="/api/observer", tags=["observer"])


@router.post("/connect", response_model=ObserverStatusResponse)
async def connect_observer(
    gateway: ObserverGatewayService = Depends(get_observer_gateway_service),
) -> ObserverStatusResponse:
    return await gateway.connect_observer()


@router.get("/status", response_model=ObserverStatusResponse)
async def observer_status(
    refresh_qr: bool = Query(default=False),
    gateway: ObserverGatewayService = Depends(get_observer_gateway_service),
) -> ObserverStatusResponse:
    return await gateway.get_observer_status(refresh_qr=refresh_qr)
