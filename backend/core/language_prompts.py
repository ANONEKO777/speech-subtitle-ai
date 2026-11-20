"""The wording each target language gives the translation and summary prompts."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Prompt:
    """What `prompts/translate.md` needs to know about one target language.

    `target` completes "Translate English subtitles ... into ...". `name` stands for the language
    in the rules, and `reply_name` in the reply shape. `key` is the field the reply puts the
    translation in. `example` is the reply to the prompt's worked example. `style` is the
    language's own rules, one "- " bullet per line. The last three finish the bullet about spoken
    fillers."""

    target: str
    name: str
    reply_name: str
    key: str
    example: str
    style: str
    filler_not: str
    you_know: str
    filler_cue: str


@dataclass(frozen=True, slots=True)
class SummaryText:
    """The summary prompt's language rule, and the headings of the written `summary` file."""

    rule: str
    title: str
    chapters: str
    key_points: str
    takeaways: str
    missing: str
    separator: str


def _plain(language: str) -> str:
    return f"Write every field in {language}. Keep names, products and code in their original spelling."


_NO_LATIN = ": never write them in Latin letters or as a filler sound"
_LATIN = ", and never write a filler sound in their place"
_LITERAL = ", or written with a short natural equivalent; never translate it as a literal question"


def _prompt(
    target: str, name: str, example: str, style: str, filler_cue: str, *, latin: bool
) -> Prompt:
    return Prompt(
        target,
        name,
        name,
        "text",
        example,
        style,
        _LATIN if latin else _NO_LATIN,
        _LITERAL,
        filler_cue,
    )


ZH_TW_PROMPT = Prompt(
    target="Traditional Chinese as used in Taiwan (繁體中文, 台灣慣用語)",
    name="Chinese",
    reply_name="Traditional Chinese",
    key="zh",
    example='{"translations": [{"id": 7, "zh": "[[7]]所以上個月，我做了一件相當[[8]]瘋狂的事。"}, {"id": 9, "zh": "我送出了 2,000 個 PR。"}]}',
    style='- Write Traditional Chinese characters only (這, 們, 說, 為, 國, 來). Never use Simplified characters.\n- Use Taiwan vocabulary, not Mainland China vocabulary. Examples: 影片 (not 視頻), 軟體 (not 軟件), 程式 (not 程序), 程式碼 (not 代碼), 資料 (not 數據), 網路 (not 網絡), 伺服器 (not 服務器), 滑鼠 (not 鼠標), 螢幕 (not 屏幕), 記憶體 (not 內存), 品質 (not 質量), 專案 (not 項目), 預設 (not 默認), 支援 (not 支持), 使用者 (not 用戶), 介面 (not 界面), 演算法 (not 算法), 資料庫 (not 數據庫), 檔案 (not 文件), 效能 (not 性能), 最佳化 (not 優化), 部落格 (not 博客), 打造 or 建立 (not 搭建), 透過 (not 通過), 當機 (not 死機), 平台 (not 平臺), 開發者 or 工程師 (not 程序員), 執行 (not 運行, as in running software), 設定 (not 設置, as in configuring software), 執行緒 (not 線程), 應用程式 (not 應用程序), 除錯 (not 調試), 資訊 (not 信息). Chat threads such as a Slack thread are 討論串. "Tech debt" is 技術債.\n- Write a "pull request" as "PR" or "合併請求", never as 拉取請求.\n- Use full-width Chinese punctuation (，。？！：；「」). Put a space between Chinese text and Latin letters or digits only when it keeps the line readable.\n',
    filler_not=": never write them in Latin letters or as 嗯 or 呃",
    you_know=", or written 你知道的, 就是 or 對吧; never write it as 你知不知道",
    filler_cue="嗯，",
)
ZH_TW_SUMMARY = SummaryText(
    rule=(
        "Write every field in Traditional Chinese as used in Taiwan (繁體中文, 台灣慣用語), never "
        "Simplified characters. Use Taiwan vocabulary: 影片 (not 視頻), 軟體 (not 軟件), 程式 "
        "(not 程序), 資料 (not 數據), 伺服器, 使用者, 專案, 設定, 執行, 效能. Keep names, "
        "products and code in their original spelling."
    ),
    title="重點整理",
    chapters="章節",
    key_points="關鍵觀點",
    takeaways="結論與金句",
    missing="未涵蓋時段",
    separator="：",
)
EN_SUMMARY = SummaryText(
    rule="Write every field in English.",
    title="Summary",
    chapters="Chapters",
    key_points="Key points",
    takeaways="Takeaways",
    missing="Not covered",
    separator=": ",
)


def _ex(first: str, second: str, key: str = "text") -> str:
    return (
        f'{{"translations": [{{"id": 7, "{key}": "[[7]]{first}"}}, '
        f'{{"id": 9, "{key}": "{second}"}}]}}'
    )


