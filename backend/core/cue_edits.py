"""Corrections a person made to translated cues: the rules they must meet, and the record that
keeps them when a later run translates the project again.

The English line is the transcript every translation and summary is built from, so an edit may
not change it. A corrected cue is kept in `edits.<code>.json` with the cue as the translator made
it, so putting it back removes the mark. `reapply` puts them back over a fresh translation.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from backend.core.languages import Language
from backend.core.model import Cue
from backend.core.segmenter import CueRules
from backend.core.source_langs import SOURCES
from backend.core.subtitle_io import parse_subs, read_text_file, render_subs, write_text_file

MAX_CUE_MS = CueRules().max_cue_ms
EDITS_SCHEMA_VERSION = 1

ProblemCode = Literal[
    "english_changed",
    "empty",
    "bad_text",
    "end_before_start",
    "too_long",
    "overlap",
    "out_of_order",
]


@dataclass(frozen=True, slots=True)
class CueProblem:
    """What is wrong with the cue `id`. `other` is the cue it collides with, if any."""

    id: int
    code: ProblemCode
    message: str
    other: int | None = None


def edits_file(lang: Language) -> str:
    return f"edits.{lang.file_code}.json"


def _changed(cue: Cue, was: Cue | None) -> bool:
    return was is None or (cue.start_ms, cue.end_ms, cue.zh) != (was.start_ms, was.end_ms, was.zh)


def timing_problems(cues: Sequence[Cue], changed: set[int]) -> list[CueProblem]:
    """Problems of the cues in `changed`. A cue must start no earlier than the cue before it, in
    id order, and no earlier than where any earlier cue ends. A collision is blamed on the
    changed cue of the pair."""
    problems: list[CueProblem] = []
    ordered = sorted(cues, key=lambda c: c.id)
    reach: Cue | None = None
    previous: Cue | None = None
    for cue in ordered:
        if cue.id in changed and cue.end_ms - cue.start_ms > MAX_CUE_MS:
            seconds = (cue.end_ms - cue.start_ms) / 1000
            problems.append(
                CueProblem(cue.id, "too_long", f"{seconds:.1f} s is longer than the 7 s limit")
            )
        if previous and cue.start_ms < previous.start_ms:
            culprit, other = (cue, previous) if cue.id in changed else (previous, cue)
            if culprit.id in changed or other.id in changed:
                problems.append(
                    CueProblem(culprit.id, "out_of_order", "starts before another cue", other.id)
                )
        elif reach and cue.start_ms < reach.end_ms and (cue.id in changed or reach.id in changed):
            culprit, other = (cue, reach) if cue.id in changed else (reach, cue)
            problems.append(CueProblem(culprit.id, "overlap", "overlaps another cue", other.id))
        previous = cue
        if reach is None or cue.end_ms > reach.end_ms:
            reach = cue
    return problems


def check(current: Sequence[Cue], proposed: Sequence[Cue]) -> list[CueProblem]:
    """Every problem of `proposed` as a correction of `current`. Only cues the person changed are
    blamed for timing, so a project that already has a long cue can still be edited elsewhere."""
    was = {c.id: c for c in current}
    problems: list[CueProblem] = []
    changed: set[int] = set()
    for cue in proposed:
        before = was.get(cue.id)
        if before and cue.src != before.src:
            problems.append(
                CueProblem(
                    cue.id,
                    "english_changed",
                    f"the {SOURCES[cue.lang].name} line cannot be edited",
                )
            )
        if _changed(cue, before):
            changed.add(cue.id)
            if before and before.zh and not cue.zh.strip():
                problems.append(CueProblem(cue.id, "empty", "the text is empty"))
    return [*problems, *timing_problems(proposed, changed)]


def _load(folder: Path, lang: Language) -> tuple[dict[int, Cue], dict[int, Cue]]:
    """The edited cues and, for each, the cue as the translator made it."""
    path = folder / edits_file(lang)
    if not path.is_file():
        return {}, {}
    doc = json.loads(read_text_file(path))
    edited_cues, origins = (parse_subs(json.dumps(doc[key])) for key in ("edited", "origin"))
    return {c.id: c for c in edited_cues}, {c.id: c for c in origins}


def edited(folder: Path, lang: Language) -> list[Cue]:
    return list(_load(folder, lang)[0].values())


def applied(folder: Path, lang: Language) -> list[Cue]:
    """The edited cues whose English line is still in the cue file, so the edit shows there."""
    path = folder / lang.files.subs
    if not path.is_file():
        return []
    present = {c.id: c for c in parse_subs(read_text_file(path))}
    return [e for e in edited(folder, lang) if (c := present.get(e.id)) and c.src == e.src]


def record(folder: Path, lang: Language, current: Sequence[Cue], proposed: Sequence[Cue]) -> None:
    """Remember the cues of `proposed` that differ from `current`. A cue put back to what the
    translator made stops counting as edited."""
    was = {c.id: c for c in current}
    kept, origin = _load(folder, lang)
    for cue in proposed:
        if not _changed(cue, was.get(cue.id)):
            continue
        origin.setdefault(cue.id, was[cue.id])
        if _changed(cue, origin[cue.id]):
            kept[cue.id] = cue
        else:
            kept.pop(cue.id, None)
            del origin[cue.id]
    doc = {
        "schema_version": EDITS_SCHEMA_VERSION,
        "edited": json.loads(render_subs(kept[i] for i in sorted(kept))),
        "origin": json.loads(render_subs(origin[i] for i in sorted(kept))),
    }
    text = json.dumps(doc, ensure_ascii=False, indent=2)
    write_text_file(folder / edits_file(lang), text + "\n")


@dataclass(frozen=True, slots=True)
class Reapplied:
    kept: int
    unmatched: int
    """Edits whose English line is no longer in the project. They stay in the edits file."""


def reapply(folder: Path, lang: Language) -> Reapplied:
    """Put the person's corrections over the cue file just translated. An edit applies to the cue
    with its id and English line. Its times apply too, unless they would collide with a cue that
    was not edited, and then only its text does."""
    edits = edited(folder, lang)
    if not edits:
        return Reapplied(0, 0)
    path = folder / lang.files.subs
    fresh = parse_subs(read_text_file(path))
    by_id = {c.id: c for c in fresh}
    matched = applied(folder, lang)
    ids = {e.id for e in matched}
    with_times = {**by_id, **{e.id: e for e in matched}}
    if timing_problems(list(with_times.values()), ids):
        with_times = {
            **by_id,
            **{
                e.id: Cue(e.id, by_id[e.id].start_ms, by_id[e.id].end_ms, e.src, e.zh)
                for e in matched
            },
        }
    write_text_file(path, render_subs(with_times[c.id] for c in fresh))
    return Reapplied(len(matched), len(edits) - len(matched))
