"""Z0 E3: Mandarin speech rate, and the cue sizes the app's cue builder gives it.

    uv run python scripts/zh_z0_rate.py rate     # FLEURS read speech: characters per speech second
    uv run python scripts/zh_z0_rate.py cues --run e5-w   # candidate CueRules on a run's words

`rate` counts the characters of the FLEURS reference (letters, digits and Han characters, no
punctuation) over the seconds of the utterance and over the seconds of speech that the app's Silero
VAD finds in it. `cues` builds cues from the words of an E5 run (`zh_z0_e5_asr.py`) with several
`CueRules` and prints how long the cues are, how fast they go, and how many break the rules.
"""
# ruff: noqa: E501
# ruff: noqa: E501

from __future__ import annotations

import argparse
import sys
from typing import Any, cast

from zh_z0_common import storage
from zh_z0_text import (
    WORK,
    is_han,
    keep_letters,
    load_utterances,
    percentile,
    read_json,
)

from backend.core import unspaced, vad
from backend.core.model import Segment, Word
from backend.core.segmenter import CueRules, to_cues, violations

E5 = WORK / "e5"


def rate() -> None:
    onnx = storage().models_root / "silero-vad-onnx-v6.2.3" / "silero_vad.onnx"
    rows = load_utterances("zh")
    speech = vad.speech_seconds([u.wav for u in rows], onnx)
    per_audio: list[float] = []
    per_speech: list[float] = []
    chars = han = 0
    audio_s = speech_s = 0.0
    for u, s in zip(rows, speech, strict=True):
        text = keep_letters(u.raw)
        n = len(text)
        chars += n
        han += sum(1 for c in text if is_han(c))
        audio_s += u.seconds
        speech_s += s
        per_audio.append(n / u.seconds)
        if s > 0.5:
            per_speech.append(n / s)
    print(f"utterances {len(rows)}, audio {audio_s / 3600:.2f} h, speech {speech_s / 3600:.2f} h")
    print(
        f"characters {chars} (Han {han}); per audio second {chars / audio_s:.2f}; per speech second {chars / speech_s:.2f}"
    )
    for label, values in (("per audio s", per_audio), ("per speech s", per_speech)):
        print(
            f"{label}: p10 {percentile(values, 10):.2f}, p50 {percentile(values, 50):.2f}, p90 {percentile(values, 90):.2f}, max {max(values):.2f}"
        )


def cues(tag: str) -> None:
    run = cast("dict[str, Any]", read_json(E5 / f"{tag}.json"))
    words = [Word(str(t), int(a), int(b)) for t, a, b in cast("list[list[Any]]", run["words"])]
    segment = Segment(
        " ".join(w.text for w in words), words[0].start_ms, words[-1].end_ms, tuple(words)
    )
    print(
        f"{tag}: {len(words)} words, {sum(len(w.text) for w in words)} characters, {run['audio_s']:.0f} s"
    )
    print(
        "| max_line_chars (columns) | max_cps | cues | per min | chars p50 / p90 / max | columns p90 | seconds p50 / p90 / max | cps p90 / max | cps over 7 / 9 / 12 | two-line cues | violations |"
    )
    print("|---|---|---|---|---|---|---|---|---|---|---|")
    for line, cps in (
        (40, 14.0),
        (32, 14.0),
        (28, 14.0),
        (36, 12.0),
        (40, 10.0),
        (36, 10.0),
        (32, 10.0),
        (28, 10.0),
    ):
        rules = CueRules(max_line_chars=line, unspaced=True, max_cps=cps)
        built = to_cues([segment], rules, "zh")
        chars = [len(c.src.replace("\n", "")) for c in built]
        columns = [max(unspaced.columns(part) for part in c.src.split("\n")) for c in built]
        secs = [(c.end_ms - c.start_ms) / 1000 for c in built]
        speed = [n / max(s, 0.1) for n, s in zip(chars, secs, strict=True)]
        two = sum(1 for c in built if "\n" in c.src)
        print(
            f"| {line} | {cps:g} | {len(built)} | {len(built) / (run['audio_s'] / 60):.1f} | "
            f"{percentile(chars, 50):.0f} / {percentile(chars, 90):.0f} / {max(chars)} | {percentile(columns, 90):.0f} | "
            f"{percentile(secs, 50):.1f} / {percentile(secs, 90):.1f} / {max(secs):.1f} | "
            f"{percentile(speed, 90):.1f} / {max(speed):.1f} | "
            f"{sum(1 for v in speed if v > 7)} / {sum(1 for v in speed if v > 9)} / {sum(1 for v in speed if v > 12)} | "
            f"{two} | {len(violations(built, rules))} |"
        )


def main() -> int:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("rate")
    c = sub.add_parser("cues")
    c.add_argument("--run", required=True)
    args = parser.parse_args()
    if args.cmd == "rate":
        rate()
    else:
        cues(args.run)
    return 0


if __name__ == "__main__":
    sys.exit(main())
