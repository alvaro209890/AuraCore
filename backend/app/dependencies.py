from __future__ import annotations

from functools import lru_cache

from fastapi import Depends, Header, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.config import Settings
from app.services.account_registry import AccountRecord, AccountRegistry
from app.services.firebase_auth import FirebaseAuthError, FirebaseAuthService, VerifiedFirebaseUser
from app.services.observer_gateway import WhatsAppAgentGatewayService
from app.services.service_bundle import ServiceBundle, ServiceBundleCache
from app.services.supabase_store import SupabaseStore

bearer_scheme = HTTPBearer(auto_error=False)


@lru_cache
def get_settings() -> Settings:
    return Settings()


@lru_cache
def get_account_registry() -> AccountRegistry:
    settings = get_settings()
    return AccountRegistry(
        database_root=settings.normalized_database_root,
        registry_path=settings.auth_registry_path,
        message_retention_max_rows=min(
            settings.message_retention_max_rows,
            settings.memory_analysis_max_messages,
        ),
        first_analysis_queue_limit=min(
            settings.memory_first_analysis_max_messages,
            settings.memory_analysis_max_messages,
        ),
    )


@lru_cache
def get_firebase_auth_service() -> FirebaseAuthService:
    return FirebaseAuthService(settings=get_settings())


@lru_cache
def get_service_bundle_cache() -> ServiceBundleCache:
    return ServiceBundleCache(base_settings=get_settings())


@lru_cache
def get_system_supabase_store() -> SupabaseStore:
    settings = get_settings()
    return SupabaseStore(
        database_path=settings.system_gateway_database_path,
        default_user_id=settings.system_user_id,
        message_retention_max_rows=min(
            settings.message_retention_max_rows,
            settings.memory_analysis_max_messages,
        ),
        first_analysis_queue_limit=min(
            settings.memory_first_analysis_max_messages,
            settings.memory_analysis_max_messages,
        ),
    )


@lru_cache
def get_global_whatsapp_agent_gateway_service():
    return WhatsAppAgentGatewayService(settings=get_settings())


def require_internal_api_token(
    x_internal_api_token: str | None = Header(default=None),
    settings: Settings = Depends(get_settings),
) -> None:
    if x_internal_api_token != settings.internal_api_token:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid internal API token.")


def get_verified_firebase_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    auth_service: FirebaseAuthService = Depends(get_firebase_auth_service),
) -> VerifiedFirebaseUser:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Bearer token ausente.")
    try:
        return auth_service.verify_bearer_token(credentials.credentials)
    except FirebaseAuthError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc


def get_current_account_optional(
    identity: VerifiedFirebaseUser = Depends(get_verified_firebase_user),
    registry: AccountRegistry = Depends(get_account_registry),
) -> AccountRecord | None:
    account = registry.get_account_by_firebase_uid(identity.uid)
    if account is None:
        return None
    try:
        synced = registry.sync_account_email(firebase_uid=identity.uid, email=identity.email)
    except Exception:
        synced = None
    return synced or account


def get_current_account(
    account: AccountRecord | None = Depends(get_current_account_optional),
) -> AccountRecord:
    if account is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Conta autenticada, mas ainda nao provisionada no AuraCore.",
        )
    if account.status != "active":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Conta do AuraCore indisponivel.")
    return account


def get_internal_account(
    _: None = Depends(require_internal_api_token),
    x_auracore_user_id: str | None = Header(default=None),
    registry: AccountRegistry = Depends(get_account_registry),
) -> AccountRecord:
    normalized_user_id = (x_auracore_user_id or "").strip()
    if not normalized_user_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cabecalho x-auracore-user-id ausente na chamada interna.",
        )
    account = registry.get_account_by_app_user_id(normalized_user_id)
    if account is None or account.status != "active":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Usuario interno do AuraCore invalido.")
    return account


def get_service_bundle(
    account: AccountRecord = Depends(get_current_account),
    cache: ServiceBundleCache = Depends(get_service_bundle_cache),
) -> ServiceBundle:
    return cache.get_bundle(account)


def get_internal_service_bundle(
    account: AccountRecord = Depends(get_internal_account),
    cache: ServiceBundleCache = Depends(get_service_bundle_cache),
) -> ServiceBundle:
    return cache.get_bundle(account)


def get_supabase_store(bundle: ServiceBundle = Depends(get_service_bundle)) -> SupabaseStore:
    return bundle.store


def get_internal_supabase_store(bundle: ServiceBundle = Depends(get_internal_service_bundle)) -> SupabaseStore:
    return bundle.store


def get_internal_storage_store(
    _: None = Depends(require_internal_api_token),
    x_auracore_system_scope: str | None = Header(default=None),
    x_auracore_user_id: str | None = Header(default=None),
    cache: ServiceBundleCache = Depends(get_service_bundle_cache),
    registry: AccountRegistry = Depends(get_account_registry),
) -> SupabaseStore:
    system_scope = (x_auracore_system_scope or "").strip().lower()
    if system_scope == "global-agent":
        return get_system_supabase_store()

    normalized_user_id = (x_auracore_user_id or "").strip()
    if not normalized_user_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cabecalho x-auracore-user-id ausente na chamada interna.",
        )
    account = registry.get_account_by_app_user_id(normalized_user_id)
    if account is None or account.status != "active":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Usuario interno do AuraCore invalido.")
    return cache.get_bundle(account).store


def get_observer_gateway_service(bundle: ServiceBundle = Depends(get_service_bundle)):
    return bundle.observer_gateway


def get_internal_observer_gateway_service(bundle: ServiceBundle = Depends(get_internal_service_bundle)):
    return bundle.observer_gateway


def get_whatsapp_agent_gateway_service():
    return get_global_whatsapp_agent_gateway_service()


def get_internal_whatsapp_agent_gateway_service():
    return get_global_whatsapp_agent_gateway_service()


def get_deepseek_service(bundle: ServiceBundle = Depends(get_service_bundle)):
    return bundle.deepseek_service


def get_groq_service(bundle: ServiceBundle = Depends(get_service_bundle)):
    return bundle.groq_service


def get_assistant_context_service(bundle: ServiceBundle = Depends(get_service_bundle)):
    return bundle.assistant_context_service


def get_assistant_reply_service(bundle: ServiceBundle = Depends(get_service_bundle)):
    return bundle.assistant_reply_service


def get_memory_analysis_service(bundle: ServiceBundle = Depends(get_service_bundle)):
    return bundle.memory_service


def get_memory_job_service(bundle: ServiceBundle = Depends(get_service_bundle)):
    return bundle.memory_job_service


def get_automation_service(bundle: ServiceBundle = Depends(get_service_bundle)):
    return bundle.automation_service


def get_internal_automation_service(bundle: ServiceBundle = Depends(get_internal_service_bundle)):
    return bundle.automation_service


def get_whatsapp_agent_service(bundle: ServiceBundle = Depends(get_service_bundle)):
    return bundle.whatsapp_agent_service


def get_internal_whatsapp_agent_service(bundle: ServiceBundle = Depends(get_internal_service_bundle)):
    return bundle.whatsapp_agent_service


def get_proactive_assistant_service(bundle: ServiceBundle = Depends(get_service_bundle)):
    return bundle.proactive_assistant_service


def get_agenda_guardian_service(bundle: ServiceBundle = Depends(get_service_bundle)):
    return bundle.agenda_guardian_service


def warm_registered_accounts() -> None:
    registry = get_account_registry()
    cache = get_service_bundle_cache()
    for account in registry.list_active_accounts():
        cache.warm_bundle(account)
