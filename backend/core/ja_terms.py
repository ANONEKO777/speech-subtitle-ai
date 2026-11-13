"""The Taiwan Chinese form of the terms a Japanese talk about software and games keeps using.

Each entry names a Japanese term (a regular expression over the cue with its line breaks removed),
the form Taiwan writes, and the wrong renderings a model gives for it (regular expressions over the
translation). The translation prompt is told the table and `scripts/p30_quality_check.py` counts it,
so each word is spelled once.
"""

from __future__ import annotations

import re
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

    def in_source(self, src: str) -> bool:
        return self.pattern.search(src.replace("\n", "")) is not None

    def kept_in(self, zh: str) -> bool:
        """The translation has the Taiwan form and none of the wrong ones."""
        right = any(form.casefold() in zh.casefold() for form in (self.zh, *self.also))
        return right and not any(re.search(bad, zh) for bad in self.avoid)


def _idiom(hint: str, pattern: str, zh: str, *avoid: str) -> JaTerm:
    return JaTerm(pattern, zh, avoid, literal=False, hint=hint)


SOFTWARE_TERMS: tuple[JaTerm, ...] = (
    JaTerm("ファイル", "檔案", ("文件",)),
    JaTerm("フォルダ", "資料夾", ("文件夾",)),
    JaTerm("ブランチ", "分支", ("分枝",)),
    _idiom(
        "ブランチを切る (create a branch)",
        r"ブランチ[をが]?(?:\d+本)?切",
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
    ),
    _idiom(
        "デフォルトで有効 (enabled by default)",
        r"デフォルト(?:で|では)?は?有効",
        "預設啟用",
        "有效",
    ),
    JaTerm("コードレビュー", "程式碼審查", ("(?<!程式)碼審", "審閱")),
    _idiom("レビュー", r"(?<!プ)レビュー", "審查", "審閱"),
    _idiom(
        "コード", r"(?<!ソース)(?<!エン)(?<!デ)コード", "程式碼", "代碼", "(?<!程式)(?<!原始)碼"
    ),
    JaTerm("ソースコード", "原始碼", ("源碼", "原始程式碼")),
    JaTerm("リポジトリ", "儲存倉", ("倉庫", "儲存庫", "存儲庫")),
    JaTerm("サブミット", "提交", ("送出",)),
    JaTerm("コミット", "提交", ("確認提交",)),
    JaTerm("チェックアウト", "簽出", ("檢查出", "簽出簽出")),
    JaTerm("チェックリスト", "檢查清單", ("核對清單",), ("檢核表",)),
    JaTerm("チェンジリスト", "變更清單", ("更改清單", "更改列表")),
    JaTerm("マージ", "合併", ("融合",)),
    JaTerm("ビルド", "建置", ("構建",)),
    JaTerm("スパースストリーム", "稀疏串流", ("稀疏流", "稀疏分支流")),
    JaTerm("ストリーム", "串流", ("「流」", "流功能", "分支流", "流類型", "(?<!串)流機制")),
    JaTerm("管理者", "管理員", ("管理者",)),
    JaTerm("アセット", "資產", ("素材",)),
    JaTerm("バージョン", "版本"),
    JaTerm("ユーザー", "使用者", ("用戶", "用户")),
    JaTerm("サーバー", "伺服器", ("服務器", "伺服端")),
    JaTerm("ツール", "工具"),
    JaTerm("データ", "資料", ("數據",)),
    JaTerm("メタデータ", "中繼資料", ("元資料", "元數據")),
    JaTerm("プラグイン", "外掛", ("插件",)),
    JaTerm("ワークフロー", "工作流程", ("工作流(?!程)",), ("作業流程",)),
    JaTerm("プロジェクト", "專案", ("項目",)),
    _idiom("ロック", r"(?<![ブクフグ])ロック", "鎖定", "上鎖"),
    JaTerm("ステータス", "狀態"),
    JaTerm("ブラウザ", "瀏覽器"),
    JaTerm("コマンドライン", "命令列", ("指令行", "命令行")),
    JaTerm("ソフトウェア", "軟體", ("軟件",)),
    JaTerm("ネットワーク", "網路", ("網絡",)),
    _idiom("チャットGPT", r"チャット(?:GPT|gpt|ｇｐｔ)", "ChatGPT", "聊天 ?GPT", "對話 ?GPT"),
    _idiom("クロード", r"クロード", "Claude", "克勞德"),
    _idiom("コパイロット", r"コパイロット", "Copilot", "副駕駛", "協同駕駛"),
)

GAME_TERMS: tuple[JaTerm, ...] = (
    JaTerm("プレイヤー", "玩家", ("玩家者",)),
    JaTerm("カメラ", "攝影機", ("相機",)),
    _idiom("カービィ", r"カービ(?:ー|ィ)", "卡比", "柯比", "卡爾比"),
)

JA_TERMS: tuple[JaTerm, ...] = SOFTWARE_TERMS + GAME_TERMS
