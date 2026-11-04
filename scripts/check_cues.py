"""Run the segmenter on ASR word timestamps and report every SPEC 5.1 violation.

Accepts either the fixture format (a list of {"words": [{"text", "start_ms", "end_ms"}]})
or an M0 run file ({"segments": [{"words": [{"text", "start", "end"}]}]} in seconds).
Exits 1 when any cue breaks a rule.
"""

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from backend.core.model import Segment, Word
from backend.core.segmenter import to_cues, violations
from backend.core.subtitle_io import render_srt, write_text_file


def _word(raw: dict[str, Any]) -> Word:
    if "start_ms" in raw:
        return Word(raw["text"], int(raw["start_ms"]), int(raw["end_ms"]))
    return Word(raw["text"], round(raw["start"] * 1000), round(raw["end"] * 1000))


def load_segments(path: Path) -> list[Segment]:
    data: Any = json.loads(path.read_text(encoding="utf-8"))
    raw_segments: list[dict[str, Any]] = data["segments"] if "segments" in data else data
    segments: list[Segment] = []
    for raw in raw_segments:
        raw_words: list[dict[str, Any]] = raw["words"]
        words = tuple(_word(w) for w in raw_words)
        segments.append(Segment("", words[0].start_ms, words[-1].end_ms, words))
    return segments


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("words", type=Path)
    parser.add_argument("--srt", type=Path, help="also write the cues to this SRT file")
    args = parser.parse_args()
    segments = load_segments(args.words)
    cues = to_cues(segments)
    problems = violations(cues)
    words = sum(len(s.words or ()) for s in segments)
    print(f"{args.words.name}: {words} words -> {len(cues)} cues, {len(problems)} violations")
    for problem in problems:
        print(f"  {problem}")
    if args.srt:
        write_text_file(args.srt, render_srt(cues, "en"))
        print(f"wrote {args.srt}")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
