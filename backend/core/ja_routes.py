"""The rows of the table that says how a Japanese talk is translated into each target language.

The Japanese source's own fields describe the Traditional Chinese (Taiwan) translation, the first
target, and `HOME_RULES` is its rules text. Each row here is another target: the worked example, the
rules about the target language, how long a translation may be, what it must not contain, the terms
of Perforce and the software the talks are about, the notes prompt of the summary, whether the
target is experimental and what happens to a cue that failed every attempt. The length limits come
from the P25 measurements (`ratio_p90` in `checks/summary.tsv` of the evidence folder, and the
`direct` cue files of its `runs/full`): the limit is 1.5 times the 90th percentile of the ratio of
output characters to Japanese characters.

The rules text is the home text with the lines that are about Taiwan Chinese replaced. The lines
about the speech itself (fillers, the dropped subject, numbers, names in Latin letters) are shared.
"""

from __future__ import annotations

import re
from types import MappingProxyType

from backend.core.ja_terms import JA_TERMS, JaTerm
from backend.core.languages import Density
from backend.core.target_routes import OnFailure, SummaryNotes, TargetRoute
from backend.core.zh_tw import japanese_only_chars

HOME_RULES = """\
- Keep the speaker's spoken tone. Be natural and accurate. Do not add or remove information. Leave out spoken Japanese filler and padding such as "ええと", "えー", "あのー", "まあ", "ですね", "ということで" and "させていただきます" when <<NAME>> does not need them<<FILLER_NOT>>. Leave fillers out only from the cue they are in, and never move words between cues. A cue that holds only a filler gets <<FILLER_CUE>>. Keep a clearly respectful or humble tone natural, and never translate the お and ご honorific prefixes word for word.
- Japanese often leaves the subject out. Read the context to find who or what each sentence is about, and write that subject only when <<NAME>> needs it. Never invent a subject, a person or a number that the sentence and its context do not give.
- Write every Japanese kanji in its Traditional form as used in Taiwan (気 becomes 氣, 会 becomes 會, 点 becomes 點, 売 becomes 賣, 続 becomes 續). Never leave a kana or a kanji that only Japanese uses in the translation.
- A katakana word is usually a loanword or a name. Translate a loanword by meaning when Taiwan has a common word for it. A product, company or person name stays in Latin letters when it has one (パフォース, パーフォース, パフォッシャ, パフォーシャ, パワーフォース, パワフォース, パワーホース and ビフォ are the product Perforce, ビジュアルスタジオコード is Visual Studio Code, クロードコード is Claude Code, 東陽テクニカ is Toyo Corporation, チャットGPT is ChatGPT, クロード is Claude, コパイロット is Copilot), and is spelled in Chinese characters when it has no Latin spelling. The speech recognition garbles names, so take the name the context gives, not a literal copy of the garbled sound. Never leave a name in kana.
- A Latin word the speaker says inside a Japanese sentence (Perforce, P4, MCP, AI, PR) stays in Latin letters, and "P four" means P4.
- Use the same translation for a name or term everywhere.
- Translate only what the Japanese says. Never add a reason, a link such as 為了解決這個問題 or 因此, a clause or a name that the sentence does not have, and never turn a plain statement into an explanation.
- Keep every number exactly as spoken: the same digits, the decimal point and the percent sign (51.9% stays 51.9%), and never drop one. A number written in Arabic digits stays in Arabic digits.
- Use Taiwan wording. Finishing a game is 通關 (クリア後 is 通關後, and 清關 is customs clearance). A code repository is 儲存倉 (not 倉庫 or 儲存庫), a pipeline is 管線 (not 流水線), operations is 營運 (not 運營), metadata is 中繼資料 (not 元數據), source code is 原始碼 (not 源碼), a plug-in is 外掛 (not 插件, and not 外掛程式), storage is 儲存 (not 存儲), an interface is 介面 (not 接口), searching is 搜尋 (not 搜索), visualizing is 視覺化 (not 可視化), feedback is 回饋 (not 反饋), calling a function or tool is 呼叫 (not 調用), creating something in software is 建立 (not 創建), and accessing a resource such as a database, a file or an API is 存取 (not 訪問; 訪問 stays for a visit or an interview). 整備 is a Japanese word: say 整理 or 準備 as the sense needs.
- The Japanese comes from speech recognition and may contain mishearings. Use the context to pick the most likely meaning."""

_LINES = HOME_RULES.split("\n")
assert len(_LINES) == 10, "the home rules changed shape; recheck which lines are about Taiwan"
(
    _TONE,
    _SUBJECT,
    _HOME_SCRIPT,
    _HOME_NAMES,
    _LATIN_WORD,
    _SAME_TERM,
    _HOME_ONLY_WHAT_SAID,
    _NUMBERS,
    _HOME_WORDING,
    _MISHEARD,
) = _LINES


