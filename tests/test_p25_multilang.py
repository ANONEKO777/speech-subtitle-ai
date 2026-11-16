from __future__ import annotations

import json
from pathlib import Path

import pytest

from backend.core import translate
from backend.core.model import Cue
from backend.core.source_langs import JAPANESE_SOURCE
from backend.core.subtitle_io import render_subs, write_text_file
from scripts import p25_check
from scripts.p25_check import check, columns, percentile, problem_of
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
        assert columns("ＡＢ") == 4

    def test_kana_in_a_latin_cue_is_a_problem_of_its_own(self) -> None:
        assert problem_of("es", "Hola こ mundo") == "kana left in"

    def test_the_source_check_of_the_harness_names_kana(self) -> None:
        assert GENERIC_JA.problem("これは") is not None
        assert GENERIC_JA.problem("this") is None

    def test_a_percentile_picks_the_value_at_its_rank(self) -> None:
        assert percentile([1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0, 10.0], 0.9) == 10.0
        assert percentile([4.0, 1.0, 3.0, 2.0], 0.5) == 3.0
        assert percentile([], 0.9) == 0.0


class TestDice:
    def test_identical_sentences_score_one_and_unrelated_ones_near_zero(self) -> None:
        assert dice("今日は晴れです。", "今日は晴れです") == 1.0
        assert dice("今日は晴れです", "ブランチを切る") < 0.1

    def test_punctuation_and_width_do_not_change_the_score(self) -> None:
        assert dice("ＡＢＣ、定義", "abc定義") == 1.0

    def test_a_repeated_bigram_counts_every_time_it_repeats(self) -> None:
        assert dice("aaaa", "aa") == 0.5


def _cue(i: int, seconds: float, text: str = "") -> Cue:
    return Cue(i, 0, int(seconds * 1000), "あ" * 10, text, lang="ja")


def _latin(width: int) -> str:
    return ("hola " * width)[: width - 1] + "a"


def _write_cues(path: Path, cues: list[Cue]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    write_text_file(path, render_subs(cues))


def _write_back(path: Path, rows: list[tuple[str, float, int]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    items = [
        {"id": i, "text": text, "dice": dice_value, "judge": judge}
        for i, (text, dice_value, judge) in enumerate(rows, 1)
    ]
    path.write_text(json.dumps(items, ensure_ascii=False), encoding="utf-8")


@pytest.fixture
def evidence(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    source = tmp_path / "source.json"
    _write_cues(source, [_cue(i, 1) for i in range(1, 6)])
    monkeypatch.setattr(p25_check, "TALKS", {"full": (source, "ja")})
    out = tmp_path / "out"
    out.mkdir()
    units = [{"ids": [i], "back": False} for i in range(1, 6)]
    (out / "units.json").write_text(json.dumps({"full": units}), encoding="utf-8")
    spanish = [(10.0, 80), (10.0, 81), (10.0, 160), (1.0, 17), (1.0, 18)]
    _write_cues(
        out / "runs/full/direct.es.json",
        [_cue(i, sec, _latin(n)) for i, (sec, n) in enumerate(spanish, 1)],
    )
    korean = [(10.0, 41), (1.0, 8), (1.0, 7), (10.0, 2), (10.0, 2)]
    _write_cues(
        out / "runs/full/direct.ko.json",
        [_cue(i, sec, "한" * n) for i, (sec, n) in enumerate(korean, 1)],
    )
    _write_back(
        out / "back/direct.es.json", [("hola", 0.5, 5), ("adios", 0.3, 3), ("ひらがな", 1.0, 5)]
    )
    _write_back(out / "back/via-en.es.json", [("ひ", 0.2, 4), ("hi", 0.1, 4), ("hi", 0.4, 4)])
    return out


def _row(rows: list[dict[str, object]], route: str, code: str) -> dict[str, object]:
    return next(r for r in rows if r["route"] == route and r["target"] == code)


class TestCheckTable:
    def test_a_cue_is_over_two_lines_only_above_eighty_columns(self, evidence: Path) -> None:
        rows = check(evidence)
        assert _row(rows, "direct", "es")["over_two_lines"] == 2
        assert _row(rows, "direct", "ko")["over_two_lines"] == 1

    def test_the_rate_limit_is_fourteen_for_korean_and_seventeen_for_latin(
        self, evidence: Path
    ) -> None:
        rows = check(evidence)
        assert _row(rows, "direct", "es")["cps_limit"] == 17.0
        assert _row(rows, "direct", "es")["cps_over"] == 1
        assert _row(rows, "direct", "ko")["cps_limit"] == 14.0
        assert _row(rows, "direct", "ko")["cps_over"] == 1

    def test_the_length_ratio_columns_use_the_median_and_the_ninetieth_percentile(
        self, evidence: Path
    ) -> None:
        row = _row(check(evidence), "direct", "es")
        assert (row["ratio_med"], row["ratio_p90"]) == (8.0, 16.0)

    def test_back_translation_means_skip_kana_and_read_the_dice_column(
        self, evidence: Path
    ) -> None:
        row = _row(check(evidence), "direct", "es")
        assert (row["back_n"], row["back_dice"], row["back_judge"], row["judge_ge4"]) == (
            2,
            0.4,
            4,
            1,
        )

    def test_the_route_row_keeps_the_sentences_every_route_translated_without_kana(
        self, evidence: Path
    ) -> None:
        check(evidence)
        _, row = (evidence / "checks/routes.tsv").read_text(encoding="utf-8").splitlines()
        cells = row.split("	")
        assert cells[:2] == ["es", "1"]
        assert [float(c) for c in cells[2:4]] == [0.3, 0.1]
        assert cells[4] == ""
        assert [float(c) for c in cells[5:7]] == [3, 4]
        assert cells[8:10] == ["0", "1"]
