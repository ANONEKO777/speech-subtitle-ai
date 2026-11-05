from __future__ import annotations

import re

_MARK = r"(?:\[\[\d+\]\])?"
_SOFTWARE_NOUN = (
    "環境|選項|參數|檔案|程式碼庫|專案|變數|頁面|組態|權限|規則|偏好|伺服器|網路|代理|模型|工具|"
    "介面|系統|資料庫|帳號|帳戶|密碼|金鑰|路徑|連線|憑證|版本|快捷鍵|工作流程|管線|指令|提示|"
    "程式碼|程式|CI|CD|Docker|App"
)
_CLAUSE_CHAR = r"(?:[^，。？！、；：\s\[\]]|\[\[\d+\]\])"
_CONFIGURE_TAIL = "它們|它|好|為|成|選項|頁面|頁|畫面|選單|檔|面板|中|裡"
_CONFIGURE_HEAD = "進行|重新|完成|調整|更改|修改|變更|需要|無需|不用"
_NOT_PHYSICAL_RUN = "".join(
    f"(?<!{head})"
    for head in "地球|太陽|月球|行星|星球|星系|天體|軌道|列車|火車|機器|機械|時鐘|鐘錶".split("|")
)
_CHAT_APP = "Slack|Discord|Teams|Telegram|Reddit|Twitter|Gmail|Email|email|Mastodon|Bluesky"
_PROCEDURE_HEAD = (
    "法律|司法|行政|訴訟|議事|手續|正當|法定|作業|操作|審查|申請|審批|刑事|民事|聽證|立法|議會|"
    "標準|選舉|破產|仲裁|救濟|調解|審判|表決|針線|縫線"
)
_NOT_PROCEDURE = "".join(f"(?<!{head})" for head in _PROCEDURE_HEAD.split("|"))
_MARKDOWN_TOKEN = r"[^\s_*]+"


def _after(words: str) -> str:
    return "(?:" + "|".join(f"(?<={word})" for word in words.split("|")) + ")"


_TERMS: tuple[tuple[re.Pattern[str], str], ...] = tuple(
    (re.compile(pattern), replacement)
    for pattern, replacement in (
        ("程式代碼", "程式碼"),
        ("源代碼", "原始碼"),
        ("(?<![程源原])代碼", "程式碼"),
        ("用戶", "使用者"),
        ("(?<![個屬特人天本品習理感彈韌惰慣可])性能(?![夠否])", "效能"),
        ("(?<!演)算法", "演算法"),
        ("視頻", "影片"),
        ("軟件", "軟體"),
        ("(?<![相確堅深])信息", "資訊"),
        ("網絡", "網路"),
        ("默認", "預設"),
        ("服務器", "伺服器"),
        ("內存(?!在)", "記憶體"),
        ("屏幕", "螢幕"),
        ("鼠標", "滑鼠"),
        ("(?<![世外境眼視業各全學政商科地邊])界面(?![臨對])", "介面"),
        ("調試", "除錯"),
        ("拉取請求", "合併請求"),
        (f"設置(?={_CLAUSE_CHAR}{{0,6}}?(?:{_SOFTWARE_NOUN}))", "設定"),
        (f"設置(?={_MARK}(?:{_CONFIGURE_TAIL}))", "設定"),
        (f"{_after(_CONFIGURE_HEAD)}設置", "設定"),
        ("(?<=在)設置(?=中|裡)", "設定"),
        (f"{_NOT_PHYSICAL_RUN}運行", "執行"),
        ("(?<!大)數據(?!機)", "資料"),
        (f"{_after(_CHAT_APP)} ?線程", "討論串"),
        ("(?<![針縫])線程", "執行緒"),
        ("插件", "外掛"),
        ("(?<![小零])組件", "元件"),
        ("應用程序", "應用程式"),
        (f"{_NOT_PROCEDURE}程序(?!正義|員|性|法|違法|規則|規定|公正|問題)", "程式"),
    )
)

_WRAPPED_TOKEN = re.compile(
    rf"(?<![A-Za-z0-9_])_({_MARKDOWN_TOKEN})_(?![A-Za-z0-9_])"
    rf"|(?<![A-Za-z0-9*])(\*{{1,2}})({_MARKDOWN_TOKEN})\2(?![A-Za-z0-9*])"
)


def taiwan_terms(text: str) -> str:
    """Replace Mainland computing terms with their Taiwan equivalents."""
    for pattern, taiwan in _TERMS:
        text = pattern.sub(taiwan, text)
    return text


_LATIN_FILLER = re.compile(r"(?<![A-Za-z])(?:uh+|um+|hmm+)(?![A-Za-z])[,，]?\s*", re.IGNORECASE)
_YOU_KNOW_FILLER = re.compile(r"(?<![^，。？！\s])你知不知道(?=[，,\s]|$)[，,]?")
_ENGLISH_YOU_KNOW = re.compile(r"\byou know\b", re.IGNORECASE)
_ANY_YOU_KNOW_ZH = re.compile(r"你知不知道[，,]?\s*")
_DOUBLE_COMMA = re.compile(r"([，,])\s*[，,]+")
_LEADING_COMMA = re.compile(r"^[，,\s]+")


def drop_fillers(text: str, en: str = "") -> str:
    """Remove "uh" and "um" left in Latin letters, and the filler 你知不知道.

    When `en` is given and says "you know" without asking a question, every 你知不知道 is a
    filler. Otherwise only one standing alone between commas is dropped. A text that would be
    empty afterwards is returned unchanged."""
    cleaned = _LATIN_FILLER.sub("", text)
    if _ENGLISH_YOU_KNOW.search(en) and "?" not in en:
        cleaned = _ANY_YOU_KNOW_ZH.sub("", cleaned)
    else:
        cleaned = _YOU_KNOW_FILLER.sub("", cleaned)
    cleaned = _LEADING_COMMA.sub("", _DOUBLE_COMMA.sub(r"", cleaned)).strip()
    return cleaned if cleaned else text


def strip_markdown_emphasis(text: str) -> str:
    """Unwrap a token the model wrapped in _underscores_ or *asterisks*."""
    return _WRAPPED_TOKEN.sub(lambda m: m.group(1) or m.group(3), text)


def _gb2312_hanzi() -> str:
    chars: list[str] = []
    for lead in range(0xB0, 0xF8):
        for trail in range(0xA1, 0xFF):
            try:
                chars.append(bytes((lead, trail)).decode("gb2312"))
            except UnicodeDecodeError:
                continue
    return "".join(chars)


def in_big5(char: str) -> bool:
    try:
        char.encode("cp950")
    except UnicodeEncodeError:
        return False
    return True


TRADITIONAL_BEYOND_BIG5 = frozenset("肽麽")
SIMPLIFIED_IN_BIG5 = frozenset("么体厂")
SIMPLIFIED_ONLY = (
    frozenset(char for char in _gb2312_hanzi() if not in_big5(char)) - TRADITIONAL_BEYOND_BIG5
) | SIMPLIFIED_IN_BIG5


def simplified_chars(text: str) -> list[str]:
    return sorted(set(text) & SIMPLIFIED_ONLY)


CJK_TEXT = re.compile("[㐀-鿿　-〿＀-￯]")
