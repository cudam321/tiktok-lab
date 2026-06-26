"""Tests for analytics endpoints and metric snapshots."""

import pytest
from datetime import datetime, date, timedelta

from db.models import (
    Account,
    Post,
    PostStatus,
    MetricSnapshot,
    FollowerSnapshot,
    HealthStatus,
)


@pytest.fixture
async def seeded_data(db):
    """Seed an account with posts and metrics."""
    account = Account(
        zernio_id="zernio_analytics",
        display_name="Analytics Test",
        health_status=HealthStatus.healthy,
    )
    db.add(account)
    await db.flush()

    post = Post(
        account_id=account.id,
        zernio_post_id="post_001",
        status=PostStatus.published,
        caption="Test post",
        published_at=datetime.utcnow() - timedelta(days=1),
    )
    db.add(post)
    await db.flush()

    snapshot = MetricSnapshot(
        post_id=post.id,
        views=1000,
        likes=50,
        comments=10,
        shares=5,
        engagement_rate=6.5,
    )
    db.add(snapshot)

    follower = FollowerSnapshot(
        account_id=account.id,
        date=date.today(),
        count=5000,
        growth_abs=100,
        growth_pct=2.04,
    )
    db.add(follower)
    await db.commit()

    return account, post, snapshot, follower


@pytest.mark.asyncio
async def test_post_metrics_endpoint(client, db, seeded_data):
    account, *_ = seeded_data
    response = await client.get(f"/api/analytics/posts/{account.id}")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["views"] == 1000
    assert data[0]["engagement_rate"] == 6.5


@pytest.mark.asyncio
async def test_post_metrics_account_not_found(client):
    response = await client.get("/api/analytics/posts/999")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_summary_endpoint(client, db, seeded_data):
    response = await client.get("/api/analytics/summary")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["total_views"] == 1000
    assert data[0]["follower_count"] == 5000


@pytest.mark.asyncio
async def test_follower_trend_endpoint(client, db, seeded_data):
    account, *_ = seeded_data
    response = await client.get(f"/api/analytics/followers/{account.id}")
    assert response.status_code == 200
    data = response.json()
    assert len(data["data"]) == 1
    assert data["data"][0]["count"] == 5000


@pytest.mark.asyncio
async def test_follower_trend_account_not_found(client):
    response = await client.get("/api/analytics/followers/999")
    assert response.status_code == 404


# ---------- Combined cross-account analytics ----------


