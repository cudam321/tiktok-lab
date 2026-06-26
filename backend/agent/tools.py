"""Agent tool definitions — 8 core analyst tools that query the local database."""

import math
from datetime import datetime, date, timedelta
from typing import Any

from sqlalchemy import select, func, and_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from db.models import (
    Account,
    Post,
    PostStatus,
    MetricSnapshot,
    FollowerSnapshot,
    Experiment,
    ExperimentAssignment,
    ExperimentStatus,
    HealthStatus,
    AgentInsight,
    InsightType,
)
from services.experiments import compare_experiment, EXPERIMENT_VARIABLES


# --- Tool Definitions (for Claude API) ---

TOOL_DEFINITIONS = [
    {
        "name": "query_post_metrics",
        "description": "Query post performance metrics. Returns views, likes, comments, shares, and engagement rate for posts within a date range, optionally filtered by account.",
        "input_schema": {
            "type": "object",
            "properties": {
                "account_id": {"type": "integer", "description": "Filter by account ID. Omit for all accounts."},
                "days": {"type": "integer", "description": "Number of days to look back. Default 30.", "default": 30},
                "sort_by": {"type": "string", "enum": ["views", "engagement_rate", "likes", "published_at"], "default": "published_at"},
                "limit": {"type": "integer", "description": "Max posts to return. Default 20.", "default": 20},
            },
        },
    },
    {
        "name": "query_follower_trends",
        "description": "Analyze follower growth trends per account with period comparison. Returns daily counts, growth rates, and period-over-period changes.",
        "input_schema": {
            "type": "object",
            "properties": {
                "account_id": {"type": "integer", "description": "Account ID to analyze."},
                "days": {"type": "integer", "description": "Number of days to analyze. Default 30.", "default": 30},
            },
            "required": ["account_id"],
        },
    },
    {
        "name": "compare_experiments",
        "description": "Run statistical comparison for an A/B experiment. Returns Mann-Whitney U test results, Bayesian posterior probabilities, and a human-readable conclusion.",
        "input_schema": {
            "type": "object",
            "properties": {
                "experiment_id": {"type": "integer", "description": "Experiment ID to compare."},
            },
            "required": ["experiment_id"],
        },
    },
    {
        "name": "get_account_health",
        "description": "Get health status, sync state, recent failure rates, and posting frequency for each account.",
        "input_schema": {
            "type": "object",
            "properties": {
                "account_id": {"type": "integer", "description": "Specific account. Omit for all accounts."},
            },
        },
    },
    {
        "name": "get_content_calendar",
        "description": "Get scheduled posts, posting frequency, and identify gaps in the content calendar.",
        "input_schema": {
            "type": "object",
            "properties": {
                "account_id": {"type": "integer", "description": "Filter by account. Omit for all."},
                "days_ahead": {"type": "integer", "description": "Days to look ahead for scheduled posts. Default 14.", "default": 14},
            },
        },
    },
    {
        "name": "suggest_next_post",
        "description": "Analyze recent performance data and suggest what to post next — content type, timing, and hook style based on what's working.",
        "input_schema": {
            "type": "object",
            "properties": {
                "account_id": {"type": "integer", "description": "Account to suggest for."},
            },
            "required": ["account_id"],
        },
    },
    {
        "name": "suggest_experiment",
        "description": "Propose a new A/B test based on data gaps and untested variables. Identifies which variables haven't been tested and which have ambiguous results.",
        "input_schema": {
            "type": "object",
            "properties": {
                "account_id": {"type": "integer", "description": "Account to suggest for. Omit for cross-account."},
            },
        },
    },
    {
        "name": "flag_underperformers",
        "description": "Surface accounts and content types that are trending below their baseline. Identifies engagement drops, follower loss, and failure rate spikes.",
        "input_schema": {
            "type": "object",
            "properties": {},
        },
    },
]


# --- Tool Implementations ---


