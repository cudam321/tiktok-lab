"""Production pipeline service — upload, analyze, render, publish."""

import json
import logging
import math
import shutil
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from config import settings
from db.models import (
    Production,
    ProductionStatus,
    ProductionVariant,
    RenderStatus,
    VariablePreset,
    Post,
    PostStatus,
    Experiment,
    ExperimentStatus,
    ExperimentAssignment,
)
from services import openmontage
from services.transcription import realign_words, words_to_text

logger = logging.getLogger(__name__)


# --- Live progress map ---
# In-memory per-variant progress so the /status endpoint can stream it to the
# UI. Keyed by variant_id. Updated at render-time from the Remotion helper's
# stdout events. Persisted progress in the DB would be overkill — the lifetime
# is just the current render.
_render_progress: dict[int, dict] = {}


def set_variant_progress(variant_id: int, percent: float, phase: str) -> None:
    _render_progress[variant_id] = {
        "percent": round(max(0.0, min(1.0, percent)) * 100, 1),
        "phase": phase,
    }


def get_variant_progress(variant_id: int) -> dict | None:
    return _render_progress.get(variant_id)


def clear_variant_progress(variant_id: int) -> None:
    _render_progress.pop(variant_id, None)


# --- Productions ---


async def create_production(db: AsyncSession, source_path: str) -> Production:
    prod = Production(source_video_path=source_path, status=ProductionStatus.uploaded)
    db.add(prod)
    await db.commit()
    # Reload with variants eagerly loaded so Pydantic serialization doesn't
    # trigger a lazy-load in an async context (would raise MissingGreenlet).
    result = await db.execute(
        select(Production)
        .options(selectinload(Production.variants))
        .where(Production.id == prod.id)
    )
    return result.scalar_one()


async def get_production(db: AsyncSession, production_id: int) -> Production | None:
    return (
        await db.execute(
            select(Production)
            .options(selectinload(Production.variants))
            .where(Production.id == production_id)
        )
    ).scalar_one_or_none()


async def analyze_production(db: AsyncSession, production_id: int) -> dict:
    prod = await get_production(db, production_id)
    if not prod:
        raise ValueError(f"Production {production_id} not found")

    prod.status = ProductionStatus.analyzing
    await db.commit()

    output_dir = str(settings.production_dir / str(production_id) / "analysis")
    Path(output_dir).mkdir(parents=True, exist_ok=True)

    try:
        analysis = await openmontage.analyze_video(prod.source_video_path, output_dir)
        prod.analysis = analysis
        prod.status = ProductionStatus.ready
        await db.commit()
        return analysis
    except Exception as e:
        logger.error(f"Analysis failed for production {production_id}: {e}")
        prod.status = ProductionStatus.failed
        await db.commit()
        raise


async def list_productions(db: AsyncSession) -> list[Production]:
    result = await db.execute(
        select(Production)
        .options(selectinload(Production.variants))
        .order_by(Production.created_at.desc())
    )
    return list(result.scalars().all())


# --- Variants ---


async def add_variant(
    db: AsyncSession,
    production_id: int,
    preset_id: int | None,
    variant_label: str,
    tool_config: dict,
) -> ProductionVariant:
    variant = ProductionVariant(
        production_id=production_id,
        preset_id=preset_id,
        variant_label=variant_label,
        tool_config=tool_config,
    )
    db.add(variant)
    await db.commit()
    await db.refresh(variant)
    return variant


async def get_variants(db: AsyncSession, production_id: int) -> list[ProductionVariant]:
    result = await db.execute(
        select(ProductionVariant)
        .where(ProductionVariant.production_id == production_id)
        .order_by(ProductionVariant.created_at)
    )
    return list(result.scalars().all())


async def delete_variant(db: AsyncSession, variant_id: int) -> None:
    variant = (
        await db.execute(
            select(ProductionVariant).where(ProductionVariant.id == variant_id)
        )
    ).scalar_one_or_none()
    if variant:
        await db.delete(variant)
        await db.commit()


# --- Rendering ---


