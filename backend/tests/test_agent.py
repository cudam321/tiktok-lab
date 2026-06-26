"""Tests for agent tools — integration tests with real DB queries."""

import pytest
from datetime import datetime, date, timedelta

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
    AgentConversation,
    AgentInsight,
    InsightType,
    InsightPriority,
)
from agent.tools import (
    execute_tool,
    query_post_metrics,
    query_follower_trends,
    get_account_health,
    get_content_calendar,
    suggest_next_post,
    suggest_experiment_tool,
    flag_underperformers,
    TOOL_DEFINITIONS,
    TOOL_MAP,
)
from services.agent_service import get_insights, mark_insight_read


# --- Fixtures ---


@pytest.fixture
async def account(db):
    a = Account(
        zernio_id="zernio_agent_test",
        display_name="Agent Test",
        health_status=HealthStatus.healthy,
        last_synced_at=datetime.utcnow(),
    )
    db.add(a)
    await db.commit()
    await db.refresh(a)
    return a


@pytest.fixture
async def posts_with_metrics(db, account):
    """Create published posts with metric snapshots."""
    posts = []
    for i in range(5):
        p = Post(
            account_id=account.id,
            zernio_post_id=f"zp_{i}",
            status=PostStatus.published,
            caption=f"Test post {i}",
            published_at=datetime.utcnow() - timedelta(days=i),
        )
        db.add(p)
        await db.flush()

        snap = MetricSnapshot(
            post_id=p.id,
            views=1000 * (i + 1),
            likes=50 * (i + 1),
            comments=10 * (i + 1),
            shares=5 * (i + 1),
            engagement_rate=round((50 + 10 + 5) * (i + 1) / (1000 * (i + 1)) * 100, 2),
        )
        db.add(snap)
        posts.append(p)

    await db.commit()
    return posts


@pytest.fixture
async def follower_data(db, account):
    for i in range(10):
        d = date.today() - timedelta(days=9 - i)
        snap = FollowerSnapshot(
            account_id=account.id,
            date=d,
            count=5000 + i * 50,
            growth_abs=50,
            growth_pct=1.0,
        )
        db.add(snap)
    await db.commit()


# --- Tool Definition Tests ---


def test_all_tools_defined():
    """Every tool in TOOL_MAP must have a definition."""
    defined_names = {t["name"] for t in TOOL_DEFINITIONS}
    for name in TOOL_MAP:
        assert name in defined_names, f"Tool '{name}' missing from TOOL_DEFINITIONS"


def test_tool_definitions_have_schemas():
    for tool in TOOL_DEFINITIONS:
        assert "name" in tool
        assert "description" in tool
        assert "input_schema" in tool
        assert tool["input_schema"]["type"] == "object"


# --- query_post_metrics ---


@pytest.mark.asyncio
async def test_query_post_metrics(db, account, posts_with_metrics):
    result = await query_post_metrics(db, account_id=account.id, days=30)
    assert result["total"] == 5
    assert len(result["posts"]) == 5
    assert result["posts"][0]["views"] > 0


@pytest.mark.asyncio
async def test_query_post_metrics_sorted(db, account, posts_with_metrics):
    result = await query_post_metrics(db, account_id=account.id, sort_by="views", limit=3)
    assert len(result["posts"]) == 3
    views = [p["views"] for p in result["posts"]]
    assert views == sorted(views, reverse=True)


@pytest.mark.asyncio
async def test_query_post_metrics_empty(db):
    result = await query_post_metrics(db, account_id=999)
    assert result["total"] == 0


# --- query_follower_trends ---


@pytest.mark.asyncio
async def test_follower_trends(db, account, follower_data):
    result = await query_follower_trends(db, account_id=account.id, days=30)
    assert result["current_count"] > 0
    assert result["total_growth"] > 0
    assert len(result["recent_days"]) > 0


@pytest.mark.asyncio
async def test_follower_trends_not_found(db):
    result = await query_follower_trends(db, account_id=999)
    assert "error" in result


# --- get_account_health ---


@pytest.mark.asyncio
async def test_account_health(db, account, posts_with_metrics):
    result = await get_account_health(db, account_id=account.id)
    assert len(result["accounts"]) == 1
    assert result["accounts"][0]["health_status"] == "healthy"


@pytest.mark.asyncio
async def test_account_health_all(db, account):
    result = await get_account_health(db)
    assert len(result["accounts"]) >= 1


