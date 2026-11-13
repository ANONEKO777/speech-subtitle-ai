from __future__ import annotations

import pytest

from backend.core.model import Cue
from scripts.p30_quality_check import check, glossary, number_found, number_words, numbers


def cue(i: int, src: str, zh: str) -> Cue:
    return Cue(i, i * 2000, i * 2000 + 1500, src, zh, lang="ja")


class TestNumbers:
    def test_a_number_cut_by_a_cue_border_with_both_halves_in_the_chinese_is_broken(self) -> None:
        cues = [cue(1, "全体の51.", "全體為51."), cue(2, "9%です", "9%。")]
        report = numbers(cues)
        assert report["numbers_cut_by_a_cue_border"] == 1
        assert report["cut_numbers_whole_in_one_zh_cue"] == 0
        assert report["zh_cues_ending_in_half_a_number"] == 1

    def test_a_cut_number_the_translation_keeps_whole_is_counted_whole(self) -> None:
        cues = [cue(1, "全体の51.", "全體的 51.9%"), cue(2, "9%です", "。")]
        assert numbers(cues)["cut_numbers_whole_in_one_zh_cue"] == 1

    def test_a_number_read_across_a_line_break_is_one_number(self) -> None:
        report = numbers([cue(1, "2026.\n2に出ました", "在2026.2 推出")])
        assert report["numbers"] == 1 and report["numbers_intact"] == 1

    def test_a_dropped_number_is_not_intact(self) -> None:
        report = numbers([cue(1, "大きく4つあります", "有幾個特點")])
        assert report["numbers"] == 1 and report["numbers_intact"] == 0

    @pytest.mark.parametrize(
        ("token", "zh"), [("122", "一百二十二秒"), ("2", "兩種"), ("30", "三十週年")]
    )
    def test_a_number_written_in_chinese_words_is_intact(self, token: str, zh: str) -> None:
        assert number_found(token, zh)

    def test_number_words_cover_the_common_forms(self) -> None:
        assert "一百二十二" in number_words("122")
        assert "三十" in number_words("30")
        assert "十" in number_words("10")


class TestGlossaryAndChecks:
    def test_a_cue_with_the_wrong_term_is_counted_against_the_term(self) -> None:
        right = cue(1, "ファイルを開く", "開啟檔案")
        wrong = cue(2, "ファイルを閉じる", "關閉文件")
        assert glossary([right, wrong])["ファイル"] == (1, 2)

    def test_the_counts_over_a_small_run(self) -> None:
        cues = [
            cue(1, "ファイルを開く", "開啟文件"),
            cue(2, "ブランチを切る", "建立分支的"),
            cue(3, "これは短い文章ですのでテスト", "這是" * 20),
        ]
        counts, seen = check(cues)
        assert counts["file_cues_written_as_wenjian"] == 1
        assert counts["fragment_ending_cues"] == 1
        assert counts["length_over_2.5x"] == 1
        assert seen["ブランチを切る (create a branch)"] == "1/1"

    def test_a_cue_that_starts_with_punctuation_is_counted(self) -> None:
        counts, _ = check([cue(1, "つづきます", "。接下來")])
        assert counts["zh_cues_starting_with_punctuation"] == 1


class TestNumbersInPlaceAndWordsOutsideTheTable:
    def test_a_number_found_only_in_the_next_cue_is_not_intact_in_its_own_cue(self) -> None:
        cues = [cue(1, "全体の122秒です", "全體是"), cue(2, "次の話です", "122秒。接下來")]
        report = numbers(cues)
        assert report["numbers_intact"] == 1
        assert report["numbers_intact_in_own_cue"] == 0

    def test_a_number_in_its_own_cue_is_intact_in_place(self) -> None:
        report = numbers([cue(1, "全体の122秒です", "全體是122秒")])
        assert report["numbers_intact_in_own_cue"] == 1

    def test_a_cut_number_counts_when_any_cue_of_its_span_has_it(self) -> None:
        cues = [cue(1, "全体の51.", "全體的51.9%"), cue(2, "9%です", "。")]
        assert numbers(cues)["numbers_intact_in_own_cue"] == 1

    def test_words_the_table_has_no_line_for_are_counted(self) -> None:
        counts, _ = check(
            [
                cue(1, "ハードウェアです", "這是硬件"),
                cue(2, "デモをします", "進行演示"),
                cue(3, "アクセスします", "進行訪問"),
                cue(4, "数万です", "有數万個"),
                cue(5, "パワフォースです", "這是PowerForce"),
                cue(6, "パフォースです", "這是Perforce"),
                cue(7, "普通です", "一般的字幕"),
            ]
        )
        assert counts["mainland_words_not_in_table_cues"] == 3
        assert counts["demo_written_yanshi_cues"] == 1
        assert counts["visit_word_for_access_cues"] == 1
        assert counts["simplified_char_cues"] == 1
        assert counts["product_name_wrong_cues"] == 1
        assert counts["product_name_perforce_cues"] == 1


class TestProductNamesAndTheLongPlugInForm:
    @pytest.mark.parametrize(
        "zh",
        [
            "用Claude程式碼詢問",
            "Claude 程式碼",
            "這邊是Visual Studio碼",
            "VS 程式碼",
            "GitHub 副駕駛",
            "克勞德",
            "聊天GPT",
        ],
    )
    def test_a_chinese_word_inside_a_product_name_is_counted(self, zh: str) -> None:
        counts, _ = check([cue(1, "あのツールです", zh)])
        assert counts["product_name_translated_cues"] == 1

    @pytest.mark.parametrize(
        "zh",
        [
            "用Claude Code詢問",
            "Visual Studio Code",
            "GitHub上的程式碼庫",
            "你的程式碼",
            "Cloud Run",
        ],
    )
    def test_a_product_name_kept_in_latin_letters_is_not_counted(self, zh: str) -> None:
        counts, _ = check([cue(1, "あのツールです", zh)])
        assert counts["product_name_translated_cues"] == 0

    def test_cloud_for_claude_is_counted_only_where_the_japanese_says_claude(self) -> None:
        counts, _ = check(
            [cue(1, "クロードです", "這是Cloud"), cue(2, "クラウドです", "這是Cloud")]
        )
        assert counts["product_name_translated_cues"] == 1

    def test_the_long_plug_in_form_is_counted(self) -> None:
        counts, _ = check([cue(1, "プラグインです", "外掛程式"), cue(2, "プラグインです", "外掛")])
        assert counts["plugin_written_long_form_cues"] == 1
