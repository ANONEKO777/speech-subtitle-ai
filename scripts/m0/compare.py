import argparse
import array
import bisect
import difflib
import hashlib
import json
import math
import random
import re
import statistics
import sys
import wave
from collections import defaultdict
from pathlib import Path
from typing import TypedDict

WINDOW_SECONDS = 120.0
WINDOW_COUNT = 3
COVERAGE_TOLERANCE_SECONDS = 60.0
ONSET_SILENCE_SECONDS = 0.6
ONSET_RISE_DB = 15.0
FRAME_SECONDS = 0.01


class WordJson(TypedDict):
    text: str
    start: float
    end: float


class SegmentJson(TypedDict):
    text: str
    start: float
    end: float
    words: list[WordJson] | None


class RunJson(TypedDict):
    engine: str
    audio: str
    audio_seconds: float
    exit_code: int
    wall_seconds: float
    rtf: float
    vram_baseline_mib: int
    vram_peak_mib: int
    segments: list[SegmentJson]


def timeline_violations(segments: list[SegmentJson]) -> list[str]:
    problems: list[str] = []
    prev_seg = prev_word = 0.0
    for i, seg in enumerate(segments):
        if seg["end"] < seg["start"]:
            problems.append(f"segment {i} ends before it starts ({seg['start']} > {seg['end']})")
        if seg["start"] < prev_seg:
            problems.append(f"segment {i} starts at {seg['start']}, before {prev_seg}")
        prev_seg = seg["start"]
        for word in seg["words"] or []:
            if word["end"] < word["start"]:
                problems.append(f"word {word['text']!r} in segment {i} ends before it starts")
            if word["start"] < prev_word:
                problems.append(f"word {word['text']!r} in segment {i} starts before {prev_word}")
            prev_word = word["start"]
    return problems


def longest_gap(segments: list[SegmentJson], duration: float) -> float:
    edges = [0.0, *(t for s in segments for t in (s["start"], s["end"])), duration]
    return max(edges[i + 1] - edges[i] for i in range(0, len(edges), 2))


def repeat_loops(segments: list[SegmentJson], min_repeats: int = 3) -> int:
    loops = run = 0
    for prev, cur in zip(segments, segments[1:], strict=False):
        run = run + 1 if normalize(cur["text"]) == normalize(prev["text"]) else 0
        if run == min_repeats - 1:
            loops += 1
    return loops


def pick_windows(
    duration: float, seed: str, count: int = WINDOW_COUNT, length: float = WINDOW_SECONDS
) -> list[tuple[float, float]]:
    rng = random.Random(int(hashlib.sha256(seed.encode()).hexdigest(), 16))
    slice_len = duration / count
    if slice_len < length:
        raise ValueError(f"{duration:.0f} s is too short for {count} windows of {length:.0f} s")
    windows: list[tuple[float, float]] = []
    for i in range(count):
        start = round(i * slice_len + rng.uniform(0, slice_len - length), 1)
        windows.append((start, start + length))
    return windows


def normalize(text: str) -> str:
    return re.sub(r"[^\w']+", " ", text.lower()).strip()


def window_words(segments: list[SegmentJson], window: tuple[float, float]) -> list[str]:
    lo, hi = window
    out: list[str] = []
    for seg in segments:
        if seg["words"]:
            out += [w["text"] for w in seg["words"] if lo <= w["start"] < hi]
        elif lo <= (seg["start"] + seg["end"]) / 2 < hi:
            out += seg["text"].split()
    return out


def disagreements(a: list[str], b: list[str]) -> list[tuple[str, str]]:
    a_norm = [normalize(w) for w in a]
    b_norm = [normalize(w) for w in b]
    matcher = difflib.SequenceMatcher(a=a_norm, b=b_norm, autojunk=False)
    return [
        (" ".join(a[i1:i2]), " ".join(b[j1:j2]))
        for op, i1, i2, j1, j2 in matcher.get_opcodes()
        if op != "equal"
    ]


