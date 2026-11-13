"""Cue breaking for a language written without spaces between words (Japanese).

Whisper gives Japanese as subword tokens of one or two characters, and no word boundaries, so a
cue may only be cut where a person would cut it. Without a morphological analyser the places are
guessed from the script of the two characters on either side of the cut and from the endings that
end a clause. A cut inside a run of kanji, a run of katakana, or a hiragana run is allowed only at
a high cost, so it happens only when nothing better fits. Widths are display columns: a full-width
character is two, so a line of 20 full-width characters is 40 columns.
"""

from __future__ import annotations

import unicodedata
from collections.abc import Sequence

from backend.core.model import Word

SENTENCE_END = "。！？!?…"
CLAUSE_END = "、，,"
CLOSERS = "」』）〕】）)\"'”’"
OPENERS = "「『（〔【(“‘"
_NO_LINE_START = frozenset(
    "、。，．！？!?:;・…ー」』）〕】)ぁぃぅぇぉっゃゅょゎァィゥェォッャュョヮヵヶ々"
)
_PARTICLES = frozenset("はがをにでともへやてのか")
_ENDINGS = (
    "ます",
    "です",
    "ました",
    "でした",
    "ません",
    "ない",
    "ので",
    "から",
    "けど",
    "けれど",
    "ですが",
    "ますが",
    "ですので",
    "ますので",
    "でして",
    "まして",
    "ており",
    "ている",
    "ですね",
    "ますね",
    "ください",
    "ましょう",
    "ありまして",
    "おりまして",
    "ております",
)
_FORBIDDEN = 50.0
_NUMBER_MARKS = ".,"
_INSIDE_WORD = 9.0

HIRAGANA = "hiragana"
KATAKANA = "katakana"
KANJI = "kanji"
LATIN = "latin"
OTHER = "other"


def script(char: str) -> str:
    code = ord(char)
    if 0x3041 <= code <= 0x309F:
        return HIRAGANA
    if 0x30A1 <= code <= 0x30FF or 0xFF66 <= code <= 0xFF9F:
        return KATAKANA
    if 0x4E00 <= code <= 0x9FFF or 0x3400 <= code <= 0x4DBF or 0xF900 <= code <= 0xFAFF:
        return KANJI
    if char.isascii() and char.isalnum():
        return LATIN
    return OTHER


def columns(text: str) -> int:
    """Display columns of `text`: two for a full-width character, one for a half-width one."""
    return sum(
        0
        if unicodedata.category(char) in ("Mn", "Me", "Cf")
        else 2
        if unicodedata.east_asian_width(char) in "WF"
        else 1
        for char in text
    )


def joint(before: str, after: str) -> int:
    """Columns of the space two neighbouring words are joined with: a space only between two
    Latin words, at least one of them more than a single letter. Single letters are how an
    aligner gives the characters of one word."""
    both_latin = (
        before[-1:].isascii()
        and before[-1:].isalnum()
        and after[:1].isascii()
        and after[:1].isalnum()
    )
    return 1 if both_latin and (len(before) > 1 or len(after) > 1) else 0


def join(texts: Sequence[str]) -> str:
    out = ""
    previous = ""
    for text in texts:
        out += (" " if previous and joint(previous, text) else "") + text
        previous = text
    return out


def last_char(text: str) -> str:
    return (text.rstrip(CLOSERS) or text)[-1]


def is_sentence_end(text: str) -> bool:
    return last_char(text) in SENTENCE_END


def _boundary(before: str, after: str, head: str) -> float:
    """How bad it is to end a line with `before` and start the next with `after`. `head` is
    everything up to and including `before`."""
    if after in _NO_LINE_START or before in OPENERS:
        return _FORBIDDEN
    if before in _NUMBER_MARKS and after.isdigit() and head[-2:-1].isdigit():
        return _FORBIDDEN
    if before in SENTENCE_END:
        return 0.0
    if before in CLAUSE_END:
        return 1.5
    if head.endswith(_ENDINGS):
        return 2.0
    first, second = script(before), script(after)
    if first == HIRAGANA and before in _PARTICLES and second != HIRAGANA:
        return 2.5
    if first == HIRAGANA and second != HIRAGANA:
        return 3.5
    if first == second == HIRAGANA:
        return 5.5 if before in _PARTICLES else 8.0
    if first == second == KATAKANA:
        return _INSIDE_WORD + 3.0
    if first == second and first in (KANJI, LATIN):
        return _INSIDE_WORD
    if first == KANJI and second == HIRAGANA:
        return 7.0
    return 3.0


def break_costs(words: Sequence[Word]) -> list[float]:
    """The cost of ending a line after each word, from the script and endings of the text alone
    (the last entry is the end of the run and costs nothing)."""
    costs: list[float] = []
    head = ""
    for index, word in enumerate(words):
        head += (" " if head and joint(words[index - 1].text, word.text) else "") + word.text
        if index + 1 == len(words):
            costs.append(0.0)
        else:
            costs.append(_boundary(last_char(word.text), words[index + 1].text[0], head))
    return costs


LINE_BALANCE = 8
"""Columns of difference between two lines that cost as much as one point of break cost."""


def wrap(words: Sequence[Word], limit: int, costs: Sequence[float] | None = None) -> str:
    """The text of `words` on one line when it fits `limit` columns, else on two lines cut where
    the break costs `costs` (default `break_costs`) are lowest and the lines are about the same
    length."""
    texts = [w.text for w in words]
    whole = join(texts)
    if columns(whole) <= limit:
        return whole
    costs = break_costs(words) if costs is None else costs
    best: tuple[float, int] | None = None
    for cut in range(1, len(texts)):
        left, right = join(texts[:cut]), join(texts[cut:])
        if columns(left) > limit or columns(right) > limit:
            continue
        score = costs[cut - 1] + abs(columns(left) - columns(right)) / LINE_BALANCE
        if best is None or score < best[0]:
            best = (score, cut)
    if best is None:
        return whole
    return join(texts[: best[1]]) + "\n" + join(texts[best[1] :])
