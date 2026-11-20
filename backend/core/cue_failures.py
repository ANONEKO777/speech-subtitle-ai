"""The cues a translation could not do, kept in `failures.<code>.json` so the window can show
them after the job is over. The job's report says them once, when the translate step ran, and a
cached translation has no report."""

from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from backend.core.languages import Language
from backend.core.subtitle_io import read_text_file, write_text_file


@dataclass(frozen=True, slots=True)
class CueFailures:
    failed: tuple[int, ...] = ()
    """Cues that failed every attempt: empty, or the source text, as the source's route says."""
    english: tuple[int, ...] = ()
    """The failed cues that show their English instead."""

    def __bool__(self) -> bool:
        return bool(self.failed or self.english)


def failures_file(lang: Language) -> str:
    return f"failures.{lang.file_code}.json"


def write(folder: Path, lang: Language, failed: Sequence[int], english: Sequence[int]) -> None:
    """Replace what the last run of the translate step left. An empty list removes the file."""
    path = folder / failures_file(lang)
    if not failed and not english:
        path.unlink(missing_ok=True)
        return
    doc = {"failed": sorted(set(failed)), "english": sorted(set(english))}
    write_text_file(path, json.dumps(doc) + "\n")


def _ids(value: object) -> tuple[int, ...]:
    if not isinstance(value, list):
        return ()
    return tuple(sorted({v for v in value if type(v) is int}))


def read(folder: Path, lang: Language) -> CueFailures:
    """What `write` left, or nothing when the file is missing or damaged."""
    path = folder / failures_file(lang)
    if not path.is_file():
        return CueFailures()
    try:
        doc = json.loads(read_text_file(path))
    except ValueError:
        return CueFailures()
    if not isinstance(doc, dict):
        return CueFailures()
    return CueFailures(_ids(doc.get("failed")), _ids(doc.get("english")))
