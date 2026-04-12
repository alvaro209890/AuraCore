from __future__ import annotations

from fastapi import APIRouter, Depends

from app.dependencies import get_account_registry, require_internal_api_token
from app.schemas import ActiveAccountResponse, ActiveAccountsListResponse
from app.services.account_registry import AccountRegistry

router = APIRouter(prefix="/api/internal/accounts", tags=["internal"])


@router.get("/active", response_model=ActiveAccountsListResponse)
async def list_active_accounts(
    _: None = Depends(require_internal_api_token),
    registry: AccountRegistry = Depends(get_account_registry),
) -> ActiveAccountsListResponse:
    return ActiveAccountsListResponse(
        accounts=[
            ActiveAccountResponse(
                app_user_id=str(account.app_user_id),
                username=account.username,
            )
            for account in registry.list_active_accounts()
        ]
    )
