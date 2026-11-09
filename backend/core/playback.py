"""What watching leaves in a project: where the person stopped and how far the subtitles are
shifted. It lives in `playback.json` beside the pipeline files, which no step reads or writes, so
saving it never touches a job's outputs."""

from __future__ import annotations

import json
from collections.abc import Iterable
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, cast

from backend.core.model import Cue
from backend.core.subtitle_io import read_text_file, write_text_file

PLAYBACK_JSON = "playback.json"
MAX_OFFSET_MS = 60_000


@dataclass(frozen=True, slots=True)
class Playback:
    position_s: float = 0.0
    duration_s: float = 0.0
    offset_ms: int = 0
    opened_at_ms: int = 0


def _number(raw: object, low: float, high: float, default: float) -> float:
    ok = isinstance(raw, int | float) and not isinstance(raw, bool) and low <= raw <= high
    return float(raw) if ok and isinstance(raw, int | float) else default


def read_playback(folder: Path) -> Playback:
    """The saved state, or the defaults when there is none or the file is damaged."""
    path = folder / PLAYBACK_JSON
    try:
        raw: Any = json.loads(read_text_file(path)) if path.is_file() else {}
    except (ValueError, OSError):
        raw = {}
    o = cast("dict[str, Any]", raw) if isinstance(raw, dict) else {}
    return Playback(
        position_s=_number(o.get("position_s"), 0, 1e7, 0),
        duration_s=_number(o.get("duration_s"), 0, 1e7, 0),
        offset_ms=int(_number(o.get("offset_ms"), -MAX_OFFSET_MS, MAX_OFFSET_MS, 0)),
        opened_at_ms=int(_number(o.get("opened_at_ms"), 0, 1e16, 0)),
    )


def write_playback(folder: Path, state: Playback) -> None:
    body = {
        "position_s": state.position_s,
        "duration_s": state.duration_s,
        "offset_ms": state.offset_ms,
        "opened_at_ms": state.opened_at_ms,
    }
    write_text_file(folder / PLAYBACK_JSON, json.dumps(body, indent=2) + "\n")


def with_changes(state: Playback, **changes: float | int) -> Playback:
    return replace(state, **changes)


def shift_cues(cues: Iterable[Cue], offset_ms: int) -> list[Cue]:
    """The cues `offset_ms` later (earlier when negative). A cue that ends before time zero is
    dropped and one that starts before it starts at zero."""
    shifted: list[Cue] = []
    for c in cues:
        end = c.end_ms + offset_ms
        if end > 0:
            shifted.append(Cue(c.id, max(0, c.start_ms + offset_ms), end, c.en, c.zh))
    return shifted