def _swap(line: str, old: str, new: str) -> str:
    if old not in line:
        raise ValueError(f"the home rule no longer holds {old!r}")
    return line.replace(old, new)


def _names(who: str, spelled: str) -> str:
    """The rule about katakana words. `who` is the language that has the common word for a
    loanword, `spelled` what a name with no Latin spelling becomes."""
    line = _swap(_HOME_NAMES, "when Taiwan has", f"when {who} has")
    return _swap(line, "is spelled in Chinese characters when it has no Latin spelling", spelled)


def _only_what_said(link: str) -> str:
    return _swap(_HOME_ONLY_WHAT_SAID, "為了解決這個問題 or 因此", link)


def _rules(script: str, names: str, link: str, wording: str) -> str:
    return "\n".join(
        (
            _TONE,
            _SUBJECT,
            script,
            names,
            _LATIN_WORD,
            _SAME_TERM,
            _only_what_said(link),
            _NUMBERS,
            wording,
            _MISHEARD,
        )
    )


_KANA = re.compile("[぀-ヿㇰ-ㇿｦ-ﾟ]")
_KATAKANA_MIDDLE_DOT = "・"
_CJK = re.compile("[぀-ヿ㐀-䶿一-鿿ｦ-ﾟ]")
_MIN_CJK_TO_REQUIRE = 5
_LATIN_IN_HANGUL = re.compile("[가-힣][a-z]")
_ENGLISH_RUN = re.compile(r"(?<![A-Za-z'])(?:[A-Za-z][A-Za-z']*[.,;:!?]? ){3,}[A-Za-z][A-Za-z']*")
_MIN_ENGLISH_WORDS = 3
_LOWERCASE_WORD = re.compile("(?<![A-Za-z'])[a-z]{3,}(?![A-Za-z'])")

_TAIWAN_FORMS_IN_SIMPLIFIED = (
    "支援",
    "影像",
    "软体",
    "资讯",
    "程式",
    "伺服器",
    "网路",
    "档案",
    "使用者",
    "滑鼠",
    "记忆体",
    "预设",
    "最佳化",
    "资料库",
    "部落格",
)
"""Words the Taiwan Chinese output of the model writes in characters that Simplified Chinese also
has, so the character check does not see them. Each one has its own word in Mainland China
(支持, 视频, 软件, 信息, 程序, 服务器, 网络, 文件, 用户, 鼠标, 内存, 默认, 优化, 数据库, 博客), the
words the `zh-CN` prompt already names."""


def _needs_script(source: str) -> bool:
    """A cue with this many kana and kanji has words to translate. A cue of "はい" may come back as
    a single mark."""
    return len(_CJK.findall(source)) >= _MIN_CJK_TO_REQUIRE


def _no_kana(text: str) -> str | None:
    if kana := sorted(set(_KANA.findall(text)) - {_KATAKANA_MIDDLE_DOT}):
        return f"still holds Japanese kana {''.join(kana)}; translate it, or use Latin letters for a name"
    return None


def _english_problem(text: str) -> str | None:
    return _no_kana(text)


def _english_tail(text: str) -> str | None:
    """A run of four or more English words, three of them plain lowercase words, is a sentence the
    model left in English, not a product name (Visual Studio Code, Model Context Protocol)."""
    for run in _ENGLISH_RUN.finditer(text):
        if len(_LOWERCASE_WORD.findall(run.group())) >= _MIN_ENGLISH_WORDS:
            return f"has English text {run.group()[:30]!r} left in it; translate all of it"
    return None


def _simplified_problem(text: str) -> str | None:
    if problem := _no_kana(text):
        return problem
    if kanji := japanese_only_chars(text):
        return f"uses Japanese kanji forms {''.join(kanji)}; write Simplified Chinese characters"
    if found := [word for word in _TAIWAN_FORMS_IN_SIMPLIFIED if word in text]:
        return f"uses Taiwan wording {', '.join(found)}; write the Mainland China words"
    return _english_tail(text)


def _korean_problem(text: str) -> str | None:
    if problem := _no_kana(text):
        return problem
    if _LATIN_IN_HANGUL.search(text):
        return "has Latin letters inside a Hangul word; write the whole word in Hangul"
    return _english_tail(text)


def _middle_dot(text: str) -> str:
    return text.replace(_KATAKANA_MIDDLE_DOT, "·")


def _unchanged(text: str) -> str:
    return text


_NAME_SAID = frozenset(
    {
        "チャットGPT",
        "クロードコード",
        "クロード",
        "ビジュアルスタジオコード / Visual Studioコード",
        "VSコード",
        "GitHubコパイロット",
        "コパイロット",
    }
)
NAME_TERMS: tuple[JaTerm, ...] = tuple(term for term in JA_TERMS if term.said in _NAME_SAID)
"""The products the speech recognition garbles. Their forms are in Latin letters, so they hold for
every target."""

