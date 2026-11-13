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
