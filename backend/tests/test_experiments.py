"""Tests for experiment engine — CRUD, assignment, statistics."""

import pytest
import math
from datetime import datetime

from db.models import (
    Account,
    Post,
    PostStatus,
    MetricSnapshot,
    Experiment,
    ExperimentAssignment,
    ExperimentStatus,
    HealthStatus,
)
from services.experiments import (
    create_experiment,
    get_experiment,
    list_experiments,
    start_experiment,
    complete_experiment,
    delete_experiment,
    assign_post_to_variant,
    get_variant_counts,
    compare_experiment,
    mann_whitney_u,
    bayesian_ab,
    EXPERIMENT_VARIABLES,
)


# --- Fixtures ---


@pytest.fixture
async def account(db):
    a = Account(
        zernio_id="zernio_exp_test",
        display_name="Exp Test",
        health_status=HealthStatus.healthy,
    )
    db.add(a)
    await db.commit()
    await db.refresh(a)
    return a


@pytest.fixture
async def experiment(db, account):
    return await create_experiment(
        db,
        name="Hook A vs B",
        variable="hook_style",
        variants=["question_hook", "statement_hook"],
        hypothesis="Questions get more engagement",
        account_id=account.id,
    )


# --- CRUD Tests ---


@pytest.mark.asyncio
async def test_create_experiment(db, account):
    exp = await create_experiment(
        db,
        name="Test Exp",
        variable="posting_time",
        variants=["morning", "evening"],
    )
    assert exp.id is not None
    assert exp.status == ExperimentStatus.draft
    assert exp.variants == ["morning", "evening"]


@pytest.mark.asyncio
async def test_create_invalid_variable(db):
    with pytest.raises(ValueError, match="Invalid variable"):
        await create_experiment(db, name="Bad", variable="invalid_var", variants=["a", "b"])


@pytest.mark.asyncio
async def test_create_insufficient_variants(db):
    with pytest.raises(ValueError, match="at least 2"):
        await create_experiment(db, name="Bad", variable="hook_style", variants=["only_one"])


@pytest.mark.asyncio
async def test_list_experiments(db, experiment):
    exps = await list_experiments(db)
    assert len(exps) >= 1


@pytest.mark.asyncio
async def test_start_and_complete(db, experiment):
    started = await start_experiment(db, experiment.id)
    assert started.status == ExperimentStatus.running

    completed = await complete_experiment(db, experiment.id)
    assert completed.status == ExperimentStatus.completed
    assert completed.completed_at is not None


@pytest.mark.asyncio
async def test_delete_running_blocked(db, experiment):
    await start_experiment(db, experiment.id)
    with pytest.raises(ValueError, match="Cannot delete a running"):
        await delete_experiment(db, experiment.id)


@pytest.mark.asyncio
async def test_delete_draft(db, experiment):
    result = await delete_experiment(db, experiment.id)
    assert result is True


# --- Assignment Tests ---


@pytest.mark.asyncio
async def test_assign_post_to_variant(db, account, experiment):
    post = Post(account_id=account.id, status=PostStatus.draft, caption="Test")
    db.add(post)
    await db.commit()
    await db.refresh(post)

    assignment = await assign_post_to_variant(
        db, post.id, experiment.id, "question_hook"
    )
    assert assignment.variant_name == "question_hook"


@pytest.mark.asyncio
async def test_assign_invalid_variant(db, account, experiment):
    post = Post(account_id=account.id, status=PostStatus.draft, caption="Test")
    db.add(post)
    await db.commit()
    await db.refresh(post)

    with pytest.raises(ValueError, match="not in experiment"):
        await assign_post_to_variant(db, post.id, experiment.id, "nonexistent")


@pytest.mark.asyncio
async def test_assign_duplicate_blocked(db, account, experiment):
    post = Post(account_id=account.id, status=PostStatus.draft, caption="Test")
    db.add(post)
    await db.commit()
    await db.refresh(post)

    await assign_post_to_variant(db, post.id, experiment.id, "question_hook")
    with pytest.raises(ValueError, match="already assigned"):
        await assign_post_to_variant(db, post.id, experiment.id, "statement_hook")


@pytest.mark.asyncio
async def test_variant_counts(db, account, experiment):
    for i in range(3):
        p = Post(account_id=account.id, status=PostStatus.draft, caption=f"P{i}")
        db.add(p)
        await db.flush()
        db.add(ExperimentAssignment(
            post_id=p.id, experiment_id=experiment.id, variant_name="question_hook"
        ))
    for i in range(2):
        p = Post(account_id=account.id, status=PostStatus.draft, caption=f"Q{i}")
        db.add(p)
        await db.flush()
        db.add(ExperimentAssignment(
            post_id=p.id, experiment_id=experiment.id, variant_name="statement_hook"
        ))
    await db.commit()

    counts = await get_variant_counts(db, experiment.id)
    assert counts["question_hook"] == 3
    assert counts["statement_hook"] == 2


