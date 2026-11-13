"""The languages a talk can be spoken in, as one typed table.

What differs between source languages lives in a `SourceLanguage`: the names of the files that
hold what was said, the cue rules, the wording of the translation and summary prompts, how long a
translation may be next to it, and the check a translation must pass. The rest of the code asks the
`SourceLanguage` it was given and never tests for a language code. English is the default and its
files, prompts and cue rules are exactly what the first release made.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, replace
from types import MappingProxyType

from backend.core import unspaced
from backend.core.ja_terms import JA_TERMS, JaTerm
from backend.core.kana import romanize_katakana
from backend.core.languages import Density, Language
from backend.core.model import DEFAULT_SOURCE
from backend.core.segmenter import CueRules
from backend.core.zh_tw import (
    japanese_only_chars,
    taiwan_terms_from_japanese,
    traditional_from_japanese,
)

ENGLISH = DEFAULT_SOURCE
JAPANESE = "ja"

_KANA = re.compile("[぀-ヿㇰ-ㇿｦ-ﾟ]")
_LATIN_WORD = re.compile(r"[A-Za-z0-9]+")
_CJK = re.compile("[぀-ヿ㐀-䶿一-鿿ｦ-ﾟ]")
_KATAKANA_MIDDLE_DOT = "・"
_MIDDLE_DOT = "·"


class UnknownSource(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class SourceFiles:
    """The names of the files that hold the talk as it was said."""

    subs: str
    srt: str


@dataclass(frozen=True, slots=True)
class SourcePrompt:
    """What `prompts/translate.md` needs to know about the language it translates from. `name`
    stands for the language in the rules and `key` is the field of each entry that holds the text.
    `entries` is the example's input, `rules` replaces the rules about the speech itself and
    `leftover` is the rule about words left untranslated. `examples` gives the worked reply for
    the target languages that have one, or is empty when the target's own example is the reply."""

    name: str
    key: str
    entries: str
    rules: str
    leftover: str
    examples: Mapping[str, str]


