"""Experiment engine — CRUD, variant assignment, statistical comparison."""

import logging
import math
from datetime import datetime
from typing import Any

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from db.models import (
    Experiment,
    ExperimentAssignment,
    ExperimentStatus,
    Post,
    PostStatus,
    MetricSnapshot,
)

logger = logging.getLogger(__name__)

EXPERIMENT_VARIABLES = [
    # Original analyst variables
    "hook_style",
    "posting_time",
    "hashtag_strategy",
    "caption_style",
    "edit_pace",
    "video_length",
    "content_type",
    "text_overlay",
    # Production variables (Phase 6)
    "music_style",
    "color_grade",
    "effects",
    "target_duration",
]


# --- CRUD ---


async def list_experiments(
    db: AsyncSession,
    status: ExperimentStatus | None = None,
    account_id: int | None = None,
) -> list[Experiment]:
    query = select(Experiment).order_by(Experiment.created_at.desc())
    if status:
        query = query.where(Experiment.status == status)
    if account_id:
        query = query.where(Experiment.account_id == account_id)
    return list((await db.execute(query)).scalars().all())


async def get_experiment(db: AsyncSession, experiment_id: int) -> Experiment | None:
    return (
        await db.execute(
            select(Experiment)
            .where(Experiment.id == experiment_id)
            .options(selectinload(Experiment.assignments))
        )
    ).scalar_one_or_none()


async def create_experiment(
    db: AsyncSession,
    name: str,
    variable: str,
    variants: list[str],
    hypothesis: str | None = None,
    metric_target: str = "engagement_rate",
    min_sample_size: int = 10,
    account_id: int | None = None,
) -> Experiment:
    if variable not in EXPERIMENT_VARIABLES:
        raise ValueError(
            f"Invalid variable '{variable}'. Must be one of: {', '.join(EXPERIMENT_VARIABLES)}"
        )
    if len(variants) < 2:
        raise ValueError("Need at least 2 variants")

    experiment = Experiment(
        name=name,
        variable=variable,
        variants=variants,
        hypothesis=hypothesis,
        metric_target=metric_target,
        min_sample_size=min_sample_size,
        account_id=account_id,
        status=ExperimentStatus.draft,
    )
    db.add(experiment)
    await db.commit()
    await db.refresh(experiment)
    logger.info(f"Created experiment: {name}")
    return experiment


async def update_experiment(
    db: AsyncSession,
    experiment_id: int,
    name: str | None = None,
    hypothesis: str | None = None,
    status: ExperimentStatus | None = None,
) -> Experiment:
    exp = await get_experiment(db, experiment_id)
    if not exp:
        raise ValueError("Experiment not found")

    if name is not None:
        exp.name = name
    if hypothesis is not None:
        exp.hypothesis = hypothesis
    if status is not None:
        if status == ExperimentStatus.completed:
            exp.completed_at = datetime.utcnow()
        exp.status = status

    await db.commit()
    await db.refresh(exp)
    return exp


async def start_experiment(db: AsyncSession, experiment_id: int) -> Experiment:
    return await update_experiment(db, experiment_id, status=ExperimentStatus.running)


async def complete_experiment(db: AsyncSession, experiment_id: int) -> Experiment:
    return await update_experiment(db, experiment_id, status=ExperimentStatus.completed)


async def delete_experiment(db: AsyncSession, experiment_id: int) -> bool:
    exp = await get_experiment(db, experiment_id)
    if not exp:
        return False
    if exp.status == ExperimentStatus.running:
        raise ValueError("Cannot delete a running experiment — pause or complete it first")
    await db.delete(exp)
    await db.commit()
    return True


# --- Variant Assignment ---


async def assign_post_to_variant(
    db: AsyncSession,
    post_id: int,
    experiment_id: int,
    variant_name: str,
) -> ExperimentAssignment:
    exp = await get_experiment(db, experiment_id)
    if not exp:
        raise ValueError("Experiment not found")
    if variant_name not in exp.variants:
        raise ValueError(f"Variant '{variant_name}' not in experiment variants: {exp.variants}")

    # Check if post already assigned
    existing = (
        await db.execute(
            select(ExperimentAssignment).where(
                ExperimentAssignment.post_id == post_id
            )
        )
    ).scalar_one_or_none()
    if existing:
        raise ValueError("Post is already assigned to an experiment")

    assignment = ExperimentAssignment(
        post_id=post_id,
        experiment_id=experiment_id,
        variant_name=variant_name,
    )
    db.add(assignment)
    await db.commit()
    await db.refresh(assignment)
    return assignment


