"""Tests for account management — unlimited accounts, CRUD."""

import pytest
from datetime import datetime

from db.models import Account, HealthStatus
from services.accounts import (
    get_all_accounts,
    get_account,
    get_account_count,
    disconnect_account,
    AccountLimitError,
)


@pytest.mark.asyncio
async def test_account_count_empty(db):
    count = await get_account_count(db)
    assert count == 0


@pytest.mark.asyncio
async def test_create_and_list_accounts(db):
    for i in range(3):
        account = Account(
            zernio_id=f"zernio_{i}",
            display_name=f"Account {i}",
            health_status=HealthStatus.healthy,
        )
        db.add(account)
    await db.commit()

    accounts = await get_all_accounts(db)
    assert len(accounts) == 3
    assert accounts[0].display_name == "Account 0"


@pytest.mark.asyncio
async def test_get_account_by_id(db):
    account = Account(
        zernio_id="zernio_test",
        display_name="Test Account",
        health_status=HealthStatus.healthy,
    )
    db.add(account)
    await db.commit()
    await db.refresh(account)

    fetched = await get_account(db, account.id)
    assert fetched is not None
    assert fetched.display_name == "Test Account"


@pytest.mark.asyncio
async def test_get_account_not_found(db):
    fetched = await get_account(db, 999)
    assert fetched is None


@pytest.mark.asyncio
async def test_disconnect_account(db):
    account = Account(
        zernio_id="zernio_del",
        display_name="To Delete",
        health_status=HealthStatus.healthy,
    )
    db.add(account)
    await db.commit()
    await db.refresh(account)

    # disconnect_account calls zernio_client which will fail in test,
    # but the local delete still works (it catches the exception)
    result = await disconnect_account(db, account.id)
    assert result is True

    count = await get_account_count(db)
    assert count == 0


@pytest.mark.asyncio
async def test_disconnect_nonexistent(db):
    result = await disconnect_account(db, 999)
    assert result is False


@pytest.mark.asyncio
async def test_unlimited_accounts(db):
    """No cap on account count — every Zernio account syncs through."""
    for i in range(12):
        account = Account(
            zernio_id=f"zernio_many_{i}",
            display_name=f"Account {i}",
            health_status=HealthStatus.healthy,
        )
        db.add(account)
    await db.commit()

    count = await get_account_count(db)
    assert count == 12


# --- API endpoint tests ---


@pytest.mark.asyncio
async def test_list_accounts_endpoint(client, db):
    response = await client.get("/api/accounts")
    assert response.status_code == 200
    data = response.json()
    assert data["count"] == 0
    assert data["max_accounts"] is None


@pytest.mark.asyncio
async def test_get_account_endpoint_not_found(client):
    response = await client.get("/api/accounts/999")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_health_check(client):
    response = await client.get("/api/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"
