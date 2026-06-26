"""Variable preset endpoints for the Workshop."""

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from config import settings
from db.database import get_db
from db.models import VariablePreset
from services import openmontage

router = APIRouter(prefix="/api/presets", tags=["presets"])


# --- Response / Request Models ---


class PresetResponse(BaseModel):
    id: int
    name: str
    variable_type: str
    remotion_composition: str
    params: dict
    pre_process: list[dict] | None
    preview_thumbnail: str | None
    created_at: datetime
    updated_at: datetime | None

    model_config = {"from_attributes": True}


class CreatePresetRequest(BaseModel):
    name: str
    variable_type: str
    remotion_composition: str
    params: dict = {}
    pre_process: list[dict] | None = None


class UpdatePresetRequest(BaseModel):
    name: str | None = None
    params: dict | None = None
    pre_process: list[dict] | None = None
    remotion_composition: str | None = None


class TestToolRequest(BaseModel):
    tool: str
    inputs: dict


# --- Endpoints ---


@router.get("", response_model=list[PresetResponse])
async def list_presets(db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(VariablePreset).order_by(VariablePreset.created_at.desc())
    )
    return result.scalars().all()


@router.post("", response_model=PresetResponse, status_code=201)
async def create_preset(req: CreatePresetRequest, db: AsyncSession = Depends(get_db)):
    preset = VariablePreset(
        name=req.name,
        variable_type=req.variable_type,
        remotion_composition=req.remotion_composition,
        params=req.params,
        pre_process=req.pre_process,
    )
    db.add(preset)
    await db.commit()
    await db.refresh(preset)
    return preset


@router.get("/{preset_id}", response_model=PresetResponse)
async def get_preset(preset_id: int, db: AsyncSession = Depends(get_db)):
    preset = (
        await db.execute(select(VariablePreset).where(VariablePreset.id == preset_id))
    ).scalar_one_or_none()
    if not preset:
        raise HTTPException(404, "Preset not found")
    return preset


@router.put("/{preset_id}", response_model=PresetResponse)
async def update_preset(
    preset_id: int, req: UpdatePresetRequest, db: AsyncSession = Depends(get_db)
):
    preset = (
        await db.execute(select(VariablePreset).where(VariablePreset.id == preset_id))
    ).scalar_one_or_none()
    if not preset:
        raise HTTPException(404, "Preset not found")

    if req.name is not None:
        preset.name = req.name
    if req.params is not None:
        preset.params = req.params
    if req.pre_process is not None:
        preset.pre_process = req.pre_process
    if req.remotion_composition is not None:
        preset.remotion_composition = req.remotion_composition

    await db.commit()
    await db.refresh(preset)
    return preset


@router.delete("/{preset_id}", status_code=204)
async def delete_preset(preset_id: int, db: AsyncSession = Depends(get_db)):
    preset = (
        await db.execute(select(VariablePreset).where(VariablePreset.id == preset_id))
    ).scalar_one_or_none()
    if not preset:
        raise HTTPException(404, "Preset not found")
    await db.delete(preset)
    await db.commit()


@router.post("/{preset_id}/test")
async def test_preset(
    preset_id: int,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
):
    """Apply a preset's pre-process tools to an uploaded test clip."""
    preset = (
        await db.execute(select(VariablePreset).where(VariablePreset.id == preset_id))
    ).scalar_one_or_none()
    if not preset:
        raise HTTPException(404, "Preset not found")
    if not preset.pre_process:
        raise HTTPException(400, "This preset has no pre-process tools to test")

    # Save uploaded file
    test_dir = settings.uploads_dir / "test_clips"
    test_dir.mkdir(parents=True, exist_ok=True)
    test_path = test_dir / file.filename
    content = await file.read()
    test_path.write_bytes(content)

    # Run pre-process steps
    current_video = str(test_path)
    for i, step in enumerate(preset.pre_process):
        tool_name = step["tool"]
        inputs = dict(step.get("inputs", {}))
        output = str(test_dir / f"test_{preset_id}_{i}_{tool_name}.mp4")
        inputs["input_path"] = current_video
        inputs["output_path"] = output

        result = await openmontage.run_tool(tool_name, inputs)
        if not result.get("success"):
            raise HTTPException(500, f"Tool {tool_name} failed: {result.get('error')}")
        current_video = output

    return FileResponse(current_video, media_type="video/mp4")


@router.post("/test-raw")
async def test_raw(
    req: TestToolRequest,
    file: UploadFile = File(...),
):
    """Test arbitrary tool params on an uploaded clip."""
    test_dir = settings.uploads_dir / "test_clips"
    test_dir.mkdir(parents=True, exist_ok=True)
    test_path = test_dir / file.filename
    content = await file.read()
    test_path.write_bytes(content)

    inputs = dict(req.inputs)
    output = str(test_dir / f"test_raw_{req.tool}.mp4")
    inputs["input_path"] = str(test_path)
    inputs["output_path"] = output

    result = await openmontage.run_tool(req.tool, inputs)
    if not result.get("success"):
        raise HTTPException(500, f"Tool {req.tool} failed: {result.get('error')}")

    return FileResponse(output, media_type="video/mp4")


@router.post("/transcribe")
async def transcribe_clip(file: UploadFile = File(...)):
    """Transcribe a Workshop test clip via the shared transcription service."""
    from services.transcription import transcribe_video

    test_dir = settings.uploads_dir / "test_clips"
    test_dir.mkdir(parents=True, exist_ok=True)
    safe_name = (file.filename or "clip.mov").replace(" ", "_")
    test_path = test_dir / safe_name
    content = await file.read()
    test_path.write_bytes(content)

    try:
        result = await transcribe_video(test_path)
    except RuntimeError as e:
        raise HTTPException(400, str(e))
    except FileNotFoundError as e:
        raise HTTPException(500, str(e))
    except Exception as e:
        raise HTTPException(500, f"Transcription failed: {e}")

    return {"captions": result["words"], "text": result["text"]}


@router.get("/tools/list")
async def list_tools():
    """List available OpenMontage tools with input schemas."""
    tools = await openmontage.list_tools()
    return {"tools": tools}
