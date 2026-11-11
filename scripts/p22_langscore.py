"""P22 lever: score what Qwen3-ASR and Whisper do to a two-language talk, per pause-cut segment.

`p22_langmap.py` labels each segment from the Qwen3-ASR `-l auto` text, so it cannot score Qwen3.
This script groups the segments by two signals that do not come from Qwen3 and then reads what
each engine wrote for each group.

- `lid`: Whisper `-l auto` picks one language for the whole segment (its own language ID).
- `en_run`: Whisper `-l ja` wrote a run of four or more Latin words. Whisper written for Japanese
  keeps English speech as English about half of the time, so a run is evidence of English speech.

Groups. `ja_only`: lid is ja and no English run. `en_only`: lid is en and Qwen3 `-l auto` wrote
English. `ja_then_en`: lid is en but Qwen3 `-l auto` wrote Japanese (the segment holds a Japanese
passage and its English interpretation with no pause of the cut length between them).
It reads text only. Nobody heard the audio.

    uv run python scripts/p22_langscore.py RUNS_DIR OUT.json [FINE_TAG]

FINE_TAG (for example `fine300`) also scores a finer cut: runs named
`qwen3-kirby-chunks-auto-lenient-FINE_TAG.json` and `whisper-kirby-chunks-auto-FINE_TAG.json`.
"""

from __future__ import annotations

import json
import re
import statistics
import sys
from collections import Counter
from pathlib import Path
from typing import Any

from p22_langmap import Rec, load_chunks, script_of, text_of

EN_RUN = re.compile(r"(?:[A-Za-z'’\-]+[ ,.]+){3,}[A-Za-z'’\-]+")
LATIN_WORD = re.compile(r"[A-Za-z]{2,}")


def seconds(rec: Rec) -> float:
    return (rec["end_ms"] - rec["start_ms"]) / 1000


def segments(runs: Path, tag: str = "fine") -> list[Rec]:
    qwen_auto = load_chunks(runs / f"qwen3-kirby-chunks-auto-lenient-{tag}.json")
    whisper_auto = load_chunks(runs / f"whisper-kirby-chunks-auto-{tag}.json")
    ja_file = runs / f"whisper-kirby-chunks-ja-{tag}.json"
    qwen_ja_file = runs / f"qwen3-kirby-chunks-ja-lenient-{tag}.json"
    whisper_ja = load_chunks(ja_file) if ja_file.is_file() else None
    qwen_ja = load_chunks(qwen_ja_file) if qwen_ja_file.is_file() else None
    out: list[Rec] = []
    for k, (qa, wa) in enumerate(zip(qwen_auto, whisper_auto, strict=True)):
        row: Rec = {
            "start_ms": qa["start_ms"],
            "end_ms": qa["end_ms"],
            "lid": wa.get("detected"),
            "qwen_auto": text_of(qa),
        }
        if whisper_ja is not None:
            row["whisper_ja"] = text_of(whisper_ja[k])
            row["en_run"] = bool(EN_RUN.search(row["whisper_ja"]))
        if qwen_ja is not None:
            row["qwen_ja"] = text_of(qwen_ja[k])
        out.append(row)
    return out


def group_of(row: Rec) -> str:
    qwen = script_of(row["qwen_auto"])
    if row["lid"] == "ja" and qwen == "ja" and not row.get("en_run"):
        return "ja_only"
    if row["lid"] == "en" and qwen == "en":
        return "en_only"
    if row["lid"] == "en" and qwen == "ja":
        return "ja_then_en"
    return "other"


