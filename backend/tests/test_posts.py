"""Tests for post management — CRUD, status flow, retry logic."""

import pytest
from datetime import datetime, timedelta

from db.models import Account, Post, PostStatus, HealthStatus
from services.posts import (
    create_draft,
    get_post,
    list_posts,
    mark_ready,
    schedule_post,
    retry_failed,
    update_post,
    delete_post,
)


@pytest.fixture
async def account(db):
    a = Account(
        zernio_id="zernio_post_test",
        display_name="Post Test Account",
        health_status=HealthStatus.healthy,
    )
    db.add(a)
    await db.commit()
    await db.refresh(a)
    return a


@pytest.mark.asyncio
async def test_create_draft(db, account):
    post = await create_draft(db, account.id, caption="Test caption")
    assert post.id is not None
    assert post.status == PostStatus.draft
    assert post.caption == "Test caption"
    assert post.account_id == account.id


@pytest.mark.asyncio
async def test_create_draft_invalid_account(db):
    with pytest.raises(ValueError, match="Account not found"):
        await create_draft(db, 999, caption="No account")


@pytest.mark.asyncio
async def test_list_posts(db, account):
    await create_draft(db, account.id, caption="Post 1")
    await create_draft(db, account.id, caption="Post 2")

    posts, total = await list_posts(db)
    assert total == 2
    assert len(posts) == 2


@pytest.mark.asyncio
async def test_list_posts_filter_by_status(db, account):
    await create_draft(db, account.id, caption="Draft")
    post2 = await create_draft(db, account.id, caption="Ready")
    await mark_ready(db, post2.id)

    drafts, count = await list_posts(db, status=PostStatus.draft)
    assert count == 1
    assert drafts[0].caption == "Draft"

    ready, count = await list_posts(db, status=PostStatus.ready)
    assert count == 1
    assert ready[0].caption == "Ready"


@pytest.mark.asyncio
async def test_update_draft(db, account):
    post = await create_draft(db, account.id, caption="Old")
    updated = await update_post(db, post.id, caption="New")
    assert updated.caption == "New"


@pytest.mark.asyncio
async def test_cannot_update_published(db, account):
    post = await create_draft(db, account.id, caption="Test")
    post.status = PostStatus.published
    await db.commit()

    with pytest.raises(ValueError, match="Cannot edit"):
        await update_post(db, post.id, caption="Edit")


@pytest.mark.asyncio
async def test_mark_ready(db, account):
    post = await create_draft(db, account.id, caption="Test")
    ready = await mark_ready(db, post.id)
    assert ready.status == PostStatus.ready


@pytest.mark.asyncio
async def test_mark_ready_only_drafts(db, account):
    post = await create_draft(db, account.id, caption="Test")
    await mark_ready(db, post.id)

    with pytest.raises(ValueError, match="Only drafts"):
        await mark_ready(db, post.id)


@pytest.mark.asyncio
async def test_schedule_post(db, account):
    post = await create_draft(db, account.id, caption="Test")
    scheduled_time = datetime.utcnow() + timedelta(hours=2)
    scheduled = await schedule_post(db, post.id, scheduled_time)
    assert scheduled.status == PostStatus.scheduled
    assert scheduled.scheduled_at == scheduled_time


@pytest.mark.asyncio
async def test_retry_failed(db, account):
    post = await create_draft(db, account.id, caption="Test")
    post.status = PostStatus.failed
    post.retry_count = 3
    post.failure_reason = "some error"
    await db.commit()

    retried = await retry_failed(db, post.id)
    assert retried.status == PostStatus.scheduled
    assert retried.retry_count == 0
    assert retried.failure_reason is None


@pytest.mark.asyncio
async def test_retry_only_failed(db, account):
    post = await create_draft(db, account.id, caption="Test")
    with pytest.raises(ValueError, match="only retry failed"):
        await retry_failed(db, post.id)


@pytest.mark.asyncio
async def test_delete_draft(db, account):
    post = await create_draft(db, account.id, caption="Test")
    result = await delete_post(db, post.id)
    assert result is True

    fetched = await get_post(db, post.id)
    assert fetched is None


@pytest.mark.asyncio
async def test_cannot_delete_published(db, account):
    post = await create_draft(db, account.id, caption="Test")
    post.status = PostStatus.published
    await db.commit()

    with pytest.raises(ValueError, match="Cannot delete"):
        await delete_post(db, post.id)


# --- API endpoint tests ---


@pytest.mark.asyncio
async def test_list_posts_endpoint(client, db):
    response = await client.get("/api/posts")
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 0
    assert data["posts"] == []


@pytest.mark.asyncio
async def test_create_post_endpoint(client, db):
    # Create account first
    a = Account(
        zernio_id="zernio_api_post",
        display_name="API Post Test",
        health_status=HealthStatus.healthy,
    )
    db.add(a)
    await db.commit()
    await db.refresh(a)

    response = await client.post(
        "/api/posts",
        json={"account_id": a.id, "caption": "Hello TikTok"},
    )
    assert response.status_code == 201
    data = response.json()
    assert data["status"] == "draft"
    assert data["caption"] == "Hello TikTok"


@pytest.mark.asyncio
async def test_post_status_flow_endpoint(client, db):
    a = Account(
        zernio_id="zernio_flow",
        display_name="Flow Test",
        health_status=HealthStatus.healthy,
    )
    db.add(a)
    await db.commit()
    await db.refresh(a)

    # Create
    res = await client.post("/api/posts", json={"account_id": a.id, "caption": "Flow"})
    post_id = res.json()["id"]

    # Mark ready
    res = await client.post(f"/api/posts/{post_id}/ready")
    assert res.status_code == 200
    assert res.json()["status"] == "ready"

    # Schedule
    res = await client.post(
        f"/api/posts/{post_id}/schedule",
        json={"scheduled_at": "2026-05-01T12:00:00"},
    )
    assert res.status_code == 200
    assert res.json()["status"] == "scheduled"


@pytest.mark.asyncio
async def test_get_post_not_found(client):
    response = await client.get("/api/posts/999")
    assert response.status_code == 404
