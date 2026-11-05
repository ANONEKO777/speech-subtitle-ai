"""The languages a talk can be translated into, as one typed table.

Everything that differs between target languages lives in a `Language`: its names, the file names
of its outputs, the checks a translated cue must pass, the clean-up applied to a reply, and the
wording of its prompts. The rest of the code never tests for a language code. It asks the
`Language` it was given.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from enum import StrEnum
from types import MappingProxyType
from typing import Literal

from backend.core import fillers
from backend.core.language_prompts import PROMPTS, SUMMARIES, Prompt, SummaryText
from backend.core.zh_tw import (
    CJK_TEXT,
    gb2312_hanzi,
    simplified_chars,
    taiwan_terms,
)

DEFAULT_CODE = "zh-TW"
ENGLISH = "en"

TextCheck = Callable[[str, str, bool], str | None]
"""(text, english, required) -> what is wrong with a translation, or None. `required` says the
text must hold characters of the language's script. The English is empty for a line of a summary."""


class UnknownLanguage(ValueError):
    pass


class Wrap(StrEnum):
    """Where a long line of a language may be broken in a subtitle: anywhere but inside a Latin
    word or number (`CJK`), only after a space (`SPACES`), or between Thai grapheme clusters, and
    after a space where there is one (`THAI`)."""

    CJK = "cjk"
    SPACES = "spaces"
    THAI = "thai"


Quality = Literal["stable", "experimental"]


@dataclass(frozen=True, slots=True)
class Density:
    """How long a translation may be next to its English, in characters. Languages differ: a
    Chinese cue is about half as long as its English, a Spanish one is longer."""

    max_per_en_char: float
    slack: int
    min_per_en_char: float


@dataclass(frozen=True, slots=True)
class LangFiles:
    """The names of the files a project holds for one target language."""

    subs: str
    srt: str
    ass: str
    vtt: str
    summary: str
    summary_parts: str


@dataclass(frozen=True, slots=True)
class Language:
    code: str
    name: str
    native: str
    file_code: str
    prompt: Prompt
    summary: SummaryText
    check: TextCheck
    needs_script: Callable[[str], bool]
    terms: Callable[[str], str]
    clean: Callable[[str, str], str]
    density: Density
    wrap: Wrap
    quality: Quality

    def problem(self, text: str, en: str) -> str | None:
        """What is wrong with `text` as the translation of the cue `en`, or None."""
        return self.check(text, en, self.needs_script(en))

    def title_problem(self, text: str) -> str | None:
        """What is wrong with a heading in this language. A title may be all names."""
        return self.check(text, "", False)

    def prose_problem(self, text: str) -> str | None:
        return self.check(text, "", True)

    @property
    def is_default(self) -> bool:
        return self.code == DEFAULT_CODE

    @property
    def files(self) -> LangFiles:
        """The default language keeps the names the first release gave its files."""
        c = self.file_code
        if self.is_default:
            return LangFiles(
                f"subs.{c}.json",
                f"{c}.srt",
                "bilingual.ass",
                "bilingual.vtt",
                "summary.md",
                "summary.parts.json",
            )
        return LangFiles(
            f"subs.{c}.json",
            f"{c}.srt",
            f"bilingual.en-{c}.ass",
            f"bilingual.en-{c}.vtt",
            f"summary.{c}.md",
            f"summary.{c}.parts.json",
        )


_ENGLISH_STOP = frozenset(
    "the and of that this with is are you your we they have has it but what would from can".split()
)
_WORD = re.compile(r"[A-Za-z']+")
_LOWER_WORD = re.compile(r"(?<![A-Za-z])[a-z]{3,}(?![A-Za-z])")
_KANA = re.compile("[぀-ヿㇰ-ㇿｦ-ﾟ]")
_HANGUL = re.compile("[ᄀ-ᇿ㄰-㆏가-힯]")
_THAI = re.compile("[฀-๿]")
_CYRILLIC = re.compile("[Ѐ-ӿ]")
_IDEOGRAPH = re.compile("[㐀-䶿一-鿿豈-﫿]")
_ASIAN_PUNCT = re.compile("[　-〿＀-￯]")
_SCRIPTS: Mapping[str, re.Pattern[str]] = MappingProxyType(
    {
        "Japanese kana": _KANA,
        "Hangul": _HANGUL,
        "Thai": _THAI,
        "Cyrillic": _CYRILLIC,
        "Chinese": _IDEOGRAPH,
    }
)
_NEEDS_WORDS = 3
_NEEDS_KANA_WORDS = 5


