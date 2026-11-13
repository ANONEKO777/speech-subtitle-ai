from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field

from backend.api.deps import Context
from backend.core.audio import AudioError
from backend.core.language_detect import Detection
from backend.core.languages import DEFAULT_CODE, LANGUAGES
from backend.core.media import accepted_extensions, is_media
from backend.core.source_langs import MIXED_SOURCE, SOURCES, SourceLanguage
from backend.engines.base import EngineError
from backend.engines.table import missing_files
from backend.manager.active import runs_on_cpu
from backend.manager.detect import Undetectable

router = APIRouter(prefix="/api", tags=["languages"])


def _unavailable(source: SourceLanguage, request: Request, ctx: Context) -> str | None:
    """Why a job in this source language would be refused on this machine, before it starts:
    `cpu` when jobs run on the CPU and the speech engine has no CPU build, `missing_files` when
    the engine is not installed. None when it can run."""
    if source.asr_engine is None:
        return None
    if runs_on_cpu(request.app.state.user_data, ctx.detect_hardware, ctx.registry):
        return "cpu"
    if missing_files(source.asr_engine, ctx.storage, registry=ctx.registry):
        return "missing_files"
    return None


@router.get("/languages")
def list_languages(request: Request, ctx: Context) -> dict[str, Any]:
    """The target languages a job may ask for, the file names each one writes, and the source
    languages a video may be in with whether this machine can process each one now."""
    reasons = {code: _unavailable(source, request, ctx) for code, source in SOURCES.items()}
    return {
        "sources": [
            {
                "code": source.code,
                "name": source.name,
                "native_name": source.native,
                "available": reasons[source.code] is None,
                "reason": reasons[source.code],
            }
            for source in SOURCES.values()
        ],
        "default": DEFAULT_CODE,
        "languages": [
            {
                "code": lang.code,
                "name": lang.name,
                "native_name": lang.native,
                "quality": lang.quality,
                "files": {
                    "subtitles": lang.files.srt,
                    "bilingual_ass": lang.files.ass,
                    "bilingual_vtt": lang.files.vtt,
                    "summary": lang.files.summary,
                },
            }
            for lang in LANGUAGES.values()
        ],
    }


class DetectBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    video_path: str = Field(min_length=1)


def _detected_json(found: Detection, mixed_reason: str | None) -> dict[str, Any]:
    """`detected` is what the audio holds and `suggested` what the window may preselect: the
    same, except that a talk in both languages is suggested as the language that spoke most when
    this machine cannot process a mixed one (`mixed_unavailable` then says why)."""
    suggested = found.code
    mixed_unavailable = None
    if found.code == MIXED_SOURCE.code and mixed_reason is not None:
        suggested = max(found.shares, key=lambda item: item[1])[0]
        mixed_unavailable = mixed_reason
    return {
        "detected": found.code,
        "suggested": suggested,
        "mixed_unavailable": mixed_unavailable,
        "confidence": round(found.confidence, 3),
        "sure": found.sure,
        "shares": {code: round(value, 3) for code, value in found.shares},
        "clear": found.clear,
        "samples": [
            {
                "start_s": round(s.start_s, 1),
                "code": s.heard.code,
                "probability": s.heard.probability,
                "speech_s": round(s.speech_s, 2),
            }
            for s in found.samples
        ],
    }


@router.post("/languages/detect")
def detect_language(body: DetectBody, request: Request, ctx: Context) -> dict[str, Any]:
    """Name the language of a video from a few short pieces of its audio, so the window can
    preselect it. It is a guess (the `confidence` is the share of pieces that agree) and a refusal
    here (503) only means there is no guess, never that the video is bad."""
    video = Path(body.video_path)
    if not video.is_absolute() or not video.is_file() or not is_media(video):
        raise HTTPException(
            422,
            f"video_path must be the absolute path of a media file ({accepted_extensions()}): "
            f"{video}",
        )
    try:
        found = request.app.state.detector(video)
    except (Undetectable, EngineError, AudioError) as exc:
        raise HTTPException(503, str(exc)) from exc
    return _detected_json(found, _unavailable(MIXED_SOURCE, request, ctx))