def all_words(segments: list[SegmentJson]) -> list[WordJson]:
    return [w for s in segments for w in s["words"] or []]


def matched_start_deltas(a: list[SegmentJson], b: list[SegmentJson]) -> list[float]:
    a_words, b_words = all_words(a), all_words(b)
    matcher = difflib.SequenceMatcher(
        a=[normalize(w["text"]) for w in a_words],
        b=[normalize(w["text"]) for w in b_words],
        autojunk=False,
    )
    return [
        a_words[block.a + k]["start"] - b_words[block.b + k]["start"]
        for block in matcher.get_matching_blocks()
        for k in range(block.size)
    ]


def speech_onsets(wav_path: Path) -> list[float]:
    with wave.open(str(wav_path), "rb") as wav:
        rate = wav.getframerate()
        pcm = array.array("h", wav.readframes(wav.getnframes()))
    hop = int(rate * FRAME_SECONDS)
    levels = [
        10 * math.log10(sum(x * x for x in pcm[i : i + hop]) / hop + 1)
        for i in range(0, len(pcm) - hop, hop)
    ]
    threshold = sorted(levels)[len(levels) // 10] + ONSET_RISE_DB
    needed = round(ONSET_SILENCE_SECONDS / FRAME_SECONDS)
    onsets: list[float] = []
    quiet = 0
    for i, level in enumerate(levels):
        if level < threshold:
            quiet += 1
            continue
        if quiet >= needed:
            onsets.append(i * FRAME_SECONDS)
        quiet = 0
    return onsets


def onset_offsets(segments: list[SegmentJson], onsets: list[float]) -> list[float]:
    starts = sorted(w["start"] for w in all_words(segments))
    offsets: list[float] = []
    for onset in onsets:
        k = bisect.bisect_left(starts, onset)
        near = [starts[j] for j in (k - 1, k) if 0 <= j < len(starts)]
        if near:
            offsets.append(min(near, key=lambda t: abs(t - onset)) - onset)
    return offsets


def spread(values: list[float]) -> str:
    mags = sorted(abs(v) for v in values)
    if not mags:
        return "no data"
    within = sum(m <= 0.5 for m in mags) / len(mags)
    return (
        f"n={len(mags)}, median signed {statistics.median(values):+.2f} s, "
        f"|d| p50 {mags[len(mags) // 2]:.2f} s, p90 {mags[int(0.9 * (len(mags) - 1))]:.2f} s, "
        f"{within:.0%} within 0.5 s"
    )


def timing_rows(runs: dict[str, dict[str, list[RunJson]]], audio_dir: Path | None) -> list[str]:
    rows: list[str] = []
    for audio, by_engine in sorted(runs.items()):
        firsts = {e: r[0] for e, r in sorted(by_engine.items()) if r[0]["exit_code"] == 0}
        engines = list(firsts)
        if len(engines) == 2:
            a, b = engines
            deltas = matched_start_deltas(firsts[a]["segments"], firsts[b]["segments"])
            rows.append(f"- {audio}, {a} minus {b} word starts: {spread(deltas)}")
        if audio_dir is not None and (audio_dir / audio).exists():
            onsets = speech_onsets(audio_dir / audio)
            for engine, run in firsts.items():
                offsets = onset_offsets(run["segments"], onsets)
                rows.append(f"- {audio}, {engine} nearest word start to onset: {spread(offsets)}")
    return rows


def load_runs(run_dir: Path) -> dict[str, dict[str, list[RunJson]]]:
    runs: dict[str, dict[str, list[RunJson]]] = defaultdict(lambda: defaultdict(list))
    for path in sorted(run_dir.glob("*.run.json")):
        run: RunJson = json.loads(path.read_text(encoding="utf-8"))
        runs[run["audio"]][run["engine"]].append(run)
    return runs


def metrics_rows(runs: dict[str, dict[str, list[RunJson]]]) -> list[str]:
    rows = [
        "| audio | engine | runs | RTF median (range) | VRAM peak MiB median (range) "
        "| segments | last end / length s | timeline violations | longest gap s | repeat loops |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]
    for audio, by_engine in sorted(runs.items()):
        for engine, engine_runs in sorted(by_engine.items()):
            ok = [r for r in engine_runs if r["exit_code"] == 0]
            failed = len(engine_runs) - len(ok)
            if not ok:
                rows.append(f"| {audio} | {engine} | 0 ok, {failed} failed | | | | | | | |")
                continue
            rtfs = [r["rtf"] for r in ok]
            peaks = [r["vram_peak_mib"] for r in ok]
            first = ok[0]
            segs = first["segments"]
            last_end = max((s["end"] for s in segs), default=0.0)
            covered = first["audio_seconds"] - last_end <= COVERAGE_TOLERANCE_SECONDS
            rows.append(
                f"| {audio} | {engine} | {len(ok)} ok, {failed} failed "
                f"| {statistics.median(rtfs):.4f} ({min(rtfs):.4f}-{max(rtfs):.4f}) "
                f"| {statistics.median(peaks):.0f} ({min(peaks)}-{max(peaks)}) | {len(segs)} "
                f"| {last_end:.1f} / {first['audio_seconds']:.1f} {'ok' if covered else 'SHORT'} "
                f"| {len(timeline_violations(segs))} "
                f"| {longest_gap(segs, first['audio_seconds']):.1f} | {repeat_loops(segs)} |"
            )
    return rows


def sample_tables(runs: dict[str, dict[str, list[RunJson]]]) -> list[str]:
    out: list[str] = []
    for audio, by_engine in sorted(runs.items()):
        engines = sorted(by_engine)
        if len(engines) != 2 or not all(by_engine[e][0]["exit_code"] == 0 for e in engines):
            out.append(f"\n{audio}: needs one successful run from each of two engines, skipped.")
            continue
        a_run, b_run = (by_engine[e][0] for e in engines)
        for lo, hi in pick_windows(a_run["audio_seconds"], seed=audio):
            a_words = window_words(a_run["segments"], (lo, hi))
            b_words = window_words(b_run["segments"], (lo, hi))
            hunks = disagreements(a_words, b_words)
            out += [
                f"\n### {audio} {lo:.1f}-{hi:.1f} s",
                f"\n{len(a_words)} vs {len(b_words)} words, {len(hunks)} disagreements.\n",
                f"| # | {engines[0]} | {engines[1]} | wrong side |",
                "|---|---|---|---|",
            ]
            out += [f"| {i} | {a} | {b} | |" for i, (a, b) in enumerate(hunks, 1)]
            for engine, words in ((engines[0], a_words), (engines[1], b_words)):
                out.append(f"\n{engine} full text: {' '.join(words)}")
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description="Summarize M0 engine runs and sample windows.")
    parser.add_argument("run_dir", type=Path, help="directory with *.run.json files")
    parser.add_argument("--out", type=Path, required=True, help="markdown file to write")
    parser.add_argument("--audio-dir", type=Path, help="16 kHz wavs, enables the onset check")
    args = parser.parse_args()

    runs = load_runs(args.run_dir)
    if not runs:
        raise SystemExit(f"no *.run.json in {args.run_dir}")
    lines = ["# M0 comparison", "", *metrics_rows(runs)]
    lines += ["", "## Timing", "", *timing_rows(runs, args.audio_dir), "", "## Sampled windows"]
    lines += sample_tables(runs)
    args.out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    for audio, by_engine in sorted(runs.items()):
        for engine, engine_runs in sorted(by_engine.items()):
            for run in engine_runs:
                bad = timeline_violations(run["segments"])
                print(f"{audio} {engine}: exit={run['exit_code']} violations={len(bad)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
