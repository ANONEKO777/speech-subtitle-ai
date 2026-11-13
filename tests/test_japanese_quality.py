"""P30: sentence units, term glossary, prompt wording and cache keys for the Japanese flow. The
sentences here are invented, not lines from any talk."""

from __future__ import annotations

from dataclasses import replace

import pytest
from test_pipeline import SETTINGS

from backend.core import pipeline, translate
from backend.core.model import Cue, Step
from backend.core.pipeline import STEPS, Settings, derive_key
from backend.core.source_langs import ENGLISH_SOURCE, JAPANESE_SOURCE, MIXED_SOURCE


def ja(*texts: str) -> list[Cue]:
    return [Cue(i, i * 2000, i * 2000 + 1500, t, lang="ja") for i, t in enumerate(texts, 1)]


def spans(cues: list[Cue], source=JAPANESE_SOURCE, limit: int = 6) -> list[tuple[int, int]]:
    return [(u.start, u.stop) for u in translate.sentence_units(cues, 0, len(cues), limit, source)]


class TestSentenceUnits:
    def test_a_sentence_without_a_full_stop_ends_at_a_final_form(self) -> None:
        cues = ja("今日は新しい機能を", "ご紹介いたします", "続いて設定の", "話をします")
        assert spans(cues) == [(0, 2), (2, 4)]

    @pytest.mark.parametrize(
        "last", ["ました", "ません", "でした", "ください", "ましょう", "ですよ", "ますね", "です"]
    )
    def test_each_final_form_ends_a_unit(self, last: str) -> None:
        assert spans(ja("これを見て", f"確認し{last}", "次の話は")) == [(0, 2), (2, 3)]

    def test_a_final_form_the_next_cue_goes_on_with_does_not_end_the_unit(self) -> None:
        cues = ja("設定を変更します", "ので少し待って", "ください", "次の項目は")
        assert spans(cues) == [(0, 3), (3, 4)]

    def test_a_filler_after_a_noun_does_not_end_a_unit(self) -> None:
        cues = ja("分岐を作成する際ですね", "一分未満で完了します")
        assert spans(cues) == [(0, 2)]

    def test_a_full_stop_still_ends_a_unit_even_when_the_next_cue_continues(self) -> None:
        assert spans(ja("今日は晴れ。", "ので外出します")) == [(0, 1), (1, 2)]

    def test_speech_without_any_final_form_is_cut_at_the_limit(self) -> None:
        cues = ja(*["とても長い話を続けて"] * 7)
        assert spans(cues, limit=3) == [(0, 3), (3, 6), (6, 7)]

    def test_english_units_ignore_the_japanese_rules(self) -> None:
        cues = [
            Cue(i, 0, 1, t) for i, t in enumerate(["It works", "and it is ready", "Now go."], 1)
        ]
        assert spans(cues, ENGLISH_SOURCE) == [(0, 3)]

    def test_a_mixed_talk_applies_each_cue_its_own_language_rule(self) -> None:
        cues = [
            Cue(1, 0, 1, "確認します", lang="ja"),
            Cue(2, 1, 2, "Next we look", lang="en"),
            Cue(3, 2, 3, "at it.", lang="en"),
        ]
        assert spans(cues, MIXED_SOURCE) == [(0, 1), (1, 3)]


def keys(settings: Settings) -> dict[Step, str]:
    out: dict[Step, str] = {}
    for spec in STEPS:
        out[spec.step] = derive_key(spec, settings, "1:2", out)
    return out


class TestCacheKeys:
    def test_a_new_cut_rule_cuts_a_japanese_talk_again(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        settings = replace(SETTINGS, source_lang="ja")
        before = keys(settings)
        monkeypatch.setattr(pipeline, "UNSPACED_CUT", "other")
        after = keys(settings)
        assert before[Step.AUDIO] == after[Step.AUDIO]
        assert before[Step.ASR] == after[Step.ASR]
        assert before[Step.SEGMENT] != after[Step.SEGMENT]
        assert before[Step.TRANSLATE] != after[Step.TRANSLATE]

    def test_a_new_unit_rule_translates_a_japanese_talk_again_without_cutting_it(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        settings = replace(SETTINGS, source_lang="ja")
        before = keys(settings)
        monkeypatch.setattr(pipeline, "JAPANESE_UNITS", "other")
        after = keys(settings)
        assert before[Step.SEGMENT] == after[Step.SEGMENT]
        assert before[Step.TRANSLATE] != after[Step.TRANSLATE]
        assert before[Step.SUMMARIZE] == after[Step.SUMMARIZE]

    def test_an_english_project_keeps_every_key(self, monkeypatch: pytest.MonkeyPatch) -> None:
        before = keys(SETTINGS)
        monkeypatch.setattr(pipeline, "UNSPACED_CUT", "other")
        monkeypatch.setattr(pipeline, "JAPANESE_UNITS", "other")
        assert keys(SETTINGS) == before