def summarize(rows: list[Rec]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for name in ("ja_only", "en_only", "ja_then_en", "other"):
        g = [r for r in rows if group_of(r) == name]
        item: dict[str, Any] = {"segments": len(g), "seconds": round(sum(seconds(r) for r in g))}
        if not g:
            out[name] = item
            continue
        item["qwen_auto_chars_per_s"] = round(
            sum(len(r["qwen_auto"]) for r in g) / sum(seconds(r) for r in g), 2
        )
        item["qwen_auto_has_english_run"] = sum(bool(EN_RUN.search(r["qwen_auto"])) for r in g)
        if "whisper_ja" in g[0]:
            item["whisper_ja_has_english_run"] = sum(r["en_run"] for r in g)
            item["whisper_ja_chars_over_qwen_auto_chars"] = round(
                sum(len(r["whisper_ja"]) for r in g) / max(1, sum(len(r["qwen_auto"]) for r in g)),
                2,
            )
            item["whisper_ja_script"] = dict(Counter(script_of(r["whisper_ja"]) for r in g))
        if "qwen_ja" in g[0]:
            item["qwen_ja_script"] = dict(Counter(script_of(r["qwen_ja"]) for r in g))
            item["qwen_ja_has_english_run"] = sum(bool(EN_RUN.search(r["qwen_ja"])) for r in g)
            item["qwen_ja_seconds_of_english_written_as_japanese"] = (
                round(
                    sum(
                        seconds(r)
                        for r in g
                        if name == "en_only" and script_of(r["qwen_ja"]) == "ja"
                    ),
                    1,
                )
                if name == "en_only"
                else None
            )
        out[name] = item
    return out


def vad_chunk_exposure(runs: Path, rows: list[Rec]) -> dict[str, Any]:
    """English-only speech in the app's chunks that Qwen3 `-l ja` wrote with no English word."""
    chunks = load_chunks(runs / "qwen3-kirby-chunks-ja-lenient.json")
    english = [r for r in rows if group_of(r) == "en_only"]
    total = sum(seconds(r) for r in english)
    lost = 0.0
    chunks_with_english = chunks_without_latin = 0
    for chunk in chunks:
        inside = [
            r
            for r in english
            if chunk["start_ms"] <= (r["start_ms"] + r["end_ms"]) // 2 < chunk["end_ms"]
        ]
        if not inside:
            continue
        chunks_with_english += 1
        if not LATIN_WORD.search(text_of(chunk)):
            chunks_without_latin += 1
            lost += sum(seconds(r) for r in inside)
    return {
        "english_only_seconds": round(total),
        "in_chunks_whose_ja_text_has_no_latin_word_seconds": round(lost),
        "share": round(lost / total, 3),
        "chunks_with_english_only_speech": chunks_with_english,
        "of_which_no_latin_word": chunks_without_latin,
    }


def recovery_on_finer_cut(coarse: list[Rec], fine: list[Rec]) -> dict[str, Any]:
    """Do the segments of the coarse cut that hold both languages split into one language each?"""
    mixed = [r for r in coarse if group_of(r) == "ja_then_en"]
    recovered = split = 0
    pieces: list[int] = []
    words_coarse = words_fine = 0
    for seg in mixed:
        inside = [
            f for f in fine if seg["start_ms"] <= (f["start_ms"] + f["end_ms"]) // 2 < seg["end_ms"]
        ]
        pieces.append(len(inside))
        words_coarse += len(LATIN_WORD.findall(seg["qwen_auto"]))
        words_fine += sum(len(LATIN_WORD.findall(f["qwen_auto"])) for f in inside)
        split += len(inside) >= 2
        kinds = {script_of(f["qwen_auto"]) for f in inside}
        recovered += {"ja", "en"} <= kinds
    return {
        "coarse_ja_then_en_segments": len(mixed),
        "split_into_two_or_more_pieces": split,
        "pieces_median": statistics.median(pieces) if pieces else None,
        "pieces_include_both_a_japanese_and_an_english_text": recovered,
        "latin_words_in_qwen_auto_coarse": words_coarse,
        "latin_words_in_qwen_auto_fine": words_fine,
    }


def fine_scores(rows: list[Rec]) -> dict[str, Any]:
    """On a finer cut, Qwen3 `-l auto` against Whisper's language ID, segment by segment."""
    confusion: Counter[tuple[str, str]] = Counter()
    for r in rows:
        confusion[(str(r["lid"]), script_of(r["qwen_auto"]))] += 1
    both = sum(
        1 for r in rows if r["lid"] in ("ja", "en") and script_of(r["qwen_auto"]) in ("ja", "en")
    )
    agree = sum(
        1 for r in rows if r["lid"] in ("ja", "en") and r["lid"] == script_of(r["qwen_auto"])
    )
    english = [r for r in rows if r["lid"] == "en"]
    forced: dict[str, Any] = {}
    if english and "qwen_ja" in english[0]:
        forced = {
            "whisper_lid_en_segments": len(english),
            "whisper_lid_en_seconds": round(sum(seconds(r) for r in english)),
            "qwen_auto_script_of_them": dict(Counter(script_of(r["qwen_auto"]) for r in english)),
            "qwen_ja_script_of_them": dict(Counter(script_of(r["qwen_ja"]) for r in english)),
            "qwen_ja_seconds_written_as_japanese": round(
                sum(seconds(r) for r in english if script_of(r["qwen_ja"]) == "ja")
            ),
            "qwen_auto_seconds_written_as_japanese": round(
                sum(seconds(r) for r in english if script_of(r["qwen_auto"]) == "ja")
            ),
        }
    return {
        **forced,
        "segments": len(rows),
        "speech_seconds": round(sum(seconds(r) for r in rows)),
        "qwen_auto_script_vs_whisper_lid": {
            f"{a}|{b}": n for (a, b), n in sorted(confusion.items())
        },
        "agree_where_both_are_ja_or_en": f"{agree}/{both}",
        "qwen_auto_chars_per_s": round(
            sum(len(r["qwen_auto"]) for r in rows if script_of(r["qwen_auto"]) == "ja")
            / max(1.0, sum(seconds(r) for r in rows if script_of(r["qwen_auto"]) == "ja")),
            2,
        ),
    }


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
    runs, out_path = Path(sys.argv[1]), Path(sys.argv[2])
    rows = segments(runs)
    result: dict[str, Any] = {
        "segments": len(rows),
        "groups": summarize(rows),
        "app_chunks_exposure": vad_chunk_exposure(runs, rows),
    }
    if len(sys.argv) > 3:
        fine = segments(runs, sys.argv[3])
        result[f"cut_{sys.argv[3]}"] = fine_scores(fine)
        result[f"cut_{sys.argv[3]}_recovery"] = recovery_on_finer_cut(rows, fine)
    out_path.write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