async def render_variant(db: AsyncSession, variant_id: int) -> None:
    """Render a single variant: pre-process → Remotion render."""
    variant = (
        await db.execute(
            select(ProductionVariant).where(ProductionVariant.id == variant_id)
        )
    ).scalar_one_or_none()
    if not variant:
        raise ValueError(f"Variant {variant_id} not found")

    prod = await get_production(db, variant.production_id)
    if not prod:
        raise ValueError(f"Production {variant.production_id} not found")

    variant.render_status = RenderStatus.rendering
    await db.commit()
    set_variant_progress(variant.id, 0.0, "Queued")

    prod_dir = settings.production_dir / str(prod.id)
    prod_dir.mkdir(parents=True, exist_ok=True)
    config = variant.tool_config

    try:
        # Normalize shape. Two accepted layouts in tool_config:
        #   Legacy (single variable):
        #     { "remotion": {"composition": "VariableCaptions", "props": {...}},
        #       "pre_process": [...] }
        #   Multi-variable (VariantComposer):
        #     { "variables": [{"type": "captions", "params": {...}, "pre_process": [...]}, ...] }
        variables_list = config.get("variables")

        # Step 1: Pre-process with OpenMontage tools. For multi-variable
        # variants we aggregate each variable's pre_process into one chain.
        current_video = prod.source_video_path
        if variables_list:
            pre_process_steps = []
            for v in variables_list:
                pre_process_steps.extend(v.get("pre_process") or [])
        else:
            pre_process_steps = config.get("pre_process", [])
        n_pre = len(pre_process_steps)

        for i, step in enumerate(pre_process_steps):
            tool_name = step["tool"]
            # Pre-process phase maps to 0..5% overall so the render phase gets
            # the bulk of the bar. Each pre-process step is an even slice.
            step_start = (i / n_pre) * 0.05
            set_variant_progress(variant.id, step_start, f"Pre-process {i + 1}/{n_pre}: {tool_name}")
            inputs = dict(step.get("inputs", {}))
            output = str(prod_dir / f"preprocess_{variant.id}_{i}_{tool_name}.mp4")
            inputs["input_path"] = current_video
            inputs["output_path"] = output

            result = await openmontage.run_tool(tool_name, inputs)
            if not result.get("success"):
                raise RuntimeError(f"Pre-process {tool_name} failed: {result.get('error')}")
            current_video = output

        # Step 2: Remotion render
        remotion_config = config.get("remotion")
        needs_remotion = bool(variables_list or remotion_config)
        if needs_remotion:
            if variables_list:
                composition = "VariantComposer"
                overlay_variables = [
                    {
                        "type": v["type"],
                        "params": dict(v.get("params") or {}),
                    }
                    for v in variables_list
                    # Pre-process-only variables have no Remotion overlay — skip.
                    if v["type"] in {"captions", "persistent_text", "text_overlay"}
                ]
                props = {"variables": overlay_variables}
            else:
                assert remotion_config is not None
                composition = remotion_config["composition"]
                props = dict(remotion_config.get("props", {}))

            # Copy video to Remotion public folder
            composer_pub = settings.remotion_composer_path / "public" / "productions"
            composer_pub.mkdir(parents=True, exist_ok=True)
            video_filename = f"variant_{variant.id}.mp4"
            dest_video = composer_pub / video_filename
            shutil.copy2(current_video, dest_video)
            props["videoSrc"] = f"public/productions/{video_filename}"

            # Always overwrite captions from the canonical transcript on the
            # Production, so edits to wording propagate to every variant
            # without needing to re-save.
            if prod.analysis:
                words = (prod.analysis.get("transcript") or {}).get("words") or []
                if words:
                    props["captions"] = words

            # Displayed dimensions (rotation-aware) — so a vertical-shot 4K clip
            # renders as 2160x3840 instead of upside-down 3840x2160.
            probe = await openmontage.probe_video(current_video)
            src_w = probe["width"]
            src_h = probe["height"]
            duration_s = probe["duration_s"] or 30
            duration_frames = math.ceil(duration_s * 30)

            # Cap output at 1080x1920 (TikTok's native max — the platform
            # downscales larger uploads to this anyway, so rendering at 4K is
            # pure waste). Preserve source aspect + orientation; snap to even
            # dimensions (H.264 requires even width/height). Never upscale.
            is_portrait = src_h >= src_w
            max_w = 1080 if is_portrait else 1920
            max_h = 1920 if is_portrait else 1080
            scale = min(max_w / src_w, max_h / src_h, 1.0)
            width = max(2, round(src_w * scale / 2) * 2)
            height = max(2, round(src_h * scale / 2) * 2)
            logger.info(
                f"Variant {variant.id}: source {src_w}x{src_h} → render {width}x{height} (scale {scale:.3f})"
            )

            output_path = str(prod_dir / f"variant_{variant.id}_final.mp4")

            # The Remotion helper reports 0..1 progress. We map its 0..1 to the
            # render phase of the variant's overall bar — pre-process took 0..5%,
            # so Remotion runs 5..100%.
            def _on_progress(pct: float, phase: str) -> None:
                overall = 0.05 + 0.95 * max(0.0, min(1.0, pct))
                set_variant_progress(variant.id, overall, phase)

            render_result = await openmontage.render_remotion(
                composition=composition,
                props=props,
                output_path=output_path,
                width=width,
                height=height,
                duration_frames=duration_frames,
                on_progress=_on_progress,
            )

            if not render_result.get("success"):
                raise RuntimeError(f"Remotion render failed: {render_result.get('error')}")

            variant.output_path = output_path
        else:
            # No Remotion step — pre-processed video is the final output
            variant.output_path = current_video

        variant.render_status = RenderStatus.done
        set_variant_progress(variant.id, 1.0, "Done")
        await db.commit()
        logger.info(f"Variant {variant.id} rendered successfully: {variant.output_path}")

    except Exception as e:
        logger.error(f"Render failed for variant {variant.id}: {e}")
        variant.render_status = RenderStatus.failed
        variant.error_message = str(e)[:500]
        set_variant_progress(variant.id, 0.0, f"Failed: {str(e)[:120]}")
        await db.commit()
        raise


