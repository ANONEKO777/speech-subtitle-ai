"""P22 lever: the per-segment language map of a two-language talk, and how each approach does on it.

Needs the runs of the `-fine` family: Whisper `-l auto`, `-l ja` and `-l en` and Qwen3-ASR `-l auto`
on the pause-cut segments of `p22_finesegs.py`, plus the whole-file Whisper runs. Forcing the wrong
language makes Whisper translate rather than fail, so the script of a forced decode says nothing
about what was spoken. The label of a segment is the script of the Qwen3-ASR `-l auto` text, which
stayed in the spoken language in every segment read by eye. It is one model's reading and it is also
the reference for the Whisper approaches, so Qwen3-ASR is not scored against itself.

    uv run python scripts/p22_langmap.py RUNS_DIR OUT.json
"""

from __future__ import annotations

import json
import math
import re
import statistics
import sys
from collections import Counter
from pathlib import Path
from typing import Any, cast

KANA = re.compile("[぀-ヿ]")
CJK = re.compile("[㐀-鿿]")
LATIN = re.compile("[A-Za-z]")
Rec = dict[str, Any]


def script_of(text: str) -> str:
    ja = len(KANA.findall(text)) + len(CJK.findall(text))
    en = len(LATIN.findall(text))
    if ja == 0 and en == 0:
        return "none"
    if ja >= 2 * en:
        return "ja"
    if en >= 2 * ja:
        return "en"
    return "mixed"


def load_chunks(path: Path) -> list[Rec]:
    return cast("list[Rec]", json.loads(path.read_text(encoding="utf-8"))["chunks"])


def text_of(chunk: Rec) -> str:
    return " ".join(s["text"] for s in chunk["segments"]).strip()


def mean_logp(chunk: Rec) -> float:
    ps = [u["p"] for s in chunk["segments"] for u in s["units"] if u.get("p")]
    return statistics.mean(math.log(max(p, 1e-6)) for p in ps) if ps else float("-inf")


def vote(label: str) -> str | None:
    return label if label in ("ja", "en") else None


def label_segments(runs: Path) -> list[Rec]:
    auto = load_chunks(runs / "whisper-kirby-chunks-auto-fine.json")
    ja = load_chunks(runs / "whisper-kirby-chunks-ja-fine.json")
    en = load_chunks(runs / "whisper-kirby-chunks-en-fine.json")
    qwen = load_chunks(runs / "qwen3-kirby-chunks-auto-lenient-fine.json")
    out: list[Rec] = []
    for a, j, e, q in zip(auto, ja, en, qwen, strict=True):
        lp_ja, lp_en = mean_logp(j), mean_logp(e)
        out.append(
            {
                "i": a["index"],
                "start_ms": a["start_ms"],
                "end_ms": a["end_ms"],
                "label": script_of(text_of(q)),
                "auto_detected": a.get("detected"),
                "restricted_logp": "ja" if lp_ja > lp_en else "en",
                "text_qwen3": text_of(q),
                "text_whisper_ja": text_of(j),
                "text_whisper_en": text_of(e),
            }
        )
    return out


WORD = re.compile(r"[a-z]{4,}")


def overlap(a: str, b: str) -> float:
    x, y = set(WORD.findall(a.lower())), set(WORD.findall(b.lower()))
    return len(x & y) / max(1, len(x | y))


