"""Account management service — syncs with Zernio's connected TikTok accounts.

Accounts are connected on Zernio's dashboard. This service mirrors them locally.
"""

import logging
from datetime import datetime

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from config import settings
from db.models import Account, HealthStatus
from services import zernio

logger = logging.getLogger(__name__)


class AccountLimitError(Exception):
    pass


async def get_account_count(db: AsyncSession) -> int:
    result = await db.execute(select(func.count(Account.id)))
    return result.scalar_one()


async def get_all_accounts(db: AsyncSession) -> list[Account]:
    result = await db.execute(select(Account).order_by(Account.connected_at))
    return list(result.scalars().all())


async def get_account(db: AsyncSession, account_id: int) -> Account | None:
    result = await db.execute(select(Account).where(Account.id == account_id))
    return result.scalar_one_or_none()


async def get_account_by_zernio_id(db: AsyncSession, zernio_id: str) -> Account | None:
    result = await db.execute(select(Account).where(Account.zernio_id == zernio_id))
    return result.scalar_one_or_none()


async def sync_accounts_from_zernio(db: AsyncSession) -> list[Account]:
    """Pull TikTok accounts from Zernio and mirror locally.

    Zernio handles all account connections — we just read what's there.
    Each Zernio profile has 1 TikTok account. We pull all TikTok accounts
    across all profiles.
    """
    tiktok_accounts = await zernio.list_accounts()

    synced = []
    for za in tiktok_accounts:
        zernio_id = str(za.get("_id", za.get("id")))
        existing = await get_account_by_zernio_id(db, zernio_id)

        if existing:
            existing.display_name = za.get("displayName", za.get("name", existing.display_name))
            existing.username = za.get("username", existing.username)
            existing.avatar_url = za.get("avatarUrl", za.get("avatar", existing.avatar_url))
            existing.profile_id = za.get("profileId", existing.profile_id)
            existing.last_synced_at = datetime.utcnow()
            synced.append(existing)
        else:
            account = Account(
                zernio_id=zernio_id,
                profile_id=za.get("profileId"),
                display_name=za.get("displayName", za.get("name", "TikTok Account")),
                username=za.get("username"),
                avatar_url=za.get("avatarUrl", za.get("avatar")),
                health_status=HealthStatus.healthy,
                last_synced_at=datetime.utcnow(),
            )
            db.add(account)
            synced.append(account)
            logger.info(f"Synced new account from Zernio: {account.display_name}")

    await db.commit()
    for a in synced:
        await db.refresh(a)

    return synced


async def disconnect_account(db: AsyncSession, account_id: int) -> bool:
    """Remove account locally. Does NOT disconnect from Zernio — do that on their dashboard."""
    account = await get_account(db, account_id)
    if not account:
        return False

    await db.delete(account)
    await db.commit()
    logger.info(f"Removed local account: {account.display_name}")
    return True


async def update_account_health(
    db: AsyncSession, account_id: int, status: HealthStatus
) -> Account | None:
    account = await get_account(db, account_id)
    if not account:
        return None
    account.health_status = status
    await db.commit()
    await db.refresh(account)
    return account
