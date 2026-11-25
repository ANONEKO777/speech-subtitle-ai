"""Z0 E2: what the converter candidates do to real recognised text.

    .work/zh-z0/venv-native/Scripts/python scripts/zh_z0_asr_convert.py q-auto w-zh

For the text of each run (Simplified, as the engines write it) it counts the utterances that the
character configuration `s2tw` changes beyond plain `s2t` (variant characters), the utterances that
`s2twp` changes beyond `s2tw` (wording: terms are replaced), and the places where the converters
disagree, which is where a one-to-many character is decided. Reading the disagreements is the
quality check there is: the references are Simplified, so the converted text has no ground truth.
"""
# ruff: noqa: E501
# ruff: noqa: E501

from __future__ import annotations

import difflib
import importlib
import sys
from collections import Counter
from collections.abc import Callable
from typing import Any, cast

from zh_z0_text import RUNS, read_json

Convert = Callable[[str], str]
AMBIGUOUS = "发后干里面布只台范复制志获钟周云向系冲松征占"


def opencc(config: str) -> Convert:
    return cast("Convert", cast("Any", importlib.import_module("opencc")).OpenCC(config).convert)


def purepy(config: str) -> Convert:
    module = cast("Any", importlib.import_module("opencc_purepy"))
    return cast("Convert", module.OpenCC(config).convert)


def zhconv(variant: str) -> Convert:
    module = cast("Any", importlib.import_module("zhconv_rs"))
    return lambda text: cast("str", module.zhconv(text, variant))


def diffs(a: str, b: str) -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []
    for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(None, a, b, autojunk=False).get_opcodes():
        if tag != "equal":
            out.append((a[i1:i2], b[j1:j2]))
    return out


def main() -> int:
    s2t, s2tw, s2twp = opencc("s2t"), opencc("s2tw"), opencc("s2twp")
    pure, rust = purepy("s2t"), zhconv("zh-hant")
    for tag in sys.argv[1:]:
        run = cast("dict[str, Any]", read_json(RUNS / f"{tag}.json"))
        texts = [t for t in cast("dict[str, str]", run["texts"]).values() if t.strip()]
        chars = sum(len(t) for t in texts)
        variant = sum(1 for t in texts if s2t(t) != s2tw(t))
        wording = sum(1 for t in texts if s2tw(t) != s2twp(t))
        ambiguous = sum(1 for t in texts for c in t if c in AMBIGUOUS)
        word_changes: Counter[tuple[str, str]] = Counter()
        variant_changes: Counter[tuple[str, str]] = Counter()
        disagree: Counter[tuple[str, str, str]] = Counter()
        examples: list[str] = []
        for t in texts:
            word_changes.update(diffs(s2tw(t), s2twp(t)))
            variant_changes.update(diffs(s2t(t), s2tw(t)))
            outs = {"opencc-s2tw": s2tw(t), "purepy-s2t": pure(t), "zhconv-hant": rust(t)}
            if len(set(outs.values())) > 1:
                for x, y in diffs(outs["opencc-s2tw"], outs["zhconv-hant"]):
                    disagree[("s2tw vs zhconv", x, y)] += 1
                for x, y in diffs(outs["opencc-s2tw"], outs["purepy-s2t"]):
                    disagree[("s2tw vs purepy", x, y)] += 1
                if len(examples) < 8:
                    examples.append(" | ".join(f"{k}: {v}" for k, v in outs.items()))
        print(f"\n## {tag}: {len(texts)} utterances, {chars} characters")
        print(
            f"- utterances changed by s2tw beyond s2t (variant characters): {variant} ({variant / len(texts):.1%})"
        )
        print(
            f"- utterances changed by s2twp beyond s2tw (wording replaced): {wording} ({wording / len(texts):.1%})"
        )
        print(
            f"- ambiguous Simplified characters in the text: {ambiguous} ({1000 * ambiguous / chars:.1f} per 1000)"
        )
        print(
            "- top variant changes s2t -> s2tw:",
            ", ".join(f"{a}->{b} x{n}" for (a, b), n in variant_changes.most_common(10)),
        )
        print(
            "- top wording changes s2tw -> s2twp:",
            ", ".join(f"{a}->{b} x{n}" for (a, b), n in word_changes.most_common(12)),
        )
        print(
            "- top disagreements:",
            ", ".join(f"[{k}] {a}->{b} x{n}" for (k, a, b), n in disagree.most_common(14)),
        )
        for e in examples:
            print("  ", e)
    return 0


if __name__ == "__main__":
    sys.exit(main())