async def query_post_metrics(db: AsyncSession, **kwargs) -> dict[str, Any]:
    account_id = kwargs.get("account_id")
    days = kwargs.get("days", 30)
    sort_by = kwargs.get("sort_by", "published_at")
    limit = kwargs.get("limit", 20)

    cutoff = datetime.utcnow() - timedelta(days=days)
    query = select(Post).where(
        Post.status == PostStatus.published,
        Post.published_at >= cutoff,
    )
    if account_id:
        query = query.where(Post.account_id == account_id)

    posts = (await db.execute(query.order_by(Post.published_at.desc()))).scalars().all()

    results = []
    for post in posts:
        latest = (
            await db.execute(
                select(MetricSnapshot)
                .where(MetricSnapshot.post_id == post.id)
                .order_by(MetricSnapshot.captured_at.desc())
                .limit(1)
            )
        ).scalar_one_or_none()

        account = (await db.execute(select(Account).where(Account.id == post.account_id))).scalar_one_or_none()

        results.append({
            "post_id": post.id,
            "account": account.display_name if account else "Unknown",
            "caption": (post.caption or "")[:100],
            "published_at": post.published_at.isoformat() if post.published_at else None,
            "views": latest.views if latest else 0,
            "likes": latest.likes if latest else 0,
            "comments": latest.comments if latest else 0,
            "shares": latest.shares if latest else 0,
            "engagement_rate": latest.engagement_rate if latest else 0,
        })

    # Sort
    sort_key = sort_by if sort_by in ("views", "likes", "engagement_rate") else "published_at"
    if sort_key in ("views", "likes", "engagement_rate"):
        results.sort(key=lambda x: x.get(sort_key, 0), reverse=True)

    return {"posts": results[:limit], "total": len(results), "period_days": days}


async def query_follower_trends(db: AsyncSession, **kwargs) -> dict[str, Any]:
    account_id = kwargs["account_id"]
    days = kwargs.get("days", 30)

    account = (await db.execute(select(Account).where(Account.id == account_id))).scalar_one_or_none()
    if not account:
        return {"error": "Account not found"}

    cutoff = date.today() - timedelta(days=days)
    snapshots = (
        await db.execute(
            select(FollowerSnapshot)
            .where(FollowerSnapshot.account_id == account_id, FollowerSnapshot.date >= cutoff)
            .order_by(FollowerSnapshot.date)
        )
    ).scalars().all()

    if not snapshots:
        return {"account": account.display_name, "data": [], "summary": "No follower data available."}

    first = snapshots[0]
    last = snapshots[-1]
    total_growth = last.count - first.count
    avg_daily = total_growth / len(snapshots) if snapshots else 0

    # Period comparison: current half vs previous half
    mid = len(snapshots) // 2
    first_half_growth = snapshots[mid].count - snapshots[0].count if mid > 0 else 0
    second_half_growth = snapshots[-1].count - snapshots[mid].count if mid > 0 else 0

    return {
        "account": account.display_name,
        "period_days": days,
        "current_count": last.count,
        "total_growth": total_growth,
        "avg_daily_growth": round(avg_daily, 1),
        "trend": "accelerating" if second_half_growth > first_half_growth else "decelerating" if second_half_growth < first_half_growth else "steady",
        "data_points": len(snapshots),
        "recent_days": [
            {"date": s.date.isoformat(), "count": s.count, "growth": s.growth_abs}
            for s in snapshots[-7:]
        ],
    }


async def compare_experiments_tool(db: AsyncSession, **kwargs) -> dict[str, Any]:
    experiment_id = kwargs["experiment_id"]
    try:
        return await compare_experiment(db, experiment_id)
    except ValueError as e:
        return {"error": str(e)}


async def get_account_health(db: AsyncSession, **kwargs) -> dict[str, Any]:
    account_id = kwargs.get("account_id")

    query = select(Account)
    if account_id:
        query = query.where(Account.id == account_id)

    accounts = (await db.execute(query)).scalars().all()
    results = []

    for account in accounts:
        # Recent failure rate
        week_ago = datetime.utcnow() - timedelta(days=7)
        recent_posts = (
            await db.execute(
                select(Post).where(
                    Post.account_id == account.id,
                    Post.created_at >= week_ago,
                    Post.status.in_([PostStatus.published, PostStatus.failed]),
                )
            )
        ).scalars().all()

        total = len(recent_posts)
        failed = sum(1 for p in recent_posts if p.status == PostStatus.failed)
        failure_rate = (failed / total * 100) if total > 0 else 0

        # Posting frequency
        month_ago = datetime.utcnow() - timedelta(days=30)
        month_posts = (
            await db.execute(
                select(func.count(Post.id)).where(
                    Post.account_id == account.id,
                    Post.status == PostStatus.published,
                    Post.published_at >= month_ago,
                )
            )
        ).scalar_one()

        results.append({
            "account_id": account.id,
            "display_name": account.display_name,
            "health_status": account.health_status.value,
            "last_synced": account.last_synced_at.isoformat() if account.last_synced_at else None,
            "posts_last_7d": total,
            "failure_rate_7d": round(failure_rate, 1),
            "posts_last_30d": month_posts,
            "posts_per_week_30d": round(month_posts / 4.3, 1),
        })

    return {"accounts": results}


