"""Text, paths and FLEURS manifests for the Z0 scripts. `ZH_Z0_DATA` names the data folder and
`ZH_Z0_WORK` the work folder; the default is `<main checkout>/.work/zh-z0` found from any worktree.
No engine imports, so a scratch
environment that only holds a converter package can run the scoring scripts."""

from __future__ import annotations

import csv
import json
import os
import unicodedata
import wave
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT.parents[1] if ROOT.parent.name == ".worktrees" else ROOT
WORK = Path(os.environ.get("ZH_Z0_WORK") or MAIN / ".work" / "zh-z0")
DATA = Path(os.environ.get("ZH_Z0_DATA") or WORK / "data")
RUNS = WORK / "runs"
FLEURS_LANGS = {"zh": "cmn_hans_cn", "ja": "ja_jp", "ko": "ko_kr", "en": "en_us"}
SAMPLE_RATE = 16000


def wav_seconds(path: Path) -> float:
    with wave.open(str(path), "rb") as reader:
        return reader.getnframes() / reader.getframerate()


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=1), encoding="utf-8")


@dataclass(frozen=True, slots=True)
class Utterance:
    """One FLEURS test utterance."""

    key: str
    lang: str
    wav: Path
    raw: str
    seconds: float
    gender: str


def load_utterances(lang: str) -> list[Utterance]:
    """The utterances the data step extracted, in file order of the dataset's `test.tsv`."""
    manifest = DATA / FLEURS_LANGS[lang] / "manifest.json"
    rows = cast("list[dict[str, Any]]", read_json(manifest))
    return [
        Utterance(
            str(r["key"]),
            lang,
            DATA / FLEURS_LANGS[lang] / "pcm" / str(r["file"]),
            str(r["raw"]),
            float(r["seconds"]),
            str(r["gender"]),
        )
        for r in rows
    ]


def read_tsv(path: Path) -> list[list[str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.reader(handle, delimiter="\t", quoting=csv.QUOTE_NONE))


def nfkc(text: str) -> str:
    return unicodedata.normalize("NFKC", text)


def keep_letters(text: str) -> str:
    """The text a CER compares: NFKC, lower case, letters and digits only (no punctuation or
    spaces), because the references and the engines punctuate differently."""
    return "".join(ch for ch in nfkc(text).casefold() if unicodedata.category(ch)[0] in "LN")


def edit_distance(a: str, b: str) -> int:
    if not a:
        return len(b)
    if not b:
        return len(a)
    previous = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        current = [i]
        for j, cb in enumerate(b, 1):
            current.append(min(previous[j] + 1, current[j - 1] + 1, previous[j - 1] + (ca != cb)))
        previous = current
    return previous[-1]


def is_han(ch: str) -> bool:
    return "㐀" <= ch <= "鿿" or "豈" <= ch <= "﫿"


def percentile(values: Sequence[float], q: float) -> float:
    """Nearest-rank percentile, `q` in 0..100."""
    ordered = sorted(values)
    if not ordered:
        return 0.0
    rank = max(1, min(len(ordered), round(q / 100 * len(ordered) + 0.4999999)))
    return ordered[rank - 1]
