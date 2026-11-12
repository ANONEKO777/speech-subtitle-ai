"""P23b lever: count and check the outputs of a Japanese and English (`ja+en`) project folder.

    uv run python scripts/p23b_check.py PROJECT.vst [--json out.json] [--samples N]

Reports the cue counts by language, the places where the language changes, cues that hold a
language other than their tag by script, the rule violations of each language, and the output
checks on every translated cue and on the summary (the Japanese checks for `ja` cues, the English
ones for `en` cues). Prints N evenly spaced cues with their tag, time, source and translation.
Exit code 1 when any check finds an error.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path

from backend.core.languages import get as get_language
from backend.core.model import Cue
from backend.core.segmenter import violations
from backend.core.source_langs import MIXED_SOURCE, is_bare_punctuation
from backend.core.subtitle_io import parse_project, parse_subs, read_text_file
from backend.core.zh_tw import taiwan_terms, taiwan_terms_from_japanese
from backend.engines.mixed import is_japanese_text

ZH_TW = get_language("zh-TW")
_LATIN = re.compile("[A-Za-z]")
_KANA = re.compile("[぀-ヿ]")


def cue_problems(cue: Cue) -> list[str]:
    source = MIXED_SOURCE.of(cue.lang)
    found: list[str] = []
    if problem := ZH_TW.problem(cue.zh, cue.src):
        found.append(f"cue {cue.id} {problem}")
    if problem := source.problem(cue.zh):
        found.append(f"cue {cue.id} {problem}")
    if cue.lang == "ja" and taiwan_terms(taiwan_terms_from_japanese(cue.zh)) != cue.zh:
        found.append(f"cue {cue.id} has Mainland wording: {cue.zh}")
    if cue.zh == cue.src and (
        _KANA.search(cue.src) if cue.lang == "ja" else _LATIN.search(cue.src)
    ):
        found.append(f"cue {cue.id} kept its {source.name}")
    if is_bare_punctuation(cue.zh) and not is_bare_punctuation(cue.src):
        found.append(f"cue {cue.id} is only punctuation: {cue.zh}")
    return found


def script_mismatch(cue: Cue) -> bool:
    """A `ja` cue with no kana or kanji, or an `en` cue that has any."""
    return is_japanese_text(cue.src) != (cue.lang == "ja")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("folder", type=Path)
    parser.add_argument("--json", type=Path)
    parser.add_argument("--samples", type=int, default=12)
    args = parser.parse_args(argv)
    folder: Path = args.folder
    project = parse_project(read_text_file(folder / "project.json"))
    if project.source_lang != "ja+en":
        print(f"error: {folder} is a {project.source_lang} project", file=sys.stderr)
        return 2
    cues = parse_subs(read_text_file(folder / "subs.zh-TW.json"))
    source = parse_subs(read_text_file(folder / "subs.src.json"))
    problems = [p for cue in cues for p in cue_problems(cue)]
    summary = (folder / "summary.md").read_text(encoding="utf-8")
    for problem in (ZH_TW.prose_problem(summary), MIXED_SOURCE.problem(summary)):
        if problem:
            problems.append(f"summary {problem}")
    by_lang = Counter(cue.lang for cue in cues)
    changes = sum(1 for a, b in zip(cues, cues[1:], strict=False) if a.lang != b.lang)
    rule_violations = {
        code: violations([c for c in source if c.lang == code], MIXED_SOURCE.of(code).cues)
        for code in ("ja", "en")
    }
    report: dict[str, object] = {
        "cues": len(cues),
        "source_cues_match": [c.id for c in cues] == [c.id for c in source],
        "cues_by_lang": dict(by_lang),
        "seconds_by_lang": {
            code: round(sum(c.end_ms - c.start_ms for c in cues if c.lang == code) / 1000)
            for code in by_lang
        },
        "language_changes": changes,
        "cues_whose_script_disagrees_with_their_tag": [c.id for c in cues if script_mismatch(c)],
        "cues_with_a_neighbour_of_another_language_overlapping": sum(
            1
            for a, b in zip(cues, cues[1:], strict=False)
            if a.lang != b.lang and b.start_ms < a.end_ms
        ),
        "rule_violations": {k: len(v) for k, v in rule_violations.items()},
        "zh_cues_empty": sum(1 for cue in cues if not cue.zh),
        "output_check_errors": problems,
        "summary_chars": len(summary),
    }
    text = json.dumps(report, ensure_ascii=False, indent=1)
    print(text)
    step = max(1, len(cues) // max(args.samples, 1))
    print("\nsampled cues (id, tag, start s):")
    for cue in cues[::step][: args.samples]:
        print(f"  {cue.id:4d} [{cue.lang}] {cue.start_ms / 1000:8.1f}  {cue.src!r} -> {cue.zh!r}")
    if args.json:
        args.json.write_text(text + "\n", encoding="utf-8")
    bad = (
        problems or report["zh_cues_empty"] or report["cues_whose_script_disagrees_with_their_tag"]
    )
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
