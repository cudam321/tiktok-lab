"""Thin wrapper to invoke OpenMontage tools from FastAPI."""

import asyncio
import json
import logging
import sys
from pathlib import Path
from typing import Any

from config import settings

logger = logging.getLogger(__name__)


def _require_openmontage() -> Path:
    """Return the configured OpenMontage root, or raise a clear error if unset.

    Phase 6 (AI content production) requires a separate, EXTERNAL OpenMontage
    install. Set ``OPENMONTAGE_PATH`` in your .env to enable it. This is checked
    lazily (at call time, not import time) so the rest of the app runs fine
    without OpenMontage configured.
    """
    path = settings.openmontage_path
    if path is None:
        raise RuntimeError(
            "OpenMontage is not configured. Phase 6 (AI content production) requires "
            "an external OpenMontage install — set OPENMONTAGE_PATH in your .env to its "
            "checkout root. See README for details."
        )
    return path


def _tool_runner_script(tool_name: str, inputs_json_path: str) -> str:
    """Generate a Python script that runs an OpenMontage tool."""
    return f"""
import json, sys
sys.path.insert(0, {str(settings.openmontage_path)!r})
from tools.tool_registry import registry
registry.discover()
tool = registry.get({tool_name!r})
if tool is None:
    print(json.dumps({{"success": False, "error": "Tool not found: {tool_name}"}}))
    sys.exit(1)
with open({inputs_json_path!r}) as f:
    inputs = json.load(f)
result = tool.execute(inputs)
print(json.dumps({{
    "success": result.success,
    "data": result.data,
    "artifacts": result.artifacts,
    "error": result.error,
    "duration_seconds": result.duration_seconds,
}}))
"""


async def run_tool(tool_name: str, inputs: dict[str, Any]) -> dict:
    """Run an OpenMontage tool via subprocess, return result dict."""
    _require_openmontage()
    tmp_dir = settings.data_dir / "tmp"
    tmp_dir.mkdir(parents=True, exist_ok=True)

    import time
    inputs_path = (tmp_dir / f"inputs_{tool_name}_{int(time.time() * 1000)}.json").resolve()
    inputs_path.write_text(json.dumps(inputs), encoding="utf-8")

    script = _tool_runner_script(tool_name, str(inputs_path))

    try:
        proc = await asyncio.create_subprocess_exec(
            sys.executable, "-c", script,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=str(settings.openmontage_path),
        )
        stdout, stderr = await proc.communicate()

        if proc.returncode != 0:
            logger.error(f"Tool {tool_name} failed: {stderr.decode()}")
            return {"success": False, "error": stderr.decode()[-500:]}

        return json.loads(stdout.decode())
    except Exception as e:
        logger.error(f"Failed to run tool {tool_name}: {e}")
        return {"success": False, "error": str(e)}
    finally:
        inputs_path.unlink(missing_ok=True)


async def list_tools() -> list[dict]:
    """Return available tools with their input_schemas."""
    _require_openmontage()
    script = f"""
import json, sys
sys.path.insert(0, {str(settings.openmontage_path)!r})
from tools.tool_registry import registry
registry.discover()
tools = []
for tool in registry.list_all_tools():
    info = tool.get_info()
    tools.append({{
        "name": info.get("name"),
        "tier": info.get("tier"),
        "capability": info.get("capability"),
        "input_schema": info.get("input_schema"),
        "status": tool.get_status().value if hasattr(tool.get_status(), 'value') else str(tool.get_status()),
    }})
print(json.dumps(tools))
"""
    try:
        proc = await asyncio.create_subprocess_exec(
            sys.executable, "-c", script,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=str(settings.openmontage_path),
        )
        stdout, stderr = await proc.communicate()
        if proc.returncode != 0:
            logger.error(f"Failed to list tools: {stderr.decode()}")
            return []
        return json.loads(stdout.decode())
    except Exception as e:
        logger.error(f"Failed to list tools: {e}")
        return []


