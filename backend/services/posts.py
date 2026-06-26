"""Post management service — create, schedule, publish, retry."""

import logging
from datetime import datetime, timedelta

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import Account, Post, PostStatus
from services import zernio

logger = logging.getLogger(__name__)

# Retry backoff: 30s, 2min, 10min
RETRY_DELAYS = [30, 120, 600]
MAX_RETRIES = 3


async def list_posts(
    db: AsyncSession,
    account_id: int | None = None,
    status: PostStatus | None = None,
    limit: int = 50,
    offset: int = 0,
) -> tuple[list[Post], int]:
    """List posts with optional filters. Returns (posts, total_count)."""
    query = select(Post)
    count_query = select(func.count(Post.id))

    if account_id:
        query = query.where(Post.account_id == account_id)
        count_query = count_query.where(Post.account_id == account_id)
    if status:
        query = query.where(Post.status == status)
        count_query = count_query.where(Post.status == status)

    total = (await db.execute(count_query)).scalar_one()
    posts = (
        await db.execute(
            query.order_by(Post.created_at.desc()).limit(limit).offset(offset)
        )
    ).scalars().all()

    return list(posts), total


async def get_post(db: AsyncSession, post_id: int) -> Post | None:
    return (await db.execute(select(Post).where(Post.id == post_id))).scalar_one_or_none()


async def create_draft(
    db: AsyncSession,
    account_id: int,
    caption: str | None = None,
    media_path: str | None = None,
    tiktok_settings: dict | None = None,
    scheduled_at: datetime | None = None,
) -> Post:
    """Create a new draft post."""
    account = (
        await db.execute(select(Account).where(Account.id == account_id))
    ).scalar_one_or_none()
    if not account:
        raise ValueError("Account not found")

    post = Post(
        account_id=account_id,
        caption=caption,
        media_path=media_path,
        tiktok_settings=tiktok_settings or {},
        status=PostStatus.draft,
        scheduled_at=scheduled_at,
    )
    db.add(post)
    await db.commit()
    await db.refresh(post)
    logger.info(f"Created draft post {post.id} for account {account.display_name}")
    return post


async def update_post(
    db: AsyncSession,
    post_id: int,
    caption: str | None = None,
    media_path: str | None = None,
    tiktok_settings: dict | None = None,
    scheduled_at: datetime | None = None,
) -> Post:
    """Update a draft or ready post."""
    post = await get_post(db, post_id)
    if not post:
        raise ValueError("Post not found")
    if post.status not in (PostStatus.draft, PostStatus.ready):
        raise ValueError(f"Cannot edit post in '{post.status.value}' status")

    if caption is not None:
        post.caption = caption
    if media_path is not None:
        post.media_path = media_path
    if tiktok_settings is not None:
        post.tiktok_settings = tiktok_settings
    if scheduled_at is not None:
        post.scheduled_at = scheduled_at

    await db.commit()
    await db.refresh(post)
    return post


async def mark_ready(db: AsyncSession, post_id: int) -> Post:
    """Move a draft to 'ready' status (awaiting user approval)."""
    post = await get_post(db, post_id)
    if not post:
        raise ValueError("Post not found")
    if post.status != PostStatus.draft:
        raise ValueError(f"Only drafts can be marked ready, current: {post.status.value}")

    post.status = PostStatus.ready
    await db.commit()
    await db.refresh(post)
    return post


async def schedule_post(db: AsyncSession, post_id: int, scheduled_at: datetime) -> Post:
    """User approves a ready post → schedule it."""
    post = await get_post(db, post_id)
    if not post:
        raise ValueError("Post not found")
    if post.status not in (PostStatus.draft, PostStatus.ready):
        raise ValueError(f"Cannot schedule post in '{post.status.value}' status")

    post.status = PostStatus.scheduled
    post.scheduled_at = scheduled_at
    await db.commit()
    await db.refresh(post)
    logger.info(f"Scheduled post {post.id} for {scheduled_at}")
    return post


