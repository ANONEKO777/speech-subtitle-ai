"""Z0 E5: score the app's ASR path against the hard-sub reference of the operator's video.

    .work/zh-z0/venv-native/Scripts/python scripts/zh_z0_e5_score.py e5-w e5-q e5-q-hant

The reference (`e5/reference.tsv`) is text a model read from burned-in subtitles in the picture. Hard
subs are edited and condensed, so a CER against them is an upper bound and a sanity check, not a
ground truth. Only the stretches whose lines were read by eye are scored (the `spans`): the words
of a run whose middle falls inside a stretch are compared with the lines of that stretch, after
dropping punctuation and spaces and making both Simplified (`t2s` of the `opencc` wheel).

Timing: the on and off times of the lines come from `e5/timeline.json` (the strip of the picture
read at 10 frames per second). The cue start times of a run are compared with the start of the
nearest line. The speech rate is the reference characters per second the lines are on screen, and
the run's characters per second of VAD speech.
"""
# ruff: noqa: E501
# ruff: noqa: E501

from __future__ import annotations

import importlib
import sys
from collections.abc import Callable
from typing import Any, cast

from zh_z0_text import WORK, edit_distance, is_han, keep_letters, percentile, read_json

E5 = WORK / "e5"
MERGE = {98: 99, 102: 103}
"""Raw lines the strip detector cut in two because the background changed: the first one's end is
the second one's end."""
Convert = Callable[[str], str]


def reference() -> list[dict[str, Any]]:
    timeline = {
        int(x["id"]): x
        for x in cast("list[dict[str, Any]]", read_json(E5 / "timeline.json")["lines"])
    }
    rows: list[dict[str, Any]] = []
    for number, line in enumerate((E5 / "reference.tsv").read_text(encoding="utf-8").splitlines()):
        if number == 0:
            continue
        fields = line.split("\t")
        ident = int(fields[0])
        end = float(timeline[MERGE.get(ident, ident)]["end"])
        rows.append({"id": ident, "start": float(fields[1]), "end": end, "text": fields[3]})
    return rows


def spans(rows: list[dict[str, Any]]) -> list[list[dict[str, Any]]]:
    groups: list[list[dict[str, Any]]] = []
    for row in rows:
        if groups and row["id"] - groups[-1][-1]["id"] <= 2:
            groups[-1].append(row)
        else:
            groups.append([row])
    return groups


def script_counts(text: str, t2s: Convert) -> tuple[int, int]:
    sys.path.insert(0, str(WORK.parents[1]))
    from backend.core.zh_tw import SIMPLIFIED_ONLY

    traditional = sum(1 for c in text if is_han(c) and t2s(c) != c)
    simplified = sum(1 for c in text if c in SIMPLIFIED_ONLY)
    return traditional, simplified


def score(tag: str, rows: list[dict[str, Any]], t2s: Convert) -> dict[str, Any]:
    run = cast("dict[str, Any]", read_json(E5 / f"{tag}.json"))
    words = cast("list[list[Any]]", run["words"])
    cues = cast("list[list[Any]]", run["cues"])
    edits = chars = 0
    asr_text_all = ""
    for group in spans(rows):
        t0, t1 = group[0]["start"] - 0.3, group[-1]["end"] + 0.3
        hyp = "".join(str(w[0]) for w in words if t0 <= (w[1] + w[2]) / 2000 <= t1)
        ref = "".join(r["text"] for r in group)
        asr_text_all += hyp
        a, b = keep_letters(t2s(ref)), keep_letters(t2s(hyp))
        edits += edit_distance(a, b)
        chars += len(a)
    traditional, simplified = script_counts(asr_text_all, t2s)
    starts = [float(r["start"]) for r in rows]
    ends = [float(r["end"]) for r in rows]
    in_span = [
        c
        for c in cues
        if any(g[0]["start"] - 0.3 <= c[0] / 1000 <= g[-1]["end"] for g in spans(rows))
    ]
    start_err = [min(abs(c[0] / 1000 - s) for s in starts) for c in in_span]
    ref_missed = [min((abs(c[0] / 1000 - r["start"]) for c in cues), default=99) for r in rows]
    end_err = [min(abs(c[1] / 1000 - e) for e in ends) for c in in_span]
    cue_chars = [len(str(c[2]).replace("\n", "")) for c in cues]
    cue_len = [(c[1] - c[0]) / 1000 for c in cues]
    ref_len = [r["end"] - r["start"] for r in rows]
    speech_s = sum(b - a for a, b in cast("list[list[int]]", run["chunks"])) / 1000
    han = sum(1 for w in words for c in str(w[0]) if is_han(c))
    return {
        "tag": tag,
        "engine": run["engine"],
        "lang_flag": run["lang_flag"],
        "cer_script_free": edits / max(chars, 1),
        "ref_chars": chars,
        "traditional_chars": traditional,
        "simplified_chars": simplified,
        "cues_total": len(cues),
        "cues_per_min": len(cues) / (run["audio_s"] / 60),
        "ref_lines_per_min": len(rows) / (sum(ref_len) / 60) if rows else 0,
        "cue_start_error_s_p50_p90": [percentile(start_err, 50), percentile(start_err, 90)],
        "cue_end_error_s_p50_p90": [percentile(end_err, 50), percentile(end_err, 90)],
        "ref_start_matched_within_0.5s": sum(1 for x in ref_missed if x <= 0.5) / max(len(rows), 1),
        "ref_start_matched_within_1s": sum(1 for x in ref_missed if x <= 1.0) / max(len(rows), 1),
        "cue_chars_p50_p90_max": [
            percentile(cue_chars, 50),
            percentile(cue_chars, 90),
            max(cue_chars),
        ],
        "cue_seconds_p50_p90_max": [percentile(cue_len, 50), percentile(cue_len, 90), max(cue_len)],
        "ref_line_seconds_p50_p90": [percentile(ref_len, 50), percentile(ref_len, 90)],
        "ref_line_chars_p50_p90_max": [
            percentile([len(r["text"]) for r in rows], 50),
            percentile([len(r["text"]) for r in rows], 90),
            max(len(r["text"]) for r in rows),
        ],
        "asr_han_chars": han,
        "vad_speech_s": speech_s,
        "asr_chars_per_vad_speech_s": han / max(speech_s, 1),
        "ref_chars_per_line_second": sum(len(r["text"]) for r in rows) / max(sum(ref_len), 1),
    }


def main() -> int:
    opencc = cast("Any", importlib.import_module("opencc"))
    t2s = cast("Convert", opencc.OpenCC("t2s").convert)
    rows = reference()
    print(
        f"reference: {len(rows)} lines, {sum(len(r['text']) for r in rows)} characters, {len(spans(rows))} stretches"
    )
    for tag in sys.argv[1:]:
        result = score(tag, rows, t2s)
        print()
        for key, value in result.items():
            shown: Any = value
            if isinstance(value, list):
                shown = [round(float(v), 2) for v in cast("list[Any]", value)]
            elif isinstance(value, float):
                shown = round(value, 4)
            print(f"{key}: {shown}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
