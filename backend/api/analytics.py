"""Analytics query endpoints for the dashboard."""

import asyncio
import logging
import time
from datetime import datetime, date, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from db.database import get_db
from db.models import (
    Account,
    Post,
    PostStatus,
    MetricSnapshot,
    FollowerSnapshot,
)
from services import combined_analytics, zernio

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/analytics", tags=["analytics"])


# ---------- Zernio proxy cache (in-memory, per-process) ----------

_ZERNIO_CACHE: dict[tuple, tuple[float, dict]] = {}
_ZERNIO_CACHE_TTL_SECONDS = 30 * 60  # 30 min — matches our metrics polling cadence
_ZERNIO_CACHE_LOCK = asyncio.Lock()


async def _zernio_cached(key: tuple, fetch):
    """Cache Zernio responses by key for TTL seconds. Concurrent hits coalesce
    behind a single lock so we don't fan out duplicate API calls.
    """
    now = time.monotonic()
    cached = _ZERNIO_CACHE.get(key)
    if cached and now - cached[0] < _ZERNIO_CACHE_TTL_SECONDS:
        return cached[1]
    async with _ZERNIO_CACHE_LOCK:
        cached = _ZERNIO_CACHE.get(key)
        if cached and time.monotonic() - cached[0] < _ZERNIO_CACHE_TTL_SECONDS:
            return cached[1]
        data = await fetch()
        _ZERNIO_CACHE[key] = (time.monotonic(), data)
        return data


# --- Response Models ---


class PostMetricResponse(BaseModel):
    post_id: int
    caption: str | None
    published_at: datetime | None
    views: int
    likes: int
    comments: int
    shares: int
    engagement_rate: float


class AccountMetricsSummary(BaseModel):
    account_id: int
    display_name: str
    total_posts: int
    total_views: int
    total_likes: int
    avg_engagement_rate: float
    follower_count: int | None
    follower_growth_7d: int | None


class FollowerTrendPoint(BaseModel):
    date: date
    count: int
    growth_abs: int
    growth_pct: float


class FollowerTrendResponse(BaseModel):
    account_id: int
    display_name: str
    data: list[FollowerTrendPoint]


# --- Routes ---


@router.get("/posts/{account_id}", response_model=list[PostMetricResponse])
async def get_post_metrics(
    account_id: int,
    days: int = Query(default=30, ge=1, le=90),
    db: AsyncSession = Depends(get_db),
):
    """Get latest metrics for published posts on an account."""
    account = (await db.execute(select(Account).where(Account.id == account_id))).scalar_one_or_none()
    if not account:
        raise HTTPException(status_code=404, detail="Account not found")

    cutoff = datetime.utcnow() - timedelta(days=days)
    posts = (
        await db.execute(
            select(Post)
            .where(
                Post.account_id == account_id,
                Post.status == PostStatus.published,
                Post.published_at >= cutoff,
            )
            .order_by(Post.published_at.desc())
        )
    ).scalars().all()

    results = []
    for post in posts:
        # Get latest snapshot
        latest = (
            await db.execute(
                select(MetricSnapshot)
                .where(MetricSnapshot.post_id == post.id)
                .order_by(MetricSnapshot.captured_at.desc())
                .limit(1)
            )
        ).scalar_one_or_none()

        results.append(
            PostMetricResponse(
                post_id=post.id,
                caption=post.caption,
                published_at=post.published_at,
                views=latest.views if latest else 0,
                likes=latest.likes if latest else 0,
                comments=latest.comments if latest else 0,
                shares=latest.shares if latest else 0,
                engagement_rate=latest.engagement_rate if latest else 0.0,
            )
        )

    return results


@router.get("/summary", response_model=list[AccountMetricsSummary])
async def get_accounts_summary(db: AsyncSession = Depends(get_db)):
    """Get high-level metrics summary for all accounts."""
    accounts = (await db.execute(select(Account))).scalars().all()
    results = []

    for account in accounts:
        # Total published posts
        post_count = (
            await db.execute(
                select(func.count(Post.id)).where(
                    Post.account_id == account.id,
                    Post.status == PostStatus.published,
                )
            )
        ).scalar_one()

        # Aggregate latest metrics per post
        total_views = 0
        total_likes = 0
        engagement_rates = []

        posts = (
            await db.execute(
                select(Post).where(
                    Post.account_id == account.id,
                    Post.status == PostStatus.published,
                )
            )
        ).scalars().all()

        for post in posts:
            latest = (
                await db.execute(
                    select(MetricSnapshot)
                    .where(MetricSnapshot.post_id == post.id)
                    .order_by(MetricSnapshot.captured_at.desc())
                    .limit(1)
                )
            ).scalar_one_or_none()
            if latest:
                total_views += latest.views
                total_likes += latest.likes
                engagement_rates.append(latest.engagement_rate)

        # Latest follower count
        follower = (
            await db.execute(
                select(FollowerSnapshot)
                .where(FollowerSnapshot.account_id == account.id)
                .order_by(FollowerSnapshot.date.desc())
                .limit(1)
            )
        ).scalar_one_or_none()

        # 7-day follower growth
        week_ago = date.today() - timedelta(days=7)
        follower_7d = (
            await db.execute(
                select(FollowerSnapshot)
                .where(
                    FollowerSnapshot.account_id == account.id,
                    FollowerSnapshot.date <= week_ago,
                )
                .order_by(FollowerSnapshot.date.desc())
                .limit(1)
            )
        ).scalar_one_or_none()

        growth_7d = None
        if follower and follower_7d:
            growth_7d = follower.count - follower_7d.count

        results.append(
            AccountMetricsSummary(
                account_id=account.id,
                display_name=account.display_name,
                total_posts=post_count,
                total_views=total_views,
                total_likes=total_likes,
                avg_engagement_rate=(
                    round(sum(engagement_rates) / len(engagement_rates), 4)
                    if engagement_rates
                    else 0.0
                ),
                follower_count=follower.count if follower else None,
                follower_growth_7d=growth_7d,
            )
        )

    return results