# --- get_content_calendar ---


@pytest.mark.asyncio
async def test_content_calendar(db, account):
    # Add a scheduled post
    p = Post(
        account_id=account.id,
        status=PostStatus.scheduled,
        caption="Scheduled",
        scheduled_at=datetime.utcnow() + timedelta(days=1),
    )
    db.add(p)
    await db.commit()

    result = await get_content_calendar(db, account_id=account.id)
    assert result["total_scheduled"] == 1
    assert len(result["gap_days"]) > 0


# --- suggest_next_post ---


@pytest.mark.asyncio
async def test_suggest_next_post(db, account, posts_with_metrics):
    result = await suggest_next_post(db, account_id=account.id)
    assert result["data_points"] == 5
    assert result["avg_engagement_30d"] > 0
    assert "suggestion" in result


@pytest.mark.asyncio
async def test_suggest_next_post_no_data(db, account):
    result = await suggest_next_post(db, account_id=account.id)
    assert result["data_points"] == 0
    assert "Not enough data" in result["suggestion"]


# --- suggest_experiment ---


@pytest.mark.asyncio
async def test_suggest_experiment(db, account):
    result = await suggest_experiment_tool(db, account_id=account.id)
    assert len(result["untested_variables"]) > 0
    assert result["suggestion"] is not None
    assert "variable" in result["suggestion"]


@pytest.mark.asyncio
async def test_suggest_experiment_after_testing(db, account):
    # Create an experiment for one variable
    exp = Experiment(
        name="Test",
        variable="hook_style",
        variants=["a", "b"],
        status=ExperimentStatus.running,
        account_id=account.id,
    )
    db.add(exp)
    await db.commit()

    result = await suggest_experiment_tool(db, account_id=account.id)
    assert "hook_style" in result["tested_variables"]
    assert "hook_style" not in result["untested_variables"]


# --- flag_underperformers ---


@pytest.mark.asyncio
async def test_flag_underperformers_clean(db, account):
    result = await flag_underperformers(db)
    # With healthy data and no extreme drops, should have few/no alerts
    assert "alerts" in result


@pytest.mark.asyncio
async def test_flag_sync_gap(db):
    """Account with stale sync should trigger sync_gap alert."""
    a = Account(
        zernio_id="stale_sync",
        display_name="Stale",
        health_status=HealthStatus.healthy,
        last_synced_at=datetime.utcnow() - timedelta(hours=5),
    )
    db.add(a)
    await db.commit()

    result = await flag_underperformers(db)
    sync_alerts = [a for a in result["alerts"] if a["type"] == "sync_gap"]
    assert len(sync_alerts) >= 1


# --- execute_tool dispatch ---


@pytest.mark.asyncio
async def test_execute_tool_unknown(db):
    result = await execute_tool(db, "nonexistent_tool", {})
    assert "error" in result


@pytest.mark.asyncio
async def test_execute_tool_dispatch(db, account, posts_with_metrics):
    result = await execute_tool(db, "query_post_metrics", {"account_id": account.id})
    assert "posts" in result


# --- Insights ---


@pytest.mark.asyncio
async def test_insights_crud(db):
    insight = AgentInsight(
        type=InsightType.briefing,
        title="Test Briefing",
        body="Test body content",
        priority=InsightPriority.low,
    )
    db.add(insight)
    await db.commit()
    await db.refresh(insight)

    insights = await get_insights(db)
    assert len(insights) >= 1

    unread = await get_insights(db, unread_only=True)
    assert len(unread) >= 1

    await mark_insight_read(db, insight.id)
    unread_after = await get_insights(db, unread_only=True)
    assert len(unread_after) < len(unread)


# --- API Endpoint Tests ---


@pytest.mark.asyncio
async def test_chat_empty_message(client):
    response = await client.post("/api/agent/chat", json={"message": ""})
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_chat_no_api_key(client, monkeypatch):
    """Without API key, agent returns a helpful message."""
    monkeypatch.setattr("config.settings.anthropic_api_key", "")
    monkeypatch.setattr("config.settings.openai_api_key", "")
    response = await client.post("/api/agent/chat", json={"message": "Hello"})
    assert response.status_code == 200
    assert "not configured" in response.json()["response"]


@pytest.mark.asyncio
async def test_insights_endpoint(client):
    response = await client.get("/api/agent/insights")
    assert response.status_code == 200
    assert isinstance(response.json(), list)
