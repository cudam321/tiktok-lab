"""APScheduler polling jobs for metrics, followers, health, and backups."""

import logging
import shutil
import sqlite3
from datetime import datetime, date, timedelta
from pathlib import Path

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy import select

from config import settings
from db.database import async_session
from db.models import (
    Account,
    Post,
    PostStatus,
    MetricSnapshot,
    FollowerSnapshot,
    HealthStatus,
)
from services import zernio

logger = logging.getLogger(__name__)

scheduler = AsyncIOScheduler(
    job_defaults={"misfire_grace_time": 3600, "coalesce": True}
)


async def poll_post_metrics():
    """Fetch metrics via Zernio analytics API.

    Pulls published posts from Zernio, creates/updates local Post records,
    and captures MetricSnapshots with views/likes/comments/shares.
    """
    logger.info("Polling post metrics...")
    async with async_session() as db:
        accounts = (await db.execute(select(Account))).scalars().all()
        account_map = {a.zernio_id: a for a in accounts}

        try:
            # Paginate through all analytics
            page = 1
            total_synced = 0
            while True:
                analytics_data = await zernio.get_analytics(limit=50, page=page, sort_by="date", order="desc")
                posts_data = analytics_data.get("posts", [])
                if not posts_data:
                    break

                for post_data in posts_data:
                    zernio_post_id = str(post_data.get("_id", ""))
                    if not zernio_post_id:
                        continue

                    # Find which account this post belongs to
                    platforms = post_data.get("platforms", [])
                    tiktok_platform = next(
                        (p for p in platforms if p.get("platform") == "tiktok"), None
                    )
                    if not tiktok_platform:
                        continue

                    account_zernio_id = tiktok_platform.get("accountId", "")
                    account = account_map.get(account_zernio_id)
                    if not account:
                        continue

                    # Create or find local Post
                    post = (
                        await db.execute(
                            select(Post).where(Post.zernio_post_id == zernio_post_id)
                        )
                    ).scalar_one_or_none()

                    if not post:
                        published_at = post_data.get("publishedAt")
                        post = Post(
                            account_id=account.id,
                            zernio_post_id=zernio_post_id,
                            tiktok_post_id=tiktok_platform.get("platformPostId"),
                            status=PostStatus.published,
                            caption=post_data.get("content", ""),
                            published_at=datetime.fromisoformat(published_at.replace("Z", "+00:00")) if published_at else None,
                        )
                        db.add(post)
                        await db.flush()

                    # Extract metrics from analytics
                    analytics = post_data.get("analytics", {})
                    views = int(analytics.get("views", 0))
                    likes = int(analytics.get("likes", 0))
                    comments = int(analytics.get("comments", 0))
                    shares = int(analytics.get("shares", 0))
                    engagement = (
                        (likes + comments + shares) / views * 100 if views > 0 else 0.0
                    )

                    snapshot = MetricSnapshot(
                        post_id=post.id,
                        views=views,
                        likes=likes,
                        comments=comments,
                        shares=shares,
                        engagement_rate=round(engagement, 4),
                    )
                    db.add(snapshot)
                    total_synced += 1

                # Stop if we got fewer than requested (last page)
                if len(posts_data) < 50:
                    break
                page += 1

            # Detect deleted posts: any published post whose zernio_post_id
            # is no longer in the analytics response gets marked as deleted
            all_zernio_ids = set()
            page2 = 1
            while True:
                check_data = await zernio.get_analytics(limit=50, page=page2)
                for p in check_data.get("posts", []):
                    all_zernio_ids.add(str(p.get("_id", "")))
                if len(check_data.get("posts", [])) < 50:
                    break
                page2 += 1

            published_posts = (
                await db.execute(
                    select(Post).where(
                        Post.status == PostStatus.published,
                        Post.zernio_post_id.isnot(None),
                    )
                )
            ).scalars().all()

            for post in published_posts:
                if post.zernio_post_id not in all_zernio_ids:
                    post.status = PostStatus.deleted
                    logger.info(f"Post {post.id} marked deleted (no longer in Zernio)")

            for account in accounts:
                account.last_synced_at = datetime.utcnow()

            await db.commit()
            logger.info(f"Polled analytics: {total_synced} post snapshots")

        except Exception as e:
            logger.error(f"Failed polling post metrics: {e}")