async def get_content_calendar(db: AsyncSession, **kwargs) -> dict[str, Any]:
    account_id = kwargs.get("account_id")
    days_ahead = kwargs.get("days_ahead", 14)

    now = datetime.utcnow()
    future = now + timedelta(days=days_ahead)

    query = select(Post).where(
        Post.status == PostStatus.scheduled,
        Post.scheduled_at >= now,
        Post.scheduled_at <= future,
    )
    if account_id:
        query = query.where(Post.account_id == account_id)

    scheduled = (await db.execute(query.order_by(Post.scheduled_at))).scalars().all()

    # Find gaps (days with no scheduled posts)
    scheduled_dates = set()
    for p in scheduled:
        if p.scheduled_at:
            scheduled_dates.add(p.scheduled_at.date())

    gaps = []
    for i in range(days_ahead):
        d = (now + timedelta(days=i)).date()
        if d not in scheduled_dates:
            gaps.append(d.isoformat())

    posts_data = []
    for p in scheduled:
        account = (await db.execute(select(Account).where(Account.id == p.account_id))).scalar_one_or_none()
        posts_data.append({
            "post_id": p.id,
            "account": account.display_name if account else "Unknown",
            "caption": (p.caption or "")[:80],
            "scheduled_at": p.scheduled_at.isoformat() if p.scheduled_at else None,
        })

    return {
        "scheduled_posts": posts_data,
        "total_scheduled": len(scheduled),
        "gap_days": gaps[:10],
        "days_ahead": days_ahead,
    }


async def suggest_next_post(db: AsyncSession, **kwargs) -> dict[str, Any]:
    account_id = kwargs["account_id"]

    account = (await db.execute(select(Account).where(Account.id == account_id))).scalar_one_or_none()
    if not account:
        return {"error": "Account not found"}

    # Analyze top performing posts
    cutoff = datetime.utcnow() - timedelta(days=30)
    posts = (
        await db.execute(
            select(Post).where(
                Post.account_id == account_id,
                Post.status == PostStatus.published,
                Post.published_at >= cutoff,
            )
        )
    ).scalars().all()

    post_metrics = []
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
            post_metrics.append({
                "caption": post.caption or "",
                "published_at": post.published_at,
                "views": latest.views,
                "engagement_rate": latest.engagement_rate,
                "hour": post.published_at.hour if post.published_at else None,
            })

    if not post_metrics:
        return {
            "account": account.display_name,
            "suggestion": "Not enough data yet. Post consistently for 1-2 weeks to build a baseline.",
            "data_points": 0,
        }

    # Find best performing time
    by_hour: dict[int, list[float]] = {}
    for pm in post_metrics:
        if pm["hour"] is not None:
            by_hour.setdefault(pm["hour"], []).append(pm["engagement_rate"])

    best_hour = None
    if by_hour:
        best_hour = max(by_hour, key=lambda h: sum(by_hour[h]) / len(by_hour[h]))

    # Top posts by engagement
    top = sorted(post_metrics, key=lambda x: x["engagement_rate"], reverse=True)[:3]
    avg_eng = sum(p["engagement_rate"] for p in post_metrics) / len(post_metrics)

    return {
        "account": account.display_name,
        "data_points": len(post_metrics),
        "avg_engagement_30d": round(avg_eng, 2),
        "best_posting_hour": best_hour,
        "top_posts": [
            {"caption": p["caption"][:80], "engagement": round(p["engagement_rate"], 2)}
            for p in top
        ],
        "suggestion": f"Based on {len(post_metrics)} posts, your best engagement is around hour {best_hour or 'N/A'}. "
        f"Average engagement: {avg_eng:.1f}%. Study your top performers for content patterns.",
    }


async def suggest_experiment_tool(db: AsyncSession, **kwargs) -> dict[str, Any]:
    account_id = kwargs.get("account_id")

    # Find which variables have been tested
    query = select(Experiment)
    if account_id:
        query = query.where(Experiment.account_id == account_id)
    experiments = (await db.execute(query)).scalars().all()

    tested = set()
    inconclusive = []
    for exp in experiments:
        tested.add(exp.variable)
        if exp.status == ExperimentStatus.completed and exp.confidence and exp.confidence > 0.05:
            inconclusive.append(exp.variable)

    untested = [v for v in EXPERIMENT_VARIABLES if v not in tested]

    suggestion = None
    if untested:
        var = untested[0]
        suggestion = {
            "variable": var,
            "reason": f"'{var}' has never been tested. Start here to build baseline knowledge.",
            "recommended_variants": _default_variants(var),
        }
    elif inconclusive:
        var = inconclusive[0]
        suggestion = {
            "variable": var,
            "reason": f"Previous test for '{var}' was inconclusive (p > 0.05). Rerun with larger sample.",
            "recommended_variants": _default_variants(var),
        }

    return {
        "tested_variables": list(tested),
        "untested_variables": untested,
        "inconclusive_variables": inconclusive,
        "suggestion": suggestion,
    }


