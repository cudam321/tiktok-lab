"""Unified transcription service.

One pipeline, one word shape, used by both Workshop preview transcription and
Production analyze. Edits on a Production's transcript round-trip through
``realign_words`` so users can rewrite wording (fix typos, brand names,
punctuation) without losing per-word timings.

Word shape (canonical across the app):
    {"word": str, "startMs": int, "endMs": int}
"""

from __future__ import annotations

import asyncio
import difflib
import logging
import re
from pathlib import Path
from typing import TypedDict

from config import settings

logger = logging.getLogger(__name__)


class Word(TypedDict):
    word: str
    startMs: int
    endMs: int


class Transcript(TypedDict):
    text: str
    words: list[Word]


WHISPER_LIMIT_MB = 24.5


async def transcribe_video(video_path: Path) -> Transcript:
    """Extract audio and transcribe via OpenAI Whisper API, returning canonical words."""
    from openai import AsyncOpenAI

    if not settings.openai_api_key:
        raise RuntimeError("OPENAI_API_KEY not set — needed for Whisper transcription")

    video_path = Path(video_path)
    if not video_path.exists():
        raise FileNotFoundError(f"Video not found: {video_path}")

    audio_path = video_path.with_suffix(".transcribe.mp3")
    proc = await asyncio.create_subprocess_exec(
        "ffmpeg", "-y",
        "-i", str(video_path),
        "-vn",
        "-ac", "1",
        "-ar", "16000",
        "-b:a", "64k",
        "-f", "mp3",
        str(audio_path),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    _, stderr = await proc.communicate()
    if proc.returncode != 0:
        raise RuntimeError(f"Audio extraction failed: {stderr.decode()[-400:]}")

    size_mb = audio_path.stat().st_size / (1024 * 1024)
    if size_mb > WHISPER_LIMIT_MB:
        raise RuntimeError(
            f"Extracted audio is {size_mb:.1f} MB, over Whisper's 25 MB limit. "
            "Source video is too long — split it before transcribing."
        )

    client = AsyncOpenAI(api_key=settings.openai_api_key)
    with open(audio_path, "rb") as f:
        resp = await client.audio.transcriptions.create(
            model="whisper-1",
            file=f,
            response_format="verbose_json",
            timestamp_granularities=["word"],
        )

    words: list[Word] = []
    for w in getattr(resp, "words", []) or []:
        words.append({
            "word": w.word.strip(),
            "startMs": int(w.start * 1000),
            "endMs": int(w.end * 1000),
        })

    return {"text": (resp.text or "").strip(), "words": words}


# --- Realignment ---

_WORD_SPLIT_RE = re.compile(r"\S+")


def _tokenize(text: str) -> list[str]:
    return _WORD_SPLIT_RE.findall(text.strip())


# Minimum per-token duration when interpolating inserts/replacements. Keeps
# inserted words visible even when neighbors have no natural gap.
_MIN_PER_TOKEN_MS = 180


def _interpolate(
    edited_tokens: list[str],
    span_start_ms: int,
    span_end_ms: int,
) -> list[Word]:
    """Spread edited tokens evenly across the given time span.

    If the span is smaller than ``n * _MIN_PER_TOKEN_MS``, the span is extended
    past ``span_end_ms`` so each token gets a legible duration. This can cause
    overlap with the next original word; CaptionOverlay resolves overlaps by
    picking the first matching page at the current frame time.
    """
    n = len(edited_tokens)
    if n == 0:
        return []
    total = max(span_end_ms - span_start_ms, n * _MIN_PER_TOKEN_MS)
    per = total / n
    out: list[Word] = []
    for i, tok in enumerate(edited_tokens):
        s = int(span_start_ms + i * per)
        e = int(span_start_ms + (i + 1) * per)
        out.append({"word": tok, "startMs": s, "endMs": e})
    return out


def realign_words(original: list[Word], edited_text: str) -> list[Word]:
    """Return new word list from edited text, preserving timings where possible.

    Uses a sequence diff between the original tokens and the edited tokens:
      - equal ranges: copy originals verbatim
      - replace ranges: spread new tokens across the replaced time span
      - insert ranges: interpolate within the gap between neighbors
      - delete ranges: drop

    Casing/punctuation edits on matched words are respected by overriding the
    original ``word`` field with the edited token for equal ranges (so
    capitalization and punctuation fixes stick) — but we still match on a
    normalized form so minor punctuation differences don't block alignment.
    """
    if not original:
        # Nothing to align to — best effort: distribute across [0, 0].
        tokens = _tokenize(edited_text)
        if not tokens:
            return []
        # Without any timing reference, give each token a nominal 300ms slot.
        out: list[Word] = []
        cursor = 0
        for tok in tokens:
            out.append({"word": tok, "startMs": cursor, "endMs": cursor + 300})
            cursor += 300
        return out

    edited_tokens = _tokenize(edited_text)
    if not edited_tokens:
        return []

    norm = lambda s: re.sub(r"[^\w]", "", s).lower()
    orig_norm = [norm(w["word"]) for w in original]
    edit_norm = [norm(t) for t in edited_tokens]

    matcher = difflib.SequenceMatcher(a=orig_norm, b=edit_norm, autojunk=False)

    result: list[Word] = []
    for op, i1, i2, j1, j2 in matcher.get_opcodes():
        if op == "equal":
            # Copy original timings, but take the edited token (preserves case/punct).
            for k in range(i2 - i1):
                orig = original[i1 + k]
                result.append({
                    "word": edited_tokens[j1 + k],
                    "startMs": orig["startMs"],
                    "endMs": orig["endMs"],
                })
        elif op == "replace":
            # Span = time covered by the removed originals.
            span_start = original[i1]["startMs"]
            span_end = original[i2 - 1]["endMs"]
            result.extend(_interpolate(edited_tokens[j1:j2], span_start, span_end))
        elif op == "insert":
            # No originals to borrow from — interpolate between neighbors.
            prev_end = original[i1 - 1]["endMs"] if i1 > 0 else 0
            next_start = (
                original[i1]["startMs"]
                if i1 < len(original)
                else prev_end + 600 * (j2 - j1)
            )
            result.extend(_interpolate(edited_tokens[j1:j2], prev_end, next_start))
        elif op == "delete":
            # Originals vanish — nothing to emit.
            continue

    # Enforce monotonically non-decreasing timings.
    for i in range(1, len(result)):
        if result[i]["startMs"] < result[i - 1]["startMs"]:
            result[i]["startMs"] = result[i - 1]["startMs"]
        if result[i]["endMs"] < result[i]["startMs"]:
            result[i]["endMs"] = result[i]["startMs"] + 1

    return result


def words_to_text(words: list[Word]) -> str:
    """Join words back into a single text string."""
    return " ".join(w["word"] for w in words).strip()