async def poll_follower_stats():
    """Fetch follower counts via Zernio.

    GET /v1/accounts/{id}/follower-stats (requires analytics add-on)
    """
    logger.info("Polling follower stats...")
    today = date.today()

    async with async_session() as db:
        accounts = (await db.execute(select(Account))).scalars().all()

        for account in accounts:
            try:
                # Try follower-stats endpoint first, fall back to account list
                count = 0
                try:
                    data = await zernio.get_follower_stats(account.zernio_id)
                    accts = data.get("accounts", [])
                    acc_data = next(
                        (a for a in accts if str(a.get("field_id", "")) == account.zernio_id),
                        accts[0] if accts else {}
                    )
                    count = int(acc_data.get("followersCount", acc_data.get("followers_count", 0)) or 0)
                except Exception:
                    pass

                # Fall back to account listing if follower-stats returned 0
                if count == 0:
                    all_accounts = await zernio.list_accounts()
                    matched = next((a for a in all_accounts if a["_id"] == account.zernio_id), None)
                    if matched:
                        count = int(matched.get("followersCount", 0) or 0)

                # Get previous snapshot for growth calc
                prev = (
                    await db.execute(
                        select(FollowerSnapshot)
                        .where(
                            FollowerSnapshot.account_id == account.id,
                            FollowerSnapshot.date < today,
                        )
                        .order_by(FollowerSnapshot.date.desc())
                        .limit(1)
                    )
                ).scalar_one_or_none()

                growth_abs = count - prev.count if prev else 0
                growth_pct = (growth_abs / prev.count * 100) if prev and prev.count > 0 else 0.0

                # Upsert: update if today's snapshot exists, else insert
                existing = (
                    await db.execute(
                        select(FollowerSnapshot).where(
                            FollowerSnapshot.account_id == account.id,
                            FollowerSnapshot.date == today,
                        )
                    )
                ).scalar_one_or_none()

                if existing:
                    existing.count = count
                    existing.growth_abs = growth_abs
                    existing.growth_pct = round(growth_pct, 4)
                else:
                    db.add(FollowerSnapshot(
                        account_id=account.id,
                        date=today,
                        count=count,
                        growth_abs=growth_abs,
                        growth_pct=round(growth_pct, 4),
                    ))
                await db.commit()
                logger.info(f"Follower snapshot for {account.display_name}: {count}")

            except Exception as e:
                await db.rollback()
                logger.error(f"Failed polling followers for account {account.id}: {e}")


async def check_account_health():
    """Check health status via Zernio's account health endpoint.

    GET /v1/accounts/{id}/health
    """
    logger.info("Checking account health...")
    async with async_session() as db:
        accounts = (await db.execute(select(Account))).scalars().all()

        for account in accounts:
            try:
                health_data = await zernio.get_account_health(account.zernio_id)
                status = health_data.get("status", health_data.get("health", "healthy"))

                if status in ("healthy", "connected", "active"):
                    account.health_status = HealthStatus.healthy
                elif status in ("warning", "degraded"):
                    account.health_status = HealthStatus.warning
                else:
                    account.health_status = HealthStatus.error

                account.last_synced_at = datetime.utcnow()

            except Exception as e:
                logger.warning(f"Health check failed for {account.display_name}: {e}")
                # Don't flip to error on API failure — keep current status

        await db.commit()


async def backup_database():
    """Daily SQLite .backup with 30-day retention."""
    logger.info("Running database backup...")
    db_path = settings.data_dir / "tiktok_lab.db"
    backup_dir = settings.backup_dir
    backup_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = backup_dir / f"tiktok_lab_{timestamp}.db"

    try:
        src = sqlite3.connect(str(db_path))
        dst = sqlite3.connect(str(backup_path))
        src.backup(dst)
        dst.close()
        src.close()
        logger.info(f"Backup created: {backup_path}")

        # 30-day retention
        cutoff = datetime.now() - timedelta(days=30)
        for f in backup_dir.glob("tiktok_lab_*.db"):
            try:
                file_date = datetime.strptime(f.stem.split("_", 2)[2], "%Y%m%d_%H%M%S")
                if file_date < cutoff:
                    f.unlink()
                    logger.info(f"Deleted old backup: {f}")
            except (ValueError, IndexError):
                continue

    except Exception as e:
        logger.error(f"Backup failed: {e}")


async def process_scheduled_posts():
    """Publish posts whose scheduled_at has passed."""
    from services.posts import publish_now

    logger.info("Processing scheduled posts...")
    async with async_session() as db:
        now = datetime.utcnow()
        posts = (
            await db.execute(
                select(Post).where(
                    Post.status == PostStatus.scheduled,
                    Post.scheduled_at <= now,
                )
            )
        ).scalars().all()

        for post in posts:
            try:
                await publish_now(db, post.id)
            except Exception as e:
                logger.error(f"Failed to publish scheduled post {post.id}: {e}")


def start_scheduler():
    """Register all polling jobs and start the scheduler."""
    scheduler.add_job(poll_post_metrics, "interval", minutes=30, id="poll_metrics")
    scheduler.add_job(poll_follower_stats, "cron", hour=0, minute=0, id="poll_followers")
    scheduler.add_job(check_account_health, "interval", hours=6, id="health_check")
    scheduler.add_job(backup_database, "cron", hour=3, minute=0, id="daily_backup")
    scheduler.add_job(process_scheduled_posts, "interval", minutes=1, id="publish_scheduled")

    # Agent proactive runs (only if an AI API key is configured)
    from config import settings as _settings
    if _settings.anthropic_api_key or _settings.openai_api_key:
        from agent.scheduler import daily_briefing, anomaly_scan
        scheduler.add_job(daily_briefing, "cron", hour=8, minute=0, id="daily_briefing")
        scheduler.add_job(anomaly_scan, "interval", hours=2, id="anomaly_scan")
        logger.info("Agent proactive jobs registered")

    scheduler.start()
    logger.info("Scheduler started with polling jobs")


def stop_scheduler():
    if scheduler.running:
        scheduler.shutdown(wait=False)