async def render_all(db: AsyncSession, production_id: int) -> None:
    """Queue all pending variants for rendering."""
    prod = await get_production(db, production_id)
    if not prod:
        raise ValueError(f"Production {production_id} not found")

    prod.status = ProductionStatus.rendering
    await db.commit()

    variants = await get_variants(db, production_id)
    pending = [v for v in variants if v.render_status == RenderStatus.pending]

    for variant in pending:
        try:
            await render_variant(db, variant.id)
        except Exception as e:
            logger.error(f"Variant {variant.id} render failed: {e}")
            continue

    # Check final status
    variants = await get_variants(db, production_id)
    all_done = all(v.render_status == RenderStatus.done for v in variants)
    any_failed = any(v.render_status == RenderStatus.failed for v in variants)

    if all_done:
        prod.status = ProductionStatus.done
    elif any_failed:
        prod.status = ProductionStatus.failed
    await db.commit()


async def render_all_background(production_id: int) -> None:
    """Run ``render_all`` with an owned AsyncSession.

    The API endpoint kicks off rendering via ``asyncio.create_task`` which
    outlives the request. The request's session is closed when the handler
    returns, so the background task MUST open its own session — otherwise every
    DB call silently no-ops and nothing renders.
    """
    from db.database import async_session

    async with async_session() as db:
        try:
            await render_all(db, production_id)
        except Exception as e:
            logger.exception(f"Background render for production {production_id} failed: {e}")
            # Best-effort: mark production failed so the UI stops spinning.
            try:
                prod = await get_production(db, production_id)
                if prod:
                    prod.status = ProductionStatus.failed
                    await db.commit()
            except Exception:
                pass


# --- Publishing ---


async def publish_production(
    db: AsyncSession, production_id: int, account_id: int
) -> list[Post]:
    """Create Post drafts from rendered variants + auto-create experiment."""
    prod = await get_production(db, production_id)
    if not prod:
        raise ValueError(f"Production {production_id} not found")

    variants = await get_variants(db, production_id)
    done_variants = [v for v in variants if v.render_status == RenderStatus.done]
    if not done_variants:
        raise ValueError("No rendered variants to publish")

    # Auto-create experiment (1 clip = 1 implicit experiment)
    experiment = Experiment(
        name=f"Production #{prod.id}",
        variable="production_variant",
        variants=[v.variant_label for v in done_variants],
        hypothesis="Testing variable combinations on source clip",
        status=ExperimentStatus.running,
        account_id=account_id,
    )
    db.add(experiment)
    await db.flush()

    posts = []
    for variant in done_variants:
        post = Post(
            account_id=account_id,
            status=PostStatus.draft,
            caption=f"Variant {variant.variant_label}",
            media_path=variant.output_path,
            production_id=str(prod.id),
        )
        db.add(post)
        await db.flush()

        variant.post_id = post.id

        assignment = ExperimentAssignment(
            post_id=post.id,
            experiment_id=experiment.id,
            variant_name=variant.variant_label,
        )
        db.add(assignment)
        posts.append(post)

    await db.commit()
    return posts


# --- Transcript editing ---


async def update_transcript(
    db: AsyncSession,
    production_id: int,
    *,
    words: list[dict] | None = None,
    text: str | None = None,
) -> dict:
    """Update a production's transcript.

    Pass either ``words`` (a verbatim word list with timings) or ``text``
    (full edited text — timings are realigned against the current transcript
    via diff). Returns the new transcript dict.
    """
    if words is None and text is None:
        raise ValueError("Pass either `words` or `text`")

    prod = await get_production(db, production_id)
    if not prod:
        raise ValueError(f"Production {production_id} not found")

    analysis = dict(prod.analysis or {})
    current = dict(analysis.get("transcript") or {})
    current_words = list(current.get("words") or [])

    if words is not None:
        new_words = [
            {
                "word": str(w.get("word", "")).strip(),
                "startMs": int(w.get("startMs", 0)),
                "endMs": int(w.get("endMs", 0)),
            }
            for w in words
            if str(w.get("word", "")).strip()
        ]
    else:
        assert text is not None
        new_words = realign_words(current_words, text)

    new_transcript = {"text": words_to_text(new_words), "words": new_words}
    analysis["transcript"] = new_transcript
    prod.analysis = analysis
    # SQLAlchemy doesn't auto-detect in-place JSON mutations; force it.
    from sqlalchemy.orm.attributes import flag_modified
    flag_modified(prod, "analysis")
    await db.commit()
    return new_transcript
