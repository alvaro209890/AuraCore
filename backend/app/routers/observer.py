from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from app.dependencies import get_evolution_api_service
from app.schemas import ObserverStatusResponse
from app.services.evolution_api import EvolutionApiService

router = APIRouter(prefix="/api/observer", tags=["observer"])


@router.post("/connect", response_model=ObserverStatusResponse)
async def connect_observer(
    evolution_api: EvolutionApiService = Depends(get_evolution_api_service),
) -> ObserverStatusResponse:
    return await evolution_api.connect_observer()


@router.get("/status", response_model=ObserverStatusResponse)
async def observer_status(
    refresh_qr: bool = Query(default=False),
    evolution_api: EvolutionApiService = Depends(get_evolution_api_service),
) -> ObserverStatusResponse:
    return await evolution_api.get_observer_status(refresh_qr=refresh_qr)

