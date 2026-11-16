from __future__ import annotations

import pytest

from backend.core import translate
from backend.core.model import Cue
from backend.core.source_langs import JAPANESE_SOURCE
from scripts.p25_check import columns, problem_of
from scripts.p25_ja_multilang import (
    GENERIC_JA,
    TARGETS,
    ZH_SOURCE,
    dice,
    english_target,
    generic_rules,
    pivot_cues,
    target,
)


def _system(code: str) -> str:
    cues = [Cue(1, 0, 1000, "パワフォースP4を使います。", lang="ja")]
    batch = translate.plan_batches(cues, source=GENERIC_JA)[0]
    request = translate.build_request(cues, batch, (), lang=target(code), source=GENERIC_JA)
    return request.messages[0]["content"]


class TestPrompt:
    @pytest.mark.parametrize("code", TARGETS)
    def test_a_non_chinese_target_is_not_told_to_write_taiwan_chinese(self, code: str) -> None:
        text = _system(code)
        assert "Taiwan" not in text and "為了解決" not in text
        assert code == "zh-CN" or "Traditional" not in text

    def test_the_target_language_stands_where_the_rules_said_chinese(self) -> None:
        assert "Korean readers" in _system("ko")

    def test_the_pipeline_rules_still_hold_the_lines_the_harness_drops(self) -> None:
        assert "Use Taiwan wording" in JAPANESE_SOURCE.prompt.rules
        assert "Use Taiwan wording" not in generic_rules(JAPANESE_SOURCE.prompt.rules)

    def test_rules_that_changed_upstream_stop_the_harness(self) -> None:
        with pytest.raises(ValueError, match="no longer hold"):
            generic_rules("- nothing to rewrite")


class TestPivot:
    def test_a_pivot_cue_keeps_its_timing_and_takes_the_middle_text_as_its_source(self) -> None:
        cues = [Cue(5, 100, 900, "日本語", lang="ja"), Cue(6, 900, 1500, "english", lang="en")]
        middle = [Cue(5, 100, 900, "日本語", "Japanese", lang="ja")]
        (cue,) = pivot_cues(cues, middle, "en")
        assert (cue.id, cue.start_ms, cue.end_ms, cue.src, cue.zh, cue.lang) == (
            5,
            100,
            900,
            "Japanese",
            "",
            "en",
        )

    def test_the_chinese_middle_step_splits_sentences_at_chinese_marks(self) -> None:
        assert ZH_SOURCE.sentence_end.search("這是一句話。")
        assert not ZH_SOURCE.sentence_end.search("這是一句話")


class TestChecks:
    def test_kana_left_in_a_korean_cue_is_a_problem(self) -> None:
        assert problem_of("ko", "이것은 テスト 입니다") is not None

    def test_english_left_in_a_spanish_cue_is_a_problem(self) -> None:
        assert problem_of("es", "this is the thing that we have with you") is not None

    def test_a_vietnamese_cue_with_no_diacritics_is_a_problem(self) -> None:
        assert problem_of("vi", "toi dang lam viec o day voi ban") is not None
        assert problem_of("vi", "Tôi đang làm việc ở đây với bạn") is None

    def test_english_as_a_target_rejects_chinese_characters(self) -> None:
        assert english_target().check("We use 倉庫 here", "", True) is not None

    def test_a_marker_left_in_is_a_problem(self) -> None:
        assert problem_of("es", "Hola [[7]] mundo") == "marker left in"

    def test_full_width_characters_count_two_columns(self) -> None:
        assert columns("ab한") == 4


class TestDice:
    def test_identical_sentences_score_one_and_unrelated_ones_near_zero(self) -> None:
        assert dice("今日は晴れです。", "今日は晴れです") == 1.0
        assert dice("今日は晴れです", "ブランチを切る") < 0.1

    def test_punctuation_and_width_do_not_change_the_score(self) -> None:
        assert dice("ＡＢＣ、定義", "abc定義") == 1.0
