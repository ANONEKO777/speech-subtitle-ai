"""Clean-up of a model's reply that does not depend on a Taiwan or Mainland vocabulary: spoken
fillers the model left in, and markdown it wrapped around a word."""

from __future__ import annotations

import re

ZH_FILLER_CUE = "嗯，"

_MARKDOWN_TOKEN = r"[^\s_*]+"
_WRAPPED_TOKEN = re.compile(
    rf"(?<![A-Za-z0-9_])_({_MARKDOWN_TOKEN})_(?![A-Za-z0-9_])"
    rf"|(?<![A-Za-z0-9*])(\*{{1,2}})({_MARKDOWN_TOKEN})\2(?![A-Za-z0-9*])"
)
_LATIN_FILLER = re.compile(r"(?<![A-Za-z])(?:uh+|um+|hmm+)(?![A-Za-z])[,，、]?\s*", re.IGNORECASE)
_ZH_YOU_KNOW_ALONE = re.compile(r"(?<![^，。？！\s])你知不知道(?=[，,\s]|$)[，,]?")
_ZH_YOU_KNOW_ANY = re.compile(r"你知不知道[，,]?\s*")
_ZH_YOU_KNOW_CLAUSE = re.compile(
    r"(?<![^，。？！、；：\s])(?:你知不知道|你知道|你知)(?=[，,。\s]|$)[，,]?"
)
_ENGLISH_YOU_KNOW = re.compile(r"\byou know\b", re.IGNORECASE)
_ENGLISH_YOU_KNOW_FILLER = re.compile(
    r"(?:^|[,.;:!—-]\s*)you know\b(?=\s*(?:[,.;…]|$))", re.IGNORECASE
)
_ENGLISH_ONLY_YOU_KNOW = re.compile(r"[\s,.;…—-]*(?:you know[\s,.;…—-]*)+", re.IGNORECASE)
_DOUBLE_COMMA = re.compile(r"([，,])\s*[，,]+")
_LEADING_COMMA = re.compile(r"^[，,\s]+")


def strip_markdown_emphasis(text: str) -> str:
    """Unwrap a token the model wrapped in _underscores_ or *asterisks*."""
    return _WRAPPED_TOKEN.sub(lambda m: m.group(1) or m.group(3), text)


_UM_FILLER = re.compile(r"(?<![A-Za-z])(?:uh+|um+|hmm+)(?![A-Za-z])", re.IGNORECASE)
_SET_OFF_UM = re.compile(
    r"(?:^|(?<=[,;:.!?—-]))\s*um+(?=\s*(?:[,;:.!?…—-]|$))[,，、]?\s*",
    re.IGNORECASE,
)
_UH_HMM_FILLER = re.compile(r"(?<![A-Za-z])(?:uh+|hmm+)(?![A-Za-z])[,，、]?\s*", re.IGNORECASE)


def _drop_set_off_um(match: re.Match[str]) -> str:
    """Leave one space where a set-off "um" stood between a comma and a word, so "Plus, um, Sie"
    becomes "Plus, Sie"."""
    after = match.string[match.end() : match.end() + 1]
    return " " if match.start() > 0 and after.isalnum() else ""


def drop_latin_fillers(text: str, en: str = "", *, um_is_a_word: bool = False) -> str:
    """Remove "uh", "um" and "hmm" left in Latin letters: a filler the model carried over.

    In a language where "um" is a word (`um_is_a_word`), "uh" and "hmm" still go, and "um" goes
    only when `en` has a filler "um", "uh" or "hmm" and the "um" is set off by punctuation or the
    ends of the text, so an article is kept."""
    if not um_is_a_word:
        return _LATIN_FILLER.sub("", text)
    text = _UH_HMM_FILLER.sub("", text)
    return _SET_OFF_UM.sub(_drop_set_off_um, text) if _UM_FILLER.search(en) else text


def english_you_know_filler(en: str) -> bool:
    """True when the English cue says "you know" as a filler: set off by commas or the ends of
    the cue and not asked as a question. "Do you know the answer" and "you know that" are not."""
    return "?" not in en and _ENGLISH_YOU_KNOW_FILLER.search(en) is not None


def drop_fillers(text: str, en: str = "") -> str:
    """Remove "uh" and "um" left in Latin letters, and the filler 你知不知道, 你知道 or 你知.

    When `en` is given and says "you know" without asking a question, every 你知不知道 is a
    filler. When `en` says it as a filler (see `english_you_know_filler`), a clause that is only
    你知道 or 你知 is one too. Otherwise only a 你知不知道 standing alone between commas is
    dropped. A text that would be empty afterwards is returned unchanged, except that a cue
    whose English is nothing but "you know" gets `ZH_FILLER_CUE`."""
    cleaned = drop_latin_fillers(text)
    if _ENGLISH_YOU_KNOW.search(en) and "?" not in en:
        cleaned = _ZH_YOU_KNOW_ANY.sub("", cleaned)
    else:
        cleaned = _ZH_YOU_KNOW_ALONE.sub("", cleaned)
    filler = english_you_know_filler(en)
    if filler:
        cleaned = _ZH_YOU_KNOW_CLAUSE.sub("", cleaned)
    cleaned = _LEADING_COMMA.sub("", _DOUBLE_COMMA.sub(r"", cleaned)).strip()
    if cleaned:
        return cleaned
    return ZH_FILLER_CUE if filler and _ENGLISH_ONLY_YOU_KNOW.fullmatch(en) else text
