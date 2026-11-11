"""P23b lever: pick the 120 Kirby segments a person labels by ear, stratified toward the hard cases.

The unit is the 300 ms pause cut of P22 (777 segments). It is the cut whose pieces the candidate
engine X would tag one by one, so a label on a piece scores the tag the engine would write. The
700 ms cut hides the 60 Japanese-then-English segments inside single segments and gives the
labeller a segment with two answers.

Strata, in the order a segment is claimed (a segment counts once, under the first stratum it fits):

- `disagree`: Whisper language ID and the Qwen3 `-l auto` script are Japanese or English and differ.
- `fragment`: Whisper heard Korean or Chinese, or Qwen3 wrote Korean letters over a Japanese guess.
- `ja_then_en`: a piece inside one of the 60 segments of the 700 ms cut where Qwen3 `-l auto` wrote
  only Japanese but Whisper heard English. Pieces of a group that stayed whole come first.
- `en_as_ja`: Whisper heard English and Qwen3 `-l ja` wrote Japanese, at 2 s or longer.
- `ordinary_ja` and `ordinary_en`: random fill of segments no hard-case rule claims.

The two model guesses go into the manifest under `guesses`. The label page never reads them.

    uv run python scripts/p23b_sample.py [--runs RUNS_DIR] [--out MANIFEST.json] [--seed N]
"""

from __future__ import annotations

import argparse
import json
import random
import sys
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from p22_langmap import load_chunks
from p22_langscore import group_of, script_of, segments

DEFAULT_RUNS = Path(
    "C:/Users/abcd1997/.claude/orchestrate/video-subtitle-translator/swarm/P22/runs"
)
DEFAULT_OUT = Path(__file__).resolve().parents[1] / ".work/p23b-labels/manifest.json"
FINE_TAG = "fine300"
TOTAL = 120
QUOTAS = {"disagree": 14, "fragment": 14, "ja_then_en": 32, "en_as_ja": 20}
MAX_SEGMENT_MS = 30_000
MIN_SPLIT_PART_MS = 1_000
LONG_ENOUGH_MS = 2_000
ORDINARY_MIN_MS = 1_500


@dataclass(frozen=True)
class Segment:
    id: str
    index: int
    start_ms: int
    end_ms: int
    whisper_lid: str | None
    qwen_auto_script: str
    qwen_ja_script: str
    parent700: int | None
    gaps: tuple[tuple[int, int], ...]

    @property
    def duration_ms(self) -> int:
        return self.end_ms - self.start_ms


def split_at_largest_pause(seg: Segment) -> list[Segment]:
    """Cut a segment longer than 30 s at its largest internal pause, then recurse on the halves."""
    if seg.duration_ms <= MAX_SEGMENT_MS:
        return [seg]
    inside = [
        g
        for g in seg.gaps
        if seg.start_ms + MIN_SPLIT_PART_MS <= g[0] and g[1] <= seg.end_ms - MIN_SPLIT_PART_MS
    ]
    if inside:
        a, b = max(inside, key=lambda g: g[1] - g[0])
        cut_end, cut_start = a, b
    else:
        cut_end = cut_start = (seg.start_ms + seg.end_ms) // 2
    left = Segment(
        f"{seg.id}a", seg.index, seg.start_ms, cut_end, seg.whisper_lid, seg.qwen_auto_script,
        seg.qwen_ja_script, seg.parent700, tuple(g for g in seg.gaps if g[1] <= cut_end),
    )  # fmt: skip
    right = Segment(
        f"{seg.id}b", seg.index, cut_start, seg.end_ms, seg.whisper_lid, seg.qwen_auto_script,
        seg.qwen_ja_script, seg.parent700, tuple(g for g in seg.gaps if g[0] >= cut_start),
    )  # fmt: skip
    return [*split_at_largest_pause(left), *split_at_largest_pause(right)]


def unit_gaps(chunk: dict[str, Any]) -> tuple[tuple[int, int], ...]:
    """Pauses between consecutive timed units of a chunk, in absolute milliseconds."""
    base = chunk["start_ms"]
    spans = sorted(
        (base + u["start_ms"], base + u["end_ms"]) for s in chunk["segments"] for u in s["units"]
    )
    return tuple((a[1], b[0]) for a, b in zip(spans, spans[1:], strict=False) if b[0] > a[1])


def load_segments(runs: Path) -> list[Segment]:
    coarse = segments(runs)
    fine = segments(runs, FINE_TAG)
    chunks = load_chunks(runs / f"whisper-kirby-chunks-auto-{FINE_TAG}.json")
    groups = [r for r in coarse if group_of(r) == "ja_then_en"]
    out: list[Segment] = []
    for k, (row, chunk) in enumerate(zip(fine, chunks, strict=True)):
        mid = (row["start_ms"] + row["end_ms"]) // 2
        parent = next((i for i, g in enumerate(groups) if g["start_ms"] <= mid < g["end_ms"]), None)
        out.append(
            Segment(
                f"s{k:04d}",
                k,
                row["start_ms"],
                row["end_ms"],
                row["lid"],
                script_of(row["qwen_auto"]),
                script_of(row["qwen_ja"]),
                parent,
                unit_gaps(chunk),
            )  # fmt: skip
        )
    return [part for seg in out for part in split_at_largest_pause(seg)]


def is_disagree(s: Segment) -> bool:
    return (
        s.whisper_lid in ("ja", "en")
        and s.qwen_auto_script in ("ja", "en")
        and (s.whisper_lid != s.qwen_auto_script)
    )


def is_fragment(s: Segment) -> bool:
    return s.whisper_lid in ("ko", "zh") or (s.whisper_lid == "ja" and s.qwen_auto_script == "none")


