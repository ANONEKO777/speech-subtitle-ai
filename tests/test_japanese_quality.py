"""P30: sentence units, term glossary, prompt wording and cache keys for the Japanese flow. The
sentences here are invented, not lines from any talk."""

from __future__ import annotations

from dataclasses import replace

import pytest
from test_pipeline import SETTINGS

from backend.core import pipeline, translate
from backend.core.languages import get as get_language
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


def system_text(cues: list[Cue], source=JAPANESE_SOURCE) -> str:
    batch = translate.Batch((translate.Unit(0, len(cues)),))
    request = translate.build_request(cues, batch, (), 0, source=source)
    return request.messages[0]["content"]


class TestTermGlossary:
    def test_a_request_names_the_terms_its_text_has_with_their_taiwan_form(self) -> None:
        text = system_text(ja("ファイルを", "ブランチに保存します"))
        assert '- "ファイル" must be translated as "檔案"' in text
        assert '- "ブランチ" must be translated as "分支"' in text

    def test_a_request_leaves_out_the_terms_its_text_does_not_have(self) -> None:
        text = system_text(ja("ファイルを保存します"))
        assert "ブランチ" not in text.split("Glossary.")[1]
        assert "プレイヤー" not in text

    def test_an_idiom_is_named_with_its_meaning(self) -> None:
        text = system_text(ja("新しいブランチを", "切ります"))
        assert '"ブランチを切る (create a branch)" must be translated as "建立分支"' in text
        text = system_text(ja("この設定はデフォルトで無効です"))
        assert '"デフォルトで無効 (disabled by default)" must be translated as "預設停用"' in text

    def test_the_context_around_a_batch_counts(self) -> None:
        cues = ja("ファイルを", "保存します", "次です")
        batch = translate.Batch((translate.Unit(1, 3),))
        request = translate.build_request(cues, batch, (), 1, source=JAPANESE_SOURCE)
        assert '"ファイル" must be translated' in request.messages[0]["content"]

    @pytest.mark.parametrize(
        "text", ["ソースコードを読む", "プレビューを見る", "ブロックを置く", "デコードする"]
    )
    def test_a_longer_word_does_not_name_a_term_it_only_contains(self, text: str) -> None:
        prompt = system_text(ja(text)).split("Glossary.")[-1]
        for word in ("コード", "レビュー", "ロック"):
            if word in text and word == "コード":
                assert '"コード" must' not in prompt
            if word in text and word != "コード":
                assert f'"{word}" must' not in prompt

    def test_the_source_code_term_is_named_for_source_code(self) -> None:
        assert '"ソースコード" must be translated as "原始碼"' in system_text(
            ja("ソースコードを読む")
        )

    def test_an_english_request_has_no_term_lines(self) -> None:
        cues = [Cue(1, 0, 1, "Open the file in the branch.")]
        text = system_text(cues, ENGLISH_SOURCE)
        assert "must be translated as" not in text

    def test_the_mixed_talk_names_terms_only_in_its_japanese_requests(self) -> None:
        cues = [
            Cue(1, 0, 1, "ファイルを開く", lang="ja"),
            Cue(2, 1, 2, "Open the file.", lang="en"),
        ]
        batch = translate.Batch((translate.Unit(1, 2),))
        english = translate.build_request(cues, batch, (), 0, source=MIXED_SOURCE)
        assert "must be translated as" not in english.messages[0]["content"]
        batch = translate.Batch((translate.Unit(0, 1),))
        japanese = translate.build_request(cues, batch, (), 0, source=MIXED_SOURCE)
        assert '"ファイル" must be translated as "檔案"' in japanese.messages[0]["content"]


class TestTermTable:
    def test_a_term_is_found_across_a_line_break(self) -> None:
        term = next(t for t in JAPANESE_SOURCE.terms if t.ja == "ファイル")
        assert term.in_source("ファイ\nル")

    def test_the_wrong_form_fails_and_the_taiwan_form_passes(self) -> None:
        term = next(t for t in JAPANESE_SOURCE.terms if t.ja == "ファイル")
        assert term.kept_in("開啟檔案")
        assert not term.kept_in("開啟文件")
        assert not term.kept_in("開啟檔案和文件")
        assert not term.kept_in("開啟")

    def test_the_names_of_the_ai_tools_are_checked_in_latin_letters(self) -> None:
        term = next(t for t in JAPANESE_SOURCE.terms if t.zh == "ChatGPT")
        assert term.in_source("チャットgptを使う")
        assert term.kept_in("使用 chatgpt")
        assert not term.kept_in("使用聊天GPT")

    def test_no_table_form_is_one_of_its_own_wrong_forms(self) -> None:
        import re

        for term in JAPANESE_SOURCE.terms:
            for bad in term.avoid:
                assert not re.search(bad, term.zh), term


class TestPromptWording:
    def test_the_japanese_prompt_forbids_added_content_and_dropped_numbers(self) -> None:
        text = translate.system_prompt_template(get_language("zh-TW"), JAPANESE_SOURCE)
        assert "Translate only what the Japanese says" in text
        assert "51.9% stays 51.9%" in text
        assert "never drop one" in text

    def test_the_japanese_prompt_names_the_ai_products_in_latin_letters(self) -> None:
        text = translate.system_prompt_template(get_language("zh-TW"), JAPANESE_SOURCE)
        for line in ("チャットGPT is ChatGPT", "クロード is Claude", "コパイロット is Copilot"):
            assert line in text

    def test_the_english_prompt_has_none_of_it(self) -> None:
        text = translate.system_prompt_template(get_language("zh-TW"), ENGLISH_SOURCE)
        assert "Translate only what" not in text and "ChatGPT" not in text.split("Rules for")[1]
