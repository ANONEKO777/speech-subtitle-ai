"""Z0 E4: how well Whisper's language id tells Mandarin from Japanese, Korean and English.

    uv run python scripts/zh_z0_detect.py run --seconds 5 --per-lang 150
    uv run python scripts/zh_z0_detect.py report

`run` cuts pieces of the given length from random places of FLEURS test utterances (a fixed seed),
names the language of each with the app's own `name_languages` (`whisper-cli -l auto -dl`, one
process, model loaded once), and measures the seconds of speech in each with the app's Silero VAD
(`backend.core.vad.speech_seconds`). `report` prints the confusion matrix of all pieces and of the
pieces the detector would count (probability >= 0.5 and speech >= 0.5 s), and simulates what a
24-piece talk would be called when `zh` joins the languages of `language_detect.decide`.
"""
# ruff: noqa: E501
# ruff: noqa: E501

from __future__ import annotations

import argparse
import random
import sys
import wave
from collections import Counter
from pathlib import Path
from typing import Any, cast

from zh_z0_common import (
    DATA,
    RUNS,
    WORK,
    Device,
    engine_files,
    set_idle_priority,
    wait_until_free,
)
from zh_z0_text import SAMPLE_RATE, Utterance, load_utterances, read_json, write_json

from backend.core import vad
from backend.core.language_detect import Heard
from backend.engines.whispercpp import ENGINE_ID, name_languages

MIN_PROBABILITY = 0.5
MIN_SPEECH_S = 0.5
NAME_BATCH = 60
SAMPLE_COUNT = 24
MIXED_SHARE = 0.15
MIN_MIXED_PIECES = 12
MIN_PIECES = 3
SURE_SHARE = 0.9


def cut(utt: Utterance, start_s: float, seconds: float, target: Path) -> bool:
    with wave.open(str(utt.wav), "rb") as reader:
        if reader.getnframes() / SAMPLE_RATE < seconds + 0.05:
            return False
        reader.setpos(int(start_s * SAMPLE_RATE))
        frames = reader.readframes(int(seconds * SAMPLE_RATE))
    with wave.open(str(target), "wb") as writer:
        writer.setnchannels(1)
        writer.setsampwidth(2)
        writer.setframerate(SAMPLE_RATE)
        writer.writeframes(frames)
    return True


def run(seconds: float, per_lang: int, seed: int) -> None:
    set_idle_priority()
    wait_until_free()
    rng = random.Random(seed)
    work = WORK / "tmp" / f"detect-{seconds:g}"
    work.mkdir(parents=True, exist_ok=True)
    pieces: list[dict[str, Any]] = []
    wavs: list[Path] = []
    for lang in ("zh", "ja", "ko", "en"):
        pool = [u for u in load_utterances(lang) if u.seconds >= seconds + 0.1]
        for index, utt in enumerate(rng.sample(pool, min(per_lang, len(pool)))):
            start = rng.uniform(0, utt.seconds - seconds - 0.05)
            target = work / f"{lang}-{index:03d}.wav"
            if cut(utt, start, seconds, target):
                wavs.append(target)
                pieces.append(
                    {"lang": lang, "key": utt.key, "start_s": round(start, 2), "wav": target.name}
                )
    found = engine_files(ENGINE_ID)
    heard: list[Heard] = []
    for first in range(0, len(wavs), NAME_BATCH):
        heard += name_languages(
            found.binary,
            found.model,
            wavs[first : first + NAME_BATCH],
            device=Device.CUDA,
            timeout_s=3600,
        )
    model = DATA.parent.parent.parent  # placeholder replaced below
    del model
    from zh_z0_common import storage

    vad_model = storage().models_root / "silero-vad-onnx-v6.2.3" / "silero_vad.onnx"
    speech = vad.speech_seconds(wavs, vad_model)
    for piece, tag, seconds_of_speech in zip(pieces, heard, speech, strict=True):
        piece["heard"] = tag.code
        piece["p"] = round(tag.probability, 3)
        piece["speech_s"] = round(seconds_of_speech, 2)
    write_json(RUNS / f"detect-{seconds:g}s.json", {"seconds": seconds, "pieces": pieces})
    print(f"{len(pieces)} pieces of {seconds:g} s named")


def matrix(pieces: list[dict[str, Any]], languages: tuple[str, ...]) -> str:
    columns = sorted(
        {str(p["heard"]) for p in pieces},
        key=lambda c: (-sum(1 for p in pieces if p["heard"] == c), c),
    )
    lines = [
        "| spoken \\ named | " + " | ".join(columns) + " | n | right |",
        "|---|" + "---|" * (len(columns) + 2),
    ]
    for lang in languages:
        mine = [p for p in pieces if p["lang"] == lang]
        counts = Counter(str(p["heard"]) for p in mine)
        right = counts[lang] / max(len(mine), 1)
        lines.append(
            f"| {lang} | "
            + " | ".join(str(counts[c]) for c in columns)
            + f" | {len(mine)} | {right:.1%} |"
        )
    return "\n".join(lines)