async def flag_underperformers(db: AsyncSession, **kwargs) -> dict[str, Any]:
    alerts = []
    accounts = (await db.execute(select(Account))).scalars().all()

    for account in accounts:
        # Engagement drop: >50% below 7-day rolling average
        week_ago = datetime.utcnow() - timedelta(days=7)
        recent_posts = (
            await db.execute(
                select(Post).where(
                    Post.account_id == account.id,
                    Post.status == PostStatus.published,
                    Post.published_at >= week_ago,
                )
            )
        ).scalars().all()

        engagement_rates = []
        for post in recent_posts:
            snap = (
                await db.execute(
                    select(MetricSnapshot)
                    .where(MetricSnapshot.post_id == post.id)
                    .order_by(MetricSnapshot.captured_at.desc())
                    .limit(1)
                )
            ).scalar_one_or_none()
            if snap:
                engagement_rates.append(snap.engagement_rate)

        if len(engagement_rates) >= 3:
            avg = sum(engagement_rates) / len(engagement_rates)
            latest = engagement_rates[0]
            if avg > 0 and latest < avg * 0.5:
                alerts.append({
                    "type": "engagement_drop",
                    "account": account.display_name,
                    "detail": f"Latest engagement ({latest:.1f}%) is >50% below 7-day average ({avg:.1f}%)",
                    "severity": "high",
                })

        # Follower loss: >2% decrease in 24h
        today_snap = (
            await db.execute(
                select(FollowerSnapshot)
                .where(FollowerSnapshot.account_id == account.id)
                .order_by(FollowerSnapshot.date.desc())
                .limit(1)
            )
        ).scalar_one_or_none()

        if today_snap and today_snap.growth_pct < -2.0:
            alerts.append({
                "type": "follower_loss",
                "account": account.display_name,
                "detail": f"Follower count dropped {today_snap.growth_pct:.1f}% ({today_snap.growth_abs:+d})",
                "severity": "high",
            })

        # Failure rate spike: >30% in last 7 days
        all_recent = (
            await db.execute(
                select(Post).where(
                    Post.account_id == account.id,
                    Post.created_at >= week_ago,
                    Post.status.in_([PostStatus.published, PostStatus.failed]),
                )
            )
        ).scalars().all()
        if len(all_recent) >= 3:
            fail_count = sum(1 for p in all_recent if p.status == PostStatus.failed)
            fail_rate = fail_count / len(all_recent) * 100
            if fail_rate > 30:
                alerts.append({
                    "type": "failure_rate_spike",
                    "account": account.display_name,
                    "detail": f"{fail_rate:.0f}% of posts failed in last 7 days ({fail_count}/{len(all_recent)})",
                    "severity": "critical",
                })

        # Sync gap: no snapshots for >2 hours
        if account.last_synced_at:
            hours_since = (datetime.utcnow() - account.last_synced_at).total_seconds() / 3600
            if hours_since > 2:
                alerts.append({
                    "type": "sync_gap",
                    "account": account.display_name,
                    "detail": f"No sync for {hours_since:.1f} hours",
                    "severity": "medium",
                })

    return {"alerts": alerts, "total": len(alerts)}


def _default_variants(variable: str) -> list[str]:
    defaults = {
        "hook_style": ["question_hook", "statement_hook"],
        "posting_time": ["morning_9am", "evening_7pm"],
        "hashtag_strategy": ["niche_tags", "trending_tags"],
        "caption_style": ["short_punchy", "storytelling"],
        "edit_pace": ["fast_cuts", "slow_cinematic"],
        "video_length": ["15_seconds", "60_seconds"],
        "content_type": ["tutorial", "entertainment"],
        "text_overlay": ["with_text", "no_text"],
    }
    return defaults.get(variable, ["variant_a", "variant_b"])


# --- Tool Dispatch ---

TOOL_MAP = {
    "query_post_metrics": query_post_metrics,
    "query_follower_trends": query_follower_trends,
    "compare_experiments": compare_experiments_tool,
    "get_account_health": get_account_health,
    "get_content_calendar": get_content_calendar,
    "suggest_next_post": suggest_next_post,
    "suggest_experiment": suggest_experiment_tool,
    "flag_underperformers": flag_underperformers,
}


async def execute_tool(db: AsyncSession, tool_name: str, args: dict) -> dict[str, Any]:
    handler = TOOL_MAP.get(tool_name)
    if not handler:
        return {"error": f"Unknown tool: {tool_name}"}
    try:
        return await handler(db, **args)
    except Exception as e:
        return {"error": f"Tool execution failed: {e}"}
