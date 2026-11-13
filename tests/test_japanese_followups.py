"""P32: product names that stay in Latin letters, the rewrites that read the Japanese, the
Perforce aliases a user overrides and the plug-in word. The sentences are invented."""

from __future__ import annotations

import json
import re
from collections.abc import Sequence

import pytest
from test_japanese_terms import named_lines, table_terms_in, term

from backend.core import translate
from backend.core.ja_terms import fix_from_source
from backend.core.languages import get as get_language
from backend.core.model import Cue
from backend.core.source_langs import ENGLISH_SOURCE, JAPANESE_SOURCE, MIXED_SOURCE, SourceLanguage
from backend.core.translate import GlossaryEntry, glossary_for
from backend.llm.client import Message

VISUAL_STUDIO_CODE = "ビジュアルスタジオコード / Visual Studioコード"


def cues_of(*texts: str, lang: str = "ja") -> list[Cue]:
    return [Cue(i, i * 2000, i * 2000 + 1500, t, lang=lang) for i, t in enumerate(texts, 1)]


def translated(
    cues: list[Cue],
    replies: Sequence[str],
    glossary: Sequence[GlossaryEntry] = (),
    source: SourceLanguage = JAPANESE_SOURCE,
    batch_size: int = 10,
) -> list[str]:
    """Each reply is the `zh` of the entry that starts the next request."""
    answers = iter(replies)

    def chat(messages: Sequence[Message], temperature: float) -> str:
        asked = json.loads(messages[-1]["content"])["translate"]
        return json.dumps({"translations": [{"id": asked[0]["id"], "zh": next(answers)}]})

    done = translate.run(
        cues,
        chat,
        glossary,
        batch_size=batch_size,
        max_retries=0,
        sleep=lambda _: None,
        keep_english=True,
        source=source,
    )
    return [cue.zh for cue in done]


class TestProductNames:
    @pytest.mark.parametrize(
        ("text", "said", "right", "wrong"),
        [
            (
                "夜にクロードコードを動かす",
                "クロードコード",
                "晚上跑Claude Code",
                "晚上跑Claude程式碼",
            ),
            ("クロード コードを使う", "クロードコード", "Claude Code", "Claude 程式碼"),
            ("クロードコードを使う", "クロードコード", "Claude Code", "克勞德 Code"),
            (
                "ビジュアルスタジオコードを開く",
                VISUAL_STUDIO_CODE,
                "開啟Visual Studio Code",
                "開啟Visual Studio碼",
            ),
            (
                "Visual Studioコードを開く",
                VISUAL_STUDIO_CODE,
                "visual studio code",
                "Visual Studio 程式碼",
            ),
            (
                "visual studioコードの拡張",
                VISUAL_STUDIO_CODE,
                "Visual Studio Code",
                "visual studio 代碼",
            ),
            ("VSコードで開く", "VSコード", "在VS Code開啟", "在VS 程式碼開啟"),
            ("GitHubコパイロットを使う", "GitHubコパイロット", "GitHub Copilot", "GitHub 副駕駛"),
        ],
    )
    def test_a_product_name_is_a_table_term_and_its_translation_by_meaning_is_wrong(
        self, text: str, said: str, right: str, wrong: str
    ) -> None:
        assert said in table_terms_in(text)
        assert term(said).kept_in(right)
        assert not term(said).kept_in(f"{right}，{wrong}")

    @pytest.mark.parametrize(
        "text",
        [
            "クロードコードを使う",
            "Visual Studioコードを開く",
            "Visual Studio コードを開く",
            "visual studio コードを開く",
            "VSコードで開く",
            "VS コードで開く",
        ],
    )
    def test_the_plain_code_line_is_not_named_for_a_product(self, text: str) -> None:
        assert "コード" not in table_terms_in(text)

    def test_the_plain_code_line_still_names_ordinary_code(self) -> None:
        assert "コード" in table_terms_in("このコードを直します")

    def test_a_request_tells_the_model_the_product_name(self) -> None:
        lines = named_lines("クロードコードに聞きます")
        assert '- "クロードコード" must be translated as "Claude Code"' in lines

    def test_the_prompt_does_not_tell_the_model_what_to_do_with_the_word_code(self) -> None:
        text = translate.system_prompt_template(get_language("zh-TW"), JAPANESE_SOURCE)
        assert "コード of" not in text
        assert "never translate the コード" not in text

    def test_the_prompt_rule_names_the_two_products(self) -> None:
        text = translate.system_prompt_template(get_language("zh-TW"), JAPANESE_SOURCE)
        assert "クロードコード is Claude Code" in text
        assert "ビジュアルスタジオコード is Visual Studio Code" in text


