"""Z0 E1/E2: character error rate, script and punctuation of the runs of `zh_z0_asr.py`.

    .work/zh-z0/venv-native/Scripts/python scripts/zh_z0_score.py w-zh q-zh q-zh-hant ...

Needs the `opencc` wheel (scratch environment, not a repository dependency) to compare script-free:
reference and hypothesis are both made Simplified by `t2s` before the edit distance, so a Traditional
output is not charged for its script. The raw CER (no conversion) is printed beside it.

Reference: the FLEURS `raw_transcription`, with parenthesised Latin glosses removed (the speaker
does not say them: `埃尔多安（Recep Tayyip Erdoğan）`). The comparison keeps letters and digits only.
`plain` is the subset whose reference holds no Latin letter or digit: Arabic digits and Chinese
numerals (2013 or 二零一三) are both right and count as errors against each other.
"""
# ruff: noqa: E501
# ruff: noqa: E501

from __future__ import annotations

import importlib
import json
import random
import re
import statistics
import sys
from collections import Counter
from collections.abc import Callable
from pathlib import Path
from typing import Any, cast

from zh_z0_text import (
    RUNS,
    edit_distance,
    is_han,
    keep_letters,
    load_utterances,
    percentile,
    read_json,
)

ROOT = Path(__file__).resolve().parents[1]
_GLOSS = re.compile(r"[（(][^（）()]*[）)]")
_ASCII_ALNUM = re.compile("[A-Za-z0-9]")
_PUNCT = re.compile("[，。、？！；：“”‘’「」『』《》（）,.?!;:\"']")
Convert = Callable[[str], str]


def converter(config: str) -> Convert:
    opencc = cast("Any", importlib.import_module("opencc"))
    return cast("Convert", opencc.OpenCC(config).convert)


def clean_reference(raw: str) -> str:
    def drop(match: re.Match[str]) -> str:
        return match.group(0) if any(is_han(c) for c in match.group(0)) else ""

    return _GLOSS.sub(drop, raw)


def markers() -> tuple[Convert, frozenset[str]]:
    sys.path.insert(0, str(ROOT))
    from backend.core.zh_tw import SIMPLIFIED_ONLY

    return converter("t2s"), SIMPLIFIED_ONLY


def script_of(text: str, t2s: Convert, simplified_only: frozenset[str]) -> tuple[int, int]:
    """(characters only Traditional writes, characters only Simplified writes). A character both
    scripts share (的, 我, 干) is in neither count."""
    traditional = sum(1 for c in text if is_han(c) and t2s(c) != c)
    simplified = sum(1 for c in text if c in simplified_only)
    return traditional, simplified


