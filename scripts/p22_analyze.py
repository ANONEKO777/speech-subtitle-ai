"""P22 lever: measure the runs that `p22_asr.py` saved.

table RUNS_DIR WAV_DIR            one row per run: speed, VRAM, text size, loops, silence text,
                                  timestamp shape, boundary error against VAD speech edges
window RUN_JSON START_S DUR_S     print the text a run gave for one window
cer REF_JSON RUN_JSON...          character error rate of each run against a reference file
"""

from __future__ import annotations

import bisect
import json
import re
import statistics
import sys
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

import numpy as np
from numpy.typing import NDArray

from backend.core import vad

ONNX = Path(__file__).resolve().parents[3] / "models/silero-vad/silero_vad.onnx"
Probs = NDArray[np.float32]


@dataclass(frozen=True, slots=True)
class U:
    text: str
    start: int
    end: int


@dataclass(frozen=True, slots=True)
class S:
    start: int
    end: int
    text: str
    chunk: int


@dataclass(frozen=True, slots=True)
class Run:
    meta: dict[str, Any]
    segs: list[S]
    units: list[U]


def load(path: Path) -> Run:
    meta = cast("dict[str, Any]", json.loads(path.read_text(encoding="utf-8")))
    segs: list[S] = []
    units: list[U] = []
    for chunk in cast("list[dict[str, Any]]", meta["chunks"]):
        base = int(chunk["start_ms"])
        for seg in cast("list[dict[str, Any]]", chunk["segments"]):
            segs.append(
                S(
                    base + int(seg["start_ms"]),
                    base + int(seg["end_ms"]),
                    seg["text"],
                    chunk["index"],
                )
            )
            for u in cast("list[dict[str, Any]]", seg["units"]):
                units.append(U(u["text"], base + int(u["start_ms"]), base + int(u["end_ms"])))
    meta = {k: v for k, v in meta.items() if k != "chunks"}
    return Run(meta, segs, units)


def probs_for(wav: Path) -> Probs:
    cache = wav.with_suffix(".vadprobs.npy")
    if cache.is_file():
        return cast("Probs", np.load(cache))
    probs = vad.frame_probs(wav, ONNX)
    np.save(cache, probs)
    return probs


_DIGITS = "〇一二三四五六七八九"
_FILLERS = ("まあ", "ええと", "えーと", "あのー")


def _kanji_number(match: re.Match[str]) -> str:
    text = match.group(0)
    if not any(c in "十百千" for c in text):
        return "".join(str(_DIGITS.index(c)) for c in text)
    total, current = 0, 0
    for c in text:
        if c in _DIGITS:
            current = _DIGITS.index(c)
        else:
            unit = {"十": 10, "百": 100, "千": 1000}[c]
            total += (current or 1) * unit
            current = 0
    return str(total + current)


def normalise(text: str, *, for_cer: bool = False, ja_only: bool = False) -> str:
    """NFKC, lower case, letters and digits only. With `for_cer`, kanji numbers become digits,
    "four" becomes 4 and the fillers まあ and ええと are dropped, so the score does not punish
    style choices the subtitle step makes anyway."""
    text = unicodedata.normalize("NFKC", text).lower()
    if for_cer:
        for filler in _FILLERS:
            text = text.replace(filler, "")
        text = re.sub("[〇一二三四五六七八九十百千]+", _kanji_number, text)
        text = re.sub(r"four", "4", text)
    if ja_only:
        return "".join(c for c in text if "぀" <= c <= "ヿ" or "㐀" <= c <= "鿿")
    return "".join(c for c in text if unicodedata.category(c)[0] in "LN")


def edit_distance(ref: str, hyp: str, *, free_hyp_edges: bool = False) -> int:
    """Levenshtein distance. With `free_hyp_edges`, hypothesis text before and after the best
    matching span costs nothing, so a window cut in the middle of a sentence is not punished."""
    prev = [0] * (len(hyp) + 1) if free_hyp_edges else list(range(len(hyp) + 1))
    for i, cr in enumerate(ref, 1):
        cur = [i]
        for j, ch in enumerate(hyp, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (cr != ch)))
        prev = cur
    return min(prev) if free_hyp_edges else prev[-1]