def interpretation_test(rows: list[Rec]) -> dict[str, Any]:
    """Does a Japanese passage have an English passage just after it that says the same thing?

    The Whisper `-l en` decode of Japanese speech is an English translation of it. It is compared
    with the Qwen3 English text of the next four segments, and with four segments taken from
    elsewhere as a baseline."""
    english = [r["text_qwen3"] if r["label"] == "en" else "" for r in rows]
    hits: list[float] = []
    base: list[float] = []
    for k, r in enumerate(rows):
        if r["label"] != "ja" or len(r["text_whisper_en"]) < 40:
            continue
        near = " ".join(english[k + 1 : k + 5])
        far = " ".join(english[(k + len(rows) // 2) % len(rows) :][:4])
        hits.append(overlap(r["text_whisper_en"], near))
        base.append(overlap(r["text_whisper_en"], far))
    return {
        "japanese_segments_tested": len(hits),
        "median_word_overlap_next_english": round(statistics.median(hits), 3),
        "median_word_overlap_unrelated_english": round(statistics.median(base), 3),
        "share_with_overlap_at_least_0.2": round(sum(h >= 0.2 for h in hits) / len(hits), 3),
        "share_of_baseline_at_least_0.2": round(sum(h >= 0.2 for h in base) / len(base), 3),
    }


def whole_text_in(run: Path, start_ms: int, end_ms: int) -> str:
    out: list[str] = []
    for chunk in load_chunks(run):
        for seg in chunk["segments"]:
            mid = chunk["start_ms"] + (seg["start_ms"] + seg["end_ms"]) // 2
            if start_ms <= mid < end_ms:
                out.append(seg["text"])
    return " ".join(out).strip()


def accuracy(rows: list[Rec], got: dict[int, str]) -> dict[str, Any]:
    ok = wrong = 0
    en_as_ja = ja_as_en = en_n = ja_n = 0
    for r in rows:
        if r["label"] not in ("ja", "en"):
            continue
        g = got.get(r["i"], "none")
        if r["label"] == "en":
            en_n += 1
            en_as_ja += g == "ja"
        else:
            ja_n += 1
            ja_as_en += g == "en"
        if g == r["label"]:
            ok += 1
        else:
            wrong += 1
    return {
        "segments": ok + wrong,
        "language_decision_correct": ok,
        "accuracy": round(ok / max(1, ok + wrong), 4),
        "english_speech_read_as_japanese": f"{en_as_ja}/{en_n}",
        "japanese_speech_read_as_english": f"{ja_as_en}/{ja_n}",
    }


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
    runs, out_path = Path(sys.argv[1]), Path(sys.argv[2])
    rows = label_segments(runs)
    summary: dict[str, Any] = {"segments_total": len(rows)}
    summary["labels"] = Counter(r["label"] for r in rows)
    speech = [r for r in rows if r["label"] in ("ja", "en", "mixed")]
    for lang in ("ja", "en"):
        secs = sum(r["end_ms"] - r["start_ms"] for r in speech if r["label"] == lang) / 1000
        summary[f"{lang}_seconds"] = round(secs)
    switches = sum(1 for a, b in zip(speech, speech[1:], strict=False) if a["label"] != b["label"])
    summary["language_switches"] = switches
    methods: dict[str, dict[int, str]] = {
        "per-segment auto (Whisper top pick, any language)": {
            r["i"]: r["auto_detected"] or "none" for r in rows
        },
        "per-segment restricted to en/ja (forced decodes, higher mean token probability)": {
            r["i"]: r["restricted_logp"] for r in rows
        },
    }
    for name, path in (
        ("whole file -l ja", "whisper-kirby-whole-ja.json"),
        ("whole file -l en", "whisper-kirby-whole-en.json"),
        ("whole file -l auto", "whisper-kirby-whole-auto.json"),
    ):
        file = runs / path
        if file.is_file():
            methods[name] = {
                r["i"]: script_of(whole_text_in(file, r["start_ms"], r["end_ms"])) for r in rows
            }
    summary["whisper_pick_not_en_or_ja"] = sum(
        1 for r in rows if r["label"] in ("ja", "en") and r["auto_detected"] not in ("ja", "en")
    )
    summary["interpretation_test"] = interpretation_test(rows)
    summary["methods"] = {name: accuracy(rows, got) for name, got in methods.items()}
    out_path.write_text(
        json.dumps({"summary": summary, "segments": rows}, ensure_ascii=False, indent=1),
        encoding="utf-8",
    )
    print(json.dumps(summary, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
