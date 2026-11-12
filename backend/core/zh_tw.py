from __future__ import annotations

import re
import unicodedata
from collections.abc import Callable

_MARK = r"(?:\[\[\d+\]\])?"


def _not_after(words: str) -> str:
    return "".join(f"(?<!{word})" for word in words.split("|"))


def _spaced(words: str) -> str:
    """Each word as written and as followed by a space, for a Latin word set off from Chinese."""
    return "|".join(f"{word}|{word} " for word in words.split("|"))


_SOFTWARE_NOUN = (
    "環境|選項|參數|檔案|程式碼庫|專案|變數|頁面|組態|權限|規則|偏好|伺服器|網路|代理|模型|工具|"
    "介面|系統|資料庫|帳號|帳戶|密碼|金鑰|路徑|連線|憑證|版本|快捷鍵|工作流程|管線|指令|提示|"
    "程式碼|程式|CI|CD|Docker|App"
)
_CLAUSE_CHAR = r"(?:[^，。？！、；：\s\[\]]|\[\[\d+\]\])"
_CONFIGURE_TAIL = "它們|它|好|為|成|選項|頁面|頁|畫面|選單|檔|面板|中|裡"
_CONFIGURE_HEAD = "進行|重新|完成|調整|更改|修改|變更|需要|無需|不用"
_NOT_PHYSICAL_RUN = _not_after(
    "地球|太陽|月球|行星|星球|星系|天體|軌道|列車|火車|機器|機械|時鐘|鐘錶"
)
_CHAT_APP = "Slack|Discord|Teams|Telegram|Reddit|Twitter|Gmail|Email|email|Mastodon|Bluesky"
_PROCEDURE_HEAD = (
    "法律|司法|行政|訴訟|議事|手續|正當|法定|作業|操作|審查|申請|審批|刑事|民事|聽證|立法|議會|"
    "標準|選舉|破產|仲裁|救濟|調解|審判|表決|針線|縫線"
)
_NOT_PROCEDURE = _not_after(_PROCEDURE_HEAD)


_ACCESSED = (
    "權限|控制|令牌|權杖|資料庫|資料|檔案|伺服器|端點|API|URL|網址|記憶體|資源|儲存庫|程式碼|金鑰|"
    "憑證|日誌|紀錄|目錄|帳號|帳戶|主機|裝置|硬體|系統|工具|介面"
)
_ACCESS_OF = "你的|我的|其|該|它的|它們的|這些|所有|整個|私有|公開|遠端|本機|本地|外部|內部|敏感"
_ACCESS_ENDS = r"(?:\Z|[^一-鿿]|中(?!心)|裡|內|上|時|並|而|來|去|和|與|或|及)"
_FOUNDED = (
    "公司|團隊|組織|企業|品牌|學校|基金會|國家|帝國|王朝|文明|新創|事業|協會|樂團|樂隊|宗教|流派|"
    "政黨|工作室|社團|俱樂部"
)
_NOT_FOUNDING = _not_after("共同|聯合")
_NOT_A_PORT = _not_after(
    _spaced("USB|HDMI|VGA|SATA|PCIe|-C|Lightning|Thunderbolt|DisplayPort")
    + "|"
    + "充電|耳機|電源|網線|音頻|音訊|串口|並口|硬體|物理|實體"
)
_NOT_A_SEARCH_PARTY = _not_after("警方|警察|地毯式")
_GAP = rf" ?{_MARK} ?"
_CALLED = "函式|函數|方法|API|模型|工具|介面|端點|服務|子程式|外掛"
_CALLER = "工具|函式|函數|方法|API|模型|系統|遞迴|遠端|重複|再次|多次"
_OPTIMIZED = "過|效能|程式|演算法|查詢|編譯|記憶體|速度|延遲|成本|提示|模型|渲染|載入"
_IMPORT_OBJECT = "模組|套件|程式庫|函式庫|依賴|相依|命名空間|類別|檔案|目錄|資料夾|函式"
_IMPORT_TARGET = (
    "(?:另一個|一個|同一個|這個|那個|該)?"
    "(?:渲染執行緒|主執行緒|執行緒|模組|套件|目錄|資料夾|檔案|程式碼庫|資料庫|記憶體)"
)
_IMPORT_OF = "(?:那些|所有|這些|這個|該|其|它們?的|的)?(?:[^，。？！；]{0,8}被導入的)?"
_IMPORT_PAIR = "(?:[和與及或](?:依賴|相依)(?!性?注入)|或(?:阻斷|阻止|禁止|限制)導入)"
_IMPORT_ENDS = (
    r"(?:\Z|[^一-鿿]|的|了|項|們|和|與|或|及|到|至|進|中(?!心)|裡|內|上|時|並|而|來|去|也|都)"
)
_WAREHOUSE = re.compile("貨|物流|庫存|出貨|商品|配送|倉儲|貨架|運輸|零售|電商|工廠|搬運|超市")
_CODE_REPOSITORY = re.compile(
    "程式碼|代碼|Git|GitHub|GitLab|分支|提交|合併|PR|CI|單一|克隆|開源|函式庫|monorepo|repo|技能|代理人"
)
_CUE_MARK = re.compile(r"\[\[\d+\]\]")