def clear(piece: dict[str, Any], languages: tuple[str, ...]) -> bool:
    return (
        piece["heard"] in languages
        and piece["p"] >= MIN_PROBABILITY
        and piece["speech_s"] >= MIN_SPEECH_S
    )


def call_talk(codes: list[str], languages: tuple[str, ...]) -> str:
    """`language_detect.decide`, with the languages of `languages`: None, a language, or `mixed`."""
    if len(codes) < MIN_PIECES:
        return "none"
    shares = {lang: codes.count(lang) / len(codes) for lang in languages}
    main = max(shares, key=lambda k: shares[k])
    others = sorted(shares.values())[:-1]
    if len(codes) >= MIN_MIXED_PIECES and others and others[-1] >= MIXED_SHARE:
        return "mixed"
    return main if shares[main] >= 0 else "none"


def simulate(
    pieces: list[dict[str, Any]],
    languages: tuple[str, ...],
    spoken: dict[str, float],
    rng: random.Random,
    trials: int,
) -> Counter[str]:
    """`trials` talks of 24 pieces, each piece drawn from the real pieces of the language it is
    spoken in (with the given shares of languages), counted only when clear."""
    by_lang = {lang: [p for p in pieces if p["lang"] == lang] for lang in spoken}
    out: Counter[str] = Counter()
    names = list(spoken)
    weights = [spoken[n] for n in names]
    for _ in range(trials):
        drawn = [rng.choice(by_lang[rng.choices(names, weights)[0]]) for _ in range(SAMPLE_COUNT)]
        codes = [str(p["heard"]) for p in drawn if clear(p, languages)]
        out[call_talk(codes, languages)] += 1
    return out


def report() -> None:
    rng = random.Random(7)
    for path in sorted(RUNS.glob("detect-*s.json")):
        data = cast("dict[str, Any]", read_json(path))
        pieces = cast("list[dict[str, Any]]", data["pieces"])
        print(f"\n## pieces of {data['seconds']:g} s ({len(pieces)} pieces)\n")
        print("All pieces, what Whisper named:\n")
        print(matrix(pieces, ("zh", "ja", "ko", "en")))
        kept = [p for p in pieces if p["p"] >= MIN_PROBABILITY and p["speech_s"] >= MIN_SPEECH_S]
        print(
            f"\nPieces the detector counts (p >= 0.5 and speech >= 0.5 s): {len(kept)} of {len(pieces)}\n"
        )
        print(matrix(kept, ("zh", "ja", "ko", "en")))
        for lang in ("zh", "ja", "ko", "en"):
            mine = [p for p in pieces if p["lang"] == lang]
            wrong = [p for p in mine if p["heard"] != lang]
            probs = sorted(p["p"] for p in mine if p["heard"] == lang)
            low = sum(1 for p in wrong if p["p"] < MIN_PROBABILITY)
            print(
                f"- {lang}: {len(wrong)} of {len(mine)} named another language, {low} of them with "
                f"probability under 0.5; right ones have probability median {probs[len(probs) // 2] if probs else 0}"
            )
        if data["seconds"] != 5:
            continue
        print("\nSimulated 24-piece talks (clear pieces only), languages zh, ja, en:\n")
        languages = ("zh", "ja", "en")
        for label, spoken in (
            ("Mandarin only", {"zh": 1.0}),
            ("Japanese only", {"ja": 1.0}),
            ("English only", {"en": 1.0}),
            ("Korean only", {"ko": 1.0}),
            ("Mandarin 90 / English 10", {"zh": 0.9, "en": 0.1}),
            ("Mandarin 80 / English 20", {"zh": 0.8, "en": 0.2}),
            ("Mandarin 50 / Japanese 50", {"zh": 0.5, "ja": 0.5}),
        ):
            counts = simulate(pieces, languages, spoken, rng, 2000)
            print(f"- {label}: " + ", ".join(f"{k} {v / 20:.1f}%" for k, v in counts.most_common()))


def main() -> int:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="cmd", required=True)
    runner = sub.add_parser("run")
    runner.add_argument("--seconds", type=float, default=5.0)
    runner.add_argument("--per-lang", type=int, default=150)
    runner.add_argument("--seed", type=int, default=20261126)
    sub.add_parser("report")
    args = parser.parse_args()
    if args.cmd == "run":
        run(args.seconds, args.per_lang, args.seed)
    else:
        report()
    return 0


if __name__ == "__main__":
    sys.exit(main())
