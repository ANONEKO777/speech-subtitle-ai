"""P22 lever: the per-segment language map of a two-language talk, and how each approach does on it.

Needs the runs of the `-fine` family: Whisper `-l auto`, `-l ja` and `-l en` on the pause-cut
segments of `p22_finesegs.py`, plus the whole-file Whisper runs. A segment's label is the majority
of three votes that do not share a decoder choice: the script of the `-l ja` text, Whisper's own
language pick on the audio, and the language whose forced decode had the higher mean token
probability. The labels are one model's reading, and `sample` prints segments to check by eye.

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
    out: list[Rec] = []
    for a, j, e in zip(auto, ja, en, strict=True):
        text_ja, text_en = text_of(j), text_of(e)
        lp_ja, lp_en = mean_logp(j), mean_logp(e)
        votes = {
            "script_ja_decode": vote(script_of(text_ja)),
            "whisper_pick": vote(a.get("detected") or ""),
            "restricted_logp": "ja" if lp_ja > lp_en else "en",
        }
        counts = Counter(v for v in votes.values() if v)
        top, n = counts.most_common(1)[0] if counts else ("none", 0)
        if not text_ja and not text_en:
            label, agreement = "none", "empty"
        elif n >= 2:
            label, agreement = top, "unanimous" if n == 3 else "majority"
        else:
            label, agreement = "unclear", "split"
        out.append(
            {
                "i": a["index"],
                "start_ms": a["start_ms"],
                "end_ms": a["end_ms"],
                "label": label,
                "agreement": agreement,
                "votes": votes,
                "auto_detected": a.get("detected"),
                "lp_ja": round(lp_ja, 3),
                "lp_en": round(lp_en, 3),
                "text_auto": text_of(a),
                "text_ja": text_ja,
                "text_en": text_en,
            }
        )
    return out


def whole_text_in(run: Path, start_ms: int, end_ms: int) -> str:
    out: list[str] = []
    for chunk in load_chunks(run):
        for seg in chunk["segments"]:
            if start_ms <= (seg["start_ms"] + seg["end_ms"]) // 2 < end_ms:
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
    summary["agreement"] = Counter(r["agreement"] for r in rows)
    speech = [r for r in rows if r["label"] in ("ja", "en")]
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
            r["i"]: r["votes"]["restricted_logp"] for r in rows
        },
    }
    for name, path in (
        ("whole file -l ja", "whisper-kirby-whole-ja.json"),
        ("whole file -l en", "whisper-kirby-whole-en.json"),
        ("whole file -l auto", "whisper-kirby-whole-auto.json"),
        ("Qwen3-ASR -l ja (script of text)", "qwen3-kirby-chunks-ja-lenient.json"),
    ):
        file = runs / path
        if file.is_file():
            methods[name] = {
                r["i"]: script_of(whole_text_in(file, r["start_ms"], r["end_ms"])) for r in rows
            }
    summary["methods"] = {name: accuracy(rows, got) for name, got in methods.items()}
    out_path.write_text(
        json.dumps({"summary": summary, "segments": rows}, ensure_ascii=False, indent=1),
        encoding="utf-8",
    )
    print(json.dumps(summary, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