_SYNC = r"(?<![ァ-ヺーｦ-ﾟ])シンク(?!ロ)"
"""シンク is sync. シンクロ (synchro) and a longer katakana word are not."""
_PERFORCE = (
    JaTerm("シェルブ", "shelve", ("(?i:shell)", "(?i:shelb)"), ("shelves", "shelving", "shelved")),
    JaTerm("スパースストリーム", "sparse stream"),
    JaTerm("ストリーム", "stream", ("(?i:\\bflow\\b)",), ("streams",)),
    JaTerm("ブランチ", "branch", ("(?i:industr)",), ("branches",)),
    JaTerm("ワークスペース", "workspace"),
    JaTerm("チェンジリスト", "changelist", ("(?i:change list)",), ("changelists",)),
    JaTerm("サブミット", "submit", (), ("submitting", "submitted")),
    JaTerm(
        _SYNC,
        "sync",
        ("(?i:\\bsink\\b)",),
        ("syncing", "synced"),
        literal=False,
        hint="シンク (sync)",
    ),
)
"""Perforce words the model mistranslated in P25: シェルブ as shell, ストリーム as an ordinary flow,
ブランチ as an industry. They keep the English word of the product."""
EN_TERMS: tuple[JaTerm, ...] = (*NAME_TERMS, *_PERFORCE)
ZH_CN_TERMS: tuple[JaTerm, ...] = (
    *NAME_TERMS,
    JaTerm("シェルブ", "搁置", ("外壳", "(?i:shell)"), ("shelve",)),
    JaTerm("スパースストリーム", "Sparse Stream"),
    JaTerm("ストリーム", "Stream", (), ("流",)),
    JaTerm("ブランチ", "分支", ("行业",), ("branch",)),
    JaTerm("ワークスペース", "工作区", (), ("workspace",)),
    JaTerm("チェンジリスト", "变更列表", ("更改列表",), ("changelist", "变更清单")),
    JaTerm("サブミット", "提交", ("送出",), ("submit",)),
    JaTerm(_SYNC, "同步", ("水槽",), ("sync",), literal=False, hint="シンク (sync)"),
)
KO_TERMS: tuple[JaTerm, ...] = NAME_TERMS
"""Korean keeps the product names and nothing else: no Korean reader has checked the transliteration
of the Perforce words, and a wrong fixed form is worse than the model's own."""

_NAMES_LATIN = (
    "is written in Latin letters, as its Hepburn romanisation, when it has no other Latin spelling"
)

_EN_WORDING = (
    "- Write plain spoken English, with contractions where a speaker would use them. Use the "
    "software terms English-speaking engineers use (commit, branch, repository, pipeline, "
    "workspace) and the term table below when it names one."
)
_ZH_CN_WORDING = (
    "- Use Mainland China wording, not Taiwan wording: 软件 (not 软体), 视频 (not 影片), 支持 "
    "(not 支援), 源代码 (not 原始码), 服务器 (not 伺服器), 数据 (not 资料), 文件 (not 档案), 用户 "
    "(not 使用者), 界面 (not 介面), 网络 (not 网路), 程序 (not 程式), 默认 (not 预设), 优化 "
    "(not 最佳化), 项目 (not 专案), 设置 (not 设定), 仓库 (not 儲存倉) for a code repository, "
    "调用 (not 呼叫) a function or tool. Use full-width Chinese punctuation."
)
_KO_WORDING = (
    "- Write natural spoken Korean in Hangul with the polite 합니다 endings only, never the 해요 "
    "endings, and keep that style in every cue. Write only Hangul, Latin letters, digits and "
    "punctuation: never kana and never Chinese characters. A product, company or person name is "
    "written in Latin letters."
)

