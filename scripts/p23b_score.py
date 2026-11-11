"""P23b lever: score a language-tag output against the labels a person made by ear.

Inputs:
- the manifest from `p23b_sample.py` (strata and times),
- `labels.json` exported by the label page (labels `ja`, `en`, `both`, `unclear`),
- a tag file: a JSON list of `{"id": segment id, "tag": ...}`. The tag is `ja`, `en`, `both`
  (also `ja+en`, `mixed`), or `none` (also null or empty) when the engine wrote nothing. A list of
  tags such as `["ja", "en"]` means the subtitles of that segment carried both. A segment with no
  entry counts as `none`.

It prints the accuracy by stratum, the segments of 2 s or longer where English speech was written
as Japanese or dropped, and every exact disagreement. `unclear` labels are left out of the scores.

    uv run python scripts/p23b_score.py MANIFEST.json LABELS.json TAGS.json [--json OUT.json]
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, cast

LONG_ENOUGH_S = 2.0
ACCURACY_GATE = 0.98
BOTH_ALIASES = {"both", "ja+en", "en+ja", "mixed"}


@dataclass(frozen=True)
class Row:
    id: str
    stratum: str
    start_s: float
    duration_s: float
    truth: str
    tag: str
    note: str

    @property
    def correct(self) -> bool:
        return self.truth == self.tag

    @property
    def english_lost(self) -> bool:
        """English speech of 2 s or longer that the tag wrote as Japanese or dropped."""
        return (
            self.duration_s >= LONG_ENOUGH_S
            and self.truth in ("en", "both")
            and self.tag in ("ja", "none")
        )


def normalize_tag(raw: Any) -> str:
    if isinstance(raw, list):
        items: list[Any] = raw  # type: ignore[assignment]
        kinds = {normalize_tag(x) for x in items} - {"none"}
        if kinds >= {"ja", "en"} or "both" in kinds:
            return "both"
        return next(iter(kinds), "none")
    text = str(raw or "").strip().lower()
    if text in BOTH_ALIASES:
        return "both"
    return text if text in ("ja", "en") else "none"


def load_labels(path: Path) -> dict[str, dict[str, Any]]:
    data: Any = json.loads(path.read_text(encoding="utf-8"))
    rows = cast("list[dict[str, Any]]", data["labels"] if isinstance(data, dict) else data)
    return {r["id"]: r for r in rows}


def load_tags(path: Path) -> dict[str, str]:
    rows: list[dict[str, Any]] = json.loads(path.read_text(encoding="utf-8"))
    return {str(r.get("id", r.get("segment_id"))): normalize_tag(r.get("tag")) for r in rows}


def build_rows(
    manifest: dict[str, Any], labels: dict[str, dict[str, Any]], tags: dict[str, str]
) -> tuple[list[Row], list[str], list[str]]:
    """Scored rows, ids with no label, and ids the labeller marked unclear."""
    rows: list[Row] = []
    unlabelled: list[str] = []
    unclear: list[str] = []
    for seg in manifest["segments"]:
        label = labels.get(seg["id"], {}).get("label")
        if label is None:
            unlabelled.append(seg["id"])
        elif label == "unclear":
            unclear.append(seg["id"])
        else:
            rows.append(
                Row(
                    seg["id"],
                    seg["stratum"],
                    seg["start_s"],
                    seg["duration_s"],
                    label,
                    tags.get(seg["id"], "none"),
                    labels[seg["id"]].get("note", ""),
                )  # fmt: skip
            )
    return rows, unlabelled, unclear


def by_stratum(rows: list[Row]) -> dict[str, tuple[int, int]]:
    out: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    for r in rows:
        out[r.stratum][0] += 1
        out[r.stratum][1] += r.correct
    return {k: (v[0], v[1]) for k, v in sorted(out.items())}


def pct(correct: int, n: int) -> str:
    return f"{100 * correct / n:.1f}%" if n else "n/a"


def fmt_row(r: Row) -> str:
    note = f"  note: {r.note}" if r.note else ""
    where = f"{r.id}  {r.start_s:8.1f}s  {r.duration_s:5.1f}s  [{r.stratum}]"
    return f"  {where}  heard {r.truth}, tagged {r.tag}{note}"


def render(rows: list[Row], unlabelled: list[str], unclear: list[str], total: int) -> str:
    n, ok = len(rows), sum(r.correct for r in rows)
    lost = sorted((r for r in rows if r.english_lost), key=lambda r: r.start_s)
    wrong = sorted((r for r in rows if not r.correct), key=lambda r: r.start_s)
    out = [
        f"segments {total}: scored {n}, unclear {len(unclear)}, not labelled {len(unlabelled)}",
        f"language tag accuracy: {ok}/{n} = {pct(ok, n)}",
        "by stratum:",
    ]
    out += [f"  {k:12s} {c}/{m} = {pct(c, m)}" for k, (m, c) in by_stratum(rows).items()]
    out.append(
        f"English of {LONG_ENOUGH_S:g} s or longer written as Japanese or dropped: {len(lost)}"
    )
    out += [fmt_row(r) for r in lost]
    out.append(f"exact disagreements: {len(wrong)}")
    out += [fmt_row(r) for r in wrong]
    passed = n > 0 and ok / n >= ACCURACY_GATE and not lost
    out.append(
        f"P23b gate (accuracy >= {ACCURACY_GATE:.0%} and 0 lost English segments): "
        + ("PASS on this sample" if passed else "FAIL")
    )
    return "\n".join(out)


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("manifest", type=Path)
    ap.add_argument("labels", type=Path)
    ap.add_argument("tags", type=Path)
    ap.add_argument("--json", type=Path, help="also write the rows and the unlabelled ids here")
    args = ap.parse_args()
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    rows, unlabelled, unclear = build_rows(manifest, load_labels(args.labels), load_tags(args.tags))
    print(render(rows, unlabelled, unclear, len(manifest["segments"])))
    if args.json:
        payload = {"rows": [asdict(r) for r in rows], "unlabelled": unlabelled, "unclear": unclear}
        args.json.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