@pytest.fixture
async def combined_seeded(db):
    """Seed two accounts with multi-day snapshots so we can verify daily/cumulative
    aggregation, deleted-post retention, and engagement-rate-on-totals."""
    from datetime import datetime, date, timedelta

    today = date.today()
    a1 = Account(
        zernio_id="z_a1", display_name="Account 1", health_status=HealthStatus.healthy
    )
    a2 = Account(
        zernio_id="z_a2", display_name="Account 2", health_status=HealthStatus.healthy
    )
    db.add_all([a1, a2])
    await db.flush()

    # Account 1 / Post A: published 5d ago, daily snapshots accumulating
    p_a = Post(
        account_id=a1.id,
        zernio_post_id="p_a",
        status=PostStatus.published,
        caption="A",
        published_at=datetime.utcnow() - timedelta(days=5),
    )
    # Account 1 / Post B: published 3d ago, two snapshots same day (we keep latest)
    p_b = Post(
        account_id=a1.id,
        zernio_post_id="p_b",
        status=PostStatus.published,
        caption="B",
        published_at=datetime.utcnow() - timedelta(days=3),
    )
    # Account 2 / Post C: published 4d ago, then DELETED 1d ago — keeps last value
    p_c = Post(
        account_id=a2.id,
        zernio_post_id="p_c",
        status=PostStatus.deleted,
        caption="C",
        published_at=datetime.utcnow() - timedelta(days=4),
    )
    db.add_all([p_a, p_b, p_c])
    await db.flush()

    def snap(post_id, day_offset, hour, views, likes, comments, shares):
        captured = datetime.combine(
            today - timedelta(days=day_offset), datetime.min.time()
        ) + timedelta(hours=hour)
        eng = (likes + comments + shares) / views * 100 if views > 0 else 0
        return MetricSnapshot(
            post_id=post_id,
            captured_at=captured,
            views=views,
            likes=likes,
            comments=comments,
            shares=shares,
            engagement_rate=round(eng, 4),
        )

    db.add_all(
        [
            # Post A: cumulative growth across 5 days
            snap(p_a.id, 5, 18, 100, 5, 1, 0),
            snap(p_a.id, 4, 18, 300, 20, 3, 1),
            snap(p_a.id, 3, 18, 600, 40, 5, 2),
            snap(p_a.id, 2, 18, 900, 60, 8, 3),
            snap(p_a.id, 1, 18, 1100, 75, 10, 4),
            snap(p_a.id, 0, 6, 1200, 80, 11, 4),
            # Post B: published 3d ago, two snapshots same day (keep latest)
            snap(p_b.id, 3, 12, 50, 3, 0, 0),
            snap(p_b.id, 3, 22, 200, 12, 1, 0),  # latest of day 3 — used
            snap(p_b.id, 2, 22, 500, 30, 2, 1),
            snap(p_b.id, 1, 22, 800, 50, 4, 2),
            snap(p_b.id, 0, 6, 1000, 65, 6, 3),
            # Post C: cumulative through deletion (last snapshot 1 day ago, then no more)
            snap(p_c.id, 4, 12, 200, 10, 1, 0),
            snap(p_c.id, 3, 12, 500, 30, 3, 1),
            snap(p_c.id, 2, 12, 700, 45, 5, 2),
            snap(p_c.id, 1, 12, 800, 50, 6, 2),
        ]
    )

    db.add_all(
        [
            FollowerSnapshot(
                account_id=a1.id, date=today - timedelta(days=5), count=4900,
                growth_abs=0, growth_pct=0,
            ),
            FollowerSnapshot(
                account_id=a1.id, date=today - timedelta(days=3), count=4950,
                growth_abs=50, growth_pct=1.0,
            ),
            FollowerSnapshot(
                account_id=a1.id, date=today, count=5000, growth_abs=50, growth_pct=1.0,
            ),
            FollowerSnapshot(
                account_id=a2.id, date=today - timedelta(days=5), count=2000,
                growth_abs=0, growth_pct=0,
            ),
            FollowerSnapshot(
                account_id=a2.id, date=today, count=2100, growth_abs=100, growth_pct=5.0,
            ),
        ]
    )

    await db.commit()
    return a1, a2, p_a, p_b, p_c


@pytest.mark.asyncio
async def test_combined_kpis_alltime(client, db, combined_seeded):
    response = await client.get("/api/analytics/combined?days=0")
    assert response.status_code == 200
    body = response.json()

    # All-time totals: latest snapshot per post, summed
    # Post A latest = 1200/80/11/4, Post B = 1000/65/6/3, Post C = 800/50/6/2
    # Total: views=3000, likes=195, comments=23, shares=9
    alltime = body["kpis"]["alltime"]
    assert alltime["views"] == 3000
    assert alltime["likes"] == 195
    assert alltime["comments"] == 23
    assert alltime["shares"] == 9
    assert alltime["engagement"] == 195 + 23 + 9  # 227
    # Engagement rate computed on totals: 227 / 3000 * 100 ≈ 7.5667
    assert abs(alltime["engagement_rate"] - 7.5667) < 0.01


@pytest.mark.asyncio
async def test_combined_window_kpis(client, db, combined_seeded):
    """3-day window: views earned = total now − total 3 days before window start.

    Window: days [today-2 .. today]. Pre-window cumulative = end-of-day(today-3).
    Post A had 600 views at end of day 3. Post B had 200 (latest of day 3).
    Post C had 500 at end of day 3. Pre-window total = 1300.
    Today total = 3000. Window earned = 1700.
    """
    response = await client.get("/api/analytics/combined?days=3")
    assert response.status_code == 200
    body = response.json()
    assert body["kpis"]["views"] == 1700


@pytest.mark.asyncio
async def test_combined_timeseries_cumulative_monotonic(client, db, combined_seeded):
    """Cumulative views must be monotonically non-decreasing day over day."""
    response = await client.get("/api/analytics/combined?days=0")
    body = response.json()
    series = body["timeseries"]
    assert len(series) >= 5
    cumvalues = [p["views_cumulative"] for p in series]
    assert all(b >= a for a, b in zip(cumvalues, cumvalues[1:])), cumvalues


