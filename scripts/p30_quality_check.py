"""P30 lever: automatic checks on the Chinese a Japanese talk was translated into.

    uv run python scripts/p30_quality_check.py TRANSLATED.json [MORE.json ...] [--json out.json]
        [--windows eval.json]

Each file is a translated cue file (`subs.zh-TW.json`); only its Japanese cues are looked at. One
column of counts is printed per file. With `--windows` (the evaluation set), the counts are made
over the windows of the file's run only. The checks:

- numbers: a number in the Japanese (digits, read across cue borders) appears in the Chinese of the
  cues around it, as digits or as number words; a number the cue border cuts in two in the source;
  a Chinese cue that ends in the first half of a number.
- file wording: cues that write ファイル as 文件 and not 檔案, and the total of each in the run.
- Mainland wording: cues the Taiwan wording step would still change (`scripts/p23a_check.py`).
- fragment endings: a cue whose Chinese ends on a word that needs a continuation (的, 和, 與, ...).
- length: a cue whose Chinese is more than 2.5 times as long as its Japanese, which an added clause
  causes; and cues whose Chinese is under 0.25 or over 1.3 times its Japanese (a typical cue is
  0.6), which is how a sentence put one cue out of place shows.
- a Chinese cue that starts with punctuation: the sentence it finishes was put in the cue before.
- kana left in the Chinese.
- glossary: for each term of `backend.core.ja_terms`, the cues that have the Japanese term and
  whose Chinese has the Taiwan form and none of the wrong ones. The translation prompt reads the
  same table, so this count shows that the model follows the prompt and does not show that the
  table is right (marked `*` in the printout).
- words the table does not name: cues with a Mainland word the table has no line for, a simplified
  character, the product name written as something other than Perforce, a product that stays in
  Latin letters written with a Chinese word in it (Claude Code as Claude程式碼), the plug-in
  written 外掛程式 where the prompt asks for 外掛, and the Japanese word for demo or access written
  as the Mainland word. These do not depend on the prompt.

Run it from the checkout it checks, or with `PYTHONPATH` set to it: it imports `backend.core` from
whichever checkout Python finds first, and an editable install of another checkout answers silently.

Exit code is 0: this reports, the judge is a person.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import re
import sys
from collections.abc import Sequence
from pathlib import Path
from types import ModuleType

from backend.core.ja_terms import JA_TERMS
from backend.core.model import Cue
from backend.core.source_langs import JAPANESE_SOURCE
from backend.core.subtitle_io import parse_subs, read_text_file
from backend.core.zh_tw import simplified_chars

_NUMBER = re.compile(r"\d+(?:[.,]\d+)*")
_DANGLING_END = re.compile(r"[的和與及在對將把但並而由向從為以之或讓使跟同比被給]\Z")
_DIGITS = "〇一二三四五六七八九"
NOT_IN_THE_TABLE = ("硬件", "演示", "訪問", "視頻", "信息", "屏幕", "打印", "文檔")
"""Mainland words that no line of the table names and that the Taiwan wording step may leave."""
PRODUCT_WRONG = re.compile(r"Power ?[Ff]orce|PowerHorse|BIFFO|Biffo|Pforce")
PRODUCT_TRANSLATED = re.compile(
    r"(?i:Claude|Visual ?Studio|VS|GitHub) ?(?:程式碼|代碼|碼)(?!庫)|克勞德|副駕駛|協同駕駛"
    r"|聊天 ?GPT|對話 ?GPT"
)
"""A Chinese rendering inside the name of a product that stays in Latin letters (Claude Code
written Claude程式碼, Copilot written 副駕駛). The patterns do not come from the term table."""
CLOUD_FOR_CLAUDE = re.compile(r"(?<![A-Za-z])Cloud(?![A-Za-z])")
PLUGIN_LONG_FORM = re.compile("外掛程式(?!碼|庫|設計|架構|介面|語言|開發|編寫|撰寫)")
CIRCULAR = frozenset({"glossary_cues_right", "glossary_cues_seen"})
LENGTH_LIMIT = 2.5
LOW_RATIO = 0.25
HIGH_RATIO = 1.3
MIN_SOURCE_CHARS = 6


def _p23a() -> ModuleType:
    path = Path(__file__).with_name("p23a_check.py")
    spec = importlib.util.spec_from_file_location("p23a_check", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["p23a_check"] = module
    spec.loader.exec_module(module)
    return module


def number_words(digits: str) -> list[str]:
    """How an integer below 100000 is written in Chinese numerals, in the common ways."""
    if not digits.isdigit() or len(digits) > 5:
        return []
    if digits == "2":
        return ["二", "兩", "雙"]
    value = int(digits)
    spelled = "".join(_DIGITS[int(d)] for d in digits)
    forms = {spelled}
    units = ("", "十", "百", "千", "萬")
    out = ""
    zero = False
    for place, char in enumerate(digits):
        d = int(char)
        unit = units[len(digits) - 1 - place]
        if d == 0:
            zero = bool(out)
            continue
        if zero:
            out += "零"
            zero = False
        out += ("" if d == 1 and unit == "十" and place == 0 else _DIGITS[d]) + unit
    forms.add(out)
    if value >= 10:
        forms.add(
            out.replace("二", "兩", 1) if out.startswith("二百") or out.startswith("二千") else out
        )
    return sorted(f for f in forms if f)


def number_found(token: str, zh: str) -> bool:
    plain = token.replace(",", "")
    flat = zh.replace(",", "")
    if plain in flat:
        return True
    whole = plain.split(".")[0]
    return plain == whole and any(word in zh for word in number_words(whole))


def numbers(cues: Sequence[Cue]) -> dict[str, int]:
    """Count the numbers of the Japanese read as one stream over each run of consecutive cues."""
    total = intact = split = split_intact = zh_cut = in_place = 0
    for index, cue in enumerate(cues):
        nxt = cues[index + 1] if index + 1 < len(cues) else None
        if nxt is not None and re.search(r"\d[.,]\Z", cue.zh.rstrip()) and nxt.zh[:1].isdigit():
            zh_cut += 1
    stream = ""
    owner: list[int] = []
    for index, cue in enumerate(cues):
        flat = cue.src.replace("\n", "")
        stream += flat
        owner += [index] * len(flat)
    for match in _NUMBER.finditer(stream):
        first, last = owner[match.start()], owner[match.end() - 1]
        around = "".join(c.zh for c in cues[max(0, first - 1) : last + 2])
        total += 1
        in_place += any(number_found(match.group(), c.zh) for c in cues[first : last + 1])
        if first != last:
            split += 1
            split_intact += any(
                number_found(match.group(), c.zh) for c in cues[max(0, first - 1) : last + 2]
            )
        else:
            intact += number_found(match.group(), around)
    return {
        "numbers": total,
        "numbers_intact": intact + split_intact,
        "numbers_intact_in_own_cue": in_place,
        "numbers_cut_by_a_cue_border": split,
        "cut_numbers_whole_in_one_zh_cue": split_intact,
        "zh_cues_ending_in_half_a_number": zh_cut,
    }


def glossary(cues: Sequence[Cue]) -> dict[str, tuple[int, int]]:
    result: dict[str, tuple[int, int]] = {}
    for term in JA_TERMS:
        hits = [c for c in cues if term.in_source(c.src)]
        right = sum(1 for c in hits if term.kept_in(c.zh))
        result[term.said] = (right, len(hits))
    return result


def not_in_the_table(cues: Sequence[Cue]) -> dict[str, int]:
    """Counts that read no term of the table, so the prompt cannot have taught the model them."""
    return {
        "mainland_words_not_in_table_cues": sum(
            1 for c in cues if any(word in c.zh for word in NOT_IN_THE_TABLE)
        ),
        "simplified_char_cues": sum(1 for c in cues if simplified_chars(c.zh) or "万" in c.zh),
        "visit_word_for_access_cues": sum(
            1 for c in cues if "アクセス" in c.src.replace("\n", "") and "訪問" in c.zh
        ),
        "demo_written_yanshi_cues": sum(
            1 for c in cues if "デモ" in c.src.replace("\n", "") and "演示" in c.zh
        ),
        "product_name_wrong_cues": sum(1 for c in cues if PRODUCT_WRONG.search(c.zh)),
        "product_name_translated_cues": sum(
            1
            for c in cues
            if PRODUCT_TRANSLATED.search(c.zh)
            or ("クロード" in c.src.replace("\n", "") and CLOUD_FOR_CLAUDE.search(c.zh))
        ),
        "plugin_written_long_form_cues": sum(1 for c in cues if PLUGIN_LONG_FORM.search(c.zh)),
        "product_name_perforce_cues": sum(1 for c in cues if "Perforce" in c.zh),
    }


def check(cues: Sequence[Cue]) -> tuple[dict[str, float], dict[str, str]]:
    p23a = _p23a()
    mainland = p23a.has_mainland_wording
    ja = [c for c in cues if c.lang == "ja" and c.zh]
    file_cues = [c for c in ja if "ファイル" in c.src.replace("\n", "")]
    ratios = [
        len(re.sub(r"\W", "", c.zh)) / max(len(re.sub(r"\W", "", c.src)), 1)
        for c in ja
        if len(re.sub(r"\W", "", c.src)) >= MIN_SOURCE_CHARS
    ]
    gloss = glossary(ja)
    right = sum(r for r, _ in gloss.values())
    seen = sum(n for _, n in gloss.values())
    counts = {
        "cues": len(ja),
        **numbers(ja),
        "file_cues": len(file_cues),
        "file_cues_written_as_wenjian": sum(
            1 for c in file_cues if "文件" in c.zh and "檔案" not in c.zh
        ),
        "wenjian_in_run": sum(c.zh.count("文件") for c in ja),
        "dangan_in_run": sum(c.zh.count("檔案") for c in ja),
        "mainland_wording_cues": sum(1 for c in ja if mainland(c.zh)),
        "fragment_ending_cues": sum(1 for c in ja if _DANGLING_END.search(c.zh.rstrip("，、 "))),
        "length_over_2.5x": sum(1 for r in ratios if r > LENGTH_LIMIT),
        "length_ratio_extremes": sum(1 for r in ratios if r < LOW_RATIO or r > HIGH_RATIO),
        "zh_cues_starting_with_punctuation": sum(
            1 for c in ja if re.match(r"[，。、；：！？]", c.zh.lstrip())
        ),
        "length_ratio_mean": round(sum(ratios) / max(len(ratios), 1), 3),
        **not_in_the_table(ja),
        "kana_left_cues": sum(1 for c in ja if JAPANESE_SOURCE.problem(c.zh)),
        "glossary_cues_right": right,
        "glossary_cues_seen": seen,
    }
    return counts, {term: f"{r}/{n}" for term, (r, n) in gloss.items() if n}


def within(cues: Sequence[Cue], windows: Sequence[dict[str, object]], run: str) -> list[Cue]:
    spans = [(int(str(w["t0"])), int(str(w["t1"]))) for w in windows if w["run"] == run]
    return [c for c in cues if any(t0 <= c.start_ms and c.end_ms <= t1 + 1 for t0, t1 in spans)]


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("files", nargs="+", type=Path)
    parser.add_argument("--json", type=Path)
    parser.add_argument("--windows", type=Path)
    parser.add_argument("--run", default="")
    args = parser.parse_args(argv)
    windows = json.loads(args.windows.read_text(encoding="utf-8")) if args.windows else None
    counts: dict[str, dict[str, float]] = {}
    terms_seen: dict[str, dict[str, str]] = {}
    for path in args.files:
        cues = parse_subs(read_text_file(path))
        if windows is not None:
            cues = within(cues, windows, args.run)
        counts[path.name], terms_seen[path.name] = check(cues)
    names = list(counts)
    print(f"{'check':<36}" + "".join(f"{n[:22]:>24}" for n in names))
    for key in counts[names[0]]:
        label = f"{key}{'*' if key in CIRCULAR else ''}"
        print(f"{label:<36}" + "".join(f"{counts[n][key]!s:>24}" for n in names))
    print("* circular: the prompt and the check read the same table")
    print("glossary (cues right / cues with the term)")
    for term in sorted({t for n in names for t in terms_seen[n]}):
        print(f"{term:<36}" + "".join(f"{terms_seen[n].get(term, '-'):>24}" for n in names))
    if args.json:
        report = {n: {**counts[n], "glossary": terms_seen[n]} for n in names}
        args.json.write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
