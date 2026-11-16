"""P25 lever: automatic checks on the output of `scripts/p25_ja_multilang.py`.

    python scripts/p25_check.py OUT            # prints the summary table, writes OUT/checks/*

Reads OUT/units.json, OUT/runs/<talk>/<route>.<target>.json, OUT/runs/timing.jsonl and, when it
exists, OUT/back/<route>.<target>.json. Writes:

- `summary.tsv`: one row per route and target. Counts over the sampled cues: empty, still the
  Japanese, a script problem (the registry check of the target language with the script required,
  and no kana), a marker `[[n]]` left in, units whose Arabic digits are missing from the output;
  the ratio of output characters to Japanese characters (median, 90th percentile); display columns
  per second against the 14 columns a second the Japanese rule allows (7 full-width characters) and
  the 17 of a Latin-script subtitle; cues over two lines of 40 columns; the units that say Perforce
  and the ones whose output says it; and, from the back-translation, the mean Dice overlap of the
  character bigrams and the mean 0 to 5 score the same model gave.
- `problems.tsv`: each failing cue as route, target, talk, cue id, problem (no talk text).
- `terms.tsv`: the output of each route for the units that hold a katakana term (Perforce,
  shelve, stream, branch, workflow), to read how each language writes it.
"""

from __future__ import annotations

import argparse
import json
import re
import statistics
import unicodedata
from collections import defaultdict
from collections.abc import Sequence
from pathlib import Path
from typing import cast

from backend.core.languages import Language, get
from backend.core.model import Cue
from backend.core.subtitle_io import parse_subs, read_text_file
from scripts.p25_ja_multilang import ROUTES, TALKS, english_target, flat_ja, sampled

_KANA = re.compile("[぀-ヿㇰ-ㇿｦ-ﾟ]")
_DIGITS = re.compile(r"\d+")
_MARKER = re.compile(r"\[\[\d+\]\]")
_VIETNAMESE = re.compile("[ăâđêôơưàáảãạằắẳẵặầấẩẫậèéẻẽẹềếểễệìíỉĩịòóỏõọồốổỗộờớởỡợùúủũụừứửữựỳýỷỹỵ]")
_PERFORCE_SAID = re.compile(
    "パワ?ー?フォ|パフォ|パーフォ|Perforce|パワーホース|PowerForce", re.IGNORECASE
)
TERMS = {
    "perforce": re.compile("パワ?ー?フォース|パフォ|パーフォ|パワーホース"),
    "shelve": re.compile("シェルブ|シェルフ|シェルヴ"),
    "stream": re.compile("ストリーム"),
    "branch": re.compile("ブランチ"),
    "workflow": re.compile("ワークフロー"),
}
JA_COLUMNS_PER_SECOND = 14.0
LATIN_CPS = 17.0
LINE_COLUMNS = 40


def columns(text: str) -> int:
    return sum(2 if unicodedata.east_asian_width(ch) in "WF" else 1 for ch in text)


def language(code: str) -> Language:
    return english_target() if code == "en" else get(code)


def problem_of(code: str, text: str) -> str | None:
    """What is wrong with one translated cue: the registry check, with the script required."""
    if _MARKER.search(text):
        return "marker left in"
    if _KANA.search(text):
        return "kana left in"
    if found := language(code).check(text, "", True):
        return found
    if code == "vi" and len(text.split()) > 3 and not _VIETNAMESE.search(text.lower()):
        return "no Vietnamese diacritics"
    return None


def percentile(values: Sequence[float], share: float) -> float:
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, int(share * len(ordered)))] if ordered else 0.0


def load_runs(out: Path) -> dict[tuple[str, str, str], list[Cue]]:
    runs: dict[tuple[str, str, str], list[Cue]] = {}
    for talk in TALKS:
        for path in sorted((out / "runs" / talk).glob("*.json")):
            route, _, rest = path.name.partition(".")
            if route in ROUTES:
                runs[(talk, route, rest.removesuffix(".json"))] = parse_subs(read_text_file(path))
    return runs


