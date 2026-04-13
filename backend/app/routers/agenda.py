from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Query

from app.dependencies import get_current_account, get_supabase_store
from app.schemas import AgendaConflictResponse, AgendaEventResponse, AgendaEventsListResponse
from app.services.account_registry import AccountRecord
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
                created_at=event.created_at,
                updated_at=event.updated_at,
            )
        )
    return AgendaEventsListResponse(events=responses)


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