def is_en_as_ja(s: Segment) -> bool:
    return s.whisper_lid == "en" and s.qwen_ja_script == "ja" and s.duration_ms >= LONG_ENOUGH_MS


def is_ordinary(s: Segment, lang: str) -> bool:
    return (
        s.whisper_lid == lang
        and s.qwen_auto_script == lang
        and s.parent700 is None
        and not is_en_as_ja(s)
        and s.duration_ms >= ORDINARY_MIN_MS
    )


def pick_ja_then_en(pool: list[Segment], quota: int, rng: random.Random) -> list[Segment]:
    """One piece per group: whole groups first, then the longest piece Whisper heard as English."""
    by_group: dict[int, list[Segment]] = {}
    for s in pool:
        if s.parent700 is not None:
            by_group.setdefault(s.parent700, []).append(s)
    keys = sorted(by_group)
    rng.shuffle(keys)
    keys.sort(key=lambda k: len(by_group[k]) != 1)
    chosen: list[Segment] = []
    for k in keys:
        if len(chosen) == quota:
            break
        best = max(
            by_group[k],
            key=lambda s: (s.whisper_lid == "en", s.duration_ms >= LONG_ENOUGH_MS, s.duration_ms),
        )
        chosen.append(best)
    return chosen


def draw(pool: list[Segment], count: int, rng: random.Random) -> list[Segment]:
    pool = list(pool)
    rng.shuffle(pool)
    return pool[:count]


def select(all_segments: list[Segment], seed: int) -> list[tuple[str, Segment]]:
    rng = random.Random(seed)
    taken: dict[str, tuple[str, Segment]] = {}

    def claim(stratum: str, picks: list[Segment]) -> None:
        for s in picks:
            taken[s.id] = (stratum, s)

    def free(pred: Any) -> list[Segment]:
        return [s for s in all_segments if s.id not in taken and pred(s)]

    claim("disagree", draw(free(is_disagree), QUOTAS["disagree"], rng))
    claim("fragment", draw(free(is_fragment), QUOTAS["fragment"], rng))
    claim(
        "ja_then_en",
        pick_ja_then_en(free(lambda s: s.parent700 is not None), QUOTAS["ja_then_en"], rng),
    )
    claim("en_as_ja", draw(free(is_en_as_ja), QUOTAS["en_as_ja"], rng))
    rest = TOTAL - len(taken)
    claim("ordinary_ja", draw(free(lambda s: is_ordinary(s, "ja")), rest // 2, rng))
    claim("ordinary_en", draw(free(lambda s: is_ordinary(s, "en")), TOTAL - len(taken), rng))
    return sorted(taken.values(), key=lambda t: t[1].start_ms)


def flags(s: Segment) -> list[str]:
    named = {
        "disagree": is_disagree(s),
        "fragment": is_fragment(s),
        "ja_then_en": s.parent700 is not None,
        "en_as_ja": s.whisper_lid == "en" and s.qwen_ja_script == "ja",
    }
    return [k for k, v in named.items() if v]


def build_manifest(picks: list[tuple[str, Segment]], seed: int) -> dict[str, Any]:
    order = list(range(len(picks)))
    random.Random(seed + 1).shuffle(order)
    position = {i: p + 1 for p, i in enumerate(order)}
    entries = [
        {
            "id": s.id,
            "start_s": s.start_ms / 1000,
            "end_s": s.end_ms / 1000,
            "duration_s": round(s.duration_ms / 1000, 3),
            "stratum": stratum,
            "also_matches": [f for f in flags(s) if f != stratum],
            "split_from_index": s.index if s.id[-1] in "ab" else None,
            "parent700_group": s.parent700,
            "position": position[i],
            "guesses": {
                "whisper_lid": s.whisper_lid,
                "qwen3_auto_script": s.qwen_auto_script,
                "qwen3_ja_script": s.qwen_ja_script,
            },
        }
        for i, (stratum, s) in enumerate(picks)
    ]
    entries.sort(key=lambda e: e["position"])
    return {
        "version": 1,
        "seed": seed,
        "unit": "P22 300 ms pause cut, 777 segments",
        "note": "guesses and strata are for scoring only and are never shown to the labeller",
        "segments": entries,
    }


def report(manifest: dict[str, Any]) -> str:
    segs = manifest["segments"]
    primary = Counter(e["stratum"] for e in segs)
    also: Counter[str] = Counter()
    for e in segs:
        also.update(
            [e["stratum"], *e["also_matches"]] if e["stratum"] in QUOTAS else e["also_matches"]
        )
    seconds = sum(e["duration_s"] for e in segs)
    lines = [
        f"{len(segs)} segments, {seconds / 60:.1f} min of speech (without the 0.3 s lead and tail)"
    ]
    lines += [f"  {k}: {primary.get(k, 0)}" for k in [*QUOTAS, "ordinary_ja", "ordinary_en"]]
    lines.append(
        "segments that fit a hard-case rule, whatever stratum claimed them: "
        + ", ".join(f"{k} {also.get(k, 0)}" for k in QUOTAS)
    )
    durs = sorted(e["duration_s"] for e in segs)
    lines.append(
        f"duration min {durs[0]:.2f} s, median {durs[len(durs) // 2]:.2f} s, max {durs[-1]:.2f} s"
    )
    return "\n".join(lines)


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--runs", type=Path, default=DEFAULT_RUNS)
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    ap.add_argument("--seed", type=int, default=23)
    args = ap.parse_args()
    manifest = build_manifest(select(load_segments(args.runs), args.seed), args.seed)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(manifest, ensure_ascii=False, indent=1), encoding="utf-8")
    print(report(manifest))
    print(f"wrote {args.out}")


if __name__ == "__main__":
    main()