def check(out: Path) -> list[dict[str, object]]:
    runs = load_runs(out)
    sources = {
        talk: {c.id: c for c in parse_subs(read_text_file(path))}
        for talk, (path, _) in TALKS.items()
    }
    units = {talk: sampled(out, talk)[1] for talk in TALKS}
    back = {p.stem: cast("list[dict[str, object]]", json.loads(p.read_text(encoding="utf-8")))
            for p in (out / "back").glob("*.json")}  # fmt: skip
    problems: list[str] = []
    rows: list[dict[str, object]] = []
    keys = sorted({(r, t) for _, r, t in runs}, key=lambda k: (k[1] != "en", k[1], k[0]))
    for route, code in keys:
        stats: dict[str, list[float]] = defaultdict(list)
        count = {
            "cues": 0,
            "empty": 0,
            "still_ja": 0,
            "script": 0,
            "digits": 0,
            "perf_seen": 0,
            "perf_ok": 0,
        }
        for talk in TALKS:
            cues = runs.get((talk, route, code))
            if cues is None:
                continue
            said = {c.id: c for c in cues}
            for ids in units[talk]:
                src = sources[talk]
                ja_unit = flat_ja(list(src.values()), ids)
                out_unit = " ".join(said[i].zh for i in ids)
                missing = [d for d in _DIGITS.findall(ja_unit) if d not in out_unit]
                if missing:
                    count["digits"] += 1
                    problems.append(
                        f"{route}\t{code}\t{talk}\t{ids[0]}\tdigits {','.join(missing)} missing"
                    )
                if _PERFORCE_SAID.search(ja_unit):
                    count["perf_seen"] += 1
                    count["perf_ok"] += "perforce" in out_unit.lower()
                for i in ids:
                    cue, text = said[i], said[i].zh
                    count["cues"] += 1
                    ja = src[i].src.replace("\n", "")
                    if not text.strip():
                        count["empty"] += 1
                        problems.append(f"{route}\t{code}\t{talk}\t{i}\tempty")
                        continue
                    if text.replace("\n", "") == ja:
                        count["still_ja"] += 1
                        problems.append(f"{route}\t{code}\t{talk}\t{i}\tkept the Japanese")
                        continue
                    if found := problem_of(code, text):
                        count["script"] += 1
                        problems.append(f"{route}\t{code}\t{talk}\t{i}\t{found}")
                    seconds = max(cue.end_ms - cue.start_ms, 1) / 1000
                    stats["ratio"].append(len(text) / max(len(ja), 1))
                    stats["cps"].append(columns(text) / seconds)
                    stats["columns"].append(columns(text))
        row: dict[str, object] = {"route": route, "target": code, **count}
        row["ratio_med"] = round(statistics.median(stats["ratio"]), 2) if stats["ratio"] else 0
        row["ratio_p90"] = round(percentile(stats["ratio"], 0.9), 2)
        limit = JA_COLUMNS_PER_SECOND if code in ("zh-CN", "zh-TW", "ko", "th", "ru") else LATIN_CPS
        row["cps_med"] = round(statistics.median(stats["cps"]), 1) if stats["cps"] else 0
        row["cps_over"] = sum(v > limit for v in stats["cps"])
        row["cps_limit"] = limit
        row["over_two_lines"] = sum(v > 2 * LINE_COLUMNS for v in stats["columns"])
        rows_back = back.get(f"{route}.{code}", [])
        row["back_dice"] = (
            round(statistics.mean(cast("float", r["dice"]) for r in rows_back), 3)
            if rows_back
            else ""
        )
        row["back_judge"] = (
            round(statistics.mean(cast("int", r["judge"]) for r in rows_back), 2)
            if rows_back
            else ""
        )
        row["judge_ge4"] = sum(cast("int", r["judge"]) >= 4 for r in rows_back) if rows_back else ""
        rows.append(row)
    folder = out / "checks"
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "problems.tsv").write_text(
        "route\ttarget\ttalk\tcue\tproblem\n" + "\n".join(problems) + "\n", encoding="utf-8"
    )
    write_tsv(folder / "summary.tsv", rows)
    write_terms(out, runs, units, sources, folder / "terms.tsv")
    return rows


def write_tsv(path: Path, rows: Sequence[dict[str, object]]) -> None:
    head = list(rows[0])
    lines = ["\t".join(head)] + ["\t".join(str(r[k]) for k in head) for r in rows]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_terms(
    out: Path,
    runs: dict[tuple[str, str, str], list[Cue]],
    units: dict[str, list[list[int]]],
    sources: dict[str, dict[int, Cue]],
    path: Path,
) -> None:
    lines = ["term\ttalk\tunit\troute\ttarget\ttext"]
    for term, pattern in TERMS.items():
        for talk in TALKS:
            for ids in units[talk]:
                ja = "".join(sources[talk][i].src.replace("\n", "") for i in ids)
                if not pattern.search(ja):
                    continue
                lines.append(f"{term}\t{talk}\t{ids[0]}\tsource\tja\t{ja}")
                for (t, route, code), cues in sorted(runs.items(), key=lambda kv: kv[0][2]):
                    if t == talk:
                        said = {c.id: c.zh for c in cues}
                        text = " ".join(said[i] for i in ids)
                        lines.append(f"{term}\t{talk}\t{ids[0]}\t{route}\t{code}\t{text}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("out", type=Path)
    rows = check(parser.parse_args().out)
    print("\t".join(rows[0]))
    for r in rows:
        print("\t".join(str(v) for v in r.values()))


if __name__ == "__main__":
    main()
