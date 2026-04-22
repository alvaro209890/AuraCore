from __future__ import annotations

from fastapi import APIRouter, Body, Depends, HTTPException, Query

from app.dependencies import get_proactive_assistant_service, get_whatsapp_agent_service
from app.schemas import (
    ProactiveCandidateResponse,
    ProactiveDeliveryLogResponse,
    ProactiveCandidatesListResponse,
    ProactiveDeliveryLogsListResponse,
    ProactivePreferencesResponse,
    SimpleOkResponse,
    UpdateProactivePreferencesRequest,
    UpdateWhatsAppAgentSettingsRequest,
    WhatsAppAgentMessagesListResponse,
    WhatsAppAgentSettingsResponse,
    WhatsAppAgentStatusResponse,
    WhatsAppAgentThreadsListResponse,
    WhatsAppAgentWorkspaceResponse,
)
from app.services.observer_gateway import ObserverGatewayError
from app.services.proactive_assistant_service import ProactiveAssistantService
from app.services.whatsapp_agent_service import WhatsAppAgentService

router = APIRouter(prefix="/api/whatsapp-agent", tags=["whatsapp-agent"])


@router.get("/status", response_model=WhatsAppAgentStatusResponse)
async def get_agent_status(
    agent_service: WhatsAppAgentService = Depends(get_whatsapp_agent_service),
) -> WhatsAppAgentStatusResponse:
    try:
        return await agent_service.get_status()
    except ObserverGatewayError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.post("/connect", response_model=WhatsAppAgentStatusResponse)
async def connect_agent(
    agent_service: WhatsAppAgentService = Depends(get_whatsapp_agent_service),
) -> WhatsAppAgentStatusResponse:
    try:
        return await agent_service.connect_agent()
    except ObserverGatewayError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.post("/reset", response_model=WhatsAppAgentStatusResponse)
async def reset_agent(
    agent_service: WhatsAppAgentService = Depends(get_whatsapp_agent_service),
) -> WhatsAppAgentStatusResponse:
    try:
        return await agent_service.reset_agent()
    except ObserverGatewayError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.get("/settings", response_model=WhatsAppAgentSettingsResponse)
async def get_agent_settings(
    agent_service: WhatsAppAgentService = Depends(get_whatsapp_agent_service),
) -> WhatsAppAgentSettingsResponse:
    try:
        snapshot = await agent_service.build_workspace()
    except ObserverGatewayError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return snapshot.settings


@router.put("/settings", response_model=WhatsAppAgentSettingsResponse)
async def update_agent_settings(
    payload: UpdateWhatsAppAgentSettingsRequest = Body(...),
    agent_service: WhatsAppAgentService = Depends(get_whatsapp_agent_service),
) -> WhatsAppAgentSettingsResponse:
    return agent_service.update_settings(auto_reply_enabled=payload.auto_reply_enabled)


@router.get("/proactivity/settings", response_model=ProactivePreferencesResponse)
async def get_proactive_settings(
    proactive_service: ProactiveAssistantService = Depends(get_proactive_assistant_service),
) -> ProactivePreferencesResponse:
    return _to_proactive_preferences_response(proactive_service.get_preferences())


@router.put("/proactivity/settings", response_model=ProactivePreferencesResponse)
async def update_proactive_settings(
    payload: UpdateProactivePreferencesRequest = Body(...),
    proactive_service: ProactiveAssistantService = Depends(get_proactive_assistant_service),
) -> ProactivePreferencesResponse:
    settings = proactive_service.update_preferences(
        enabled=payload.enabled,
        intensity=payload.intensity,
        presence_mode=payload.presence_mode,
        humor_style=payload.humor_style,
        quiet_hours_start=payload.quiet_hours_start,
        quiet_hours_end=payload.quiet_hours_end,
        max_unsolicited_per_day=payload.max_unsolicited_per_day,
        min_interval_minutes=payload.min_interval_minutes,
        agenda_enabled=payload.agenda_enabled,
        followups_enabled=payload.followups_enabled,
        projects_enabled=payload.projects_enabled,
        routine_enabled=payload.routine_enabled,
        morning_digest_enabled=payload.morning_digest_enabled,
        night_digest_enabled=payload.night_digest_enabled,
        morning_digest_time=payload.morning_digest_time,
        night_digest_time=payload.night_digest_time,
    )
    return _to_proactive_preferences_response(settings)