class TestFileWordFollowsTheJapanese:
    @pytest.mark.parametrize(
        ("src", "zh", "want"),
        [
            ("ファイルを送ります", "傳送文件", "傳送檔案"),
            ("JSONファイルを読みます", "讀取JSON文件。", "讀取JSON檔案。"),
            ("ファイルとフォルダ", "文件和文件夾", "檔案和文件夾"),
            ("ファイルの説明です", "請看說明文件和文件", "請看說明文件和檔案"),
            ("ファイルです", "技術文件、設計文件、相關文件", "技術文件、設計文件、相關文件"),
        ],
    )
    def test_a_file_cue_gets_the_taiwan_word(self, src: str, zh: str, want: str) -> None:
        assert fix_from_source(zh, src) == want

    @pytest.mark.parametrize("document_word", ["ドキュメント", "書類", "文書", "資料", "文章"])
    def test_a_real_document_sense_keeps_the_word(self, document_word: str) -> None:
        src = f"ファイルと{document_word}を見ます"
        assert fix_from_source("看檔案和文件", src) == "看檔案和文件"

    def test_a_cue_without_the_japanese_file_word_is_never_touched(self) -> None:
        assert fix_from_source("請提供文件", "お願いします") == "請提供文件"

    def test_a_line_break_inside_the_word_does_not_hide_it(self) -> None:
        assert fix_from_source("傳送文件", "ファ\nイルを送ります") == "傳送檔案"

    def test_the_rewrite_is_idempotent(self) -> None:
        once = fix_from_source("傳送文件", "ファイルを送ります")
        assert fix_from_source(once, "ファイルを送ります") == once

    @pytest.mark.parametrize(
        "kept",
        [
            "規格文件",
            "契約文件",
            "合約文件",
            "公文件",
            "證明文件",
            "正式文件",
            "官方文件",
            "法律文件",
            "申請文件",
            "需求文件",
            "使用者文件",
            "API文件",
            "技術文件",
            "文件夾",
        ],
    )
    def test_a_real_document_is_never_rewritten_in_a_unit_that_says_file(self, kept: str) -> None:
        assert fix_from_source(f"請看{kept}和文件", "ファイルを送ります") == f"請看{kept}和檔案"

    @pytest.mark.parametrize(
        "document_word",
        [
            "ドキュメンテーション",
            "仕様書",
            "設計書",
            "契約書",
            "説明書",
            "取扱説明書",
            "マニュアル",
            "レポート",
            "報告書",
            "議事録",
            "論文",
            "規格",
            "証明書",
            "公文書",
            "README",
            "readme",
            "PDF",
            "資料",
        ],
    )
    def test_a_unit_that_names_a_document_in_japanese_keeps_the_word(
        self, document_word: str
    ) -> None:
        src = f"ファイルと{document_word}です"
        assert fix_from_source("看檔案和文件", src) == "看檔案和文件"

    @pytest.mark.parametrize(
        ("zh", "want"),
        [
            ("文件格式", "檔案格式"),
            ("搬移三份文件", "搬移三份檔案"),
            ("exe文件", "exe檔案"),
            ("文件和文件", "檔案和檔案"),
        ],
    )
    def test_a_computer_file_in_a_file_unit_is_still_rewritten(self, zh: str, want: str) -> None:
        assert fix_from_source(zh, "ファイルの話です") == want

    @pytest.mark.parametrize(
        ("zh", "want"),
        [
            ("取消檢查出再上鎖", "取消簽出再上鎖"),
            ("目前檢查出的檔案", "目前簽出的檔案"),
            ("檢查出和提交", "簽出和提交"),
        ],
    )
    def test_a_check_out_is_rewritten_in_a_check_out_unit(self, zh: str, want: str) -> None:
        assert fix_from_source(zh, "チェックアウトします") == want

    @pytest.mark.parametrize(
        "zh",
        [
            "檢查出現問題",
            "沒有檢查出來",
            "檢查出了三個錯誤",
            "檢查出問題",
            "被檢查出漏洞",
            "能檢查出異常",
            "檢查出兩個bug",
            "檢查出Bug",
            "檢查出許多缺陷",
            "檢查出錯誤",
            "檢查出漏洞",
            "檢查出異常",
            "被檢查出的人",
            "能檢查出的事",
            "檢查出瑕疵",
            "檢查出不一致",
            "檢查出沒有人用的設定",
            "檢查出缺陷",
        ],
    )
    def test_a_check_that_found_something_is_not_a_check_out(self, zh: str) -> None:
        assert fix_from_source(zh, "チェックアウトします") == zh

    @pytest.mark.parametrize("count", list("一兩二三四五六七八九十幾許多個"))
    def test_a_check_that_found_a_number_of_things_is_not_a_check_out(self, count: str) -> None:
        zh = f"檢查出{count}處"
        assert fix_from_source(zh, "チェックアウトします") == zh

    def test_a_mixed_talk_english_cue_with_the_word_is_not_rewritten_by_a_japanese_cue(
        self,
    ) -> None:
        cues = [
            Cue(1, 0, 1500, "Send the ファイル now.", lang="en"),
            Cue(2, 2000, 3500, "ファイルを送ります。", lang="ja"),
        ]
        answers = iter(["傳送文件。", "傳送文件。"])

        def chat(messages: Sequence[Message], temperature: float) -> str:
            asked = json.loads(messages[-1]["content"])["translate"]
            return json.dumps({"translations": [{"id": asked[0]["id"], "zh": next(answers)}]})

        done = translate.run(
            cues,
            chat,
            (),
            batch_size=1,
            max_retries=0,
            sleep=lambda _: None,
            keep_english=True,
            source=MIXED_SOURCE,
        )
        assert [cue.zh for cue in done] == ["傳送文件。", "傳送檔案。"]

    def test_a_checkout_written_as_check_out_is_written_as_checkout(self) -> None:
        assert (
            fix_from_source("書架的檢查出清單", "貸出のチェックアウト一覧です") == "書架的簽出清單"
        )
        assert fix_from_source("檢查出錯誤", "エラーです") == "檢查出錯誤"

    def test_a_cue_the_model_put_in_the_wrong_place_is_mended_by_its_unit(self) -> None:
        cues = cues_of("ファイルを", "ネットワークで", "送ります")
        zh = "[[1]]把檔案[[2]]透過網路[[3]]傳送文件。"
        assert translated(cues, [zh]) == ["把檔案", "透過網路", "傳送檔案。"]

    def test_a_unit_with_a_document_word_in_another_cue_keeps_the_word(self) -> None:
        cues = cues_of("ファイルを", "ドキュメントと", "送ります")
        zh = "[[1]]把檔案[[2]]和文件[[3]]傳送出去。"
        assert translated(cues, [zh])[1] == "和文件"

    def test_a_single_cue_unit_uses_its_own_japanese(self) -> None:
        assert translated(cues_of("ファイルを送ります。"), ["傳送文件。"]) == ["傳送檔案。"]
        assert translated(cues_of("文書を送ります。"), ["傳送文件。"]) == ["傳送文件。"]

    def test_a_next_unit_does_not_borrow_the_file_word_of_the_unit_before(self) -> None:
        cues = cues_of("ファイルを送ります。", "契約を見ます。")
        done = translated(cues, ["傳送文件。", "看合約文件。"], batch_size=1)
        assert done == ["傳送檔案。", "看合約文件。"]

    def test_the_english_cues_of_a_mixed_talk_are_not_rewritten(self) -> None:
        cues = cues_of("Open the file.", lang="en")
        assert translated(cues, ["打開文件。"], source=MIXED_SOURCE) == ["打開文件。"]
        assert ENGLISH_SOURCE.fix_from_source is None

    def test_the_japanese_cues_of_a_mixed_talk_are_rewritten(self) -> None:
        cues = cues_of("ファイルを送ります。")
        assert translated(cues, ["傳送文件。"], source=MIXED_SOURCE) == ["傳送檔案。"]


