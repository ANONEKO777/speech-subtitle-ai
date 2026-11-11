"""Katakana to Latin letters, for a name a translation left in kana after every retry.

A person's name or a title that the model will not write in Chinese is better as plain letters
than as Japanese text in a Chinese subtitle. This is the Hepburn romanisation without macrons:
a long vowel mark repeats nothing and a small tsu doubles the next consonant.
"""

from __future__ import annotations

import re

_BASE = {
    "ア": "a", "イ": "i", "ウ": "u", "エ": "e", "オ": "o",
    "カ": "ka", "キ": "ki", "ク": "ku", "ケ": "ke", "コ": "ko",
    "サ": "sa", "シ": "shi", "ス": "su", "セ": "se", "ソ": "so",
    "タ": "ta", "チ": "chi", "ツ": "tsu", "テ": "te", "ト": "to",
    "ナ": "na", "ニ": "ni", "ヌ": "nu", "ネ": "ne", "ノ": "no",
    "ハ": "ha", "ヒ": "hi", "フ": "fu", "ヘ": "he", "ホ": "ho",
    "マ": "ma", "ミ": "mi", "ム": "mu", "メ": "me", "モ": "mo",
    "ヤ": "ya", "ユ": "yu", "ヨ": "yo",
    "ラ": "ra", "リ": "ri", "ル": "ru", "レ": "re", "ロ": "ro",
    "ワ": "wa", "ヲ": "o", "ン": "n",
    "ガ": "ga", "ギ": "gi", "グ": "gu", "ゲ": "ge", "ゴ": "go",
    "ザ": "za", "ジ": "ji", "ズ": "zu", "ゼ": "ze", "ゾ": "zo",
    "ダ": "da", "ヂ": "ji", "ヅ": "zu", "デ": "de", "ド": "do",
    "バ": "ba", "ビ": "bi", "ブ": "bu", "ベ": "be", "ボ": "bo",
    "パ": "pa", "ピ": "pi", "プ": "pu", "ペ": "pe", "ポ": "po",
    "ヴ": "vu",
    "ァ": "a", "ィ": "i", "ゥ": "u", "ェ": "e", "ォ": "o",
    "ッ": "", "ー": "", "ヵ": "ka", "ヶ": "ke",
}  # fmt: skip
_SMALL_Y = {"ャ": "a", "ュ": "u", "ョ": "o"}
_PALATAL = {"キ": "ky", "ギ": "gy", "シ": "sh", "ジ": "j", "チ": "ch", "ニ": "ny", "ヒ": "hy",
            "ビ": "by", "ピ": "py", "ミ": "my", "リ": "ry", "ヂ": "j"}  # fmt: skip
_SMALL_VOWEL = {"ァ": "a", "ィ": "i", "ゥ": "u", "ェ": "e", "ォ": "o"}
_KATAKANA = re.compile("[ァ-ヺー]+")


def _romanize_run(run: str) -> str:
    out: list[str] = []
    double = False
    index = 0
    while index < len(run):
        char = run[index]
        following = run[index + 1] if index + 1 < len(run) else ""
        if char == "ッ":
            double = True
        elif char == "ー":
            pass
        elif following in _SMALL_Y and char in _PALATAL:
            out.append(_piece(_PALATAL[char] + _SMALL_Y[following], double))
            double, index = False, index + 1
        elif following in _SMALL_VOWEL and char in _BASE and _BASE[char][-1] in "aiueo":
            out.append(_piece(_BASE[char][:-1] + _SMALL_VOWEL[following], double))
            double, index = False, index + 1
        else:
            out.append(_piece(_BASE.get(char, ""), double))
            double = False
        index += 1
    return "".join(out)


def _piece(text: str, double: bool) -> str:
    return text[:1] + text if double and text[:1].isalpha() and text[:1] not in "aiueo" else text


def romanize_katakana(text: str) -> str:
    """`text` with every run of katakana written in Latin letters, capitalised like a name."""
    return _KATAKANA.sub(lambda m: _romanize_run(m.group()).capitalize(), text)
