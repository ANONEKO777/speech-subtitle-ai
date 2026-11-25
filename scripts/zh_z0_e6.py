"""Z0 E6: the operator's Taiwanese conference talk (no hard subtitles), engines read against each other.

    uv run python scripts/zh_z0_e6.py audio
    uv run python scripts/zh_z0_e5_asr.py --set e6 --tag e6-w --engine whisper --lang zh
    uv run python scripts/zh_z0_e5_asr.py --set e6 --tag e6-q --engine qwen3 --lang zh
    .work/zh-z0/venv-native/Scripts/python scripts/zh_z0_e6.py compare e6-w e6-q [e6-q-hant]

The talk is the second line of `.work/zh-z0/talk-path.txt`. The picture has only the session title
and abstract at the bottom, no subtitles of the speech, so there is no reference text. `compare`
therefore reads the runs against each other: in 20 stretches of 30 s spread over the talk it
gives the character error rate of each pair (script-free, with the first run as the reference, so
it is a disagreement rate and not an error rate), the script each run wrote, the punctuation, the
speech rate, the cue sizes, and how often chosen terms appear. Everything derived stays under
`.work/zh-z0/e6/`.
"""
# ruff: noqa: E501

from __future__ import annotations

import importlib
import re
import statistics
import subprocess
import sys
from collections import Counter
from collections.abc import Callable
from pathlib import Path
from typing import Any, cast

from zh_z0_text import WORK, edit_distance, is_han, keep_letters, percentile, read_json

E6 = WORK / "e6"
STRETCHES = 20
STRETCH_S = 30.0
Convert = Callable[[str], str]
TERMS = (
    "unreal", "虛幻", "虚幻", "引擎", "概念", "concept", "3d", "blender", "zbrush", "nanite",
    "lumen", "nvidia", "ai", "美術", "美术", "場景", "场景", "遊戲", "游戏", "設計", "设计",
)  # fmt: skip


def audio() -> None:
    lines = (WORK / "talk-path.txt").read_text(encoding="utf-8-sig").splitlines()
    video = lines[1].strip().strip('"')
    E6.mkdir(parents=True, exist_ok=True)
    subprocess.run(  # noqa: S603
        ["ffmpeg", "-v", "error", "-y", "-i", video, "-vn", "-ac", "1", "-ar", "16000",
         "-c:a", "pcm_s16le", str(E6 / "window.wav")],
        check=True,
    )  # fmt: skip
    print(f"wrote {E6 / 'window.wav'}")


def text_in(words: list[list[Any]], start_s: float, end_s: float) -> str:
    return "".join(str(w[0]) for w in words if start_s <= (w[1] + w[2]) / 2000 <= end_s)


def compare(tags: list[str]) -> None:
    opencc = cast("Any", importlib.import_module("opencc"))
    t2s = cast("Convert", opencc.OpenCC("t2s").convert)
    sys.path.insert(0, str(WORK.parents[1]))
    from backend.core.zh_tw import SIMPLIFIED_ONLY

    runs = {tag: cast("dict[str, Any]", read_json(E6 / f"{tag}.json")) for tag in tags}
    audio_s = next(iter(runs.values()))["audio_s"]
    starts = [(i + 0.5) * audio_s / STRETCHES - STRETCH_S / 2 for i in range(STRETCHES)]
    print(f"talk {audio_s / 60:.1f} min; {STRETCHES} stretches of {STRETCH_S:g} s")
    for tag, run in runs.items():
        words = cast("list[list[Any]]", run["words"])
        text = "".join(str(w[0]) for w in words)
        han = sum(1 for c in text if is_han(c))
        trad = sum(1 for c in text if is_han(c) and t2s(c) != c)
        simp = sum(1 for c in text if c in SIMPLIFIED_ONLY)
        chunks = cast("list[list[int]]", run["chunks"])
        speech = sum(b - a for a, b in chunks) / 1000
        cues = cast("list[list[Any]]", run["cues"])
        chars = [len(str(c[2]).replace("\n", "")) for c in cues]
        secs = [(c[1] - c[0]) / 1000 for c in cues]
        low = text.lower()
        print(
            f"\n{tag} ({run['engine']}, -l {run['lang_flag']}): {han} Han characters, "
            f"Traditional-only {trad}, Simplified-only {simp} "
            f"({trad / max(trad + simp, 1):.1%} Traditional), "
            f"speech {speech:.0f} s in {len(chunks)} chunks, {han / speech:.2f} Han chars per speech second, "
            f"{len(words)} words, {len(cues)} cues ({len(cues) / (audio_s / 60):.1f} per min), "
            f"cue chars p50/p90/max {percentile(chars, 50):.0f}/{percentile(chars, 90):.0f}/{max(chars)}, "
            f"cue seconds p50/p90/max {percentile(secs, 50):.1f}/{percentile(secs, 90):.1f}/{max(secs):.1f}"
        )
        punct = sum(text.count(c) for c in "，。、？！；：,.?!")
        print(f"  punctuation per 1000 Han chars {1000 * punct / max(han, 1):.0f}")
        print("  terms:", ", ".join(f"{t} {low.count(t)}" for t in TERMS if low.count(t)))
        latin = Counter(w.lower() for w in re.findall(r"[A-Za-z][A-Za-z0-9]{2,}", text))
        print("  Latin words:", ", ".join(f"{w} {n}" for w, n in latin.most_common(25)))
    first = tags[0]
    for other in tags[1:]:
        edits = total = 0
        per: list[float] = []
        for start in starts:
            ref = keep_letters(t2s(text_in(runs[first]["words"], start, start + STRETCH_S)))
            hyp = keep_letters(t2s(text_in(runs[other]["words"], start, start + STRETCH_S)))
            e = edit_distance(ref, hyp)
            edits, total = edits + e, total + len(ref)
            per.append(e / max(len(ref), 1))
        print(
            f"\n{other} against {first} (script-free): {edits / total:.2%} over {total} characters, "
            f"stretch p50 {statistics.median(per):.1%}, max {max(per):.1%}"
        )
    path = E6 / "stretches.txt"
    with path.open("w", encoding="utf-8") as sink:
        for i, start in enumerate(starts):
            sink.write(f"## stretch {i} at {start:.0f} s\n")
            for tag in tags:
                sink.write(f"{tag}: {text_in(runs[tag]['words'], start, start + STRETCH_S)}\n")
    print(f"\nstretch texts for reading: {Path(path)}")


def main() -> int:
    if sys.argv[1] == "audio":
        audio()
    else:
        compare(sys.argv[2:])
    return 0


if __name__ == "__main__":
    sys.exit(main())