class TestPerforceAliasesAreTheUsersToOverride:
    def test_a_user_entry_for_an_alias_replaces_the_default_one(self) -> None:
        mine = GlossaryEntry("PowerForce")
        glossary = glossary_for("ja", (mine,))
        assert GlossaryEntry("PowerForce", "Perforce") not in glossary
        assert mine in glossary
        assert GlossaryEntry("PowerHorse", "Perforce") in glossary

    def test_the_user_spelling_is_kept_in_a_translation(self) -> None:
        glossary = glossary_for("ja", (GlossaryEntry("PowerForce"),))
        cues = cues_of("パワフォースの話です。")
        assert translated(cues, ["這是 PowerForce 的話題。"], glossary) == [
            "這是 PowerForce 的話題。"
        ]

    def test_without_a_user_entry_the_alias_is_mended(self) -> None:
        glossary = glossary_for("ja", ())
        cues = cues_of("パワフォースの話です。")
        assert translated(cues, ["這是 PowerForce 的話題。"], glossary) == [
            "這是 Perforce 的話題。"
        ]

    def test_the_defaults_come_first_and_the_user_entries_last(self) -> None:
        mine = (GlossaryEntry("Acme", "艾克米"),)
        glossary = glossary_for("ja", mine)
        assert glossary[: len(translate.DEFAULT_GLOSSARY)] == translate.DEFAULT_GLOSSARY
        assert glossary[-1] == mine[0]
        assert set(translate.default_glossary("ja")) <= set(glossary)

    def test_a_user_entry_cannot_remove_a_product_name_every_run_starts_with(self) -> None:
        glossary = glossary_for("ja", (GlossaryEntry("Cursor", "游標"),))
        assert [e.zh for e in glossary if e.term == "Cursor"] == ["", "游標"]

    def test_english_has_no_source_entries_so_its_glossary_is_unchanged(self) -> None:
        mine = (GlossaryEntry("Cursor"), GlossaryEntry("Acme", "艾克米"))
        assert glossary_for("en", mine) == (*translate.DEFAULT_GLOSSARY, *mine)


class TestPlugInIsOneWord:
    def test_the_prompt_asks_for_the_short_form(self) -> None:
        text = translate.system_prompt_template(get_language("zh-TW"), JAPANESE_SOURCE)
        assert "a plug-in is 外掛 (not 插件, and not 外掛程式)" in text
        assert not re.search(r"plug-in is 外掛程式", text)

    def test_the_table_the_prompt_reads_asks_for_the_same_form(self) -> None:
        assert term("プラグイン").zh == "外掛"
        assert '- "プラグイン" must be translated as "外掛"' in named_lines("プラグインを入れる")
