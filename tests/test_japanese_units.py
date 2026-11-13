"""P31, P32: the sentence units of a Japanese talk and the cue borders next to a number.
The sentences are invented."""

from __future__ import annotations

import hashlib
import re
from dataclasses import replace

import pytest
from test_pipeline import SETTINGS

from backend.core import pipeline, translate, unspaced
from backend.core.model import Cue, Segment, Word
from backend.core.segmenter import merge_words, to_cues
from backend.core.source_langs import JAPANESE_SOURCE, MIXED_SOURCE, SourceLanguage


def ja(*texts: str) -> list[Cue]:
    return [Cue(i, i * 2000, i * 2000 + 1500, t, lang="ja") for i, t in enumerate(texts, 1)]


def spans(
    cues: list[Cue], source: SourceLanguage = JAPANESE_SOURCE, limit: int = 6
) -> list[tuple[int, int]]:
    return [(u.start, u.stop) for u in translate.sentence_units(cues, 0, len(cues), limit, source)]


class TestContinuations:
    @pytest.mark.parametrize(
        "second",
        [
            "と本棚の話が続きます",
            "と、猫が続けます",
            "とおり、動きます",
            "と言います",
            "というのが理由です",
            "といった具合です",
            "とですね、こうなります",
            "とABCが並びます",
            "ものの、時間がありません",
            "ものを探します",
        ],
    )
    def test_a_conditional_or_a_how_that_goes_on_does_not_end_the_unit(self, second: str) -> None:
        assert spans(ja("今日は確認します", second, "次に進みます")) == [(0, 2), (2, 3)]

    @pytest.mark.parametrize(
        "second",
        [
            "とても重要です",
            "ところで次の話は",
            "とにかく進めます",
            "ともかく続けます",
            "ともあれ終わりです",
            "しかし問題があります",
            "しばらく待ちます",
            "しっかり確認します",
            "します",
            "しました",
            "しかも速いです",
            "もし失敗したら",
            "もちろん大丈夫です",
            "もっと速くします",
            "もう終わりです",
            "もともと別の話です",
            "とりあえず始めます",
            "とくに問題はありません",
            "ときどき止まります",
            "ときには迷います",
            "とっても便利です",
            "とはいえ油断は禁物です",
            "ともに進みます",
            "とうとう完成しました",
            "とんでもない話です",
            "ものすごく速いです",
        ],
    )
    def test_a_new_sentence_that_starts_like_a_connective_ends_the_unit(self, second: str) -> None:
        assert spans(ja("今日は確認します", second)) == [(0, 1), (1, 2)]

    def test_a_connective_that_was_already_in_the_list_still_continues(self) -> None:
        assert spans(ja("確認しますので", "お待ちください")) == [(0, 2)]
        assert spans(ja("確認します", "ので少し待って", "ください")) == [(0, 3)]

    def test_a_bare_to_at_the_end_of_a_cue_goes_on_with_the_cue_before_it(self) -> None:
        assert spans(ja("今日は確認します", "と")) == [(0, 2)]

    def test_a_full_stop_ends_the_unit_before_a_cue_that_starts_with_to(self) -> None:
        assert spans(ja("今日は確認します。", "と本棚の話です")) == [(0, 1), (1, 2)]


class TestTheUnitRuleVersion:
    """`JAPANESE_UNITS` is in the cache key. Changing the rule of `sentence_units` without a new
    version leaves a project with units cut the old way, so this table pins the version to it."""

    RULES = {"finals-3": "1fc90d3a01009cd8"}

    def test_the_version_is_the_one_of_the_rule(self) -> None:
        continues = JAPANESE_SOURCE.sentence_continues
        assert continues is not None
        text = JAPANESE_SOURCE.sentence_end.pattern + chr(10) + continues.pattern
        digest = hashlib.blake2b(text.encode("utf-8"), digest_size=8).hexdigest()
        assert self.RULES.get(pipeline.JAPANESE_UNITS) == digest, (
            f"the unit rule digest is {digest}: add it under a new JAPANESE_UNITS version"
        )

    def test_the_version_is_in_the_key_of_the_translation_of_a_japanese_project(self) -> None:
        settings = replace(SETTINGS, source_lang="ja")
        assert pipeline._units_key(settings) == {"units": pipeline.JAPANESE_UNITS}  # pyright: ignore[reportPrivateUsage]
        assert pipeline._units_key(SETTINGS) == {}  # pyright: ignore[reportPrivateUsage]


class TestMixedTalkUnits:
    def test_english_cues_of_a_mixed_talk_end_at_their_own_full_stop(self) -> None:
        cues = [
            Cue(1, 0, 1, "Open the file.", lang="en"),
            Cue(2, 1, 2, "Then close it.", lang="en"),
        ]
        assert spans(cues, MIXED_SOURCE) == [(0, 1), (1, 2)]

    def test_japanese_cues_of_a_mixed_talk_keep_the_japanese_continuation(self) -> None:
        cues = [
            Cue(1, 0, 1, "確認します", lang="ja"),
            Cue(2, 1, 2, "ので待ってください", lang="ja"),
            Cue(3, 2, 3, "Next we look.", lang="en"),
        ]
        assert spans(cues, MIXED_SOURCE) == [(0, 2), (2, 3)]


class TestACueBorderNeverCutsANumber:
    @staticmethod
    def cues_with_the_number_after(prefix_words: int):
        before = list(("これはとてもたいせつなはなしでして" * 3)[:prefix_words])
        after = list("ですそしてつぎのはなしにいきます" * 3)
        tokens = [*before, "51.", "9%", *after]
        words = [Word(t, i * 300, i * 300 + 250) for i, t in enumerate(tokens)]
        merged = merge_words([Segment("", 0, 1, tuple(words))])
        segment = Segment("", merged[0].start_ms, merged[-1].end_ms, tuple(merged))
        return to_cues([segment], JAPANESE_SOURCE.cues, "ja")

    def test_no_cue_ends_in_half_of_a_number_wherever_the_number_falls(self) -> None:
        for prefix_words in range(4, 60):
            cues = self.cues_with_the_number_after(prefix_words)
            for cue in cues:
                assert not re.search(r"\d[.,]\Z", cue.src.replace("\n", "")), prefix_words
            assert "51.9%" in "".join(c.src.replace("\n", "") for c in cues)

    def test_the_same_run_does_cut_between_the_halves_when_the_rule_is_off(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(unspaced, "_NUMBER_MARKS", "")  # pyright: ignore[reportPrivateUsage]
        cut = [
            n
            for n in range(4, 60)
            if any(
                re.search(r"\d[.,]\Z", c.src.replace("\n", ""))
                for c in self.cues_with_the_number_after(n)
            )
        ]
        assert cut