PROMPTS: dict[str, Prompt] = {
    "zh-TW": ZH_TW_PROMPT,
    "zh-CN": Prompt(
        target="Simplified Chinese as used in Mainland China (简体中文)",
        name="Chinese",
        reply_name="Simplified Chinese",
        key="zh",
        example=_ex("所以上个月，我做了一件相当[[8]]疯狂的事。", "我提交了 2,000 个 PR。", "zh"),
        style=(
            "- Write Simplified Chinese characters only (这, 们, 说, 为, 国, 来). Never use "
            "Traditional characters.\n"
            "- Use Mainland China vocabulary for technical terms. Examples: 视频, 软件, 程序, "
            "代码, 数据, 网络, 服务器, 鼠标, 屏幕, 内存, 质量, 项目, 默认, 支持, 用户, 界面, "
            "算法, 数据库, 文件, 性能, 优化.\n"
            "- Use full-width Chinese punctuation (，。？！：；“”). Put a space between Chinese "
            "text and Latin letters or digits only when it keeps the line readable.\n"
        ),
        filler_not=": never write them in Latin letters or as 嗯 or 呃",
        you_know=", or written 你知道的, 就是 or 对吧; never write it as 你知不知道",
        filler_cue="嗯，",
    ),
    "en": _prompt(
        "English",
        "English",
        _ex("So last month, I did something pretty [[8]]crazy.", "I shipped 2,000 PRs."),
        "- Write natural, spoken English as engineers say it in a talk. Keep one consistent "
        "register.\n"
        "- Write technical terms the way English-speaking engineers do (commit, pull request, "
        "server, database) and keep names, products and code in their original spelling.\n",
        "Um,",
        latin=True,
    ),
    "ja": _prompt(
        "Japanese (日本語)",
        "Japanese",
        _ex("先月、私はかなり[[8]]クレイジーなことをしました。", "2,000件のPRを出しました。"),
        "- Write natural spoken Japanese in kana and kanji. Use the polite です・ます style "
        "unless the speaker is clearly casual, and keep one style throughout. Never write "
        "Chinese-only forms.\n"
        "- Write technical terms the way Japanese engineers do (ソフトウェア, サーバー, "
        "データベース) and keep well-known acronyms in Latin letters.\n"
        "- Use Japanese punctuation (、。？！「」). Do not put spaces between Japanese text and "
        "Latin letters or digits.\n",
        "ええと、",
        latin=False,
    ),
    "ko": _prompt(
        "Korean (한국어)",
        "Korean",
        _ex("그래서 지난달에 저는 꽤 [[8]]엉뚱한 일을 했습니다.", "PR을 2,000개 올렸습니다."),
        "- Write natural spoken Korean in Hangul. Use the polite 합니다/해요 style and keep one "
        "style throughout. Do not use Chinese characters or Japanese kana.\n"
        "- Write technical terms the way Korean engineers do (소프트웨어, 서버, 데이터베이스) and "
        "keep well-known acronyms in Latin letters.\n"
        "- Use standard Korean punctuation (, . ? !) and Korean word spacing.\n",
        "음, ",
        latin=False,
    ),
    "es": _prompt(
        "Spanish (español)",
        "Spanish",
        _ex("El mes pasado hice algo bastante [[8]]loco.", "Envié 2,000 PR."),
        "- Write natural, spoken Spanish that every Spanish speaker understands. Open questions "
        "and exclamations with ¿ and ¡. Address the audience in one consistent form.\n"
        "- Keep technical terms Spanish-speaking engineers use in English (software, commit, pull "
        "request) and translate the rest (archivo, servidor, base de datos).\n",
        "Eh, ",
        latin=True,
    ),
    "fr": _prompt(
        "French (français)",
        "French",
        _ex("Le mois dernier, j'ai fait un truc assez [[8]]fou.", "J'ai livré 2 000 PR."),
        '- Write natural, spoken French. Address the audience with "vous" throughout. Put a '
        "space before ?, !, : and ;.\n"
        "- Keep technical terms French engineers use in English (commit, pull request) and "
        "translate the rest (fichier, serveur, base de données).\n",
        "Euh, ",
        latin=True,
    ),
    "de": _prompt(
        "German (Deutsch)",
        "German",
        _ex(
            "Letzten Monat habe ich etwas ziemlich [[8]]Verrücktes getan.",
            "Ich habe 2.000 PRs veröffentlicht.",
        ),
        "- Write natural, spoken German. Use the form of address that fits a conference talk and "
        "keep it throughout.\n"
        "- Keep technical terms German engineers use in English (Commit, Pull Request) and "
        "translate the rest (Datei, Server, Datenbank). Write compound nouns the German way.\n",
        "Äh, ",
        latin=True,
    ),
    "pt": _prompt(
        "Brazilian Portuguese (português do Brasil)",
        "Portuguese",
        _ex("No mês passado, fiz algo bem [[8]]maluco.", "Enviei 2.000 PRs."),
        "- Write natural, spoken Brazilian Portuguese. Address the audience in one consistent "
        "form.\n"
        "- Keep technical terms Brazilian engineers use in English (commit, pull request) and "
        "translate the rest (arquivo, servidor, banco de dados).\n",
        "Hum, ",
        latin=True,
    ),
    "it": _prompt(
        "Italian (italiano)",
        "Italian",
        _ex("Il mese scorso ho fatto una cosa piuttosto [[8]]pazza.", "Ho consegnato 2.000 PR."),
        "- Write natural, spoken Italian. Address the audience in one consistent form.\n"
        "- Keep technical terms Italian engineers use in English (commit, pull request) and "
        "translate the rest the way Italian engineers do.\n",
        "Ehm, ",
        latin=True,
    ),
    "ru": _prompt(
        "Russian (русский)",
        "Russian",
        _ex("В прошлом месяце я сделал кое-что довольно [[8]]безумное.", "Я отправил 2000 PR."),
        "- Write natural, spoken Russian in Cyrillic. Address the audience in one consistent "
        "form.\n"
        "- Write technical terms the way Russian engineers do (программное обеспечение, сервер, "
        "база данных) and keep well-known names and acronyms in Latin letters.\n"
        "- Use Russian punctuation and « » for quotations.\n",
        "Эм, ",
        latin=False,
    ),
    "vi": _prompt(
        "Vietnamese (Tiếng Việt)",
        "Vietnamese",
        _ex("Tháng trước, tôi đã làm một việc khá [[8]]điên rồ.", "Tôi đã gửi 2.000 PR."),
        "- Write natural, spoken Vietnamese with every diacritic. Address the audience in one "
        "consistent form.\n"
        "- Write technical terms the way Vietnamese engineers do (phần mềm, máy chủ, cơ sở dữ "
        "liệu) and keep well-known acronyms in Latin letters.\n",
        "Ừm, ",
        latin=True,
    ),
    "th": _prompt(
        "Thai (ไทย)",
        "Thai",
        _ex("เดือนที่แล้วฉันทำเรื่องที่ค่อนข้าง[[8]]บ้าบิ่น", "ฉันส่ง PR ไป 2,000 รายการ"),
        "- Write natural, spoken Thai in Thai script. Keep one consistent level of politeness.\n"
        "- Write technical terms the way Thai engineers do (ซอฟต์แวร์, เซิร์ฟเวอร์, ฐานข้อมูล) "
        "and keep well-known acronyms in Latin letters.\n"
        "- Separate phrases and sentences with spaces, not with English punctuation.\n",
        "เอ่อ ",
        latin=False,
    ),
    "id": _prompt(
        "Indonesian (Bahasa Indonesia)",
        "Indonesian",
        _ex("Bulan lalu, saya melakukan sesuatu yang cukup [[8]]gila.", "Saya mengirim 2.000 PR."),
        "- Write natural, conversational standard Indonesian. Address the audience in one "
        "consistent form.\n"
        "- Keep technical terms Indonesian engineers use in English (commit, pull request) and "
        "translate the rest (berkas, server, basis data).\n",
        "Eh, ",
        latin=True,
    ),
}