def score(tag: str) -> dict[str, Any]:
    run = cast("dict[str, Any]", read_json(RUNS / f"{tag}.json"))
    texts = cast("dict[str, str]", run["texts"])
    if run.get("wav_dir"):
        manifest = cast("dict[str, str]", read_json(Path(run["wav_dir"]) / "manifest.json"))
        refs = {key: clean_reference(text) for key, text in manifest.items()}
    else:
        refs = {u.key: clean_reference(u.raw) for u in load_utterances(run["audio_set"])}
    t2s, simplified_only = markers()
    total_ref = edits_free = edits_raw = 0
    plain_ref = plain_edits = 0
    per_utt: list[float] = []
    pairs: dict[str, tuple[int, int]] = {}
    trad = simp = punct = han = 0
    kinds: Counter[str] = Counter()
    long_outputs = empty = spaces = 0
    worst: list[tuple[float, str, str, str]] = []
    for key, hyp in texts.items():
        ref = refs[key]
        ref_free, hyp_free = keep_letters(t2s(ref)), keep_letters(t2s(hyp))
        ref_raw, hyp_raw = keep_letters(ref), keep_letters(hyp)
        e_free = edit_distance(ref_free, hyp_free)
        edits_free += e_free
        edits_raw += edit_distance(ref_raw, hyp_raw)
        total_ref += len(ref_free)
        per_utt.append(e_free / max(len(ref_free), 1))
        pairs[key] = (e_free, len(ref_free))
        if not _ASCII_ALNUM.search(ref):
            plain_ref += len(ref_free)
            plain_edits += e_free
        t, s = script_of(hyp, t2s, simplified_only)
        trad, simp = trad + t, simp + s
        kinds[
            "traditional"
            if t and not s
            else "simplified"
            if s and not t
            else "mixed"
            if t and s
            else "neutral"
        ] += 1
        punct += len(_PUNCT.findall(hyp))
        han += sum(1 for c in hyp if is_han(c))
        spaces += 1 if " " in hyp.strip() else 0
        empty += 1 if not hyp_free else 0
        long_outputs += 1 if len(hyp_free) > 2 * max(len(ref_free), 5) else 0
        worst.append((per_utt[-1], key, ref, hyp))
    worst.sort(reverse=True)
    n = len(texts)
    return {
        "tag": tag,
        "n": n,
        "ref_chars": total_ref,
        "cer_script_free": edits_free / total_ref,
        "cer_raw": edits_raw / total_ref,
        "cer_plain": plain_edits / max(plain_ref, 1),
        "plain_share_of_chars": plain_ref / total_ref,
        "utt_cer_p50": percentile(per_utt, 50),
        "utt_cer_p90": percentile(per_utt, 90),
        "utt_cer_mean": statistics.fmean(per_utt),
        "traditional_chars": trad,
        "simplified_chars": simp,
        "traditional_share": trad / max(trad + simp, 1),
        "utterance_script": dict(kinds),
        "punct_per_1000_han": 1000 * punct / max(han, 1),
        "with_spaces": spaces,
        "empty": empty,
        "over_long": long_outputs,
        "worst": [[round(c, 2), k, r, h] for c, k, r, h in worst[:5]],
        "pairs": pairs,
        "rtf": run["rtf"],
        "peak_over_baseline_mib": run["gpu"]["peak_over_baseline_mib"],
        "errors": len(run["errors"]),
    }


def bootstrap(a: dict[str, tuple[int, int]], b: dict[str, tuple[int, int]]) -> str:
    """The CER of `a` minus the CER of `b` over the utterances both have, with a 95% interval from
    2000 resamples of the utterances."""
    keys = sorted(set(a) & set(b))
    rng = random.Random(1)
    diffs: list[float] = []
    for _ in range(2000):
        pick = [keys[rng.randrange(len(keys))] for _ in keys]
        total = sum(a[k][1] for k in pick)
        diffs.append(sum(a[k][0] for k in pick) / total - sum(b[k][0] for k in pick) / total)
    diffs.sort()
    total = sum(a[k][1] for k in keys)
    mean = sum(a[k][0] for k in keys) / total - sum(b[k][0] for k in keys) / total
    return f"{mean:+.2%} (95% {diffs[50]:+.2%} to {diffs[1949]:+.2%}, {len(keys)} utterances)"


def main() -> int:
    if sys.argv[1] == "--pair":
        one, two = score(sys.argv[2]), score(sys.argv[3])
        print(f"CER {one['tag']} minus {two['tag']}: {bootstrap(one['pairs'], two['pairs'])}")
        return 0
    rows = [score(tag) for tag in sys.argv[1:]]
    print(
        "| run | n | CER script-free | CER raw | CER plain | utt p50 / p90 | Trad. share of marked chars "
        "| punct per 1000 | RTF | peak +MiB |"
    )
    print("|---|---|---|---|---|---|---|---|---|---|")
    for r in rows:
        print(
            f"| {r['tag']} | {r['n']} | {r['cer_script_free']:.2%} | {r['cer_raw']:.2%} | "
            f"{r['cer_plain']:.2%} | {r['utt_cer_p50']:.1%} / {r['utt_cer_p90']:.1%} | "
            f"{r['traditional_share']:.1%} | {r['punct_per_1000_han']:.0f} | {r['rtf']:.4f} | "
            f"{r['peak_over_baseline_mib']} |"
        )
    print()
    for r in rows:
        print(
            f"{r['tag']}: scripts {r['utterance_script']}, spaces {r['with_spaces']}, "
            f"empty {r['empty']}, over-long {r['over_long']}, errors {r['errors']}"
        )
    (RUNS / "scores.json").write_text(
        json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
