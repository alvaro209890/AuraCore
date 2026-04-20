from __future__ import annotations

from datetime import UTC, datetime, timedelta
from dateutil import parser as dateutil_parser

from fastapi import APIRouter, Depends, HTTPException, Query

from app.dependencies import get_agenda_guardian_service, get_current_account, get_supabase_store
from app.schemas import (
    AgendaConflictResponse,
    AgendaEventResponse,
    AgendaEventsListResponse,
    AgendaPendingConfirmationResolveRequest,
    AgendaPendingConfirmationResolveResponse,
    AgendaPendingConfirmationResponse,
    AgendaPendingEventResponse,
    AgendaQueryRequest,
    AgendaQueryResponse,
    CreateAgendaEventRequest,
    SimpleOkResponse,
    UpdateAgendaEventRequest,
)
from app.services.account_registry import AccountRecord
from app.services.agenda_guardian_service import AgendaGuardianService
from app.services.supabase_store import AgendaEventRecord, SupabaseStore

router = APIRouter(prefix="/api/agenda", tags=["agenda"])


@router.get("", response_model=AgendaEventsListResponse)
async def list_agenda_events(
    limit: int = Query(default=120, ge=1, le=300),
    upcoming_only: bool = Query(default=False),
    account: AccountRecord = Depends(get_current_account),
    store: SupabaseStore = Depends(get_supabase_store),
) -> AgendaEventsListResponse:
    starts_after = datetime.now(UTC) if upcoming_only else None
    events = store.list_agenda_events(
        user_id=account.app_user_id,
        limit=limit,
        starts_after=starts_after,
    )
    responses: list[AgendaEventResponse] = []
    for event in events:
        conflict = _resolve_first_conflict(store=store, event=event)
        responses.append(
            AgendaEventResponse(
                id=event.id,
                titulo=event.titulo,
                inicio=event.inicio,
                fim=event.fim,
                status=event.status,
                contato_origem=event.contato_origem,
                message_id=event.message_id,
                has_conflict=conflict is not None,
                conflict=conflict,
                reminder_offset_minutes=event.reminder_offset_minutes,
                reminder_eligible=event.status == "firme",
                reminder_block_reason=None if event.status == "firme" else "Eventos tentativos nao disparam lembretes automáticos.",
                pre_reminder_at=_resolve_pre_reminder_at(event),
                pre_reminder_sent_at=event.pre_reminder_sent_at,
                reminder_sent_at=event.reminder_sent_at,
                recurrence_rule=event.recurrence_rule,
                parent_event_id=event.parent_event_id,
                excluded_dates=event.excluded_dates,
                created_at=event.created_at,
                updated_at=event.updated_at,
            )
    )
    return AgendaEventsListResponse(events=responses)


@router.post("", response_model=AgendaEventResponse)
async def create_agenda_event(
    payload: CreateAgendaEventRequest,
    account: AccountRecord = Depends(get_current_account),
    store: SupabaseStore = Depends(get_supabase_store),
) -> AgendaEventResponse:
    if payload.fim <= payload.inicio:
        raise HTTPException(status_code=400, detail="O fim do compromisso precisa ser depois do inicio.")
    created = store.create_agenda_event(
        user_id=account.app_user_id,
        titulo=payload.titulo,
        inicio=payload.inicio,
        fim=payload.fim,
        status=payload.status,
        contato_origem=payload.contato_origem,
        reminder_offset_minutes=payload.reminder_offset_minutes,
        recurrence_rule=payload.recurrence_rule,
        created_at=datetime.now(UTC),
    )
    return _to_agenda_event_response(store=store, event=created)


@router.put("/{event_id}", response_model=AgendaEventResponse)
async def update_agenda_event(
    event_id: str,
    payload: UpdateAgendaEventRequest,
    account: AccountRecord = Depends(get_current_account),
    store: SupabaseStore = Depends(get_supabase_store),
) -> AgendaEventResponse:
    existing = store.get_agenda_event(user_id=account.app_user_id, event_id=event_id)
    if existing is None:
        raise HTTPException(status_code=404, detail="Compromisso nao encontrado.")
    effective_inicio = payload.inicio or existing.inicio
    effective_fim = payload.fim or existing.fim
    if effective_fim <= effective_inicio:
        raise HTTPException(status_code=400, detail="O fim do compromisso precisa ser depois do inicio.")
    updated = store.update_agenda_event(
        user_id=account.app_user_id,
        event_id=event_id,
        titulo=payload.titulo,
        inicio=payload.inicio,
        fim=payload.fim,
        status=payload.status,
        contato_origem=payload.contato_origem,
        reminder_offset_minutes=payload.reminder_offset_minutes,
        recurrence_rule=payload.recurrence_rule,
        excluded_dates=payload.excluded_dates,
        reset_reminder=True,
    )
    if updated is None:
        raise HTTPException(status_code=404, detail="Compromisso nao encontrado.")
    return _to_agenda_event_response(store=store, event=updated)