async def get_variant_counts(db: AsyncSession, experiment_id: int) -> dict[str, int]:
    """Count posts per variant."""
    rows = (
        await db.execute(
            select(
                ExperimentAssignment.variant_name,
                func.count(ExperimentAssignment.id),
            )
            .where(ExperimentAssignment.experiment_id == experiment_id)
            .group_by(ExperimentAssignment.variant_name)
        )
    ).all()
    return {row[0]: row[1] for row in rows}


# --- Statistical Comparison ---


async def get_variant_metrics(
    db: AsyncSession, experiment_id: int, metric: str = "engagement_rate"
) -> dict[str, list[float]]:
    """Get metric values per variant for published posts."""
    assignments = (
        await db.execute(
            select(ExperimentAssignment)
            .where(ExperimentAssignment.experiment_id == experiment_id)
            .options(selectinload(ExperimentAssignment.post))
        )
    ).scalars().all()

    variant_values: dict[str, list[float]] = {}

    for assignment in assignments:
        post = assignment.post
        if not post or post.status != PostStatus.published:
            continue

        # Get latest metric snapshot
        snapshot = (
            await db.execute(
                select(MetricSnapshot)
                .where(MetricSnapshot.post_id == post.id)
                .order_by(MetricSnapshot.captured_at.desc())
                .limit(1)
            )
        ).scalar_one_or_none()

        if snapshot:
            value = getattr(snapshot, metric, None)
            if value is not None:
                variant_values.setdefault(assignment.variant_name, []).append(float(value))

    return variant_values


def mann_whitney_u(sample_a: list[float], sample_b: list[float]) -> dict[str, Any]:
    """Mann-Whitney U test. Returns U statistic, z-score, and approximate p-value.

    Pure Python implementation — no scipy dependency.
    """
    n_a = len(sample_a)
    n_b = len(sample_b)

    if n_a == 0 or n_b == 0:
        return {"u_stat": None, "z_score": None, "p_value": None, "significant": False}

    # Combine and rank
    combined = [(v, "a") for v in sample_a] + [(v, "b") for v in sample_b]
    combined.sort(key=lambda x: x[0])

    # Assign ranks (handle ties with average rank)
    ranks: list[float] = []
    i = 0
    while i < len(combined):
        j = i
        while j < len(combined) and combined[j][0] == combined[i][0]:
            j += 1
        avg_rank = (i + 1 + j) / 2.0
        for _ in range(i, j):
            ranks.append(avg_rank)
        i = j

    # Sum of ranks for group A
    rank_sum_a = sum(ranks[k] for k in range(len(combined)) if combined[k][1] == "a")

    u_a = rank_sum_a - n_a * (n_a + 1) / 2
    u_b = n_a * n_b - u_a
    u_stat = min(u_a, u_b)

    # Normal approximation for z-score
    mean_u = n_a * n_b / 2
    std_u = math.sqrt(n_a * n_b * (n_a + n_b + 1) / 12)

    if std_u == 0:
        return {"u_stat": u_stat, "z_score": 0, "p_value": 1.0, "significant": False}

    z_score = (u_stat - mean_u) / std_u

    # Approximate two-tailed p-value using error function
    p_value = erfc_approx(abs(z_score) / math.sqrt(2))

    return {
        "u_stat": round(u_stat, 4),
        "z_score": round(z_score, 4),
        "p_value": round(p_value, 6),
        "significant": p_value < 0.05,
    }


def erfc_approx(x: float) -> float:
    """Approximate complementary error function (Abramowitz & Stegun)."""
    t = 1.0 / (1.0 + 0.3275911 * abs(x))
    poly = t * (
        0.254829592
        + t * (-0.284496736 + t * (1.421413741 + t * (-1.453152027 + t * 1.061405429)))
    )
    result = poly * math.exp(-x * x)
    return result if x >= 0 else 2.0 - result


