from __future__ import annotations

from fastapi import APIRouter, Body, Depends, HTTPException, Query, status

from app.dependencies import (
    get_account_registry,
    get_current_account_optional,
    get_service_bundle_cache,
    get_verified_firebase_user,
)
from app.schemas import (
    AuthenticatedAccountResponse,
    RegisterAccountRequest,
    UsernameAvailabilityResponse,
)
from app.services.account_registry import (
    AccountRecord,
    AccountRegistry,
    AccountRegistryError,
    EmailAlreadyExistsError,
    UsernameAlreadyExistsError,
)
from app.services.firebase_auth import VerifiedFirebaseUser

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.get("/check-username", response_model=UsernameAvailabilityResponse)
async def check_username(
    username: str = Query(..., min_length=3, max_length=32),
    registry: AccountRegistry = Depends(get_account_registry),
) -> UsernameAvailabilityResponse:
    try:
        available, normalized = registry.is_username_available(username)
        return UsernameAvailabilityResponse(available=available, normalized_username=normalized, reason=None)
    except AccountRegistryError as exc:
        return UsernameAvailabilityResponse(available=False, normalized_username=None, reason=str(exc))


@router.get("/me", response_model=AuthenticatedAccountResponse)
async def get_me(
    identity: VerifiedFirebaseUser = Depends(get_verified_firebase_user),
    account: AccountRecord | None = Depends(get_current_account_optional),
) -> AuthenticatedAccountResponse:
    return _to_account_response(identity=identity, account=account)


@router.post("/register", response_model=AuthenticatedAccountResponse)
async def register_account(
    payload: RegisterAccountRequest = Body(...),
    identity: VerifiedFirebaseUser = Depends(get_verified_firebase_user),
    registry: AccountRegistry = Depends(get_account_registry),
    cache = Depends(get_service_bundle_cache),
) -> AuthenticatedAccountResponse:
    try:
        created = registry.provision_account(
            firebase_uid=identity.uid,
            email=identity.email,
            username=payload.username,
        )
    except UsernameAlreadyExistsError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except EmailAlreadyExistsError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except AccountRegistryError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    cache.warm_bundle(created)
    return _to_account_response(identity=identity, account=created)


def _to_account_response(
    *,
    identity: VerifiedFirebaseUser,
    account: AccountRecord | None,
) -> AuthenticatedAccountResponse:
    return AuthenticatedAccountResponse(
        firebase_uid=identity.uid,
        app_user_id=str(account.app_user_id) if account is not None else None,
        username=account.username if account is not None else None,
        email=account.email if account is not None else identity.email,
        email_verified=identity.email_verified,
        provisioned=account is not None and account.status == "active",
    )