@router.delete("/{event_id}", response_model=SimpleOkResponse)
async def delete_agenda_event(
    event_id: str,
    account: AccountRecord = Depends(get_current_account),
    store: SupabaseStore = Depends(get_supabase_store),
) -> SimpleOkResponse:
    deleted = store.delete_agenda_event(user_id=account.app_user_id, event_id=event_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Compromisso nao encontrado.")
    return SimpleOkResponse()


@router.post("/query", response_model=AgendaQueryResponse)
async def query_agenda_events(
    payload: AgendaQueryRequest,
    account: AccountRecord = Depends(get_current_account),
    agenda_guardian: AgendaGuardianService = Depends(get_agenda_guardian_service),
    store: SupabaseStore = Depends(get_supabase_store),
) -> AgendaQueryResponse:
    reference_now = payload.reference_now or datetime.now(UTC)
    result = await agenda_guardian.handle_agenda_query(
        user_id=account.app_user_id,
        text=payload.text,
        reference_now=reference_now,
    )
    return AgendaQueryResponse(
        is_query=result.is_query,
        time_range_description=result.time_range_description,
        assistant_reply=result.assistant_reply,
        events=[_to_agenda_event_response(store=store, event=event) for event in result.events],
    )


@router.get("/pending-confirmation", response_model=AgendaPendingConfirmationResponse)
async def get_pending_agenda_confirmation(
    account: AccountRecord = Depends(get_current_account),
    agenda_guardian: AgendaGuardianService = Depends(get_agenda_guardian_service),
) -> AgendaPendingConfirmationResponse:
    pending = agenda_guardian.get_pending_event(account.app_user_id)
    if pending is None:
        return AgendaPendingConfirmationResponse(has_pending_confirmation=False)

    try:
        inicio = dateutil_parser.parse(pending.event_data.get("inicio")) if pending.event_data.get("inicio") else None
        fim = dateutil_parser.parse(pending.event_data.get("fim")) if pending.event_data.get("fim") else None
    except Exception:
        inicio = None
        fim = None

    return AgendaPendingConfirmationResponse(
        has_pending_confirmation=True,
        pending_event=AgendaPendingEventResponse(
            titulo=str(pending.event_data.get("titulo") or "Compromisso"),
            inicio=inicio,
            fim=fim,
            status="firme" if str(pending.event_data.get("status") or "").strip().lower() == "firme" else "tentativo",
            contato_origem=pending.event_data.get("contato_origem"),
            reminder_offset_minutes=max(0, int(pending.event_data.get("reminder_offset_minutes") or 0)),
            recurrence_rule=pending.event_data.get("recurrence_rule"),
            source_message_id=pending.source_message_id,
            created_at=pending.created_at,
            expires_at=pending.expires_at,
            confirmation_prompt=agenda_guardian._format_confirmation_request(pending.event_data),
        ),
    )


@router.post("/pending-confirmation/resolve", response_model=AgendaPendingConfirmationResolveResponse)
async def resolve_pending_agenda_confirmation(
    payload: AgendaPendingConfirmationResolveRequest,
    account: AccountRecord = Depends(get_current_account),
    agenda_guardian: AgendaGuardianService = Depends(get_agenda_guardian_service),
    store: SupabaseStore = Depends(get_supabase_store),
) -> AgendaPendingConfirmationResolveResponse:
    result = await agenda_guardian.check_pending_confirmation(
        user_id=account.app_user_id,
        text=payload.text,
    )
    if result is None:
        return AgendaPendingConfirmationResolveResponse(
            handled=False,
            action="none",
            skipped_reason="no_pending_confirmation",
        )
    return AgendaPendingConfirmationResolveResponse(
        handled=result.detected or bool(result.skipped_reason),
        action=result.action,
        saved_event=_to_agenda_event_response(store=store, event=result.saved_event) if result.saved_event else None,
        skipped_reason=result.skipped_reason,
    )


def _resolve_first_conflict(*, store: SupabaseStore, event: AgendaEventRecord) -> AgendaConflictResponse | None:
    conflicts = store.find_agenda_conflicts(
        user_id=event.user_id,
        inicio=event.inicio,
        fim=event.fim,
        exclude_message_id=event.message_id,
        limit=1,
    )
    if not conflicts:
        return None
    item = conflicts[0]
    return AgendaConflictResponse(
        id=item.id,
        titulo=item.titulo,
        inicio=item.inicio,
        fim=item.fim,
        status=item.status,
        contato_origem=item.contato_origem,
        message_id=item.message_id,
    )


def _to_agenda_event_response(*, store: SupabaseStore, event: AgendaEventRecord) -> AgendaEventResponse:
    conflict = _resolve_first_conflict(store=store, event=event)
    return AgendaEventResponse(
        id=event.id,
        titulo=event.titulo,
        inicio=event.inicio,
        fim=event.fim,
        status=event.status,
        contato_origem=event.contato_origem,
        message_id=event.message_id,
        has_conflict=conflict is not None,
        conflict=conflict,
        reminder_offset_minutes=event.reminder_offset_minutes,
        reminder_eligible=event.status == "firme",
        reminder_block_reason=None if event.status == "firme" else "Eventos tentativos nao disparam lembretes automáticos.",
        pre_reminder_at=_resolve_pre_reminder_at(event),
        pre_reminder_sent_at=event.pre_reminder_sent_at,
        reminder_sent_at=event.reminder_sent_at,
        recurrence_rule=event.recurrence_rule,
        parent_event_id=event.parent_event_id,
        excluded_dates=event.excluded_dates,
        created_at=event.created_at,
        updated_at=event.updated_at,
    )


def _resolve_pre_reminder_at(event: AgendaEventRecord) -> datetime | None:
    if event.status != "firme" or event.reminder_offset_minutes <= 0:
        return None
    return event.inicio - timedelta(minutes=event.reminder_offset_minutes)