def _more_than_a_few_words(en: str) -> bool:
    return not en or len(en.split()) > _NEEDS_WORDS


def _wants_script(en: str) -> bool:
    """A cue of ordinary English words must come back in the target script. A line of product
    names, or a line of a summary (no English given), needs less care."""
    if not en:
        return True
    return len(en.split()) > _NEEDS_WORDS and _LOWER_WORD.search(en) is not None


def _foreign(text: str, own: tuple[str, ...]) -> str | None:
    for name, pattern in _SCRIPTS.items():
        if name not in own and pattern.search(text):
            return name
    return None


def _big5_hanzi() -> str:
    chars: list[str] = []
    for lead in range(0xA4, 0xFA):
        for trail in (*range(0x40, 0x7F), *range(0xA1, 0xFF)):
            try:
                char = bytes((lead, trail)).decode("cp950")
            except UnicodeDecodeError:
                continue
            if "一" <= char <= "鿿":
                chars.append(char)
    return "".join(chars)


TRADITIONAL_ONLY = frozenset(_big5_hanzi()) - frozenset(gb2312_hanzi())
"""Characters Big5 has and GB2312 lacks: written in Traditional Chinese, not in Simplified."""


def traditional_chars(text: str) -> list[str]:
    return sorted(set(text) & TRADITIONAL_ONLY)


def _check_zh_tw(text: str, en: str, required: bool) -> str | None:
    if simplified := simplified_chars(text):
        return f"uses Simplified characters {''.join(simplified)}; write Traditional characters"
    if required and not CJK_TEXT.search(text):
        return "is not translated into Traditional Chinese"
    return None


def _check_zh_cn(text: str, en: str, required: bool) -> str | None:
    if traditional := traditional_chars(text):
        return f"uses Traditional characters {''.join(traditional)}; write Simplified characters"
    if required and not CJK_TEXT.search(text):
        return "is not translated into Simplified Chinese"
    return None


def _check_ja(text: str, en: str, required: bool) -> str | None:
    if _HANGUL.search(text):
        return "contains Hangul; write Japanese"
    if not required:
        return None
    if not (_KANA.search(text) or _IDEOGRAPH.search(text) or _ASIAN_PUNCT.search(text)):
        return "is not translated into Japanese"
    if len(en.split()) > _NEEDS_KANA_WORDS and not _KANA.search(text):
        return "has no kana, so it is Chinese; write Japanese"
    return None


def _check_in_script(name: str, own: re.Pattern[str], own_names: tuple[str, ...]) -> TextCheck:
    def check(text: str, en: str, required: bool) -> str | None:
        if other := _foreign(text, own_names):
            return f"contains {other} characters; write {name}"
        if required and not own.search(text):
            return f"is not translated into {name}"
        return None

    return check


def _looks_english(text: str, en: str) -> bool:
    words = _WORD.findall(text.lower())
    if len(words) <= _NEEDS_WORDS:
        return False
    hits = sum(word in _ENGLISH_STOP for word in words)
    return (hits >= _NEEDS_WORDS and hits / len(words) >= 0.3) or (
        bool(en) and text.strip().lower() == en.strip().lower()
    )


def _check_latin(name: str) -> TextCheck:
    def check(text: str, en: str, required: bool) -> str | None:
        if other := _foreign(text, ()):
            return f"contains {other} characters; write {name} in Latin letters"
        if required and _looks_english(text, en):
            return f"is still English; translate it into {name}"
        return None

    return check


def _terms_none(text: str) -> str:
    return text


def _clean_zh_tw(text: str, en: str) -> str:
    return fillers.drop_fillers(fillers.strip_markdown_emphasis(taiwan_terms(text)), en)


def _clean_zh_cn(text: str, en: str) -> str:
    return fillers.drop_fillers(fillers.strip_markdown_emphasis(text), en)


def _clean_non_latin(text: str, en: str) -> str:
    return fillers.drop_latin_fillers(fillers.strip_markdown_emphasis(text))


def _clean_latin(text: str, en: str) -> str:
    return fillers.drop_latin_fillers(fillers.strip_markdown_emphasis(text))