def hyp_text(run: Run, start_ms: int, end_ms: int) -> str:
    """Text of the units that start in the window, or of the segments centred in it when the
    aligner gave no units there (CrispASR without --strict-pipeline)."""
    from_units = "".join(u.text for u in run.units if start_ms <= u.start < end_ms)
    from_segs = "".join(s.text for s in run.segs if start_ms <= (s.start + s.end) // 2 < end_ms)
    return from_units if len(from_units) >= 0.5 * len(from_segs) else from_segs


LOOP = re.compile(r"(.{2,40}?)\1{3,}")


def loops(run: Run) -> tuple[int, int]:
    inside = sum(1 for s in run.segs if LOOP.search(s.text))
    texts = [normalise(s.text) for s in run.segs]
    streak = sum(
        1 for i in range(2, len(texts)) if texts[i] and texts[i] == texts[i - 1] == texts[i - 2]
    )
    return inside, streak


def silent_segments(run: Run, probs: Probs, limit: float = 0.1) -> list[S]:
    frame = vad.FRAME_MS
    out: list[S] = []
    for s in run.segs:
        a, b = s.start // frame, max(s.start // frame + 1, s.end // frame)
        window = probs[a:b]
        if len(window) and float((window >= 0.5).mean()) < limit and normalise(s.text):
            out.append(s)
    return out


def edge_error(run: Run, probs: Probs) -> tuple[list[float], list[float]]:
    """Distance from each long-pause speech onset and offset to the nearest unit edge."""
    params = vad.VadParams(min_silence_ms=500)
    runs = vad.speech_runs(probs, params)
    starts = sorted(u.start for u in run.units)
    ends = sorted(u.end for u in run.units)

    def nearest(values: list[int], at: int) -> int:
        k = bisect.bisect_left(values, at)
        return min(abs(values[j] - at) for j in (max(0, k - 1), min(len(values) - 1, k)))

    on = [nearest(starts, a) / 1000 for a, _ in runs]
    off = [nearest(ends, b) / 1000 for _, b in runs]
    return on, off


def pct(values: list[float], q: float) -> float:
    return float(np.percentile(values, q)) if values else float("nan")


def table(runs_dir: Path, wav_dir: Path) -> None:
    print(
        "| run | wall s | RTF | VRAM peak MiB | segs | text chars | loop segs / streaks | "
        "silent-text segs | chars/unit | zero-length units % | onset p50/p90 s | offset p50/p90 s |"
    )
    print("|---|---|---|---|---|---|---|---|---|---|---|---|")
    for path in sorted(runs_dir.glob("*.json")):
        if path.name.endswith((".chunks.json", ".fine.json")):
            continue
        run = load(path)
        m = run.meta
        wav = wav_dir / m["wav"]
        probs = probs_for(wav)
        inside, streak = loops(run)
        silent = silent_segments(run, probs)
        chars = sum(len(normalise(s.text)) for s in run.segs)
        per_unit = statistics.mean(len(u.text.strip()) for u in run.units) if run.units else 0
        zero = 100 * sum(u.end == u.start for u in run.units) / max(1, len(run.units))
        on, off = edge_error(run, probs) if run.units else ([], [])
        name = path.stem
        print(
            f"| {name} | {m['wall_s']} | {m['rtf_wav']} | {m['vram_peak_mib']} | {len(run.segs)} | "
            f"{chars} | {inside} / {streak} | {len(silent)} | {per_unit:.2f} | {zero:.1f} | "
            f"{pct(on, 50):.2f} / {pct(on, 90):.2f} | {pct(off, 50):.2f} / {pct(off, 90):.2f} |"
        )


def window(run_json: Path, start_s: float, dur_s: float) -> None:
    run = load(run_json)
    a, b = int(start_s * 1000), int((start_s + dur_s) * 1000)
    for s in run.segs:
        if a <= (s.start + s.end) // 2 < b:
            print(f"[{s.start / 1000:.1f}-{s.end / 1000:.1f}] {s.text}")


def cer(ref_json: Path, run_jsons: list[Path], *, ja_only: bool = False) -> None:
    ref = cast("dict[str, list[dict[str, Any]]]", json.loads(ref_json.read_text(encoding="utf-8")))
    for path in run_jsons:
        run = load(path)
        video = cast("str", run.meta["wav"]).removesuffix(".wav")
        windows = ref.get(video, [])
        errors = total = 0
        per: list[str] = []
        for w in windows:
            r = normalise(w["text"], for_cer=True, ja_only=ja_only)
            pad = 3000
            h = normalise(
                hyp_text(run, int(w["start_s"] * 1000) - pad, int(w["end_s"] * 1000) + pad),
                for_cer=True,
                ja_only=ja_only,
            )
            e = edit_distance(r, h, free_hyp_edges=True)
            errors += e
            total += len(r)
            per.append(f"{e / max(1, len(r)):.3f}")
        rate = errors / total if total else float("nan")
        print(
            f"{path.stem}: CER {rate:.4f} ({errors}/{total} chars, {len(windows)} windows) "
            f"per-window {' '.join(per)}"
        )


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
    cmd, *rest = sys.argv[1:]
    if cmd == "table":
        table(Path(rest[0]), Path(rest[1]))
    elif cmd == "window":
        window(Path(rest[0]), float(rest[1]), float(rest[2]))
    elif cmd == "cer":
        flags = [a for a in rest if a.startswith("--")]
        cer(
            Path(rest[0]),
            [Path(p) for p in rest[1:] if not p.startswith("--")],
            ja_only="--ja-only" in flags,
        )
    else:
        raise SystemExit(__doc__)