def bayesian_ab(
    sample_a: list[float], sample_b: list[float], n_simulations: int = 10000
) -> dict[str, Any]:
    """Bayesian A/B comparison using conjugate normal-normal model.

    Returns probability that B > A, mean difference, and credible interval.
    Uses moment-matching rather than MCMC for speed.
    """
    if len(sample_a) < 2 or len(sample_b) < 2:
        return {
            "prob_b_better": None,
            "mean_diff": None,
            "ci_lower": None,
            "ci_upper": None,
            "preliminary": True,
        }

    mean_a = sum(sample_a) / len(sample_a)
    mean_b = sum(sample_b) / len(sample_b)
    var_a = sum((x - mean_a) ** 2 for x in sample_a) / (len(sample_a) - 1)
    var_b = sum((x - mean_b) ** 2 for x in sample_b) / (len(sample_b) - 1)

    se_a = math.sqrt(var_a / len(sample_a)) if var_a > 0 else 0.001
    se_b = math.sqrt(var_b / len(sample_b)) if var_b > 0 else 0.001

    # Difference of means: B - A
    diff_mean = mean_b - mean_a
    diff_se = math.sqrt(se_a**2 + se_b**2)

    if diff_se == 0:
        prob_b_better = 0.5
    else:
        # P(B > A) ≈ Φ(diff_mean / diff_se) using normal CDF
        z = diff_mean / diff_se
        prob_b_better = 0.5 * (1 + math.erf(z / math.sqrt(2)))

    # 95% credible interval on (B - A)
    ci_lower = diff_mean - 1.96 * diff_se
    ci_upper = diff_mean + 1.96 * diff_se

    min_n = min(len(sample_a), len(sample_b))

    return {
        "prob_b_better": round(prob_b_better, 4),
        "mean_diff": round(diff_mean, 4),
        "ci_lower": round(ci_lower, 4),
        "ci_upper": round(ci_upper, 4),
        "preliminary": min_n < 10,
        "sample_sizes": {"a": len(sample_a), "b": len(sample_b)},
    }


async def compare_experiment(
    db: AsyncSession, experiment_id: int
) -> dict[str, Any]:
    """Run full statistical comparison for an experiment."""
    exp = await get_experiment(db, experiment_id)
    if not exp:
        raise ValueError("Experiment not found")

    metric = exp.metric_target or "engagement_rate"
    variant_metrics = await get_variant_metrics(db, experiment_id, metric)
    variant_counts = await get_variant_counts(db, experiment_id)

    variants = exp.variants
    if len(variants) != 2:
        return {
            "error": "Statistical comparison currently supports exactly 2 variants",
            "variant_counts": variant_counts,
        }

    a_name, b_name = variants[0], variants[1]
    sample_a = variant_metrics.get(a_name, [])
    sample_b = variant_metrics.get(b_name, [])

    mw_result = mann_whitney_u(sample_a, sample_b)
    bayes_result = bayesian_ab(sample_a, sample_b)

    # Summary stats per variant
    def stats(values: list[float]) -> dict:
        if not values:
            return {"n": 0, "mean": None, "median": None, "std": None}
        n = len(values)
        mean = sum(values) / n
        sorted_v = sorted(values)
        median = sorted_v[n // 2] if n % 2 else (sorted_v[n // 2 - 1] + sorted_v[n // 2]) / 2
        std = math.sqrt(sum((x - mean) ** 2 for x in values) / n) if n > 1 else 0
        return {
            "n": n,
            "mean": round(mean, 4),
            "median": round(median, 4),
            "std": round(std, 4),
        }

    result = {
        "experiment_id": experiment_id,
        "metric": metric,
        "variants": {
            a_name: stats(sample_a),
            b_name: stats(sample_b),
        },
        "mann_whitney": mw_result,
        "bayesian": bayes_result,
        "conclusion": _interpret(mw_result, bayes_result, a_name, b_name),
    }

    # Update experiment with results
    exp.result_summary = result["conclusion"]
    exp.confidence = mw_result.get("p_value")
    await db.commit()

    return result


def _interpret(
    mw: dict, bayes: dict, a_name: str, b_name: str
) -> str:
    """Human-readable conclusion."""
    if bayes.get("prob_b_better") is None:
        return "Insufficient data for comparison."

    prob = bayes["prob_b_better"]
    preliminary = bayes.get("preliminary", True)
    sig = mw.get("significant", False)

    if preliminary:
        if prob > 0.7:
            return f"Preliminary signal: {b_name} trending better (P={prob:.0%}). Need more data."
        elif prob < 0.3:
            return f"Preliminary signal: {a_name} trending better (P={1-prob:.0%}). Need more data."
        else:
            return "Too early to tell — variants performing similarly so far."

    if sig:
        winner = b_name if prob > 0.5 else a_name
        p = mw["p_value"]
        return f"{winner} is statistically better (p={p:.4f}, Bayesian P={max(prob, 1-prob):.0%})."
    else:
        return f"No significant difference detected (p={mw.get('p_value', 'N/A')}). Consider extending the experiment."
