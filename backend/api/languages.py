from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from backend.core.languages import DEFAULT_CODE, LANGUAGES

router = APIRouter(prefix="/api", tags=["languages"])


@router.get("/languages")
def list_languages() -> dict[str, Any]:
    """The target languages a job may ask for, and the file names each one writes."""
    return {
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