def _clean_latin_um_is_a_word(text: str, en: str) -> str:
    """For a language where "um" is a word (Portuguese "um" is "a", German "um" is "around")."""
    return fillers.drop_latin_fillers(fillers.strip_markdown_emphasis(text), en, um_is_a_word=True)


_CHINESE = Density(1.2, 6, 0.12)
_DENSE = Density(1.4, 8, 0.12)
_LATIN_DENSITY = Density(2.2, 12, 0.35)
_WIDE = Density(2.2, 12, 0.3)


def _build() -> dict[str, Language]:
    def make(
        code: str,
        name: str,
        native: str,
        check: TextCheck,
        density: Density,
        *,
        needs_script: Callable[[str], bool] = _wants_script,
        clean: Callable[[str, str], str],
        terms: Callable[[str], str] = _terms_none,
        wrap: Wrap = Wrap.SPACES,
        quality: Quality = "stable",
    ) -> Language:
        return Language(
            code,
            name,
            native,
            code,
            PROMPTS[code],
            SUMMARIES[code],
            check,
            needs_script,
            terms,
            clean,
            density,
            wrap,
            quality,
        )

    table = [
        make(
            "zh-TW",
            "Traditional Chinese (Taiwan)",
            "繁體中文（台灣）",
            _check_zh_tw,
            _CHINESE,
            clean=_clean_zh_tw,
            terms=taiwan_terms,
            needs_script=_more_than_a_few_words,
            wrap=Wrap.CJK,
        ),
        make(
            "zh-CN",
            "Simplified Chinese",
            "简体中文",
            _check_zh_cn,
            _CHINESE,
            clean=_clean_zh_cn,
            needs_script=_more_than_a_few_words,
            wrap=Wrap.CJK,
        ),
        make("ja", "Japanese", "日本語", _check_ja, _DENSE, clean=_clean_non_latin, wrap=Wrap.CJK),
        make(
            "ko",
            "Korean",
            "한국어",
            _check_in_script("Korean", _HANGUL, ("Hangul",)),
            _DENSE,
            clean=_clean_non_latin,
            quality="experimental",
        ),
        make(
            "es", "Spanish", "Español", _check_latin("Spanish"), _LATIN_DENSITY, clean=_clean_latin
        ),
        make(
            "fr", "French", "Français", _check_latin("French"), _LATIN_DENSITY, clean=_clean_latin
        ),
        make(
            "de",
            "German",
            "Deutsch",
            _check_latin("German"),
            _LATIN_DENSITY,
            clean=_clean_latin_um_is_a_word,
        ),
        make(
            "pt",
            "Portuguese",
            "Português",
            _check_latin("Portuguese"),
            _LATIN_DENSITY,
            clean=_clean_latin_um_is_a_word,
        ),
        make(
            "it", "Italian", "Italiano", _check_latin("Italian"), _LATIN_DENSITY, clean=_clean_latin
        ),
        make(
            "ru",
            "Russian",
            "Русский",
            _check_in_script("Russian", _CYRILLIC, ("Cyrillic",)),
            _WIDE,
            clean=_clean_non_latin,
        ),
        make(
            "vi",
            "Vietnamese",
            "Tiếng Việt",
            _check_latin("Vietnamese"),
            _LATIN_DENSITY,
            clean=_clean_latin,
        ),
        make(
            "th",
            "Thai",
            "ไทย",
            _check_in_script("Thai", _THAI, ("Thai",)),
            _WIDE,
            clean=_clean_non_latin,
            wrap=Wrap.THAI,
            quality="experimental",
        ),
        make(
            "id",
            "Indonesian",
            "Bahasa Indonesia",
            _check_latin("Indonesian"),
            _LATIN_DENSITY,
            clean=_clean_latin,
        ),
    ]
    return {language.code: language for language in table}


LANGUAGES: Mapping[str, Language] = MappingProxyType(_build())
DEFAULT = LANGUAGES[DEFAULT_CODE]


def get(code: str) -> Language:
    """The language with this code, or `UnknownLanguage` naming the codes that exist."""
    try:
        return LANGUAGES[code]
    except KeyError:
        raise UnknownLanguage(
            f"unknown target language {code!r}; choose one of {', '.join(LANGUAGES)}"
        ) from None
