"""The Taiwan Chinese form of the terms a Japanese talk about software and games keeps using.

Each entry names a Japanese term (a regular expression over the cue with its line breaks removed),
the form Taiwan writes, and the wrong renderings a model gives for it (regular expressions over the
translation). The translation prompt is told the table and `scripts/p30_quality_check.py` counts it,
so each word is spelled once.
"""

from __future__ import annotations

import re
from collections.abc import Collection
from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class JaTerm:
    ja: str
    zh: str
    avoid: tuple[str, ...] = ()
    also: tuple[str, ...] = ()
    """Other forms Taiwan writes for it, which count as right."""
    literal: bool = True
    """`ja` is the text itself, not a pattern."""
    hint: str = ""
    """How the term reads in the prompt when `ja` is a pattern."""
    pattern: re.Pattern[str] = field(init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        source = re.escape(self.ja) if self.literal else self.ja
        object.__setattr__(self, "pattern", re.compile(source))

    @property
    def said(self) -> str:
        return self.ja if self.literal else self.hint

    def spans(self, src: str) -> list[tuple[int, int]]:
        """Where the term is in `src` with its line breaks removed."""
        return [match.span() for match in self.pattern.finditer(src.replace("\n", ""))]

    def in_source(self, src: str) -> bool:
        return self.pattern.search(src.replace("\n", "")) is not None

    def kept_in(self, zh: str) -> bool:
        """The translation has the Taiwan form and none of the wrong ones."""
        right = any(form.casefold() in zh.casefold() for form in (self.zh, *self.also))
        return right and not any(re.search(bad, zh) for bad in self.avoid)


def _idiom(hint: str, pattern: str, zh: str, *avoid: str, also: tuple[str, ...] = ()) -> JaTerm:
    return JaTerm(pattern, zh, avoid, also, literal=False, hint=hint)


_KATAKANA = "ァ-ヺーｦ-ﾟ"
_NOT_INSIDE_A_WORD = rf"(?<![{_KATAKANA}A-Za-z0-9])"
_CREATE_BRANCH = r"ブランチ[をが]?(?:\d+本)?切(?:る|っ|ら|ろ|り(?:出|ま|た|(?=[、。,]|\Z)))"
"""ブランチを切る, in the forms that create a branch (切り替え is a switch and does not match)."""
_NOT_A_BUILDING = "(?!店|敷地|土地|物件|住宅|ビル|建物|家|間取|道路)"
"""間口が広い店 and 間口が広い敷地 are about a frontage, not a game or a product that is easy to get
into. A frontage said as a predicate (この店は間口が広い) cannot be told apart and still matches."""
_NOT_A_COMPOUND = "(?<!電源)(?<!延長)(?<!Studio )(?<!studio )(?<!Claude )(?<!VS )"

SOFTWARE_TERMS: tuple[JaTerm, ...] = (
    _idiom(
        "ファイル",
        r"(?<!プロ)ファイル",
        "檔案",
        "(?<!說明)(?<!相關)(?<!技術)(?<!設計)文件",
        also=("檔",),
    ),
    JaTerm("フォルダ", "資料夾", ("文件夾",)),
    JaTerm("ブランチ", "分支", ("分枝",)),
    _idiom(
        "ブランチを切る (create a branch)",
        _CREATE_BRANCH,
        "建立分支",
        "切換",
        "切換分支",
    ),
    JaTerm("デフォルト", "預設", ("默認",)),
    _idiom(
        "デフォルトで無効 (disabled by default)",
        r"デフォルト(?:で|では)?は?無効",
        "預設停用",
        "無效",
        also=("預設關閉", "預設是關閉", "預設為關閉", "預設不啟用", "預設是停用", "預設為停用"),
    ),
    _idiom(
        "デフォルトで有効 (enabled by default)",
        r"デフォルト(?:で|では)?は?有効",
        "預設啟用",
        "有效",
        also=("預設開啟", "預設是開啟", "預設為開啟", "預設是啟用", "預設為啟用"),
    ),
    JaTerm("コードレビュー", "程式碼審查", ("(?<!程式)碼審",), ("程式碼審閱", "程式碼檢閱")),
    _idiom(
        "コースクリア型 (a game of stages)",
        r"(?:コース|ステージ)クリア(?:型|式)",
        "關卡制",
        "(?:賽道|關卡|賽程)清除",
        also=("過關制", "過關型", "關卡式"),
    ),
    _idiom("レビュー", r"(?<!プ)レビュー", "審查", also=("審閱", "檢閱")),
    _idiom(
        "間口が広く奥深い (easy to get into and deep)",
        r"(?:間口|マグチ)(?:が|の|は)?広くて?[、,]?奥深",
        "容易入門又深奧",
        "入口(?:低|門檻|寬|廣)",
        "(?:廣開|開闊的|寬廣的?)入口",
        "廣泛(?:且|而|又)?深",
        also=("入門簡單", "入門容易", "入門門檻低", "容易上手", "好上手", "易於入門"),
    ),
    _idiom(
        "間口が広い (easy to get into)",
        rf"(?:間口|マグチ)(?:が|の|は)?広(?:く|い|かっ){_NOT_A_BUILDING}",
        "容易入門",
        "入口(?:低|門檻|寬|廣)",
        "(?:廣開|開闊的|寬廣的?)入口",
        "廣泛(?:且|而|又)?深",
        also=("入門簡單", "入門容易", "入門門檻低", "門檻低", "容易上手", "好上手", "易於入門"),
    ),
    _idiom(
        "コード",
        rf"{_NOT_INSIDE_A_WORD}{_NOT_A_COMPOUND}コード(?!ネーム|レス|進行|譜)",
        "程式碼",
        "代碼",
        "(?<![式始誤條編解密證R ])碼",
    ),
    JaTerm("ソースコード", "原始碼", ("源碼",), ("原始程式碼",)),
    JaTerm("リポジトリ", "儲存倉", ("倉庫", "儲存庫", "存儲庫")),
    JaTerm("サブミット", "提交", ("送出",)),
    JaTerm("コミット", "提交", ("確認提交",)),
    JaTerm("チェックアウト", "簽出", ("檢查出", "簽出簽出")),
    JaTerm(
        "シェルブ",
        "擱置",
        ("(?i:shell)", "(?i:shelb)"),
        ("shelve", "shelving"),
    ),
    JaTerm("チェックリスト", "檢查清單", (), ("檢核表", "核對清單")),
    JaTerm("チェンジリスト", "變更清單", ("更改列表",), ("更改清單",)),
    _idiom("マージ", r"マージ(?!ン|ャン)", "合併", "融合"),
    JaTerm("ビルド", "建置", ("構建",)),
    JaTerm("スパースストリーム", "稀疏串流", ("稀疏流", "稀疏分支流")),
    JaTerm(
        "ストリーム",
        "串流",
        ("「流」", "(?<!串)流功能", "分支流", "(?<!串)流類型", "(?<!串)流機制"),
    ),
    JaTerm("アセット", "資產", (), ("素材",)),
    JaTerm("バージョン", "版本"),
    JaTerm("ユーザー", "使用者", ("用戶", "用户")),
    JaTerm("サーバー", "伺服器", ("服務器",)),
    JaTerm("ツール", "工具"),
    _idiom("データ", r"(?<!メタ)(?<!ビッグ)データ", "資料", "數據"),
    JaTerm("メタデータ", "中繼資料", ("元資料", "元數據")),
    JaTerm("プラグイン", "外掛", ("插件", "外掛程式")),
    JaTerm("ワークフロー", "工作流程", ("工作流(?!程)", "(?i:work ?flows?)"), ("作業流程",)),
    JaTerm("プロジェクト", "專案", ("項目",)),
    _idiom("ロック", r"(?<![ブクフグド])ロック(?!ダウン)", "鎖定", also=("上鎖",)),
    JaTerm("ステータス", "狀態"),
    JaTerm("ブラウザ", "瀏覽器"),
    JaTerm("コマンドライン", "命令列", ("指令行", "命令行")),
    JaTerm("ソフトウェア", "軟體", ("軟件",)),
    JaTerm("ネットワーク", "網路", ("網絡",)),
    _idiom("アクセス", r"(?<!交通)アクセス", "存取", "訪問"),
    _idiom("チャットGPT", r"チャット(?:GPT|gpt|ｇｐｔ)", "ChatGPT", "聊天 ?GPT", "對話 ?GPT"),
    _idiom(
        "クロードコード",
        r"クロード ?コード",
        "Claude Code",
        "克勞德",
        "(?i:Claude) ?(?:程式碼|代碼|碼)",
        "Cloud Code",
    ),
    _idiom("クロード", r"クロード", "Claude", "克勞德"),
    _idiom(
        "ビジュアルスタジオコード / Visual Studioコード",
        r"(?:ビジュアル|ヴィジュアル) ?スタジオ ?コード|(?i:visual) ?(?i:studio) ?コード",
        "Visual Studio Code",
        "(?i:Visual ?Studio) ?(?:程式碼|代碼|碼)",
    ),
    _idiom(
        "VSコード",
        r"(?<![A-Za-z])VS ?コード",
        "VS Code",
        "VS ?(?:程式碼|代碼|碼)",
    ),
    _idiom(
        "GitHubコパイロット",
        r"(?:GitHub|ギットハブ) ?コパイロット",
        "GitHub Copilot",
        "(?i:GitHub) ?(?:副駕駛|協同駕駛)",
    ),
    _idiom("コパイロット", r"コパイロット", "Copilot", "副駕駛", "協同駕駛"),
)

GAME_TERMS: tuple[JaTerm, ...] = (
    JaTerm("プレイヤー", "玩家", ("玩家者",)),
    JaTerm("カメラ", "攝影機", ("相機",)),
    _idiom("カービィ", r"カービ(?:ー|ィ)", "卡比", "柯比", "卡爾比"),
    _idiom(
        "フォーミング / ホーミング (homing: a shot that locks on to a target; "
        "speech recognition hears ホーミング as フォーミング in a talk about aiming)",
        rf"{_NOT_INSIDE_A_WORD}(?:フォ|ホ)ーミング",
        "自動鎖定",
        "組裝",
        "成型",
        "形成",
        "形狀",
        also=("追蹤", "自動瞄準"),
    ),
)

JA_TERMS: tuple[JaTerm, ...] = SOFTWARE_TERMS + GAME_TERMS


@dataclass(frozen=True, slots=True)
class SourceFix:
    """A rewrite of the translation that needs what the Japanese said: `wrong` becomes `right`
    when the sentence has `said` and not `unless`. The model writes the Mainland word for some
    terms in a way no prompt line stops, and the same Chinese word is right when the Japanese
    names something else."""

    said: re.Pattern[str]
    wrong: re.Pattern[str]
    right: str
    unless: re.Pattern[str] | None = None
    term: str = ""
    """The Japanese term whose glossary entry switches the rewrite off: a user who wrote their own
    translation for it chose that word."""


_NOT_AFTER = "".join(
    f"(?<!{word})"
    for word in (
        *("說明", "相關", "技術", "設計", "規格", "契約", "合約", "申請", "需求", "使用者"),
        *("API", "公", "證明", "正式", "官方", "法律"),
    )
)
"""A 文件 after one of these is a document (技術文件, 契約文件, 公文件), not a computer file."""
_FILE_NOT_DOCUMENT = re.compile(
    "ドキュメント|ドキュメンテーション|書類|文書|資料|文章|仕様書|設計書|契約書|説明書|報告書|証明書|議事録|論文"
    "|マニュアル|レポート|規格|(?i:README|PDF)"
)
_CHECK_OUT_NOT_DETECT = (
    "(?<!被)(?<!能)檢查出"
    "(?!現|來|了|問題|錯誤|異常|漏洞|缺陷|瑕疵|(?i:bug)|不|沒|[一兩二三四五六七八九十幾許多個])"
)
"""檢查出 is a check-out unless it reads as "found" (檢查出問題, 檢查出現, 被檢查出)."""

_EASY_WORDS = (
    "流[すしさ]|円滑|快適|軽快|サクサク|使いやすい|安定(?![度性])"
    "|(?<![音娯快])楽(?![しむ器曲譜団園天])"
)
_STREAM_NOT_SMOOTH = re.compile(
    "スムーズ|スムース|流暢|滑らか|なめらか|流れ|(?<!ワーク)フロー"
    "|メインストリーム|ダウンストリーム|アップストリーム|ストリームライン"
    rf"|ストリーム.{{0,12}}(?:{_EASY_WORDS})|(?:{_EASY_WORDS}).{{0,12}}ストリーム"
)
"""ストリーム is a stream (串流). A sentence that also says smooth or flow may mean 流暢 or 流動.
ワークフロー is a workflow and says neither. The loanwords with ストリーム inside (主流, 下流,
上流, a streamlined thing) are not a version-control stream. A word for easy, comfortable or
sending (円滑, 楽, 流す) counts only within 12 characters of ストリーム: a long sentence has
other things to call easy."""
_FLOW_WORDS = "流暢度?(?![地性])|流動(?![性作態畫向量速])"
_FLOW_WORD_ENDS = "主上下分合對逆水氣電暖寒潮洪河溪回交熱激金物人"
_STREAM_WRONG = re.compile(
    f"(?<=[的與和及跟或之])(?:{_FLOW_WORDS})"
    rf"|^(?:{_FLOW_WORDS})(?=$|[，。、,；！？\s或與和及跟])"
    f"|(?<!串)(?<![{_FLOW_WORD_ENDS}])流串(?![接聯連])"
    f"|(?<!串)(?<![{_FLOW_WORD_ENDS}])流(?=功能|類型|機制)"
)
"""What the model writes for ストリーム: 流暢 and 流動 (smooth, flowing) as a noun, after 的,
與, 和, 及, 跟, 或 or 之 or at the start of a cue, where its noun is not in the text (更流暢 and
流暢地 are an adjective and stay), 流串, or a bare 流 as a noun's first word (流功能). A 流 that
ends a word of its own (主流, 分流, 現金流, 物流, 人流) is not a stream, and 流暢 and 流動 followed
by a character that makes a longer word (流暢性, 流動量) stay. 串流動作 has a right 串流 in it."""
_SWITCH_BRANCH_WORDS = (
    "切り?[替換]",
    "切りかえ",
    "乗り?換",
    "乗りかえ",
    "スイッチ",
    "チェックアウト",
    "移動",
    "移[るりっすし]",
    "移行",
    "遷移",
    "変更",
    "変え",
    "戻[るりっすし]",
    "行[くきっ]",
    "入[るりっ]",
    "使い分け",
    "入れ替",
    "(?:その|別の|他の|元の)ブランチ",
    "ブランチ間",
)
_SWITCH_BRANCH = re.compile("|".join(_SWITCH_BRANCH_WORDS))
"""ブランチを切る with one of these in the unit is a switch as well as a creation, so a 切換分支
may be right. Any other way to say "move to another branch" is a miss of the rewrite, not damage."""
_LATIN_EDGE = r"A-Za-z0-9_./\\`-"
_LATIN_WORKFLOW = re.compile(
    rf"\s?(?<![{_LATIN_EDGE}])(?<![A-Za-z0-9]\s)(?:w|^W)orkflows?(?![{_LATIN_EDGE}])(?!\s[A-Za-z0-9])\s?"
    r"(?!(?:[^`]*`[^`]*`)*[^`]*`[^`]*\Z)"
)
"""A lone English workflow or workflows in running text. The ones in a file name (workflow.yml), a
path (.github/workflows), a variable (GITHUB_WORKFLOW), a code span, or a product or title
(Windows Workflow Foundation, GitHub Workflows) are not."""

SOURCE_FIXES: tuple[SourceFix, ...] = (
    SourceFix(
        re.compile("ファイル"),
        re.compile(f"{_NOT_AFTER}文件(?!夾)"),
        "檔案",
        unless=_FILE_NOT_DOCUMENT,
        term="ファイル",
    ),
    SourceFix(
        re.compile("チェックアウト"),
        re.compile(_CHECK_OUT_NOT_DETECT),
        "簽出",
        term="チェックアウト",
    ),
    SourceFix(
        re.compile("ストリーム"),
        _STREAM_WRONG,
        "串流",
        unless=_STREAM_NOT_SMOOTH,
        term="ストリーム",
    ),
    SourceFix(
        re.compile("スパースストリーム"),
        re.compile("稀疏流(?![程動暢量向性速派行通水氓])"),
        "稀疏串流",
        term="スパースストリーム",
    ),
    SourceFix(re.compile("ワークフロー"), _LATIN_WORKFLOW, "工作流程", term="ワークフロー"),
    SourceFix(
        re.compile(_CREATE_BRANCH),
        re.compile(r"切換(?=(?:\d+個|[一二兩三四五六七八九十]+個|新的)?分支)"),
        "建立",
        unless=_SWITCH_BRANCH,
        term="ブランチを切る",
    ),
)


def fix_from_source(zh: str, src: str, own_terms: Collection[str] = ()) -> str:
    """`zh` with the wrong forms of `SOURCE_FIXES` rewritten, for a translation of `src`. `src` is
    the whole sentence the translation belongs to, so a word the model put one cue out of place is
    still mended. A term in `own_terms` (the glossary's) keeps the user's word: its rewrite
    is off."""
    flat = src.replace("\n", "")
    for fix in SOURCE_FIXES:
        if fix.term in own_terms:
            continue
        if fix.said.search(flat) and not (fix.unless and fix.unless.search(flat)):
            zh = fix.wrong.sub(fix.right, zh)
    return zh
