"""P22 lever: pick probe sentences from a Qwen3-ASR run, evenly spaced, with no hand choosing.

pick RUN_JSON OUT.json cedec          30 Japanese sentences
pick RUN_JSON OUT.json kirby          10 English, 10 Japanese and 10 mixed sentences
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any

import p22_analyze as analyze

SPLIT = re.compile(r"(?<=[。！？])|(?<=[.!?])\s+(?=[A-Z])")
KANA = re.compile("[぀-ヿ]")
LATIN = re.compile("[A-Za-z]{2,}")


def sentences(run: analyze.Run) -> list[str]:
    out: list[str] = []
    for seg in run.segs:
        out += [p.strip() for p in SPLIT.split(seg.text) if p.strip()]
    return out


def kind(text: str) -> str:
    kana, latin = bool(KANA.search(text)), bool(LATIN.search(text))
    if kana and latin:
        return "mixed"
    return "ja" if kana else "en" if latin else "other"


def spaced(items: list[str], count: int) -> list[str]:
    step = len(items) / count
    return [items[int(i * step + step / 2)] for i in range(count)]


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
    run = analyze.load(Path(sys.argv[1]))
    video = sys.argv[3]
    pool = [s for s in sentences(run) if 20 <= len(s) <= 110]
    rows: list[dict[str, Any]] = []
    if video == "cedec":
        picked = spaced([s for s in pool if kind(s) in ("ja", "mixed")], 30)
        rows = [{"video": video, "lang": "ja", "src": s} for s in picked]
    else:
        for want, lang in (("en", "en"), ("ja", "ja"), ("mixed", "ja")):
            picked = spaced([s for s in pool if kind(s) == want], 10)
            rows += [{"video": video, "lang": lang, "kind": want, "src": s} for s in picked]
    for i, row in enumerate(rows, 1):
        row["id"] = i
    Path(sys.argv[2]).write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"{len(rows)} sentences")


if __name__ == "__main__":
    main()