async def publish_now(db: AsyncSession, post_id: int) -> Post:
    """Immediately publish a ready/scheduled post via Zernio.

    Uses Zernio's POST /v1/posts with:
    - Presigned URL upload for media
    - TikTok creator-info pre-validation
    - Required tiktokSettings (privacy_level, content_preview_confirmed, express_consent_given)
    """
    post = await get_post(db, post_id)
    if not post:
        raise ValueError("Post not found")
    if post.status not in (PostStatus.ready, PostStatus.scheduled):
        raise ValueError(f"Cannot publish post in '{post.status.value}' status")

    account = (
        await db.execute(select(Account).where(Account.id == post.account_id))
    ).scalar_one_or_none()
    if not account:
        raise ValueError("Account not found")

    # Pre-validation: TikTok creator info check
    try:
        creator_info = await zernio.get_tiktok_creator_info(account.zernio_id)
        # Check posting limits if available
        limits = creator_info.get("postingLimits", {})
        if limits and not limits.get("canPost", True):
            post.status = PostStatus.failed
            post.failure_reason = "TikTok daily API posting limit reached"
            await db.commit()
            await db.refresh(post)
            return post
    except Exception as e:
        logger.warning(f"Creator info check failed for post {post.id}: {e}")

    try:
        # Upload media via presigned URL if local file exists
        media_urls = []
        if post.media_path:
            public_url = await zernio.upload_media(post.media_path)
            media_urls.append(public_url)

        # Build tiktok_settings with required fields
        tiktok_settings = {
            "privacy_level": "PUBLIC_TO_EVERYONE",
            "allow_comment": True,
            "allow_duet": True,
            "allow_stitch": True,
            **(post.tiktok_settings or {}),
            # These are always required by Zernio/TikTok
            "content_preview_confirmed": True,
            "express_consent_given": True,
        }

        media_items = [{"type": "video", "url": u} for u in media_urls] if media_urls else None
        result = await zernio.create_post(
            content=post.caption or "",
            account_id=account.zernio_id,
            tiktok_settings=tiktok_settings,
            media=media_items,
            publish_now=True,
        )

        post.zernio_post_id = result.get("_id", result.get("id"))
        post.status = PostStatus.published
        post.published_at = datetime.utcnow()
        post.failure_reason = None
        logger.info(f"Published post {post.id}")

    except Exception as e:
        post.retry_count += 1
        post.failure_reason = str(e)

        if post.retry_count >= MAX_RETRIES:
            post.status = PostStatus.failed
            logger.error(f"Post {post.id} permanently failed after {MAX_RETRIES} retries: {e}")
        else:
            delay = RETRY_DELAYS[post.retry_count - 1]
            post.scheduled_at = datetime.utcnow() + timedelta(seconds=delay)
            post.status = PostStatus.scheduled
            logger.warning(
                f"Post {post.id} failed (attempt {post.retry_count}), retrying in {delay}s: {e}"
            )

    await db.commit()
    await db.refresh(post)
    return post


async def retry_failed(db: AsyncSession, post_id: int) -> Post:
    """Manually retry a failed post — resets retry count."""
    post = await get_post(db, post_id)
    if not post:
        raise ValueError("Post not found")
    if post.status != PostStatus.failed:
        raise ValueError("Can only retry failed posts")

    post.retry_count = 0
    post.status = PostStatus.scheduled
    post.scheduled_at = datetime.utcnow()
    post.failure_reason = None
    await db.commit()
    await db.refresh(post)
    logger.info(f"Reset post {post.id} for retry")
    return post


async def delete_post(db: AsyncSession, post_id: int) -> bool:
    """Delete a draft or failed post."""
    post = await get_post(db, post_id)
    if not post:
        return False
    if post.status in (PostStatus.published, PostStatus.scheduled):
        raise ValueError(f"Cannot delete post in '{post.status.value}' status")

    await db.delete(post)
    await db.commit()
    return True