def _summary(language: str, *labels: str, sep: str = ": ") -> SummaryText:
    return SummaryText(_plain(language), *labels, separator=sep)


SUMMARIES: dict[str, SummaryText] = {
    "zh-TW": ZH_TW_SUMMARY,
    "en": EN_SUMMARY,
    "zh-CN": SummaryText(
        "Write every field in Simplified Chinese as used in Mainland China (简体中文), never "
        "Traditional characters. Keep names, products and code in their original spelling.",
        "重点整理",
        "章节",
        "关键观点",
        "结论与金句",
        "未涵盖时段",
        "：",
    ),
    "ja": _summary(
        "Japanese", "要点まとめ", "章", "重要なポイント", "結論と名言", "未対応の区間", sep="："
    ),
    "ko": _summary("Korean", "핵심 요약", "챕터", "핵심 포인트", "결론과 명언", "다루지 못한 구간"),
    "es": _summary("Spanish", "Resumen", "Capítulos", "Puntos clave", "Conclusiones", "Sin cubrir"),
    "fr": _summary(
        "French", "Résumé", "Chapitres", "Points clés", "À retenir", "Non couvert", sep=" : "
    ),
    "de": _summary(
        "German", "Zusammenfassung", "Kapitel", "Kernaussagen", "Fazit", "Nicht abgedeckt"
    ),
    "pt": _summary(
        "Brazilian Portuguese", "Resumo", "Capítulos", "Pontos-chave", "Conclusões", "Não coberto"
    ),
    "it": _summary(
        "Italian", "Riepilogo", "Capitoli", "Punti chiave", "Conclusioni", "Non coperto"
    ),
    "ru": _summary(
        "Russian", "Краткое содержание", "Главы", "Ключевые мысли", "Выводы", "Не охвачено"
    ),
    "vi": _summary("Vietnamese", "Tóm tắt", "Chương", "Điểm chính", "Kết luận", "Chưa bao quát"),
    "th": _summary("Thai", "สรุปประเด็นสำคัญ", "บท", "ประเด็นหลัก", "ข้อสรุป", "ช่วงที่ไม่ครอบคลุม"),
    "id": _summary("Indonesian", "Ringkasan", "Bab", "Poin utama", "Kesimpulan", "Tidak tercakup"),
}