def _cue_of(match: re.Match[str]) -> str:
    """The cue the match is in. A reply that holds several cues is cut at the cue markers, so the
    grouping of cues never changes what a rule sees."""
    text = match.string
    start = max((m.end() for m in _CUE_MARK.finditer(text, 0, match.start())), default=0)
    after = _CUE_MARK.search(text, match.end())
    return text[start : after.start() if after else len(text)]


def _repository(match: re.Match[str]) -> str:
    """儲存庫 when the cue the word is in talks about code and not about goods."""
    cue = _cue_of(match)
    if _WAREHOUSE.search(cue) or not _CODE_REPOSITORY.search(cue):
        return match.group()
    return "儲存庫"


def _monorepo(match: re.Match[str]) -> str:
    """單一儲存倉 for a monorepo, unless the cue is about goods."""
    return match.group() if _WAREHOUSE.search(_cue_of(match)) else "單一儲存倉"


def _after(words: str) -> str:
    return "(?:" + "|".join(f"(?<={word})" for word in words.split("|")) + ")"


_TERMS: tuple[tuple[re.Pattern[str], str | Callable[[re.Match[str]], str]], ...] = tuple(
    (re.compile(pattern), replacement)
    for pattern, replacement in (
        ("程式代碼", "程式碼"),
        ("源代碼", "原始碼"),
        ("(?<![資能電水光熱泉])源碼(?!頭)", "原始碼"),
        ("運營(?!商)", "營運"),
        ("(?<![單一二三四五六七八九十百千萬億紀公美日])元(?:數據|資料)", "中繼資料"),
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


_ENGLISH_TERMS: tuple[tuple[re.Pattern[str], str | Callable[[re.Match[str]], str]], ...] = tuple(
    (re.compile(pattern), replacement)
    for pattern, replacement in (
        (
            f"訪問(?={_MARK}(?:了|到|過)?{_GAP}(?:{_ACCESS_OF})?(?:{_ACCESSED})+{_ACCESS_ENDS})",
            "存取",
        ),
        (
            f"{_NOT_FOUNDING}創建(?!者|人|於|時期|時代|了?[這那該一]?[家間個所]?(?:新的|新)?(?:{_FOUNDED}))",
            "建立",
        ),
        ("可視化", "視覺化"),
        ("存儲(?!器)", "儲存"),
        (f"{_NOT_A_SEARCH_PARTY}搜索(?!隊|令|票|救援|行動|[與和及]救援)", "搜尋"),
        (f"{_NOT_A_PORT}接口(?!卡|板|線|人|處)", "介面"),
        (
            f"(?:{_after(_spaced(_CALLER))})調用|調用(?=了?{_GAP}(?:{_CALLED}))",
            "呼叫",
        ),
        (f"(?:{_after('效能|性能')})優化|優化(?=了?(?:{_OPTIMIZED}))", "最佳化"),
        ("反饋(?!迴路|回路|環路|電路|放大)", "回饋"),
        (
            f"導入(?=(?:了|過)?{_GAP}{_IMPORT_OF}(?:{_IMPORT_OBJECT}){_IMPORT_ENDS})"
            f"|導入(?=(?:到|至|進){_GAP}(?:{_IMPORT_TARGET}){_IMPORT_ENDS})"
            f"|導入(?={_IMPORT_PAIR})",
            "匯入",
        ),
        ("單一(?:倉庫|儲存庫)", _monorepo),
        ("倉庫", _repository),
    )
)


_NOT_FACTORY_LINE = _not_after("生產|裝配|組裝|製造|工廠|工業|汽車")
_JAPANESE_TERMS: tuple[tuple[re.Pattern[str], str | Callable[[re.Match[str]], str]], ...] = (
    (
        re.compile("倉庫"),
        lambda m: m.group() if _WAREHOUSE.search(m.string) else "儲存庫",
    ),
    (re.compile(f"{_NOT_FACTORY_LINE}流水線"), "管線"),
)


def taiwan_terms_from_japanese(text: str) -> str:
    """Taiwan wording for words a Japanese talk gives that an English one does not: a code
    repository (リポジトリ) comes out as 倉庫 and a build pipeline (パイプライン) as 流水線. A
    text that talks about goods keeps its warehouse, and one about a factory its assembly line.
    Neither is in `taiwan_terms`, so the output of an English talk keeps them."""
    for pattern, taiwan in _JAPANESE_TERMS:
        text = pattern.sub(taiwan, text)
    return text


def taiwan_terms_from_english(text: str) -> str:
    """Taiwan wording for the Mainland words an English talk gives, and that a Japanese talk
    writes for another sense: 導入 is adopting something in Japanese, 訪問 is a visit or an
    interview, and 創建 and 搜索 are valid Chinese. Every rule here replaces only next to words
    that make the Mainland sense certain, and a missed word is better than a wrong one."""
    for pattern, taiwan in _ENGLISH_TERMS:
        text = pattern.sub(taiwan, text)
    return text


def taiwan_terms(text: str) -> str:
    """Replace Mainland computing terms with their Taiwan equivalents, for a talk in any
    language."""
    for pattern, taiwan in _TERMS:
        text = pattern.sub(taiwan, text)
    return text


def gb2312_hanzi() -> str:
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
    frozenset(char for char in gb2312_hanzi() if not in_big5(char)) - TRADITIONAL_BEYOND_BIG5
) | SIMPLIFIED_IN_BIG5


def simplified_chars(text: str) -> list[str]:
    return sorted(set(text) & SIMPLIFIED_ONLY)


CJK_TEXT = re.compile("[㐀-鿿　-〿＀-￯]")


def _jis_kanji() -> frozenset[str]:
    """The kanji of JIS X 0208 (levels 1 and 2), read from Shift JIS."""
    chars: set[str] = set()
    for lead in (*range(0x88, 0xA0), *range(0xE0, 0xEB)):
        for trail in (*range(0x40, 0x7F), *range(0x80, 0xFD)):
            try:
                char = bytes((lead, trail)).decode("cp932")
            except UnicodeDecodeError:
                continue
            if len(char) == 1 and unicodedata.name(char, "").startswith("CJK UNIFIED"):
                chars.add(char)
    return frozenset(chars)


JAPANESE_ONLY = (
    frozenset(char for char in _jis_kanji() if not in_big5(char))
    - SIMPLIFIED_ONLY
    - TRADITIONAL_BEYOND_BIG5
)
"""Kanji Japanese writes in its own way: in JIS, and neither in Big5 nor a Simplified character.
気, 売, 続 and 圧 are such, where Taiwan writes 氣, 賣, 續 and 壓."""


def japanese_only_chars(text: str) -> list[str]:
    return sorted(set(text) & JAPANESE_ONLY)


_SHINJITAI_PAIRS = (
    "気氣続續売賣録錄変變圧壓戦戰営營拡擴担擔検檢験驗険險剣劍県縣済濟参參児兒処處単單実實属屬帰歸"
    "弾彈恵惠悩惱応應荘莊称稱徴徵総總緑綠経經絵繪継繼絶絕覚覺観觀触觸証證訳譯読讀説說軽輕転轉辺邊"
    "遅遲郷鄉酔醉釈釋鉄鐵鋭銳関關闘鬥随隨隠隱雑雜頼賴顕顯駅驛騒騷髄髓麺麵黒黑齢齡歯齒竜龍糸絲縄繩"
    "圏圈塁壘壊壞壌壤増增壱壹奨獎嬢孃寛寬寝寢旧舊図圖価價倹儉偽僞剤劑勧勸励勵効效勲勳区區医醫卒卒"
    "厳嚴呉吳変變嘆嘆団團囲圍堕墮塩鹽増增声聲壮壯寿壽対對尽盡届屆岳嶽峡峽崎崎帯帶幣幣庁廳広廣庵庵"
    "従從徳德懐懷戸戶挙舉拠據拝拜揺搖摂攝撃擊数數斉齊条條栄榮桜櫻楽樂様樣権權欠缺歓歡歩步残殘殴毆"
    "毎每浄淨渋澀渓溪済濟湾灣潜潛瀬瀨炉爐焼燒犠犧猟獵獣獸獲獲琢琢画畫異異疎疏療療砕碎碑碑礼禮禅禪"
    "秘祕穏穩窃竊窓窗粋粹糧糧紀紀紹紹繊纖罰罰聴聽肉肉脳腦臓臟艶艷荘莊薬藥蔵藏虫蟲蛍螢衛衛装裝褒褒"
    "携攜会會点點国國学學発發当當万萬与與両兩亜亞悪惡覧覽訪訪設設説說謡謠豊豐賛贊践踐軟軟輸輸辞辭迫迫逓遞進進遊遊運運違違遺遺選選郵郵都都鉱礦録錄"
    "鍵鍵鎮鎮閉閉開開間間関關陥陷陰陰隣鄰雇僱霊靈静靜頭頭顔顏類類験驗鶏雞麦麥"
)
SHINJITAI: dict[str, str] = {
    new: old
    for new, old in zip(_SHINJITAI_PAIRS[0::2], _SHINJITAI_PAIRS[1::2], strict=True)
    if new != old and (new in JAPANESE_ONLY or new in SIMPLIFIED_ONLY)
}
"""Kanji Japanese writes in its own way, and the Simplified characters that are the same
character, with the Traditional character Taiwan writes. A model copies them from the Japanese,
and retrying seldom makes it stop."""


def traditional_from_japanese(text: str) -> str:
    return text.translate(str.maketrans(SHINJITAI))