# --- Statistical Tests (known inputs/outputs) ---


class TestMannWhitneyU:
    """Mann-Whitney U with known expected values."""

    def test_identical_samples(self):
        result = mann_whitney_u([1, 2, 3, 4, 5], [1, 2, 3, 4, 5])
        assert result["p_value"] is not None
        assert result["significant"] is False

    def test_clearly_different(self):
        """Two clearly separated distributions should be significant."""
        a = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]
        b = [11, 12, 13, 14, 15, 16, 17, 18, 19, 20]
        result = mann_whitney_u(a, b)
        assert result["significant"] is True
        assert result["p_value"] < 0.01

    def test_known_u_statistic(self):
        """Small sample with manually verifiable U."""
        # A = [1, 2, 3], B = [4, 5, 6]
        # All A < all B → U_A = 0
        result = mann_whitney_u([1, 2, 3], [4, 5, 6])
        assert result["u_stat"] == 0.0

    def test_overlapping(self):
        """Overlapping distributions: should NOT be significant."""
        a = [2, 4, 6, 8, 10]
        b = [3, 5, 7, 9, 11]
        result = mann_whitney_u(a, b)
        assert result["significant"] is False

    def test_empty_sample(self):
        result = mann_whitney_u([], [1, 2, 3])
        assert result["u_stat"] is None
        assert result["significant"] is False

    def test_single_values(self):
        result = mann_whitney_u([1], [2])
        assert result["u_stat"] is not None


class TestBayesianAB:
    """Bayesian posterior with known behavior."""

    def test_b_clearly_better(self):
        a = [1.0, 2.0, 1.5, 2.5, 1.8, 2.2, 1.3, 1.9, 2.1, 1.7]
        b = [5.0, 6.0, 5.5, 6.5, 5.8, 6.2, 5.3, 5.9, 6.1, 5.7]
        result = bayesian_ab(a, b)
        assert result["prob_b_better"] > 0.99
        assert result["mean_diff"] > 0
        assert result["preliminary"] is False

    def test_a_clearly_better(self):
        a = [10.0, 11.0, 12.0, 10.5, 11.5]
        b = [1.0, 2.0, 1.5, 2.5, 1.8]
        result = bayesian_ab(a, b)
        assert result["prob_b_better"] < 0.01

    def test_similar_distributions(self):
        a = [5.0, 5.1, 4.9, 5.2, 4.8, 5.0, 5.1, 4.9, 5.0, 5.1]
        b = [5.0, 5.0, 5.1, 4.9, 5.0, 5.1, 4.9, 5.0, 5.0, 5.1]
        result = bayesian_ab(a, b)
        # Should be close to 50/50
        assert 0.3 < result["prob_b_better"] < 0.7

    def test_preliminary_flag(self):
        """< 10 samples per variant → preliminary."""
        result = bayesian_ab([1, 2, 3], [4, 5, 6])
        assert result["preliminary"] is True

    def test_insufficient_data(self):
        result = bayesian_ab([1], [2])
        assert result["prob_b_better"] is None

    def test_credible_interval(self):
        a = [1.0, 2.0, 3.0, 4.0, 5.0]
        b = [6.0, 7.0, 8.0, 9.0, 10.0]
        result = bayesian_ab(a, b)
        assert result["ci_lower"] > 0  # entire CI should be positive
        assert result["ci_upper"] > result["ci_lower"]


# --- API Endpoint Tests ---


@pytest.mark.asyncio
async def test_list_variables_endpoint(client):
    response = await client.get("/api/experiments/variables")
    assert response.status_code == 200
    data = response.json()
    assert "hook_style" in data["variables"]


@pytest.mark.asyncio
async def test_create_experiment_endpoint(client, db):
    response = await client.post(
        "/api/experiments",
        json={
            "name": "API Test",
            "variable": "posting_time",
            "variants": ["morning", "evening"],
        },
    )
    assert response.status_code == 201
    assert response.json()["status"] == "draft"


@pytest.mark.asyncio
async def test_experiment_lifecycle_endpoint(client, db):
    # Create
    res = await client.post(
        "/api/experiments",
        json={"name": "Lifecycle", "variable": "hook_style", "variants": ["a", "b"]},
    )
    exp_id = res.json()["id"]

    # Start
    res = await client.post(f"/api/experiments/{exp_id}/start")
    assert res.json()["status"] == "running"

    # Complete
    res = await client.post(f"/api/experiments/{exp_id}/complete")
    assert res.json()["status"] == "completed"


@pytest.mark.asyncio
async def test_get_experiment_not_found(client):
    response = await client.get("/api/experiments/999")
    assert response.status_code == 404
