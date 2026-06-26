"""Cross-account combined analytics service.

Aggregates `metric_snapshots` (per-post cumulative views/likes/comments/shares,
polled every 30 minutes) and `follower_snapshots` (daily follower counts per
account) across all 5 TikTok accounts into a single timeseries + KPI view.

Important semantics:
- Engagement (count) = sum(likes + comments + shares)
- Engagement Rate (%) = sum(actions) / sum(views) * 100  (computed on totals,
  NOT averaged across per-post rates — the latter is mathematically wrong for a
  combined view)
- Cumulative-at-end-of-day(post) = latest snapshot of that post on or before
  end-of-day UTC. Posts with no snapshot for a day carry forward their last
  known value (LOCF). Deleted posts retain their last known value (those views
  were earned).
- Daily delta(metric, day) = cumulative(day) - cumulative(day - 1)
  - We always walk from the earliest snapshot day so the first window day's
    delta is computed against the day prior, not the entire pre-window
    cumulative.
- All dates are computed in UTC (snapshots store `captured_at` as UTC).

Saves are not exposed by TikTok's public API and are not surfaced.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Iterable

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import Account, FollowerSnapshot, MetricSnapshot, Post, PostStatus


# ---------- Internal data structures ----------


@dataclass(frozen=True)
class _PostDayValue:
    """Latest cumulative metrics for one post at end-of-UTC-day."""

    captured_at: datetime
    views: int
    likes: int
    comments: int
    shares: int


@dataclass
class _RunningTotals:
    views: int = 0
    likes: int = 0
    comments: int = 0
    shares: int = 0

    def add(self, v: _PostDayValue) -> None:
        self.views += v.views
        self.likes += v.likes
        self.comments += v.comments
        self.shares += v.shares

    def sub(self, v: _PostDayValue) -> None:
        self.views -= v.views
        self.likes -= v.likes
        self.comments -= v.comments
        self.shares -= v.shares


@dataclass
class DailyPoint:
    day: date
    views_total: int
    likes_total: int
    comments_total: int
    shares_total: int
    views_delta: int
    likes_delta: int
    comments_delta: int
    shares_delta: int


# ---------- Snapshot loading ----------


async def _load_snapshots(
    db: AsyncSession,
) -> tuple[
    dict[int, dict[date, _PostDayValue]],
    dict[int, int],
    date | None,
]:
    """Load every snapshot for published/deleted posts in one query.

    Returns:
        - by_post: post_id -> {day -> latest snapshot value that day}
        - post_account: post_id -> account_id
        - earliest snapshot day across all posts (or None if no data)
    """
    rows = (
        await db.execute(
            select(
                MetricSnapshot.post_id,
                Post.account_id,
                MetricSnapshot.captured_at,
                MetricSnapshot.views,
                MetricSnapshot.likes,
                MetricSnapshot.comments,
                MetricSnapshot.shares,
            )
            .join(Post, Post.id == MetricSnapshot.post_id)
            .where(Post.status.in_((PostStatus.published, PostStatus.deleted)))
            .order_by(MetricSnapshot.captured_at.asc())
        )
    ).all()

    by_post: dict[int, dict[date, _PostDayValue]] = defaultdict(dict)
    post_account: dict[int, int] = {}
    earliest: date | None = None

    for post_id, account_id, captured_at, views, likes, comments, shares in rows:
        post_account[post_id] = account_id
        day = _utc_date(captured_at)
        if earliest is None or day < earliest:
            earliest = day
        prev = by_post[post_id].get(day)
        if prev is None or captured_at > prev.captured_at:
            by_post[post_id][day] = _PostDayValue(
                captured_at=captured_at,
                views=int(views or 0),
                likes=int(likes or 0),
                comments=int(comments or 0),
                shares=int(shares or 0),
            )
    return by_post, post_account, earliest


def _utc_date(dt: datetime) -> date:
    """Coerce captured_at (which may be naive UTC from SQLite) to a UTC date."""
    if dt.tzinfo is None:
        return dt.date()
    return dt.astimezone(timezone.utc).date()


def _ensure_utc(dt: datetime) -> datetime:
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


# ---------- Daily walk ----------


def _walk_daily(
    by_post: dict[int, dict[date, _PostDayValue]],
    earliest: date,
    end_day: date,
) -> list[DailyPoint]:
    """Walk every UTC day from earliest to end_day, maintaining a running
    aggregate (sum across posts of last-known cumulative). Emits a DailyPoint
    per day with both end-of-day cumulative totals and day-over-day deltas.
    """
    if end_day < earliest:
        return []

    last_known: dict[int, _PostDayValue] = {}
    running = _RunningTotals()
    points: list[DailyPoint] = []

    one_day = timedelta(days=1)
    cur = earliest
    prev_totals = (0, 0, 0, 0)

    while cur <= end_day:
        for post_id, days_map in by_post.items():
            v = days_map.get(cur)
            if v is None:
                continue
            prev = last_known.get(post_id)
            if prev is not None:
                running.sub(prev)
            running.add(v)
            last_known[post_id] = v

        cur_totals = (running.views, running.likes, running.comments, running.shares)
        points.append(
            DailyPoint(
                day=cur,
                views_total=cur_totals[0],
                likes_total=cur_totals[1],
                comments_total=cur_totals[2],
                shares_total=cur_totals[3],
                views_delta=cur_totals[0] - prev_totals[0],
                likes_delta=cur_totals[1] - prev_totals[1],
                comments_delta=cur_totals[2] - prev_totals[2],
                shares_delta=cur_totals[3] - prev_totals[3],
            )
        )
        prev_totals = cur_totals
        cur += one_day

    return points


# ---------- Per-post window helpers ----------


def _latest_on_or_before(
    days_map: dict[date, _PostDayValue], boundary: date
) -> _PostDayValue | None:
    candidates = [d for d in days_map if d <= boundary]
    if not candidates:
        return None
    return days_map[max(candidates)]


def _earned_in_window(
    days_map: dict[date, _PostDayValue], window_start: date, today: date
) -> tuple[int, int, int, int]:
    """Earned in window = latest_in_window − latest_strictly_before_window.

    If no snapshot before window_start (e.g. post was published inside the
    window), the entire latest cumulative counts as "earned in window".
    """
    latest_in = _latest_on_or_before(days_map, today)
    if latest_in is None:
        return (0, 0, 0, 0)
    before = _latest_on_or_before(
        {d: v for d, v in days_map.items() if d < window_start},
        window_start - timedelta(days=1),
    )
    if before is None:
        return (latest_in.views, latest_in.likes, latest_in.comments, latest_in.shares)
    return (
        max(latest_in.views - before.views, 0),
        max(latest_in.likes - before.likes, 0),
        max(latest_in.comments - before.comments, 0),
        max(latest_in.shares - before.shares, 0),
    )


# ---------- Followers ----------


async def _load_followers(
    db: AsyncSession,
) -> tuple[dict[int, dict[date, tuple[int, int]]], date | None]:
    rows = (
        await db.execute(
            select(
                FollowerSnapshot.account_id,
                FollowerSnapshot.date,
                FollowerSnapshot.count,
                FollowerSnapshot.growth_abs,
            ).order_by(FollowerSnapshot.date.asc())
        )
    ).all()

    by_account: dict[int, dict[date, tuple[int, int]]] = defaultdict(dict)
    earliest: date | None = None
    for account_id, day, count, growth_abs in rows:
        if earliest is None or day < earliest:
            earliest = day
        by_account[account_id][day] = (int(count), int(growth_abs or 0))
    return by_account, earliest


def _walk_followers(
    by_account: dict[int, dict[date, tuple[int, int]]],
    earliest: date | None,
    window_start: date,
    today: date,
) -> tuple[list[dict], dict]:
    if earliest is None:
        return ([], {"current": 0, "delta": 0, "gained": 0, "lost": 0})

    one_day = timedelta(days=1)
    last_count: dict[int, int] = {}
    series: list[dict] = []
    in_window_gained = 0
    in_window_lost = 0
    cur = earliest
    prev_total = 0
    first_in_window_total: int | None = None

    while cur <= today:
        for account_id, days_map in by_account.items():
            entry = days_map.get(cur)
            if entry is not None:
                last_count[account_id] = entry[0]
                if window_start <= cur <= today:
                    if entry[1] > 0:
                        in_window_gained += entry[1]
                    elif entry[1] < 0:
                        in_window_lost += -entry[1]
        total = sum(last_count.values())

        if window_start <= cur <= today:
            if first_in_window_total is None:
                first_in_window_total = prev_total or total
            series.append(
                {
                    "date": cur.isoformat(),
                    "total": total,
                    "delta": total - prev_total,
                }
            )
        prev_total = total
        cur += one_day

    current = series[-1]["total"] if series else sum(last_count.values())
    if series:
        delta = series[-1]["total"] - (first_in_window_total or series[0]["total"])
    else:
        delta = 0
    return (
        series,
        {
            "current": current,
            "delta": delta,
            "gained": in_window_gained,
            "lost": in_window_lost,
        },
    )


# ---------- Public API ----------


async def get_combined(
    db: AsyncSession,
    days: int | None,
    top_posts_limit: int = 10,
) -> dict:
    """Return KPIs + daily timeseries + per-account leaderboard + top posts.

    days=None or days=0 → all-time.
    days=N → window covering the last N UTC days ending today (inclusive).
    """
    today = datetime.now(timezone.utc).date()
    by_post, post_account, earliest = await _load_snapshots(db)

    full_series: list[DailyPoint] = (
        _walk_daily(by_post, earliest, today) if earliest is not None else []
    )

    if days and days > 0:
        window_start = today - timedelta(days=days - 1)
    else:
        window_start = full_series[0].day if full_series else today

    in_window = [p for p in full_series if window_start <= p.day <= today]

    accounts = (await db.execute(select(Account))).scalars().all()
    account_by_id = {a.id: a for a in accounts}

    # ---- KPIs (in window + all-time) ----
    if in_window:
        last = in_window[-1]
        if earliest is not None and window_start <= earliest:
            views_window = last.views_total
            likes_window = last.likes_total
            comments_window = last.comments_total
            shares_window = last.shares_total
        else:
            views_window = sum(p.views_delta for p in in_window)
            likes_window = sum(p.likes_delta for p in in_window)
            comments_window = sum(p.comments_delta for p in in_window)
            shares_window = sum(p.shares_delta for p in in_window)
        views_alltime = last.views_total
        likes_alltime = last.likes_total
        comments_alltime = last.comments_total
        shares_alltime = last.shares_total
    else:
        views_window = likes_window = comments_window = shares_window = 0
        views_alltime = likes_alltime = comments_alltime = shares_alltime = 0

    engagement_window = likes_window + comments_window + shares_window
    engagement_alltime = likes_alltime + comments_alltime + shares_alltime
    engagement_rate_window = (
        engagement_window / views_window * 100 if views_window > 0 else 0.0
    )
    engagement_rate_alltime = (
        engagement_alltime / views_alltime * 100 if views_alltime > 0 else 0.0
    )

    # ---- Followers ----
    fs_by_account, fs_earliest = await _load_followers(db)
    follower_series, follower_kpis = _walk_followers(
        fs_by_account, fs_earliest, window_start, today
    )

    # ---- Leaderboard ----
    leaderboard = _build_leaderboard(
        by_post, post_account, fs_by_account, accounts, window_start, today
    )

    # ---- Top posts ----
    top_posts = await _build_top_posts(
        db, by_post, account_by_id, window_start, today, top_posts_limit
    )

    # ---- Posts published in window ----
    all_published = (
        await db.execute(
            select(Post).where(
                Post.status.in_((PostStatus.published, PostStatus.deleted)),
                Post.published_at.isnot(None),
            )
        )
    ).scalars().all()
    if days and days > 0:
        cutoff = datetime.combine(window_start, datetime.min.time(), tzinfo=timezone.utc)
        posts_window_count = sum(
            1
            for p in all_published
            if p.published_at and _ensure_utc(p.published_at) >= cutoff
        )
    else:
        posts_window_count = len(all_published)

    return {
        "window": {
            "start": window_start.isoformat(),
            "end": today.isoformat(),
            "days": days,
            "earliest_data": earliest.isoformat() if earliest else None,
        },
        "kpis": {
            "views": views_window,
            "likes": likes_window,
            "comments": comments_window,
            "shares": shares_window,
            "engagement": engagement_window,
            "engagement_rate": round(engagement_rate_window, 4),
            "posts": posts_window_count,
            "alltime": {
                "views": views_alltime,
                "likes": likes_alltime,
                "comments": comments_alltime,
                "shares": shares_alltime,
                "engagement": engagement_alltime,
                "engagement_rate": round(engagement_rate_alltime, 4),
            },
            "followers": follower_kpis,
        },
        "timeseries": [
            {
                "date": p.day.isoformat(),
                "views_cumulative": p.views_total,
                "likes_cumulative": p.likes_total,
                "comments_cumulative": p.comments_total,
                "shares_cumulative": p.shares_total,
                "engagement_cumulative": p.likes_total + p.comments_total + p.shares_total,
                "views_daily": max(p.views_delta, 0),
                "likes_daily": max(p.likes_delta, 0),
                "comments_daily": max(p.comments_delta, 0),
                "shares_daily": max(p.shares_delta, 0),
                "engagement_daily": max(
                    p.likes_delta + p.comments_delta + p.shares_delta, 0
                ),
            }
            for p in in_window
        ],
        "followers_timeseries": follower_series,
        "leaderboard": leaderboard,
        "top_posts": top_posts,
    }


def _build_leaderboard(
    by_post: dict[int, dict[date, _PostDayValue]],
    post_account: dict[int, int],
    fs_by_account: dict[int, dict[date, tuple[int, int]]],
    accounts: list[Account],
    window_start: date,
    today: date,
) -> list[dict]:
    rows = []
    for account in accounts:
        agg_v = agg_l = agg_c = agg_s = 0
        agg_v_total = 0
        post_count = 0
        for post_id, days_map in by_post.items():
            if post_account.get(post_id) != account.id:
                continue
            post_count += 1
            v, l, c, s = _earned_in_window(days_map, window_start, today)
            agg_v += v
            agg_l += l
            agg_c += c
            agg_s += s
            latest = _latest_on_or_before(days_map, today)
            if latest:
                agg_v_total += latest.views

        engagement = agg_l + agg_c + agg_s
        engagement_rate = engagement / agg_v * 100 if agg_v > 0 else 0.0

        f_days = sorted(fs_by_account.get(account.id, {}).items())
        if f_days:
            current_followers = f_days[-1][1][0]
            in_w = [(d, v) for d, v in f_days if d >= window_start]
            before = [(d, v) for d, v in f_days if d < window_start]
            if in_w and before:
                f_delta = in_w[-1][1][0] - before[-1][1][0]
            elif in_w:
                f_delta = in_w[-1][1][0] - in_w[0][1][0]
            else:
                f_delta = 0
        else:
            current_followers = None
            f_delta = 0

        rows.append(
            {
                "account_id": account.id,
                "display_name": account.display_name,
                "username": account.username,
                "avatar_url": account.avatar_url,
                "post_count": post_count,
                "views": agg_v,
                "likes": agg_l,
                "comments": agg_c,
                "shares": agg_s,
                "engagement": engagement,
                "engagement_rate": round(engagement_rate, 4),
                "views_alltime": agg_v_total,
                "follower_count": current_followers,
                "follower_delta": f_delta,
            }
        )

    rows.sort(key=lambda r: r["views"], reverse=True)
    return rows


async def _build_top_posts(
    db: AsyncSession,
    by_post: dict[int, dict[date, _PostDayValue]],
    account_by_id: dict[int, Account],
    window_start: date,
    today: date,
    limit: int,
) -> list[dict]:
    posts = (
        await db.execute(
            select(Post).where(
                Post.status.in_((PostStatus.published, PostStatus.deleted))
            )
        )
    ).scalars().all()

    out: list[dict] = []
    for post in posts:
        days_map = by_post.get(post.id, {})
        if not days_map:
            continue
        earned_v, earned_l, earned_c, earned_s = _earned_in_window(
            days_map, window_start, today
        )
        latest_in_window = _latest_on_or_before(days_map, today)
        if latest_in_window is None:
            continue
        engagement = earned_l + earned_c + earned_s
        engagement_rate = engagement / earned_v * 100 if earned_v > 0 else 0.0
        account = account_by_id.get(post.account_id)
        out.append(
            {
                "post_id": post.id,
                "account_id": post.account_id,
                "account_name": account.display_name if account else "—",
                "caption": post.caption,
                "published_at": post.published_at.isoformat() if post.published_at else None,
                "status": post.status.value if hasattr(post.status, "value") else str(post.status),
                "views": earned_v,
                "likes": earned_l,
                "comments": earned_c,
                "shares": earned_s,
                "engagement": engagement,
                "engagement_rate": round(engagement_rate, 4),
                "views_total": latest_in_window.views,
                "engagement_rate_total": round(
                    (latest_in_window.likes + latest_in_window.comments + latest_in_window.shares)
                    / latest_in_window.views
                    * 100
                    if latest_in_window.views > 0
                    else 0.0,
                    4,
                ),
            }
        )

    out.sort(key=lambda r: r["views"], reverse=True)
    return out[:limit]