@dataclass(frozen=True, slots=True)
class SourceLanguage:
    code: str
    name: str
    native: str
    files: SourceFiles
    cues: CueRules
    prompt: SourcePrompt
    summary_map: str
    """The file in `prompts/` that tells the model how to take notes on one part of the talk."""
    chars_per_token: float
    chars_per_word: float
    """How long a word is, for sizing a part of the talk: the text has no spaces to count."""
    sentence_end: re.Pattern[str]
    density: Density | None
    """How long a translation may be next to its source, when that is not what the target says."""
    targets: frozenset[str] | None
    """The target languages with a worked example and a tested prompt, or None for all."""
    problem: Callable[[str], str | None]
    clean: Callable[[str], str]
    mends_glossary: bool
    """The glossary terms are written in the source's own script, so a translation that copies one
    is mended with the term's fixed translation."""
    repair: Callable[[str], str] | None
    """What is done to a translation that failed every attempt, before it is checked once more
    without its length. None keeps the source text in its place."""
    fonts: tuple[str, ...]
    """The families a burned-in subtitle may write the source text in, best first."""
    rejects_bare_punctuation: bool = False
    """A translation with no letter or digit in it, such as 「。」, is a bad reply: the sentence it
    belongs to was put in the cue before it."""
    members: tuple[SourceLanguage, ...] = ()
    """For a talk in more than one language, the language of each cue. Every other field is then the
    talk's as a whole: the files, the summary notes and the checks of the Chinese it is written in."""
    asr_engine: str | None = None
    """The one speech recognition engine that can do this source, when it is not the default."""
    terms: tuple[JaTerm, ...] = ()
    """The terms of the language with the Taiwan form of each. A request names the ones its text
    has."""
    sentence_continues: re.Pattern[str] | None = None
    """What a cue starts with when it goes on with the sentence the cue before it ended on, for a
    language whose speech has no full stops to end a sentence by."""

    @property
    def mixed(self) -> bool:
        return bool(self.members)

    def of(self, code: str) -> SourceLanguage:
        """The language of a cue spoken in `code`: this one, or its member for a mixed talk."""
        return next((member for member in self.members if member.code == code), self)

    @property
    def spaced(self) -> bool:
        return not self.cues.unspaced

    def supports(self, target: Language) -> bool:
        return self.targets is None or target.code in self.targets

    def example(self, target: Language) -> str:
        return self.prompt.examples.get(target.code) or target.prompt.example

    def flat(self, text: str) -> str:
        """The lines of a cue as one line."""
        lines = text.split("\n")
        return " ".join(lines) if self.spaced else unspaced.join(lines)

    def prose(self, texts: Sequence[str]) -> str:
        """The text of several cues as one run of speech."""
        if self.spaced:
            return " ".join(" ".join(text.split()) for text in texts)
        return unspaced.join([self.flat(text) for text in texts])

    def words(self, text: str) -> int:
        if self.mixed:
            japanese = self.of(JAPANESE)
            kana_and_kanji = len(_CJK.findall(text))
            return len(_LATIN_WORD.findall(text)) + -(
                -kana_and_kanji // round(japanese.chars_per_word)
            )
        if self.spaced:
            return len(text.split())
        return -(-len("".join(text.split())) // round(self.chars_per_word))


_ENGLISH_ENTRIES = (
    '{"id": 7, "en": "[[7]]So last month, I did something pretty [[8]]crazy."} '
    'and {"id": 9, "en": "I shipped 2,000 PRs."}'
)
_ENGLISH_RULES = (
    "- Keep the speaker's spoken tone. Be natural and accurate. Do not add or remove "
    'information. Leave out the filler words "uh", "um" and "er"<<FILLER_NOT>>. The phrase '
    '"you know" used as a filler (as in "so, you know, we shipped it") is left out<<YOU_KNOW>>. '
    'A real question such as "do you know the answer?" is still translated. Leave fillers out '
    "only from the cue they are in, and never move words between cues. A cue that holds only a "
    "filler gets <<FILLER_CUE>>.\n"
    "- Keep product names, company names, people's names, code, file names and commands in their "
    "original spelling. A well-known person or place may be written in <<NAME>>.\n"
    "- The English comes from speech recognition and may contain mishearings. Use the context to "
    "pick the most likely meaning."
)
_ENGLISH_LEFTOVER = (
    "- Translate every English word except names, product names and technical terms that are "
    'normally left in English. Do not leave ordinary words like "just" or "here" in the <<NAME>>.'
)

_JAPANESE_ENTRIES = (
    '{"id": 7, "ja": "[[7]]先月、ちょっと[[8]]とんでもないことをやりました。"} '
    'and {"id": 9, "ja": "二千件のPRを出しました。"}'
)
_JAPANESE_RULES = """\
- Keep the speaker's spoken tone. Be natural and accurate. Do not add or remove information. Leave out spoken Japanese filler and padding such as "ええと", "えー", "あのー", "まあ", "ですね", "ということで" and "させていただきます" when <<NAME>> does not need them<<FILLER_NOT>>. Leave fillers out only from the cue they are in, and never move words between cues. A cue that holds only a filler gets <<FILLER_CUE>>. Keep a clearly respectful or humble tone natural, and never translate the お and ご honorific prefixes word for word.
- Japanese often leaves the subject out. Read the context to find who or what each sentence is about, and write that subject only when <<NAME>> needs it. Never invent a subject, a person or a number that the sentence and its context do not give.
- Write every Japanese kanji in its Traditional form as used in Taiwan (気 becomes 氣, 会 becomes 會, 点 becomes 點, 売 becomes 賣, 続 becomes 續). Never leave a kana or a kanji that only Japanese uses in the translation.
- A katakana word is usually a loanword or a name. Translate a loanword by meaning when Taiwan has a common word for it. A product, company or person name stays in Latin letters when it has one (パフォース, パーフォース, パフォッシャ, パフォーシャ and ビフォ are the product Perforce, ビジュアルスタジオコード is Visual Studio Code, 東陽テクニカ is Toyo Corporation), and is spelled in Chinese characters when it has no Latin spelling. The speech recognition garbles names, so take the name the context gives, not a literal copy of the garbled sound. Never leave a name in kana.
- A Latin word the speaker says inside a Japanese sentence (Perforce, P4, MCP, AI, PR) stays in Latin letters, and "P four" means P4.
- Use the same translation for a name or term everywhere.
- Use Taiwan wording. Finishing a game is 通關 (クリア後 is 通關後, and 清關 is customs clearance). A code repository is 儲存倉 (not 倉庫 or 儲存庫), a pipeline is 管線 (not 流水線), operations is 營運 (not 運營), metadata is 中繼資料 (not 元數據), source code is 原始碼 (not 源碼), a plug-in is 外掛 (not 插件), storage is 儲存 (not 存儲), an interface is 介面 (not 接口), searching is 搜尋 (not 搜索), visualizing is 視覺化 (not 可視化), feedback is 回饋 (not 反饋), calling a function or tool is 呼叫 (not 調用), creating something in software is 建立 (not 創建), and accessing a resource such as a database, a file or an API is 存取 (not 訪問; 訪問 stays for a visit or an interview). 整備 is a Japanese word: say 整理 or 準備 as the sense needs. 間口が広い means the barrier to entry is low, not that something is wide.
- The Japanese comes from speech recognition and may contain mishearings. Use the context to pick the most likely meaning."""
_JAPANESE_LEFTOVER = (
    "- Translate every Japanese word except names, product names and technical terms that are "
    "normally written in Latin letters. Do not leave Japanese words or kana in the <<NAME>>."
)
_JAPANESE_EXAMPLES = {
    "zh-TW": '{"translations": [{"id": 7, "zh": "[[7]]上個月，我做了一件有點[[8]]離譜的事。"}, '
    '{"id": 9, "zh": "我送出了 2,000 個 PR。"}]}'
}


def _no_problem(text: str) -> str | None:
    return None


def _identity(text: str) -> str:
    return text


def is_bare_punctuation(text: str) -> bool:
    """Whether `text` has no letter, digit or ideograph in it, only marks and spaces."""
    return not any(unicodedata.category(char)[0] in "LN" for char in text)


def _japanese_problem(text: str) -> str | None:
    """What a Chinese translation of Japanese speech still has of Japanese in it. Kana and the
    kanji Japanese writes in its own way are the two ways a model leaves the source behind."""
    if kana := sorted(set(_KANA.findall(text)) - {_KATAKANA_MIDDLE_DOT}):
        return (
            f"still holds Japanese kana {''.join(kana)}; write Chinese, or Latin letters for a name"
        )
    if kanji := japanese_only_chars(text):
        return f"uses Japanese kanji forms {''.join(kanji)}; write Traditional Chinese characters"
    return None


def _japanese_clean(text: str) -> str:
    text = traditional_from_japanese(text.replace(_KATAKANA_MIDDLE_DOT, _MIDDLE_DOT))
    return taiwan_terms_from_japanese(text)


_ENGLISH_SENTENCE_END = re.compile(r"[.?!…][\"')\]”]*\Z")
_JAPANESE_FINAL_FORMS = (
    "(?:(?:ます|ました|ません|でした|ください|ましょう|でしょう)(?:ね|よ)?|です(?:よ)?)"
)
_JAPANESE_SENTENCE_END = re.compile(
    rf"(?:[。！？!?…][」』）)\"”]*|{_JAPANESE_FINAL_FORMS}[。！？!?]?)\Z"
)
_JAPANESE_CONTINUES = re.compile(
    "(?:が|けど|けれど|ので|から|し|ね[、。]|よ[、。]|で[、は]|て|と[いし]|も(?!う)|ば|ため|こと)"
)

ENGLISH_SOURCE = SourceLanguage(
    ENGLISH,
    "English",
    "English",
    SourceFiles("subs.en.json", "en.srt"),
    CueRules(),
    SourcePrompt("English", "en", _ENGLISH_ENTRIES, _ENGLISH_RULES, _ENGLISH_LEFTOVER, {}),
    "summarize_map.md",
    3.5,
    5.0,
    _ENGLISH_SENTENCE_END,
    None,
    None,
    _no_problem,
    _identity,
    False,
    None,
    ("Arial",),
)
JAPANESE_SOURCE = SourceLanguage(
    JAPANESE,
    "Japanese",
    "日本語",
    SourceFiles("subs.ja.json", "ja.srt"),
    CueRules(max_line_chars=40, unspaced=True, max_cps=14.0),
    SourcePrompt(
        "Japanese", "ja", _JAPANESE_ENTRIES, _JAPANESE_RULES, _JAPANESE_LEFTOVER, _JAPANESE_EXAMPLES
    ),
    "summarize_map_ja.md",
    1.2,
    2.0,
    _JAPANESE_SENTENCE_END,
    Density(1.1, 8, 0.15),
    frozenset({"zh-TW"}),
    _japanese_problem,
    _japanese_clean,
    True,
    romanize_katakana,
    ("Yu Gothic", "Meiryo", "MS Gothic"),
    rejects_bare_punctuation=True,
    sentence_continues=_JAPANESE_CONTINUES,
    terms=JA_TERMS,
)

MIXED = "ja+en"
MIXED_SOURCE = replace(
    JAPANESE_SOURCE,
    code=MIXED,
    name="Japanese and English",
    native="日本語と英語",
    files=SourceFiles("subs.src.json", "src.srt"),
    summary_map="summarize_map_ja_en.md",
    members=(JAPANESE_SOURCE, ENGLISH_SOURCE),
    asr_engine="crispasr-qwen3-asr-1.7b",
)

SOURCES: Mapping[str, SourceLanguage] = MappingProxyType(
    {source.code: source for source in (ENGLISH_SOURCE, JAPANESE_SOURCE, MIXED_SOURCE)}
)


def is_spaced(code: str) -> bool:
    """Whether speech in `code` has spaces between its words. A code that is not a source language
    (an engine can be given any it knows, such as `auto`) is taken to have them."""
    source = SOURCES.get(code)
    return source is None or source.spaced


def get_source(code: str) -> SourceLanguage:
    """The source language with this code, or `UnknownSource` naming the codes that exist."""
    try:
        return SOURCES[code]
    except KeyError:
        raise UnknownSource(
            f"unknown source language {code!r}; choose one of {', '.join(SOURCES)}"
        ) from None
