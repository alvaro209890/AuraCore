from __future__ import annotations

from fastapi import APIRouter, Body, Depends, HTTPException

from app.config import Settings
from app.dependencies import get_account_registry, get_settings, get_whatsapp_agent_gateway_service
from app.schemas import GlobalAgentStatusResponse, UpdateWhatsAppAgentAdminContactRequest, WhatsAppAgentAdminContactsListResponse
from app.services.account_registry import AccountRegistry
from app.services.observer_gateway import ObserverGatewayError, WhatsAppAgentGatewayService
from app.services.supabase_store import SupabaseStore

router = APIRouter(prefix="/api/global-agent", tags=["global-agent"])


def _get_default_agent_store(
    settings: Settings = Depends(get_settings),
 ) -> SupabaseStore:
    return SupabaseStore(
        database_path=settings.database_path,
        default_user_id=settings.default_user_id,
        message_retention_max_rows=min(
            settings.message_retention_max_rows,
            settings.memory_analysis_max_messages,
        ),
        first_analysis_queue_limit=min(
            settings.memory_first_analysis_max_messages,
            settings.memory_analysis_max_messages,
        ),
    )


@router.get("/status", response_model=GlobalAgentStatusResponse)
async def get_global_agent_status(
    registry: AccountRegistry = Depends(get_account_registry),
    gateway: WhatsAppAgentGatewayService = Depends(get_whatsapp_agent_gateway_service),
) -> GlobalAgentStatusResponse:
    try:
        status = await gateway.get_agent_status()
    except ObserverGatewayError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return _to_global_agent_status(status=status, registry=registry)


@router.post("/connect", response_model=GlobalAgentStatusResponse)
async def connect_global_agent(
    registry: AccountRegistry = Depends(get_account_registry),
    gateway: WhatsAppAgentGatewayService = Depends(get_whatsapp_agent_gateway_service),
) -> GlobalAgentStatusResponse:
    try:
        status = await gateway.connect_agent()
    except ObserverGatewayError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return _to_global_agent_status(status=status, registry=registry)


@router.post("/reset", response_model=GlobalAgentStatusResponse)
async def reset_global_agent(
    registry: AccountRegistry = Depends(get_account_registry),
    gateway: WhatsAppAgentGatewayService = Depends(get_whatsapp_agent_gateway_service),
) -> GlobalAgentStatusResponse:
    try:
        status = await gateway.reset_agent()
    except ObserverGatewayError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return _to_global_agent_status(status=status, registry=registry)


@router.get("/admin-contacts", response_model=WhatsAppAgentAdminContactsListResponse)
async def list_global_agent_admin_contacts(
    settings: Settings = Depends(get_settings),
    store: SupabaseStore = Depends(_get_default_agent_store),
) -> WhatsAppAgentAdminContactsListResponse:
    _ensure_default_admin_contact(settings=settings, store=store)
    contacts = store.list_known_contacts(user_id=settings.default_user_id, limit=200)
    return WhatsAppAgentAdminContactsListResponse(
        contacts=[
            {
                "id": contact.id,
                "user_id": str(contact.user_id),
                "contact_phone": contact.contact_phone,
                "chat_jid": contact.chat_jid,
                "contact_name": contact.contact_name,
                "name_source": contact.name_source,
                "is_admin": contact.is_admin,
                "last_seen_at": contact.last_seen_at,
                "admin_updated_at": contact.admin_updated_at,
                "updated_at": contact.updated_at,
            }
            for contact in contacts
        ],
    )


@router.put("/admin-contacts", response_model=WhatsAppAgentAdminContactsListResponse)
async def update_global_agent_admin_contact(
    payload: UpdateWhatsAppAgentAdminContactRequest = Body(...),
    settings: Settings = Depends(get_settings),
    store: SupabaseStore = Depends(_get_default_agent_store),
) -> WhatsAppAgentAdminContactsListResponse:
    _ensure_default_admin_contact(settings=settings, store=store)
    updated = store.set_known_contact_admin(
        user_id=settings.default_user_id,
        contact_phone=payload.contact_phone,
        chat_jid=payload.chat_jid,
        contact_name=payload.contact_name,
        is_admin=payload.is_admin,
    )
    if updated is None:
        raise HTTPException(status_code=400, detail="Contato invalido para atualizar admin.")
    contacts = store.list_known_contacts(user_id=settings.default_user_id, limit=200)
    return WhatsAppAgentAdminContactsListResponse(
        contacts=[
            {
                "id": contact.id,
                "user_id": str(contact.user_id),
                "contact_phone": contact.contact_phone,
                "chat_jid": contact.chat_jid,
                "contact_name": contact.contact_name,
                "name_source": contact.name_source,
                "is_admin": contact.is_admin,
                "last_seen_at": contact.last_seen_at,
                "admin_updated_at": contact.admin_updated_at,
                "updated_at": contact.updated_at,
            }
            for contact in contacts
        ],
    )


def _to_global_agent_status(
    *,
    status,
    registry: AccountRegistry,
) -> GlobalAgentStatusResponse:
    mapped_accounts = [
        account
        for account in registry.list_active_accounts()
        if account.observer_owner_phone
    ]
    return GlobalAgentStatusResponse(
        instance_name=status.instance_name,
        connected=status.connected,
        state=status.state,
        gateway_ready=status.gateway_ready,
        mapped_accounts_count=len(mapped_accounts),
        owner_number=status.owner_number,
        qr_code=status.qr_code,
        qr_expires_in_sec=status.qr_expires_in_sec,
        last_seen_at=status.last_seen_at,
        last_error=status.last_error,
        current_username=None,
        current_user_observer_phone=None,
    )


def _ensure_default_admin_contact(*, settings: Settings, store: SupabaseStore) -> None:
    owner_phone = settings.normalized_whatsapp_cli_owner_phone
    if not owner_phone:
        return
    store.upsert_known_contact(
        user_id=settings.default_user_id,
        contact_phone=owner_phone,
        chat_jid=None,
        contact_name="Alvaro",
        name_source="system_seed",
        seen_at=None,
        is_admin=True,
    )