@router.get("/proactivity/candidates", response_model=ProactiveCandidatesListResponse)
async def list_proactive_candidates(
    limit: int = Query(default=30, ge=1, le=100),
    status: list[str] | None = Query(default=None),
    proactive_service: ProactiveAssistantService = Depends(get_proactive_assistant_service),
) -> ProactiveCandidatesListResponse:
    candidates = proactive_service.list_candidates(limit=limit, statuses=status)
    return ProactiveCandidatesListResponse(
        candidates=[_to_proactive_candidate_response(candidate) for candidate in candidates],
    )


@router.post("/proactivity/candidates/{candidate_id}/dismiss", response_model=SimpleOkResponse)
async def dismiss_proactive_candidate(
    candidate_id: str,
    proactive_service: ProactiveAssistantService = Depends(get_proactive_assistant_service),
) -> SimpleOkResponse:
    if proactive_service.update_candidate_status(candidate_id=candidate_id, status="dismissed") is None:
        raise HTTPException(status_code=404, detail="Candidato proativo não encontrado.")
    return SimpleOkResponse()


@router.post("/proactivity/candidates/{candidate_id}/confirm", response_model=SimpleOkResponse)
async def confirm_proactive_candidate(
    candidate_id: str,
    proactive_service: ProactiveAssistantService = Depends(get_proactive_assistant_service),
) -> SimpleOkResponse:
    if proactive_service.update_candidate_status(candidate_id=candidate_id, status="confirmed") is None:
        raise HTTPException(status_code=404, detail="Candidato proativo não encontrado.")
    return SimpleOkResponse()


@router.post("/proactivity/candidates/{candidate_id}/complete", response_model=SimpleOkResponse)
async def complete_proactive_candidate(
    candidate_id: str,
    proactive_service: ProactiveAssistantService = Depends(get_proactive_assistant_service),
) -> SimpleOkResponse:
    if proactive_service.update_candidate_status(candidate_id=candidate_id, status="done") is None:
        raise HTTPException(status_code=404, detail="Candidato proativo não encontrado.")
    return SimpleOkResponse()


@router.get("/proactivity/deliveries", response_model=ProactiveDeliveryLogsListResponse)
async def list_proactive_deliveries(
    limit: int = Query(default=20, ge=1, le=100),
    proactive_service: ProactiveAssistantService = Depends(get_proactive_assistant_service),
) -> ProactiveDeliveryLogsListResponse:
    deliveries = proactive_service.list_deliveries(limit=limit)
    return ProactiveDeliveryLogsListResponse(
        deliveries=[_to_proactive_delivery_response(delivery) for delivery in deliveries],
    )


@router.post("/proactivity/tick", response_model=SimpleOkResponse)
async def run_proactive_tick(
    proactive_service: ProactiveAssistantService = Depends(get_proactive_assistant_service),
) -> SimpleOkResponse:
    await proactive_service.tick()
    return SimpleOkResponse()


@router.get("/workspace", response_model=WhatsAppAgentWorkspaceResponse)
async def get_agent_workspace(
    thread_id: str | None = Query(default=None),
    agent_service: WhatsAppAgentService = Depends(get_whatsapp_agent_service),
) -> WhatsAppAgentWorkspaceResponse:
    try:
        snapshot = await agent_service.build_workspace(thread_id=thread_id)
    except ObserverGatewayError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return WhatsAppAgentWorkspaceResponse(
        status=snapshot.status,
        settings=snapshot.settings,
        observer_status=snapshot.observer_status,
        active_thread_id=snapshot.active_thread_id,
        active_session=_to_session_response(snapshot.active_session),
        contact_memory=_to_contact_memory_response(snapshot.contact_memory),
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
        "session_id": message.session_id,
        "whatsapp_message_id": message.whatsapp_message_id,
        "source_inbound_message_id": message.source_inbound_message_id,
        "contact_phone": message.contact_phone,
        "chat_jid": message.chat_jid,
        "content": message.content,
        "message_timestamp": message.message_timestamp,
        "processing_status": message.processing_status,
        "learning_status": message.learning_status,
        "send_status": message.send_status,
        "error_text": message.error_text,
        "response_latency_ms": message.response_latency_ms,
        "model_run_id": message.model_run_id,
        "learned_at": message.learned_at,
        "metadata": message.metadata,
        "created_at": message.created_at,
    }


