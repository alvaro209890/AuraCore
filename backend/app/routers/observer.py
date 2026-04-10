from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from app.dependencies import get_memory_job_service, get_observer_gateway_service
from app.schemas import ObserverMessageRefreshResponse, ObserverStatusResponse
from app.services.memory_job_service import MemoryJobService
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
    memory_job_service: MemoryJobService = Depends(get_memory_job_service),
    gateway: ObserverGatewayService = Depends(get_observer_gateway_service),
) -> ObserverMessageRefreshResponse:
    sync_run = await memory_job_service.start_manual_sync(trigger="manual")
    try:
        status = await gateway.refresh_observer_messages()
    except Exception as error:
        memory_job_service.mark_sync_failed(sync_run_id=sync_run.id, error_text=str(error))
        raise
    memory_job_service.finalize_manual_sync(sync_run_id=sync_run.id)
    return ObserverMessageRefreshResponse(
        status=status,
        message=(
            "Nova sincronizacao do WhatsApp concluida. O AuraCore releu apenas chats diretos e salvou "
            "as mensagens no Supabase sem disparar analise automatica. Agora voce pode abrir a aba de "
            "memoria e rodar a analise manual quando quiser."
        ),
        sync_run_id=sync_run.id,
    )


@router.get("/status", response_model=ObserverStatusResponse)
async def observer_status(
    refresh_qr: bool = Query(default=False),
    gateway: ObserverGatewayService = Depends(get_observer_gateway_service),
) -> ObserverStatusResponse:
    return await gateway.get_observer_status(refresh_qr=refresh_qr)
