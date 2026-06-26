"""Production pipeline endpoints — upload, analyze, render, publish."""

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from config import settings
from db.database import get_db
from db.models import ProductionStatus, RenderStatus
from services import production as prod_service

router = APIRouter(prefix="/api/productions", tags=["productions"])


# --- Response / Request Models ---


class VariantResponse(BaseModel):
    id: int
    production_id: int
    preset_id: int | None
    variant_label: str
    tool_config: dict
    render_status: RenderStatus
    output_path: str | None
    error_message: str | None
    post_id: int | None
    created_at: datetime

    model_config = {"from_attributes": True}


class ProductionResponse(BaseModel):
    id: int
    source_video_path: str
    analysis: dict | None
    status: ProductionStatus
    created_at: datetime
    variants: list[VariantResponse] = []

    model_config = {"from_attributes": True}


class AddVariantRequest(BaseModel):
    preset_id: int | None = None
    variant_label: str
    tool_config: dict


class PublishRequest(BaseModel):
    account_id: int


class WordUpdate(BaseModel):
    word: str
    startMs: int
    endMs: int


class TranscriptUpdate(BaseModel):
    """Either ``words`` (explicit list) or ``text`` (full-text realign)."""
    words: list[WordUpdate] | None = None
    text: str | None = None


# --- Endpoints ---


@router.get("", response_model=list[ProductionResponse])
async def list_productions(db: AsyncSession = Depends(get_db)):
    prods = await prod_service.list_productions(db)
    return prods


@router.post("", response_model=ProductionResponse, status_code=201)
async def upload_production(
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
):
    """Upload a source video to start a new production."""
    upload_dir = settings.production_dir / "uploads"
    upload_dir.mkdir(parents=True, exist_ok=True)

    import time
    filename = f"{int(time.time())}_{file.filename}"
    source_path = upload_dir / filename
    content = await file.read()
    source_path.write_bytes(content)

    prod = await prod_service.create_production(db, str(source_path))

    # Create production-specific directory
    prod_dir = settings.production_dir / str(prod.id)
    prod_dir.mkdir(parents=True, exist_ok=True)

    return prod


@router.get("/{production_id}", response_model=ProductionResponse)
async def get_production(production_id: int, db: AsyncSession = Depends(get_db)):
    prod = await prod_service.get_production(db, production_id)
    if not prod:
        raise HTTPException(404, "Production not found")
    return prod


@router.patch("/{production_id}/transcript")
async def update_production_transcript(
    production_id: int,
    req: TranscriptUpdate,
    db: AsyncSession = Depends(get_db),
):
    """Update the canonical transcript. Accepts either explicit word list or edited text."""
    try:
        words_payload = [w.model_dump() for w in req.words] if req.words is not None else None
        transcript = await prod_service.update_transcript(
            db, production_id, words=words_payload, text=req.text
        )
        return transcript
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.post("/{production_id}/analyze")
async def analyze_production(production_id: int, db: AsyncSession = Depends(get_db)):
    """Trigger video analysis (transcription, metadata)."""
    try:
        analysis = await prod_service.analyze_production(db, production_id)
        return {"status": "done", "analysis": analysis}
    except ValueError as e:
        raise HTTPException(404, str(e))
    except Exception as e:
        raise HTTPException(500, f"Analysis failed: {e}")


@router.post("/{production_id}/variants", response_model=VariantResponse, status_code=201)
async def add_variant(
    production_id: int,
    req: AddVariantRequest,
    db: AsyncSession = Depends(get_db),
):
    variant = await prod_service.add_variant(
        db, production_id, req.preset_id, req.variant_label, req.tool_config
    )
    return variant


@router.delete("/{production_id}/variants/{variant_id}", status_code=204)
async def delete_variant(
    production_id: int, variant_id: int, db: AsyncSession = Depends(get_db)
):
    await prod_service.delete_variant(db, variant_id)


@router.get("/{production_id}/variants/{variant_id}/preview")
async def get_variant_preview(
    production_id: int, variant_id: int, db: AsyncSession = Depends(get_db)
):
    """Return Remotion props for previewing this variant in @remotion/player."""
    from sqlalchemy import select
    from db.models import ProductionVariant

    variant = (
        await db.execute(
            select(ProductionVariant).where(ProductionVariant.id == variant_id)
        )
    ).scalar_one_or_none()
    if not variant:
        raise HTTPException(404, "Variant not found")

    prod = await prod_service.get_production(db, production_id)
    if not prod:
        raise HTTPException(404, "Production not found")

    config = variant.tool_config
    remotion_config = config.get("remotion", {})
    props = dict(remotion_config.get("props", {}))

    # Set video source for browser preview
    props["videoSrc"] = f"http://localhost:8000/api/productions/{production_id}/source"

    # Always sync captions from the canonical production transcript so variants
    # reflect the latest user edits.
    if prod.analysis:
        words = (prod.analysis.get("transcript") or {}).get("words") or []
        if words:
            props["captions"] = words

    return {
        "composition": remotion_config.get("composition", "VariablePreview"),
        "props": props,
        "pre_process": config.get("pre_process", []),
    }


@router.get("/{production_id}/source")
async def get_source_video(production_id: int, db: AsyncSession = Depends(get_db)):
    """Serve the source video file for browser preview."""
    from fastapi.responses import FileResponse

    prod = await prod_service.get_production(db, production_id)
    if not prod:
        raise HTTPException(404, "Production not found")
    return FileResponse(prod.source_video_path, media_type="video/mp4")


@router.post("/{production_id}/render")
async def start_render(production_id: int, db: AsyncSession = Depends(get_db)):
    """Start batch rendering all pending variants."""
    prod = await prod_service.get_production(db, production_id)
    if not prod:
        raise HTTPException(404, "Production not found")

    # Background task owns its own DB session — the request's session is
    # closed once this handler returns.
    import asyncio
    asyncio.create_task(prod_service.render_all_background(production_id))

    return {"status": "rendering", "message": "Render started in background"}


@router.get("/{production_id}/status")
async def get_render_status(production_id: int, db: AsyncSession = Depends(get_db)):
    """Poll render progress for all variants."""
    prod = await prod_service.get_production(db, production_id)
    if not prod:
        raise HTTPException(404, "Production not found")

    variants = await prod_service.get_variants(db, production_id)
    return {
        "production_status": prod.status.value,
        "variants": [
            {
                "id": v.id,
                "label": v.variant_label,
                "render_status": v.render_status.value,
                "output_path": v.output_path,
                "error": v.error_message,
                "progress": prod_service.get_variant_progress(v.id),
            }
            for v in variants
        ],
    }


@router.post("/{production_id}/publish")
async def publish_production(
    production_id: int, req: PublishRequest, db: AsyncSession = Depends(get_db)
):
    """Create Post drafts from rendered variants + auto-create experiment."""
    try:
        posts = await prod_service.publish_production(db, production_id, req.account_id)
        return {
            "status": "published",
            "posts": [{"id": p.id, "caption": p.caption} for p in posts],
        }
    except ValueError as e:
        raise HTTPException(400, str(e))
