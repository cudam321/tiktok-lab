"""Account management endpoints.

Accounts are connected on Zernio's dashboard.
Use /api/accounts/sync to pull them into TikTok Lab.
"""

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from db.database import get_db
from db.models import HealthStatus
from services import accounts as account_service

router = APIRouter(prefix="/api/accounts", tags=["accounts"])


# --- Response Models ---


class AccountResponse(BaseModel):
    id: int
    zernio_id: str
    profile_id: str | None
    display_name: str
    username: str | None
    avatar_url: str | None
    niche: str | None
    health_status: HealthStatus
    connected_at: datetime
    last_synced_at: datetime | None

    model_config = {"from_attributes": True}


class AccountListResponse(BaseModel):
    accounts: list[AccountResponse]
    count: int
    # Retained for API compatibility. Null means unlimited (no cap). Kept so
    # the frontend type doesn't need to change if we ever reintroduce a cap.
    max_accounts: int | None = None


class UpdateAccountRequest(BaseModel):
    niche: str | None = None


# --- Routes ---


@router.get("", response_model=AccountListResponse)
async def list_accounts(db: AsyncSession = Depends(get_db)):
    accounts = await account_service.get_all_accounts(db)
    return AccountListResponse(
        accounts=[AccountResponse.model_validate(a) for a in accounts],
        count=len(accounts),
        max_accounts=None,
    )


@router.get("/sync", response_model=AccountListResponse)
async def sync_accounts(db: AsyncSession = Depends(get_db)):
    """Sync local accounts with Zernio's connected TikTok accounts.

    Call this after connecting accounts on Zernio's dashboard.
    """
    try:
        await account_service.sync_accounts_from_zernio(db)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Failed to sync from Zernio: {e}")

    all_accounts = await account_service.get_all_accounts(db)
    return AccountListResponse(
        accounts=[AccountResponse.model_validate(a) for a in all_accounts],
        count=len(all_accounts),
        max_accounts=None,
    )


@router.get("/{account_id}", response_model=AccountResponse)
async def get_account(account_id: int, db: AsyncSession = Depends(get_db)):
    account = await account_service.get_account(db, account_id)
    if not account:
        raise HTTPException(status_code=404, detail="Account not found")
    return AccountResponse.model_validate(account)


@router.patch("/{account_id}", response_model=AccountResponse)
async def update_account(
    account_id: int, body: UpdateAccountRequest, db: AsyncSession = Depends(get_db)
):
    account = await account_service.get_account(db, account_id)
    if not account:
        raise HTTPException(status_code=404, detail="Account not found")
    if body.niche is not None:
        account.niche = body.niche
        await db.commit()
        await db.refresh(account)
    return AccountResponse.model_validate(account)


@router.delete("/{account_id}")
async def remove_account(account_id: int, db: AsyncSession = Depends(get_db)):
    """Remove account from TikTok Lab. Does NOT disconnect from Zernio."""
    success = await account_service.disconnect_account(db, account_id)
    if not success:
        raise HTTPException(status_code=404, detail="Account not found")
    return {"detail": "Account removed"}