_ENGLISH_NOTES = SummaryNotes(
    "summarize_map_ja_to.md",
    "- Write every field in English, never in Japanese. Never leave kana in a note.\n"
    "- A product, company or tool name stays in Latin letters (パフォース, パーフォース, パフォッシャ and "
    "ビフォ are the product Perforce, P4 is P4, MCP is MCP). A name that has no Latin spelling is "
    "written in Latin letters. Take the name the context gives, not a literal copy of a garbled "
    "sound.",
    "35 words",
    "12 words",
)
_ZH_CN_NOTES = SummaryNotes(
    "summarize_map_ja_to.md",
    "- Write every field in Simplified Chinese as used in Mainland China (简体中文), never in "
    "Japanese and never in Traditional characters. Write each Japanese kanji in its Simplified "
    "form (気 becomes 气, 売 becomes 卖). Never leave kana in a note. Use Mainland wording: 软件, "
    "视频, 支持, 源代码, 服务器, 文件, 用户.\n"
    "- A product, company or tool name stays in Latin letters (パフォース, パーフォース, パフォッシャ and "
    "ビフォ are the product Perforce, P4 is P4, MCP is MCP). A name that has no Latin spelling is "
    "written in Chinese characters. Take the name the context gives, not a literal copy of a "
    "garbled sound.",
    "60 Chinese characters",
    "20 Chinese characters",
)
_KO_NOTES = SummaryNotes(
    "summarize_map_ja_to.md",
    "- Write every field in Korean (한국어) in Hangul, never in Japanese and never with Chinese "
    "characters. Never leave kana in a note.\n"
    "- A product, company or tool name stays in Latin letters (パフォース, パーフォース, パフォッシャ and "
    "ビフォ are the product Perforce, P4 is P4, MCP is MCP). A name that has no Latin spelling is "
    "written in Latin letters. Take the name the context gives, not a literal copy of a garbled "
    "sound.",
    "60 Korean characters",
    "20 Korean characters",
)

_EN_EXAMPLE = (
    '{"translations": [{"id": 7, "text": "[[7]]Last month, I did something a bit [[8]]outrageous."}, '
    '{"id": 9, "text": "I shipped 2,000 PRs."}]}'
)
_ZH_CN_EXAMPLE = (
    '{"translations": [{"id": 7, "zh": "[[7]]上个月，我做了一件有点[[8]]离谱的事。"}, '
    '{"id": 9, "zh": "我提交了 2,000 个 PR。"}]}'
)
_KO_EXAMPLE = (
    '{"translations": [{"id": 7, "text": "[[7]]지난달에 저는 조금 [[8]]엉뚱한 일을 했습니다."}, '
    '{"id": 9, "text": "PR을 2,000개 올렸습니다."}]}'
)

ROUTES = MappingProxyType(
    {
        "en": TargetRoute(
            rules=_rules(
                "- Write English only. Never leave a kana or a kanji in the translation: a name "
                "that has no usual English spelling is written in Latin letters.",
                _names("English", _NAMES_LATIN),
                '"in order to solve this problem" or "therefore"',
                _EN_WORDING,
            ),
            leftover=(
                "- Translate every Japanese word except names, product names and technical terms "
                "that are normally written in Latin letters. Do not leave Japanese words or kana "
                "in the <<NAME>>."
            ),
            example=_EN_EXAMPLE,
            density=Density(4.2, 8, 0.3),
            problem=_english_problem,
            needs_script=_needs_script,
            clean=_unchanged,
            terms=EN_TERMS,
            notes=_ENGLISH_NOTES,
            on_failure=OnFailure.LEAVE_EMPTY,
        ),
        "zh-CN": TargetRoute(
            rules=_rules(
                "- Write every Japanese kanji in its Simplified form as used in Mainland China "
                "(気 becomes 气, 売 becomes 卖, 続 becomes 续, 圧 becomes 压). Never "
                "use Traditional characters, and never leave a kana or a kanji that only Japanese "
                "uses in the translation.",
                _names(
                    "Mainland China",
                    "is spelled in Simplified Chinese characters when it has no Latin spelling",
                ),
                "为了解决这个问题 or 因此",
                _ZH_CN_WORDING,
            ),
            leftover=(
                "- Translate every Japanese word except names, product names and technical terms "
                "that are normally written in Latin letters. Do not leave Japanese words or kana "
                "in the <<NAME>>."
            ),
            example=_ZH_CN_EXAMPLE,
            density=Density(1.4, 8, 0.15),
            problem=_simplified_problem,
            needs_script=_needs_script,
            clean=_middle_dot,
            terms=ZH_CN_TERMS,
            notes=_ZH_CN_NOTES,
            on_failure=OnFailure.LEAVE_EMPTY,
        ),
        "ko": TargetRoute(
            rules=_rules(
                "- Write Korean in Hangul only. Never leave a kana or a kanji in the translation, "
                "and never write a Chinese character.",
                _names("Korean", _NAMES_LATIN),
                "이 문제를 해결하기 위해 or 그래서",
                _KO_WORDING,
            ),
            leftover=(
                "- Translate every Japanese word except names, product names and technical terms "
                "that are normally written in Latin letters. Do not leave Japanese words or kana "
                "in the <<NAME>>."
            ),
            example=_KO_EXAMPLE,
            density=Density(1.9, 8, 0.3),
            problem=_korean_problem,
            needs_script=_needs_script,
            clean=_middle_dot,
            terms=KO_TERMS,
            notes=_KO_NOTES,
            on_failure=OnFailure.ENGLISH_PIVOT,
            experimental=True,
        ),
    }
)
