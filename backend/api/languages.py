from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request

from backend.api.deps import Context
from backend.core.languages import DEFAULT_CODE, LANGUAGES
from backend.core.source_langs import SOURCES, SourceLanguage
from backend.engines.table import missing_files
from backend.manager.active import runs_on_cpu

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