@router.get("/followers/{account_id}", response_model=FollowerTrendResponse)
async def get_follower_trend(
    account_id: int,
    days: int = Query(default=30, ge=1, le=365),
    db: AsyncSession = Depends(get_db),
):
    """Get follower trend data for an account."""
    account = (await db.execute(select(Account).where(Account.id == account_id))).scalar_one_or_none()
    if not account:
        raise HTTPException(status_code=404, detail="Account not found")

    cutoff = date.today() - timedelta(days=days)
    snapshots = (
        await db.execute(
            select(FollowerSnapshot)
            .where(
                FollowerSnapshot.account_id == account_id,
                FollowerSnapshot.date >= cutoff,
            )
            .order_by(FollowerSnapshot.date)
        )
    ).scalars().all()

    return FollowerTrendResponse(
        account_id=account.id,
        display_name=account.display_name,
        data=[
            FollowerTrendPoint(
                date=s.date,
                count=s.count,
                growth_abs=s.growth_abs,
                growth_pct=s.growth_pct,
            )
            for s in snapshots
        ],
    )


# ---------- Combined cross-account analytics ----------


@router.get("/combined")
async def get_combined_analytics(
    days: int = Query(
        default=30,
        ge=0,
        le=3650,
        description="Window size in days. 0 means all-time.",
    ),
    top_posts_limit: int = Query(default=10, ge=1, le=50),
    db: AsyncSession = Depends(get_db),
):
    """Comprehensive cross-account analytics: KPIs (in-window + all-time),
    daily timeseries (cumulative + daily delta for views/likes/comments/shares/
    engagement), follower aggregation, per-account leaderboard, and top posts.

    Returned as a plain dict (not Pydantic) because the response shape is
    stable but nested — defining it via Pydantic adds boilerplate without
    catching real bugs (the service is fully typed).
    """
    return await combined_analytics.get_combined(
        db, days=days or None, top_posts_limit=top_posts_limit
    )


@router.get("/combined/best-time")
async def get_combined_best_time(
    platform: str = Query(default="tiktok"),
):
    """Best day-of-week × hour to post, ranked by historical avg engagement.
    Proxies Zernio /v1/analytics/best-time. Requires Analytics add-on.
    Cached in-process for 30 minutes."""
    try:
        return await _zernio_cached(
            ("best-time", platform),
            lambda: zernio.get_best_time_to_post(platform=platform),
        )
    except Exception as e:
        logger.warning(f"best-time fetch failed: {e}")
        raise HTTPException(status_code=502, detail=f"Zernio best-time failed: {e}")


@router.get("/combined/decay")
async def get_combined_decay(
    platform: str = Query(default="tiktok"),
):
    """Engagement accumulation curve over time after publish.
    Proxies Zernio /v1/analytics/content-decay. Requires Analytics add-on.
    Cached in-process for 30 minutes."""
    try:
        return await _zernio_cached(
            ("decay", platform),
            lambda: zernio.get_content_decay(platform=platform),
        )
    except Exception as e:
        logger.warning(f"content-decay fetch failed: {e}")
        raise HTTPException(status_code=502, detail=f"Zernio content-decay failed: {e}")


@router.get("/combined/posting-frequency")
async def get_combined_posting_frequency(
    platform: str = Query(default="tiktok"),
):
    """Posting frequency analysis. Proxies Zernio /v1/analytics/posting-frequency.
    Cached in-process for 30 minutes."""
    try:
        return await _zernio_cached(
            ("posting-freq", platform),
            lambda: zernio.get_posting_frequency(platform=platform),
        )
    except Exception as e:
        logger.warning(f"posting-frequency fetch failed: {e}")
        raise HTTPException(
            status_code=502, detail=f"Zernio posting-frequency failed: {e}"
        )