@pytest.mark.asyncio
async def test_combined_daily_deltas_sum_to_window_kpi(client, db, combined_seeded):
    """Sum of daily deltas across the in-window timeseries equals the window KPI
    when the window does NOT touch the earliest data day."""
    response = await client.get("/api/analytics/combined?days=3")
    body = response.json()
    deltas_sum = sum(p["views_daily"] for p in body["timeseries"])
    assert deltas_sum == body["kpis"]["views"]


@pytest.mark.asyncio
async def test_combined_engagement_rate_uses_totals_not_average(client, db, combined_seeded):
    """Engagement rate must be sum(actions)/sum(views), NOT mean of per-post rates.

    With Post A 95/1200, Post B 74/1000, Post C 58/800:
      avg-of-rates = (7.917 + 7.4 + 7.25) / 3 = 7.522
      total/total  = (95+74+58) / (1200+1000+800) = 227 / 3000 = 7.567
    These differ enough to detect the bug.
    """
    response = await client.get("/api/analytics/combined?days=0")
    rate = response.json()["kpis"]["alltime"]["engagement_rate"]
    assert abs(rate - 7.5667) < 0.01
    assert abs(rate - 7.522) > 0.01


@pytest.mark.asyncio
async def test_combined_deleted_posts_retained_in_totals(client, db, combined_seeded):
    """Post C is deleted, but its 800 views must still count toward all-time."""
    response = await client.get("/api/analytics/combined?days=0")
    body = response.json()
    # Post C contributes 800 views; without it total would be 2200
    assert body["kpis"]["alltime"]["views"] == 3000
    # Top posts must still include the deleted post
    top = body["top_posts"]
    assert any(p["status"] == "deleted" for p in top)


@pytest.mark.asyncio
async def test_combined_leaderboard_per_account(client, db, combined_seeded):
    response = await client.get("/api/analytics/combined?days=0")
    rows = response.json()["leaderboard"]
    assert len(rows) == 2
    by_name = {r["display_name"]: r for r in rows}
    # Account 1 = post A + post B latest = 1200 + 1000 = 2200 views all-time
    assert by_name["Account 1"]["views_alltime"] == 2200
    # Account 2 = post C only = 800 views
    assert by_name["Account 2"]["views_alltime"] == 800
    # Followers
    assert by_name["Account 1"]["follower_count"] == 5000
    assert by_name["Account 2"]["follower_count"] == 2100


@pytest.mark.asyncio
async def test_combined_followers_aggregated(client, db, combined_seeded):
    response = await client.get("/api/analytics/combined?days=0")
    body = response.json()
    fk = body["kpis"]["followers"]
    # Latest sum: 5000 + 2100 = 7100
    assert fk["current"] == 7100
    # Series should have entries
    assert len(body["followers_timeseries"]) >= 1


@pytest.mark.asyncio
async def test_combined_handles_empty_db(client, db):
    """No accounts, no posts — endpoint should not 500."""
    response = await client.get("/api/analytics/combined?days=30")
    assert response.status_code == 200
    body = response.json()
    assert body["kpis"]["views"] == 0
    assert body["kpis"]["alltime"]["views"] == 0
    assert body["timeseries"] == []
    assert body["leaderboard"] == []
    assert body["top_posts"] == []


@pytest.mark.asyncio
async def test_combined_repeated_same_day_snapshots_use_latest(client, db, combined_seeded):
    """Post B has two snapshots on day 3 (12:00 → 50 views, 22:00 → 200 views).
    Day-3 cumulative for Post B must be 200, not 50 and not 250.
    """
    response = await client.get("/api/analytics/combined?days=0")
    series = response.json()["timeseries"]
    # Find the day where Post B first appears (3 days ago)
    from datetime import date as _date, timedelta
    target = (_date.today() - timedelta(days=3)).isoformat()
    point = next(p for p in series if p["date"] == target)
    # Day 3: A=600, B=200 (latest of day), C=500 → 1300 total cumulative
    assert point["views_cumulative"] == 1300


@pytest.mark.asyncio
async def test_combined_window_clamps_to_today(client, db, combined_seeded):
    response = await client.get("/api/analytics/combined?days=7")
    body = response.json()
    from datetime import date as _date
    assert body["window"]["end"] == _date.today().isoformat()