def _to_thread_response(thread, agent_service: WhatsAppAgentService):
    active_session = agent_service.get_active_session_for_thread(thread_id=thread.id)
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
        "active_session_id": active_session.id if active_session is not None else None,
        "session_started_at": active_session.started_at if active_session is not None else None,
        "session_last_activity_at": active_session.last_activity_at if active_session is not None else None,
        "session_message_count": (
            agent_service.store.count_whatsapp_agent_session_messages(session_id=active_session.id)
            if active_session is not None
            else 0
        ),
        "last_message_preview": preview,
        "last_message_at": thread.last_message_at,
        "last_inbound_at": thread.last_inbound_at,
        "last_outbound_at": thread.last_outbound_at,
        "last_error_at": thread.last_error_at,
        "last_error_text": thread.last_error_text,
        "created_at": thread.created_at,
        "updated_at": thread.updated_at,
    }


def _to_session_response(session) -> dict | None:
    if session is None:
        return None
    return {
        "id": session.id,
        "thread_id": session.thread_id,
        "contact_phone": session.contact_phone,
        "chat_jid": session.chat_jid,
        "started_at": session.started_at,
        "last_activity_at": session.last_activity_at,
        "ended_at": session.ended_at,
        "reset_reason": session.reset_reason,
        "created_at": session.created_at,
        "updated_at": session.updated_at,
    }


def _to_contact_memory_response(memory) -> dict | None:
    if memory is None:
        return None
    return {
        "id": memory.id,
        "thread_id": memory.thread_id,
        "contact_name": memory.contact_name,
        "contact_phone": memory.contact_phone,
        "chat_jid": memory.chat_jid,
        "profile_summary": memory.profile_summary,
        "preferred_tone": memory.preferred_tone,
        "preferences": memory.preferences,
        "objectives": memory.objectives,
        "durable_facts": memory.durable_facts,
        "constraints": memory.constraints,
        "recurring_instructions": memory.recurring_instructions,
        "learned_message_count": memory.learned_message_count,
        "last_learned_at": memory.last_learned_at,
        "updated_at": memory.updated_at,
    }


def _to_proactive_preferences_response(settings) -> ProactivePreferencesResponse:
    return ProactivePreferencesResponse(
        user_id=str(settings.user_id),
        enabled=settings.enabled,
        intensity=settings.intensity,
        presence_mode=settings.presence_mode,
        humor_style=settings.humor_style,
        quiet_hours_start=settings.quiet_hours_start,
        quiet_hours_end=settings.quiet_hours_end,
        max_unsolicited_per_day=settings.max_unsolicited_per_day,
        min_interval_minutes=settings.min_interval_minutes,
        agenda_enabled=settings.agenda_enabled,
        followups_enabled=settings.followups_enabled,
        projects_enabled=settings.projects_enabled,
        routine_enabled=settings.routine_enabled,
        morning_digest_enabled=settings.morning_digest_enabled,
        night_digest_enabled=settings.night_digest_enabled,
        morning_digest_time=settings.morning_digest_time,
        night_digest_time=settings.night_digest_time,
        updated_at=settings.updated_at,
    )


def _to_proactive_candidate_response(candidate) -> ProactiveCandidateResponse:
    return ProactiveCandidateResponse(
        id=candidate.id,
        category=candidate.category,
        status=candidate.status,
        source_message_id=candidate.source_message_id,
        source_kind=candidate.source_kind,
        thread_id=candidate.thread_id,
        contact_phone=candidate.contact_phone,
        chat_jid=candidate.chat_jid,
        title=candidate.title,
        summary=candidate.summary,
        confidence=candidate.confidence,
        priority=candidate.priority,
        due_at=candidate.due_at,
        cooldown_until=candidate.cooldown_until,
        last_nudged_at=candidate.last_nudged_at,
        payload_json=candidate.payload_json,
        created_at=candidate.created_at,
        updated_at=candidate.updated_at,
    )


def _to_proactive_delivery_response(delivery) -> ProactiveDeliveryLogResponse:
    return ProactiveDeliveryLogResponse(
        id=delivery.id,
        candidate_id=delivery.candidate_id,
        category=delivery.category,
        decision=delivery.decision,
        score=delivery.score,
        reason_code=delivery.reason_code,
        reason_text=delivery.reason_text,
        message_text=delivery.message_text,
        message_id=delivery.message_id,
        sent_at=delivery.sent_at,
        created_at=delivery.created_at,
    )
