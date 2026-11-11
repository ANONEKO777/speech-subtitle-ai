"""P23a lever: count and check the outputs of a Japanese project folder.

    uv run python scripts/p23a_check.py PROJECT.vst [--json out.json]

Reports the cue counts, the line lengths in full-width characters, the cue timing, how many cue
and line breaks fall inside a word by the script rule of `backend.core.unspaced`, and the
output checks on every translated cue and on the summary: kana left over, Japanese kanji
forms, Simplified characters, Mainland wording, cues with only punctuation, and cues that kept
their Japanese because the model failed every attempt. Exit code 1 when any check finds an error.
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
from pathlib import Path

from backend.core import unspaced
from backend.core.languages import get as get_language
from backend.core.model import Cue, Word
from backend.core.segmenter import violations
from backend.core.source_langs import JAPANESE_SOURCE, is_bare_punctuation
from backend.core.subtitle_io import parse_project, parse_subs, read_text_file
from backend.core.zh_tw import taiwan_terms, taiwan_terms_from_japanese

ZH_TW = get_language("zh-TW")
INSIDE_WORD = 7.5
"""A break that costs at least this much by `unspaced.break_costs` is inside a word."""


def percentile(values: list[float], share: float) -> float:
    return sorted(values)[min(len(values) - 1, int(len(values) * share))]


def breaks_inside_words(cues: list[Cue]) -> tuple[int, int]:
    """How many cue ends and line breaks cost at least `INSIDE_WORD` by the script rule, and how
    many there are, over the text of all the cues as one run of characters."""
    stream: list[Word] = []
    marks: list[int] = []
    for cue in cues:
        for line in cue.src.split("\n"):
            stream += [Word(char, 0, 1) for char in line]
            marks.append(len(stream) - 1)
        marks.pop()
        marks.append(len(stream) - 1)
    costs = unspaced.break_costs(stream)
    chosen = [m for m in marks if m < len(stream) - 1]
    return sum(1 for m in chosen if costs[m] >= INSIDE_WORD), len(chosen)


def cue_problems(cue: Cue) -> list[str]:
    found: list[str] = []
    if cue.lang != "ja":
        found.append(f"cue {cue.id} is tagged {cue.lang}")
    if problem := ZH_TW.problem(cue.zh, cue.src):
        found.append(f"cue {cue.id} {problem}")
    if problem := JAPANESE_SOURCE.problem(cue.zh):
        found.append(f"cue {cue.id} {problem}")
    if taiwan_terms(taiwan_terms_from_japanese(cue.zh)) != cue.zh:
        found.append(f"cue {cue.id} has Mainland wording: {cue.zh}")
    if cue.zh == cue.src:
        found.append(f"cue {cue.id} kept its Japanese")
    if is_bare_punctuation(cue.zh) and not is_bare_punctuation(cue.src):
        found.append(f"cue {cue.id} is only punctuation: {cue.zh}")
    return found


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("folder", type=Path)
    parser.add_argument("--json", type=Path)
    args = parser.parse_args(argv)
    folder: Path = args.folder
    project = parse_project(read_text_file(folder / "project.json"))
    if project.source_lang != "ja":
        print(f"error: {folder} is a {project.source_lang} project", file=sys.stderr)
        return 2
    cues = parse_subs(read_text_file(folder / "subs.zh-TW.json"))
    source = parse_subs(read_text_file(folder / "subs.ja.json"))
    lines = [line for cue in cues for line in cue.src.split("\n")]
    columns = [float(unspaced.columns(line)) for line in lines]
    wide = [c / 2 for c in columns]
    durations = [(cue.end_ms - cue.start_ms) / 1000 for cue in cues]
    rates = [
        unspaced.columns(cue.src.replace("\n", "")) / 2 / max(d, 0.001)
        for cue, d in zip(cues, durations, strict=True)
    ]
    problems = [p for cue in cues for p in cue_problems(cue)]
    summary = (folder / "summary.md").read_text(encoding="utf-8")
    for name, text in (("summary", summary),):
        for problem in (
            ZH_TW.prose_problem(text),
            JAPANESE_SOURCE.problem(text),
            "has Mainland wording"
            if taiwan_terms(taiwan_terms_from_japanese(text)) != text
            else None,
        ):
            if problem:
                problems.append(f"{name} {problem}")
    rules = JAPANESE_SOURCE.cues
    inside, breaks = breaks_inside_words(cues)
    report: dict[str, object] = {
        "cues": len(cues),
        "source_cues_match": [c.id for c in cues] == [c.id for c in source],
        "two_line_cues": sum(1 for cue in cues if "\n" in cue.src),
        "lines": len(lines),
        "line_full_width_chars": {
            "max": max(wide),
            "mean": round(statistics.mean(wide), 1),
            "p90": percentile(wide, 0.9),
        },
        "cue_seconds": {
            "min": min(durations),
            "median": statistics.median(durations),
            "max": max(durations),
        },
        "full_width_chars_per_second": {
            "median": round(statistics.median(rates), 1),
            "p90": round(percentile(rates, 0.9), 1),
            "over_7": sum(1 for r in rates if r > 7),
        },
        "breaks_inside_a_word_by_script_rule": inside,
        "breaks": breaks,
        "rule_violations": violations(source, rules),
        "zh_cues_empty": sum(1 for cue in cues if not cue.zh),
        "zh_cues_only_punctuation": sum(1 for cue in cues if is_bare_punctuation(cue.zh)),
        "zh_cues_4_chars_or_fewer": sorted(cue.id for cue in cues if len(cue.zh) <= 4),
        "output_check_errors": problems,
        "summary_chars": len(summary),
    }
    text = json.dumps(report, ensure_ascii=False, indent=1)
    print(text)
    if args.json:
        args.json.write_text(text + "\n", encoding="utf-8")
    return 1 if problems or report["rule_violations"] or report["zh_cues_empty"] else 0


if __name__ == "__main__":
    sys.exit(main())