async def probe_video(video_path: str) -> dict:
    """Probe a video and return displayed dimensions + duration.

    Reads rotation metadata (both ``side_data_list[].rotation`` for modern
    containers and the legacy ``tags.rotate``) and swaps width/height when the
    displayed orientation is ±90°. So a 4K clip shot vertically — which ffprobe
    reports as 3840x2160 with ``rotation=-90`` — comes back as 2160x3840 here.

    Returns ``{width, height, duration_s, rotation}``.
    """
    proc = await asyncio.create_subprocess_exec(
        "ffprobe", "-v", "error",
        "-select_streams", "v:0",
        "-show_streams",
        "-show_entries", "format=duration",
        "-of", "json", video_path,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, _ = await proc.communicate()
    probe = json.loads(stdout.decode() or "{}")

    streams = probe.get("streams") or []
    vs = next((s for s in streams if s.get("width")), streams[0] if streams else {})
    width = int(vs.get("width") or 1080)
    height = int(vs.get("height") or 1920)
    duration_s = float((probe.get("format") or {}).get("duration") or 0)

    rotation = 0
    for sd in vs.get("side_data_list") or []:
        if "rotation" in sd:
            try:
                rotation = int(sd["rotation"])
            except (TypeError, ValueError):
                rotation = 0
            break
    if rotation == 0:
        legacy = (vs.get("tags") or {}).get("rotate")
        if legacy:
            try:
                rotation = int(legacy)
            except (TypeError, ValueError):
                rotation = 0

    if abs(rotation) % 180 == 90:
        width, height = height, width

    return {"width": width, "height": height, "duration_s": duration_s, "rotation": rotation}


async def analyze_video(source_path: str, output_dir: str) -> dict:
    """Transcribe + probe a source video. Returns the canonical analysis shape.

    Shape:
        {
          "duration": float | None,
          "resolution": {"width": int, "height": int} | None,
          "transcript": {"text": str, "words": [{word, startMs, endMs}, ...]} | None
        }
    """
    from services.transcription import transcribe_video

    analysis: dict = {"transcript": None, "duration": None, "resolution": None}

    try:
        analysis["transcript"] = await transcribe_video(Path(source_path))
    except Exception as e:
        logger.error(f"Transcription failed for {source_path}: {e}")
        # Leave transcript as None; user can retry analyze.

    try:
        probe = await probe_video(source_path)
        analysis["duration"] = probe["duration_s"]
        analysis["resolution"] = {"width": probe["width"], "height": probe["height"]}
        analysis["rotation"] = probe["rotation"]
    except Exception as e:
        logger.error(f"ffprobe failed for {source_path}: {e}")

    return analysis


from typing import Awaitable, Callable

ProgressCallback = Callable[[float, str], Awaitable[None] | None]


async def render_remotion(
    composition: str,
    props: dict,
    output_path: str,
    width: int = 1080,
    height: int = 1920,
    fps: int = 30,
    duration_frames: int | None = None,
    on_progress: ProgressCallback | None = None,
) -> dict:
    """Render a Remotion composition via the progress-aware Node helper.

    The helper (remotion-composer/scripts/render-with-progress.mjs) uses
    ``@remotion/renderer``'s programmatic API and emits line-delimited JSON to
    stdout. We read those events and invoke ``on_progress(percent, phase)`` for
    each meaningful update.
    """
    _require_openmontage()
    composer_path = settings.remotion_composer_path
    script_path = composer_path / "scripts" / "render-with-progress.mjs"

    payload = {
        "composition": composition,
        "props": props,
        "outputPath": str(Path(output_path).resolve()),
        "width": width,
        "height": height,
        "fps": fps,
        "durationInFrames": duration_frames,
        "codec": "h264",
        "crf": 18,
    }

    async def _fire(pct: float, phase: str):
        if on_progress is None:
            return
        try:
            result = on_progress(pct, phase)
            if asyncio.iscoroutine(result):
                await result
        except Exception as cb_err:
            logger.warning(f"Progress callback raised: {cb_err}")

    try:
        proc = await asyncio.create_subprocess_exec(
            "node", str(script_path), f"--args={json.dumps(payload)}",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=str(composer_path),
        )

        stderr_chunks: list[bytes] = []

        async def drain_stderr():
            assert proc.stderr is not None
            async for line in proc.stderr:
                stderr_chunks.append(line)

        stderr_task = asyncio.create_task(drain_stderr())

        assert proc.stdout is not None
        last_error: str | None = None
        await _fire(0.0, "Starting render")

        async for raw in proc.stdout:
            line = raw.decode(errors="replace").strip()
            if not line:
                continue
            try:
                evt = json.loads(line)
            except json.JSONDecodeError:
                # Non-JSON chatter from sub-deps; ignore but log.
                logger.debug(f"Remotion stdout (non-JSON): {line}")
                continue
            kind = evt.get("event")
            if kind == "bundle-start":
                await _fire(0.02, "Bundling")
            elif kind == "bundle-progress":
                # Bundle phase is 0..5% of total progress.
                p = float(evt.get("progress") or 0)
                await _fire(0.02 + 0.03 * max(0.0, min(1.0, p)), "Bundling")
            elif kind == "bundle-done":
                await _fire(0.05, "Bundled")
            elif kind == "render-start":
                total = evt.get("totalFrames")
                await _fire(0.06, f"Rendering 0/{total or '?'} frames")
            elif kind == "render-progress":
                p = float(evt.get("progress") or 0)
                # Render phase is 5..95% of total progress.
                overall = 0.05 + 0.9 * max(0.0, min(1.0, p))
                rendered = evt.get("renderedFrames")
                total = evt.get("totalFrames")
                label = f"Rendering {rendered}/{total}" if total else "Rendering"
                await _fire(overall, label)
            elif kind == "done":
                await _fire(0.98, "Finalizing")
            elif kind == "error":
                last_error = evt.get("message") or "Unknown renderer error"

        rc = await proc.wait()
        await stderr_task
        stderr_text = b"".join(stderr_chunks).decode(errors="replace")

        if rc != 0:
            err = last_error or stderr_text[-500:] or f"node exited {rc}"
            logger.error(f"Remotion render failed: {err}")
            return {"success": False, "error": err}

        if not Path(output_path).exists():
            return {"success": False, "error": "Render produced no output file"}

        await _fire(1.0, "Done")
        return {"success": True, "output": output_path}
    except Exception as e:
        logger.exception(f"Remotion render error: {e}")
        return {"success": False, "error": str(e)}
