"""Japanese speech: the source language table, the ASR units, the cue rules, the prompts and checks,
and the project it makes. The English half of each check says what must not change."""

from __future__ import annotations

import hashlib
import json
import re
import sys
import threading
from collections.abc import Callable, Iterable, Sequence
from dataclasses import replace
from pathlib import Path
from typing import Any, cast

import pytest
from test_pipeline import SETTINGS, Fakes, steps_of
from test_summarize import good_map, good_reduce

from backend.core import summarize, translate, unspaced
from backend.core.fonts import FontMissing, Lookup, burn_font, file_covers, windows_coverage
from backend.core.kana import romanize_katakana
from backend.core.languages import get as get_language
from backend.core.model import Cue, FormatError, Project, Segment, Step, Word
from backend.core.pipeline import STEPS, Settings, derive_key, run
from backend.core.segmenter import CueRules, merge_words, to_cues, violations
from backend.core.source_langs import (
    ENGLISH_SOURCE,
    JAPANESE_SOURCE,
    UnknownSource,
    get_source,
    is_spaced,
)
from backend.core.subtitle_io import (
    parse_project,
    parse_subs,
    read_text_file,
    render_project,
    render_subs,
)
from backend.core.translate import (
    Batch,
    ReplyError,
    Unit,
    build_request,
    default_glossary,
    parse_reply,
)
from backend.core.vad import Chunk
from backend.core.zh_tw import (
    JAPANESE_ONLY,
    SHINJITAI,
    SIMPLIFIED_ONLY,
    in_big5,
    japanese_only_chars,
    taiwan_terms,
    taiwan_terms_from_japanese,
    traditional_from_japanese,
)
from backend.engines.chunks import transcribe_chunks
from backend.engines.whispercpp import WhisperCppEngine
from backend.llm.client import Message

FIXTURE = Path(__file__).parent / "fixtures" / "engines" / "whisper_ja_15s.json"
ZH_TW = get_language("zh-TW")


def sha(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def whisper_words(language: str) -> list[Word]:
    engine = WhisperCppEngine(Path("whisper-cli"), Path("model.bin"))
    segments = engine.parse(FIXTURE, language)
    return [w for segment in segments for w in segment.words or ()]


def ja_settings(**changes: object) -> Settings:
    return replace(SETTINGS, source_lang="ja", **changes)


class TestEnglishIsUnchanged:
    """The values below were taken from the code before source languages existed."""

    def test_cache_keys_of_an_english_project(self) -> None:
        settings = Settings("e", "a", "v", "l")
        keys: dict[Step, str] = {}
        for spec in STEPS:
            keys[spec.step] = derive_key(spec, settings, "123:456", keys)
        assert {step.value: key for step, key in keys.items()} == {
            "audio": "8e082ed9fc915f5ce693f62fe78d4b8c",
            "vad": "2029e21d469e0fdbe1e8f5ebe4ef359f",
            "asr": "bb25db31eeea8dfe11c632a3994957aa",
            "segment": "8ff26819ef2e2c642d31c0d275e4293f",
            "translate": "2663c176b355f1d59d5ae7e1e38b330e",
            "export": "e81920d1550e2a47e1f7800208faa91d",
            "summarize": "ec25250565962b06a893803cf7a8d7a1",
        }

    def test_the_english_translation_prompt_is_what_it_was(self) -> None:
        cues = [Cue(1, 0, 1000, "Hello.")]
        request = build_request(cues, Batch((Unit(0, 1),)), translate.DEFAULT_GLOSSARY, 5, ZH_TW)
        assert (
            sha(request.messages[0]["content"])
            == "31ee9d4273cdb0edb1e297ab1c711ac6baecef98c4513c3750ca7dfde694f1fe"
        )
        assert (
            sha(translate.system_prompt_template(ZH_TW))
            == "8f7fb7ae131e06c38d119ce8c02f2763fc592263c312de66298af1787c9f66b2"
        )

    def test_an_english_translation_keeps_the_words_main_leaves_alone(self) -> None:
        said = "我們看了元數據、源碼與運營的報告。"
        cues = [Cue(1, 0, 1000, "We read the metadata, source and operations report.")]
        request = build_request(cues, Batch((Unit(0, 1),)), (), 5, ZH_TW)
        got = parse_reply(reply([1], said), request, cues, (), ZH_TW)
        assert got == {1: "我們看了元資料、源碼與運營的報告。"}

    def test_english_cue_files_keep_their_layout(self) -> None:
        text = render_subs([Cue(1, 0, 1000, "Hello there.", "你好。")])
        assert json.loads(text)["cues"][0] == {
            "id": 1,
            "start_ms": 0,
            "end_ms": 1000,
            "en": "Hello there.",
            "zh": "你好。",
        }

    def test_an_english_project_file_has_no_source_language(self) -> None:
        text = render_project(Project("talk.mp4"))
        assert "source_lang" not in text
        assert parse_project(text).source_lang == "en"


class TestSourceTable:
    def test_two_sources_and_their_files(self) -> None:
        assert ENGLISH_SOURCE.files.subs == "subs.en.json"
        assert ENGLISH_SOURCE.files.srt == "en.srt"
        assert JAPANESE_SOURCE.files.srt == "ja.srt"

    def test_an_unknown_source_names_the_ones_that_exist(self) -> None:
        with pytest.raises(UnknownSource, match="en, ja"):
            get_source("xx")

    def test_japanese_can_only_be_translated_into_zh_tw_for_now(self) -> None:
        assert JAPANESE_SOURCE.supports(ZH_TW)
        assert not JAPANESE_SOURCE.supports(get_language("ko"))
        assert ENGLISH_SOURCE.supports(get_language("ko"))
        with pytest.raises(ValueError, match="zh-TW"):
            ja_settings(target_lang="ko")

    def test_a_language_with_no_spaces_is_not_spaced(self) -> None:
        assert is_spaced("en") and not is_spaced("ja") and is_spaced("auto")


class TestCueFiles:
    def test_a_japanese_cue_names_its_language_and_round_trips(self) -> None:
        cue = Cue(1, 0, 1000, "こんにちは。", "你好。", "ja")
        raw = json.loads(render_subs([cue]))["cues"][0]
        assert raw["src"] == "こんにちは。" and raw["lang"] == "ja" and "en" not in raw
        assert parse_subs(render_subs([cue])) == [cue]

    def test_english_and_japanese_cues_can_share_a_file(self) -> None:
        cues = [Cue(1, 0, 1000, "Hello.", "", "en"), Cue(2, 1000, 2000, "はい。", "", "ja")]
        assert parse_subs(render_subs(cues)) == cues

    def test_a_cue_with_src_and_no_lang_is_refused(self) -> None:
        cue = {"id": 1, "start_ms": 0, "end_ms": 5, "src": "a", "zh": ""}
        text = json.dumps({"schema_version": 1, "cues": [cue]})
        with pytest.raises(FormatError, match="lang"):
            parse_subs(text)

    def test_the_project_remembers_its_source_language(self) -> None:
        text = render_project(Project("talk.mp4", source_lang="ja"))
        assert json.loads(text)["source_lang"] == "ja"
        assert parse_project(text).source_lang == "ja"

    def test_an_unknown_source_in_a_project_file_is_refused(self) -> None:
        raw = json.loads(render_project(Project("talk.mp4")))
        raw["source_lang"] = "xx"
        with pytest.raises(FormatError, match="source_lang"):
            parse_project(json.dumps(raw))


class TestWhisperTokens:
    def test_a_japanese_segment_keeps_its_tokens_as_words(self) -> None:
        first = WhisperCppEngine(Path("w"), Path("m")).parse(FIXTURE, "ja")[0]
        assert first.text.startswith("続 いて パ フ ォ ー ス P4 という")
        assert first.words is not None and len(first.words) > 25

    def test_the_spaced_merge_fused_the_sentence_into_one_word(self) -> None:
        """What the English rule did to Japanese: the P22 finding."""
        first = WhisperCppEngine(Path("w"), Path("m")).parse(FIXTURE, "en")[0]
        assert first.words is not None and len(first.words) <= 3

    def test_latin_pieces_of_one_name_stay_together_and_punctuation_joins_the_word_before(
        self,
    ) -> None:
        texts = [w.text for w in whisper_words("ja")]
        assert "P4" in texts
        assert any(t.endswith("。") for t in texts)
        assert not any(t in "、。" for t in texts)

    def test_token_times_never_go_backward(self) -> None:
        words = merge_words([Segment("", 0, 1, tuple(whisper_words("ja")))])
        assert all(a.start_ms <= b.start_ms for a, b in zip(words, words[1:], strict=False))


class TestUnspacedText:
    def test_columns_count_full_width_as_two(self) -> None:
        assert unspaced.columns("日本語abc") == 9

    def test_a_space_only_between_two_latin_words(self) -> None:
        assert unspaced.join(["Visual", "Studio", "Code"]) == "Visual Studio Code"
        assert unspaced.join(["A", "I", "の"]) == "AIの"
        assert unspaced.join(["P4", "を", "使う"]) == "P4を使う"

    def test_a_break_after_a_sentence_end_is_cheaper_than_inside_a_word(self) -> None:
        def cost(text: str, after: int) -> float:
            words = [Word(c, i * 100, i * 100 + 90) for i, c in enumerate(text)]
            return unspaced.break_costs(words)[after]

        assert cost("終わる。次へ", 3) < cost("終わる。次へ", 1)
        assert cost("今日は晴れ", 2) < cost("ストリーム", 1)
        assert cost("ストリーム", 1) > 8

    def test_a_line_never_starts_with_a_closing_mark_or_a_small_kana(self) -> None:
        text = "これはとてもよい一日でしたですからこれを、おぼえておきたいのです。"
        words = [Word(c, i * 100, i * 100 + 90) for i, c in enumerate(text)]
        for limit in range(10, 24):
            for line in unspaced.wrap(words, limit * 2).split("\n"):
                assert line[0] not in "、。ゃゅょっー"


def cues_of(words: Sequence[Word]) -> list[Cue]:
    return to_cues(
        [Segment("", words[0].start_ms, words[-1].end_ms, tuple(words))], JAPANESE_SOURCE.cues, "ja"
    )


class TestJapaneseCues:
    def test_cues_obey_the_japanese_rules(self) -> None:
        cues = cues_of(merge_words([Segment("", 0, 1, tuple(whisper_words("ja")))]))
        rules = JAPANESE_SOURCE.cues
        assert cues and violations(cues, rules) == []
        for cue in cues:
            lines = cue.src.split("\n")
            assert len(lines) <= 2
            assert all(unspaced.columns(line) <= 40 for line in lines)
            assert all(line[0] not in "、。！？ゃゅょっー" for line in lines)
            assert cue.lang == "ja"
        assert [c.id for c in cues] == list(range(1, len(cues) + 1))

    def test_no_word_is_added_or_lost(self) -> None:
        words = merge_words([Segment("", 0, 1, tuple(whisper_words("ja")))])
        cues = cues_of(words)
        said = "".join("".join(c.src.split("\n")) for c in cues).replace(" ", "")
        assert said == "".join(w.text for w in words).replace(" ", "")

    def test_cues_break_after_sentence_ends_when_it_can(self) -> None:
        cues = cues_of(merge_words([Segment("", 0, 1, tuple(whisper_words("ja")))]))
        assert any(c.src.endswith("。") for c in cues)
        for cue in cues[:-1]:
            body = cue.src.replace("\n", "")
            assert "。" not in body[:-1] or body.endswith("。")

    def test_the_english_rules_are_the_old_ones(self) -> None:
        rules = CueRules()
        assert (rules.max_line_chars, rules.unspaced, rules.max_cps) == (42, False, 17.0)
        assert JAPANESE_SOURCE.cues.max_line_chars == 40 and JAPANESE_SOURCE.cues.unspaced


class TestChunkRepair:
    class Fake:
        id = "fake"
        supports_word_timestamps = True

        def __init__(self, texts: list[str]) -> None:
            self.texts = texts

        def is_available(self) -> bool:
            return True

        def transcribe(
            self,
            wav_path: Path,
            language: str = "en",
            progress_cb: Callable[[float], None] | None = None,
            cancel: threading.Event | None = None,
        ) -> list[Segment]:
            return self.transcribe_many([wav_path], language, progress_cb, cancel)[0]

        def transcribe_many(
            self,
            wav_paths: Sequence[Path],
            language: str = "en",
            progress_cb: Callable[[float], None] | None = None,
            cancel: threading.Event | None = None,
        ) -> list[list[Segment]]:
            return [[Segment(t, 0, 500, (Word(t, 0, 500),))] for t in self.texts[: len(wav_paths)]]

    def test_english_repairs_are_not_applied_to_japanese(self, tmp_path: Path) -> None:
        import wave

        wav = tmp_path / "a.wav"
        with wave.open(str(wav), "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(16000)
            w.writeframes(b"\0\0" * 16000 * 4)
        chunks = [Chunk(0, 1000), Chunk(2000, 3000)]
        engine = self.Fake(["i", "x"])
        ja = transcribe_chunks(engine, wav, chunks, "ja")
        en = transcribe_chunks(engine, wav, chunks, "en")
        assert [w.text for w in ja] == ["i", "x"]
        assert [w.text for w in en] == ["I", "x"]


class TestTranslationPrompt:
    def test_the_japanese_prompt_names_its_source_and_keeps_the_rules(self) -> None:
        text = translate.system_prompt_template(ZH_TW, JAPANESE_SOURCE)
        assert "Translate Japanese subtitles" in text
        assert '"ja": "Japanese text"' in text
        for rule in ("Never invent a subject", "通關", "原始碼", "Perforce", "Visual Studio Code"):
            assert rule in text
        assert "<<" not in text.replace("<<GLOSSARY>>", "")
        assert "English" not in text.split("Rules for the translation:")[1]

    def test_a_request_uses_the_source_key_and_joins_japanese_without_spaces(self) -> None:
        cues = [
            Cue(1, 0, 1000, "今日は\nいい天気", lang="ja"),
            Cue(2, 1000, 2000, "ですね。", lang="ja"),
            Cue(3, 2000, 3000, "次です。", lang="ja"),
        ]
        batch = Batch((Unit(0, 2),))
        request = build_request(cues, batch, (), 5, ZH_TW, JAPANESE_SOURCE)
        body = json.loads(request.messages[1]["content"])
        assert body["translate"] == [{"id": 1, "ja": "[[1]]今日はいい天気[[2]]ですね。"}]
        assert body["context_after"] == "次です。"

    def test_a_sentence_ends_at_a_japanese_full_stop(self) -> None:
        cues = [
            Cue(i, 0, 1, t, lang="ja") for i, t in enumerate(["今日は", "晴れです。", "次は"], 1)
        ]
        units = translate.sentence_units(cues, 0, 3, 6, JAPANESE_SOURCE)
        assert [(u.start, u.stop) for u in units] == [(0, 2), (2, 3)]

    def test_the_default_glossary_for_japanese_has_the_talk_products(self) -> None:
        terms = {e.term for e in default_glossary("ja")}
        assert {"Perforce", "P4", "P4 MCP", "P4 DAM", "Helix Swarm", "東陽テクニカ"} <= terms
        assert default_glossary("en") == translate.DEFAULT_GLOSSARY


def reply(request_ids: Sequence[int], text: str) -> str:
    return json.dumps(
        {"translations": [{"id": i, "zh": text} for i in request_ids]}, ensure_ascii=False
    )


def check(src: str, zh: str, glossary: Sequence[translate.GlossaryEntry] = ()) -> dict[int, str]:
    cues = [Cue(1, 0, 1000, src, lang="ja")]
    request = build_request(cues, Batch((Unit(0, 1),)), glossary, 5, ZH_TW, JAPANESE_SOURCE)
    return parse_reply(reply([1], zh), request, cues, glossary, ZH_TW, JAPANESE_SOURCE)


class TestJapaneseOutputChecks:
    def test_a_good_translation_passes(self) -> None:
        assert check("次のページに進みます。", "接著進入下一頁。") == {1: "接著進入下一頁。"}

    def test_leftover_kana_is_refused(self) -> None:
        with pytest.raises(ReplyError, match="kana"):
            check("パフォースを使います。", "使用パフォース。")

    def test_japanese_kanji_forms_are_refused(self) -> None:
        with pytest.raises(ReplyError, match="Japanese kanji"):
            check("ゲームを働かせます。", "讓遊戲運作，働下去。")
        assert japanese_only_chars("気売働") == ["働", "売", "気"]
        assert japanese_only_chars("氣賣續") == []

    def test_simplified_characters_are_still_refused(self) -> None:
        with pytest.raises(ReplyError, match="Simplified"):
            check("次のページに進みます。", "接着进入下一页。")

    def test_a_translation_that_invents_text_is_refused(self) -> None:
        with pytest.raises(ReplyError, match="longer"):
            check("はい。", "是的，這個問題我們會在下一章詳細說明，請大家放心。")

    def test_a_latin_name_passes_and_the_katakana_dot_becomes_a_middle_dot(self) -> None:
        assert check("パフォースです。", "是 Perforce。") == {1: "是 Perforce。"}
        assert check("ジョン・スミスです。", "是約翰・史密斯。") == {1: "是約翰·史密斯。"}

    def test_a_glossary_term_in_the_source_must_be_kept(self) -> None:
        glossary = [translate.GlossaryEntry("P4")]
        with pytest.raises(ReplyError, match="P4"):
            check("P4を使います。", "使用版本控制。", glossary)
        assert check("P4を使います。", "使用 P4。", glossary) == {1: "使用 P4。"}

    def test_english_cues_are_not_checked_for_kana(self) -> None:
        cues = [Cue(1, 0, 1000, "He wrote the word hiragana.")]
        request = build_request(cues, Batch((Unit(0, 1),)), (), 5, ZH_TW)
        text = reply([1], "他寫了「ひらがな」這個詞。")
        assert parse_reply(text, request, cues, (), ZH_TW) == {1: "他寫了「ひらがな」這個詞。"}


class TestTaiwanTerms:
    @pytest.mark.parametrize(
        ("mainland", "taiwan"),
        [
            ("源代碼審查", "原始碼審查"),
            ("大數據改變了世界", "大數據改變了世界"),
            ("使用者數據", "使用者資料"),
        ],
    )
    def test_terms_for_every_talk(self, mainland: str, taiwan: str) -> None:
        assert taiwan_terms(mainland) == taiwan

    @pytest.mark.parametrize(
        ("mainland", "taiwan"),
        [
            ("針對P4的倉庫進行審查", "針對P4的儲存庫進行審查"),
            ("大規模倉庫", "大規模儲存庫"),
            ("與資產流水線整合", "與資產管線整合"),
            ("源碼審查", "原始碼審查"),
            ("運營相關意見", "營運相關意見"),
            ("運營商的網路", "運營商的網路"),
            ("資源碼", "資源碼"),
            ("元資料與原始碼", "中繼資料與原始碼"),
            ("單元資料", "單元資料"),
            ("物流倉庫的貨物", "物流倉庫的貨物"),
            ("汽車生產流水線", "汽車生產流水線"),
        ],
    )
    def test_terms_only_a_japanese_talk_needs(self, mainland: str, taiwan: str) -> None:
        assert taiwan_terms_from_japanese(mainland) == taiwan

    @pytest.mark.parametrize(
        ("said", "main_wrote"),
        [
            ("源碼審查", "源碼審查"),
            ("運營相關意見", "運營相關意見"),
            ("運營商的網路", "運營商的網路"),
            ("元數據與資料", "元資料與資料"),
            ("我們看了元數據、源碼與運營的報告。", "我們看了元資料、源碼與運營的報告。"),
        ],
    )
    def test_an_english_translation_gets_what_main_gave_it(
        self, said: str, main_wrote: str
    ) -> None:
        assert taiwan_terms(said) == main_wrote
        assert ZH_TW.terms(said) == main_wrote
        assert ZH_TW.clean(said, "We reviewed the source and the metadata.") == main_wrote

    def test_a_japanese_translation_gets_these_terms(self) -> None:
        said = "元數據、源碼與運營"
        cleaned = JAPANESE_SOURCE.clean(ZH_TW.clean(said, "メタデータ"))
        assert cleaned == "中繼資料、原始碼與營運"

    def test_english_translations_keep_their_warehouse(self) -> None:
        said = "我們把資料放進倉庫，再走流水線。"
        assert ZH_TW.clean(said, "We put the data in the warehouse.") == said


class TestPipeline:
    @staticmethod
    def ja_fakes() -> Fakes:
        class JaFakes(Fakes):
            def translate(self, messages: Sequence[Message], temperature: float) -> str:
                self.translate_calls += 1
                self.asked.append(messages[1]["content"])
                entries = json.loads(messages[1]["content"])["translate"]
                out: list[dict[str, object]] = []
                for entry in entries:
                    pieces = re.split(r"(\[\[\d+\]\])", entry["ja"])
                    zh = "".join(
                        p if re.fullmatch(r"\[\[\d+\]\]", p) else "譯" * max(2, len(p) // 3)
                        for p in pieces
                        if p.strip()
                    )
                    out.append({"id": entry["id"], "zh": zh + "。"})
                return json.dumps({"translations": out}, ensure_ascii=False)

            def summarize(self, messages: Sequence[Message], temperature: float) -> str:
                if messages[1]["content"].startswith("Part "):
                    self.asked.append(messages[0]["content"])
                    return good_map(messages)
                return good_reduce(messages, "zh-TW")

        return JaFakes(words=merge_words([Segment("", 0, 1, tuple(whisper_words("ja")))]))

    def test_a_japanese_project_has_japanese_files(self, tmp_path: Path) -> None:
        video, folder = tmp_path / "talk.mp4", tmp_path / "project"
        video.write_bytes(b"x")
        fakes = self.ja_fakes()
        report = run(video, folder, ja_settings(), fakes.ports())
        assert report.ran == tuple(Step)
        for name in ("subs.ja.json", "ja.srt", "subs.zh-TW.json", "zh-TW.srt", "summary.md"):
            assert (folder / name).is_file(), name
        for name in ("subs.en.json", "en.srt"):
            assert not (folder / name).exists(), name
        cues = parse_subs(read_text_file(folder / "subs.zh-TW.json"))
        assert all(c.lang == "ja" and c.zh for c in cues)
        assert (folder / "ja.srt").read_text(encoding="utf-8").startswith("1\n00:00:")
        assert parse_project(read_text_file(folder / "project.json")).source_lang == "ja"
        assert any("Japanese" in text for text in fakes.asked)

    def test_a_second_run_does_no_work_and_only_the_ones_that_must_rerun_rerun(
        self, tmp_path: Path
    ) -> None:
        video, folder = tmp_path / "talk.mp4", tmp_path / "project"
        video.write_bytes(b"x")
        fakes = self.ja_fakes()
        run(video, folder, ja_settings(), fakes.ports())
        assert run(video, folder, ja_settings(), fakes.ports()).ran == ()
        report = run(video, folder, ja_settings(llm_identity="llm-b"), fakes.ports())
        assert report.ran == (Step.TRANSLATE, Step.EXPORT, Step.SUMMARIZE)

    def test_switching_the_source_language_reruns_from_the_asr_on(self, tmp_path: Path) -> None:
        video, folder = tmp_path / "talk.mp4", tmp_path / "project"
        video.write_bytes(b"x")
        run(video, folder, SETTINGS, Fakes().ports())
        fakes = self.ja_fakes()
        report = run(video, folder, ja_settings(), fakes.ports())
        assert report.ran == (Step.ASR, Step.SEGMENT, Step.TRANSLATE, Step.EXPORT, Step.SUMMARIZE)
        assert (fakes.extracted, fakes.split) == (0, 0)
        assert steps_of(folder)["asr"][0].value == "done"

    def test_the_summary_notes_for_japanese_are_asked_in_chinese(self) -> None:
        lines = [summarize.Line(0, 1000, "今日は晴れです。")]
        window = summarize.make_windows(lines, chars_per_token=1.2)[0]
        system = summarize.map_messages(window, 1, JAPANESE_SOURCE)[0]["content"]
        assert "Traditional Chinese" in system and "Japanese" in system
        english = summarize.map_messages(window, 1)[0]["content"]
        assert "Write in English" in english

    def test_a_japanese_window_is_sized_by_characters(self) -> None:
        lines = [summarize.Line(i * 1000, i * 1000 + 900, "あ" * 60) for i in range(200)]
        english = summarize.make_windows(lines)
        japanese = summarize.make_windows(lines, chars_per_token=JAPANESE_SOURCE.chars_per_token)
        assert len(japanese) > len(english) * 2
        window = japanese[0]
        assert summarize.max_points(window, JAPANESE_SOURCE) > 1
        assert summarize.max_points(window) < summarize.max_points(window, JAPANESE_SOURCE)

    def test_a_summary_with_kana_is_rejected(self) -> None:
        job = summarize.ReduceInput(
            "zh-TW",
            0,
            600_000,
            (summarize.MapResult(0, 600_000, "t", (summarize.Point(1000, "x"),)),),
            (),
            (),
            JAPANESE_SOURCE,
        )
        bad = json.dumps(
            {
                "one_liner": "這場談パフォース。",
                "chapters": [{"at": "00:01", "title": "章", "summary": "內容。"}],
                "key_points": ["重點。"],
                "takeaways": [],
            },
            ensure_ascii=False,
        )
        with pytest.raises(summarize.ReplyError, match="kana"):
            summarize.parse_reduce(bad, job)


class TestBurnFont:
    JA = [Cue(1, 0, 1000, "日本語のテキスト", "文字", "ja")]

    @staticmethod
    def installed(fonts: dict[str, set[str]] | None = None) -> Lookup:
        have = fonts or {}

        def lookup(chars: Iterable[str]) -> Callable[[str], tuple[Path, set[str]] | None]:
            return lambda family: (Path(family), have[family]) if family in have else None

        return lookup

    def test_english_text_keeps_arial_and_never_looks_at_the_fonts(self) -> None:
        def refuse(chars: Iterable[str]) -> Callable[[str], tuple[Path, set[str]] | None]:
            raise AssertionError("the fonts were looked up")

        assert burn_font([Cue(1, 0, 1000, "Hello café.")], refuse) == "Arial"

    @pytest.mark.parametrize("text", ["I don’t know — really…", "He said “hi”", "50–60 • ok"])
    def test_english_typographic_punctuation_never_looks_at_the_fonts(self, text: str) -> None:
        def refuse(chars: Iterable[str]) -> Callable[[str], tuple[Path, set[str]] | None]:
            raise AssertionError("the fonts were looked up")

        assert burn_font([Cue(1, 0, 1000, text)], refuse) == "Arial"

    def test_a_japanese_cue_with_only_general_punctuation_needs_no_cjk_font(self) -> None:
        def refuse(chars: Iterable[str]) -> Callable[[str], tuple[Path, set[str]] | None]:
            raise AssertionError("the fonts were looked up")

        cues = [Cue(1, 0, 1000, "Perforce — ok…", "好", "ja")]
        assert burn_font(cues, refuse) == "Arial"

    def test_a_japanese_cue_is_still_checked_for_kana_and_full_width_forms(self) -> None:
        for text in ("あ", "ア", "漢", "「。」", "Ａ！"):
            with pytest.raises(FontMissing):
                burn_font([Cue(1, 0, 1000, text, "好", "ja")], self.installed())

    def test_japanese_text_takes_the_first_font_that_draws_all_of_it(self) -> None:
        lookup = self.installed({"Yu Gothic": {"本"}, "Meiryo": set(), "MS Gothic": set()})
        assert burn_font(self.JA, lookup) == "Meiryo"

    def test_a_pc_with_no_japanese_font_is_told_so(self) -> None:
        with pytest.raises(FontMissing, match="Yu Gothic、Meiryo、MS Gothic"):
            burn_font(self.JA, self.installed())

    def test_a_missing_glyph_is_named(self) -> None:
        lookup = self.installed({"Yu Gothic": {"語", "本"}, "Meiryo": {"語"}})
        with pytest.raises(FontMissing, match="Meiryo.*語"):
            burn_font(self.JA, lookup)

    def test_the_burned_ass_uses_the_font(self) -> None:
        from backend.core.languages import Wrap
        from backend.core.subtitle_io import render_burn_ass

        ass = render_burn_ass(
            self.JA,
            Wrap.CJK,
            mode="both",
            zh_first=True,
            size_ratio=0.05,
            color="#ffffff",
            source_font="Yu Gothic",
        )
        assert "Style: En,Yu Gothic," in ass
        english = render_burn_ass(
            self.JA, Wrap.CJK, mode="both", zh_first=True, size_ratio=0.05, color="#ffffff"
        )
        assert "Style: En,Arial," in english

    @pytest.mark.skipif(sys.platform != "win32", reason="reads the Windows font registry")
    def test_the_windows_fonts_of_this_pc_are_read_and_checked(self) -> None:
        lookup = windows_coverage("日本語あア")
        found = [lookup(family) for family in ("Yu Gothic", "Meiryo", "MS Gothic")]
        if not any(found):
            pytest.skip("no Japanese font installed")
        path, missing = next(f for f in found if f)
        assert path.is_file() and missing == set()
        assert file_covers(path, "􏿾") == {"􏿾"}


def client_shape_ok(cue: object) -> bool:
    """The check `parseCues` in app/src/api/client.ts makes on every cue of the JSON reply."""
    if not isinstance(cue, dict):
        return False
    fields = cast("dict[str, object]", cue)

    def number(key: str) -> bool:
        value = fields.get(key)
        return isinstance(value, int | float) and not isinstance(value, bool)

    return (
        number("id")
        and number("start_ms")
        and number("end_ms")
        and isinstance(fields.get("en"), str)
        and isinstance(fields.get("zh"), str)
    )


class TestCueJsonForTheUi:
    @staticmethod
    def japanese_client(tmp_path: Path, source_lang: str) -> tuple[Any, str]:
        from fastapi.testclient import TestClient
        from test_api import AUTH, GUARD, events, make_project, start_job

        from backend.main import AppConfig, create_app

        fakes = TestPipeline.ja_fakes() if source_lang == "ja" else Fakes()
        settings = ja_settings() if source_lang == "ja" else SETTINGS
        app = create_app(
            AppConfig(tmp_path / "data", GUARD, lambda options, folder: (settings, fakes.ports()))
        )
        client = TestClient(app, headers=AUTH)
        video = tmp_path / "talk.mp4"
        video.write_bytes(b"x")
        pid = make_project(client, video)
        events(client, start_job(client, pid)["id"])
        return client, pid

    def test_a_japanese_project_cue_json_passes_the_check_the_ui_makes(
        self, tmp_path: Path
    ) -> None:
        client, pid = self.japanese_client(tmp_path, "ja")
        cues = client.get(f"/api/projects/{pid}/subtitles?lang=bilingual&format=json").json()[
            "cues"
        ]
        assert cues and all(client_shape_ok(c) for c in cues)
        assert all(c["en"] == c["src"] and c["lang"] == "ja" for c in cues)
        sent = [{k: c[k] for k in ("id", "start_ms", "end_ms", "en", "zh")} for c in cues]
        assert client.put(f"/api/projects/{pid}/subtitles", json={"cues": sent}).status_code == 200

    def test_the_files_on_disk_do_not_carry_the_alias(self, tmp_path: Path) -> None:
        client, pid = self.japanese_client(tmp_path, "ja")
        folder = Path(client.get(f"/api/projects/{pid}").json()["folder"])
        on_disk = json.loads((folder / "subs.zh-TW.json").read_text(encoding="utf-8"))
        assert all("en" not in c and "src" in c for c in on_disk["cues"])

    def test_an_english_project_cue_json_is_what_it_was(self, tmp_path: Path) -> None:
        client, pid = self.japanese_client(tmp_path, "en")
        cues = client.get(f"/api/projects/{pid}/subtitles?format=json").json()["cues"]
        assert cues and all(client_shape_ok(c) for c in cues)
        assert all(set(c) == {"id", "start_ms", "end_ms", "en", "zh"} for c in cues)


class TestJobBody:
    def test_the_job_body_takes_a_source_language(self) -> None:
        from backend.api.jobs import JobBody

        options = JobBody(source_lang="ja").options()
        assert options.source_lang == "ja" and options.target_lang == "zh-TW"
        assert JobBody().options().source_lang == "en"

    def test_an_unknown_source_or_a_target_it_has_no_prompt_for_is_refused(self) -> None:
        from pydantic import ValidationError

        from backend.api.jobs import JobBody

        with pytest.raises(ValidationError, match="source language"):
            JobBody(source_lang="xx")
        with pytest.raises(ValidationError, match="zh-TW"):
            JobBody(source_lang="ja", target_lang="ko")
        assert JobBody(source_lang="en", target_lang="ko").options().target_lang == "ko"


class TestProjectStore:
    def test_a_japanese_project_reads_back_with_its_language_and_keeps_it_when_corrected(
        self, tmp_path: Path
    ) -> None:
        from backend.core.projects import ProjectStore

        video = tmp_path / "talk.mp4"
        video.write_bytes(b"x")
        store = ProjectStore(tmp_path / "projects")
        info, _ = store.create(video)
        run(video, info.folder, ja_settings(), TestPipeline.ja_fakes().ports())
        cues = store.cues(info.id)
        assert cues and all(c.lang == "ja" for c in cues)
        assert store.info(info.id).project.source_lang == "ja"
        source = store.subtitles(info.id, "en", "srt")
        assert source == (info.folder / "ja.srt").read_text(encoding="utf-8")
        english_lang_cue = replace(cues[0], zh="新的譯文。", lang="en")
        store.save_cues(info.id, [english_lang_cue, *cues[1:]])
        saved = store.cues(info.id)
        assert saved[0].zh == "新的譯文。" and saved[0].lang == "ja"
        assert (info.folder / "ja.srt").read_text(encoding="utf-8") == source

    def test_an_edit_of_the_japanese_line_is_refused_by_name(self) -> None:
        from backend.core import cue_edits

        before = [Cue(1, 0, 1000, "日本語", "文字", "ja")]
        problems = cue_edits.check(before, [replace(before[0], src="別の")])
        assert [p.code for p in problems] == ["english_changed"]
        assert "Japanese" in problems[0].message


class TestRepairs:
    @pytest.mark.parametrize(
        ("kana", "latin"),
        [
            ("コントモキ", "Kontomoki"),
            ("セレック", "Serekku"),
            ("パフォース", "Pafosu"),
            ("ジュニア", "Junia"),
            ("ビジュアル", "Bijuaru"),
            ("ファイル", "Fairu"),
            ("コンピューター", "Konpyuta"),
            ("ニッポン", "Nippon"),
        ],
    )
    def test_katakana_in_latin_letters(self, kana: str, latin: str) -> None:
        assert romanize_katakana(kana) == latin

    def test_only_katakana_is_romanised(self) -> None:
        assert romanize_katakana("我是コン智樹。") == "我是Kon智樹。"

    def test_japanese_kanji_forms_are_written_the_traditional_way_without_a_retry(self) -> None:
        assert check("登録ができます。", "可以登録了。") == {1: "可以登錄了。"}
        assert traditional_from_japanese("気続売録会点国") == "氣續賣錄會點國"

    def test_every_table_entry_is_a_japanese_form_with_a_big5_traditional_character(self) -> None:
        assert len(SHINJITAI) > 100
        for new, old in SHINJITAI.items():
            assert new in JAPANESE_ONLY or new in SIMPLIFIED_ONLY, new
            assert in_big5(old) and old not in JAPANESE_ONLY and old not in SIMPLIFIED_ONLY, old

    def test_a_name_the_model_keeps_in_kana_is_written_in_letters_after_the_last_attempt(
        self,
    ) -> None:
        cues = [Cue(1, 0, 1000, "コントモキと申します", lang="ja")]
        stubborn = json.dumps(
            {"translations": [{"id": 1, "zh": "我是コントモキ。"}]}, ensure_ascii=False
        )
        done = translate.run(
            cues,
            lambda messages, temperature: stubborn,
            batch_size=1,
            max_retries=1,
            sleep=lambda _: None,
            keep_english=True,
            source=JAPANESE_SOURCE,
        )
        assert done[0].zh == "我是Kontomoki。"

    def test_a_cue_that_cannot_be_repaired_keeps_its_japanese(self) -> None:
        cues = [Cue(1, 0, 1000, "と題しまして", lang="ja")]
        stubborn = json.dumps(
            {"translations": [{"id": 1, "zh": "と題しまして"}]}, ensure_ascii=False
        )
        done = translate.run(
            cues,
            lambda messages, temperature: stubborn,
            batch_size=1,
            max_retries=1,
            sleep=lambda _: None,
            keep_english=True,
            source=JAPANESE_SOURCE,
        )
        assert done[0].zh == "と題しまして"


class TestRetryMessagesNameTheSource:
    @staticmethod
    def rejection(cues: list[Cue], zh: str, source: translate.SourceLanguage) -> str:
        batch = Batch((Unit(0, len(cues)),))
        request = build_request(cues, batch, (), 5, ZH_TW, source)
        with pytest.raises(ReplyError) as raised:
            parse_reply(reply([cues[0].id], zh), request, cues, (), ZH_TW, source)
        return str(raised.value)

    def test_a_lost_marker_names_the_japanese_after_it(self) -> None:
        cues = [
            Cue(1, 0, 1000, "お願いします", lang="ja"),
            Cue(2, 1000, 2000, "と思います。", lang="ja"),
        ]
        message = self.rejection(cues, "[[1]]請多指教。", JAPANESE_SOURCE)
        assert "the Japanese after it is" in message and "English" not in message

    def test_a_lost_marker_in_an_english_talk_still_says_english(self) -> None:
        cues = [Cue(1, 0, 1000, "So I think"), Cue(2, 1000, 2000, "it works.")]
        message = self.rejection(cues, "[[1]]我想。", ENGLISH_SOURCE)
        assert 'the English after it is "it works."' in message

    def test_a_translation_far_too_long_names_the_japanese(self) -> None:
        cues = [Cue(1, 0, 1000, "はい。", lang="ja")]
        message = self.rejection(cues, TestLastResort.LONG, JAPANESE_SOURCE)
        assert "far longer than its Japanese" in message


class TestBarePunctuation:
    JA = [
        Cue(1, 0, 1000, "お申し付けいただければ", lang="ja"),
        Cue(2, 1000, 2000, "と思います。", lang="ja"),
    ]

    def test_a_translation_of_only_punctuation_is_refused_for_japanese(self) -> None:
        with pytest.raises(ReplyError, match="only punctuation"):
            check("と思います。", "。")
        with pytest.raises(ReplyError, match="only punctuation"):
            check("と思います。", "……")

    def test_an_english_translation_of_only_punctuation_is_not_refused(self) -> None:
        cues = [Cue(1, 0, 1000, "Mm-hm.")]
        request = build_request(cues, Batch((Unit(0, 1),)), (), 5, ZH_TW)
        assert parse_reply(reply([1], "。"), request, cues, (), ZH_TW) == {1: "。"}

    def test_a_source_that_is_only_punctuation_may_keep_it(self) -> None:
        assert check("……", "……") == {1: "……"}

    @staticmethod
    def model(whole_unit: str, alone: dict[int, str]) -> Callable[..., str]:
        def chat(messages: Sequence[translate.Message], temperature: float) -> str:
            entries = json.loads(messages[1]["content"])["translate"]
            out = [
                {"id": e["id"], "zh": whole_unit if "[[" in e["ja"] else alone[e["id"]]}
                for e in entries
            ]
            return json.dumps({"translations": out}, ensure_ascii=False)

        return chat

    def test_a_bare_full_stop_is_retranslated_on_its_own(self) -> None:
        chat = self.model(
            "[[1]]請隨時告訴我們，我們會處理[[2]]。", {1: "請隨時告訴我們，", 2: "我們會處理。"}
        )
        done = translate.run(
            self.JA, chat, max_retries=1, sleep=lambda _: None, source=JAPANESE_SOURCE
        )
        assert [c.zh for c in done] == ["請隨時告訴我們，", "我們會處理。"]

    def test_a_cue_that_stays_bare_takes_the_end_of_the_cue_before_it(self) -> None:
        chat = self.model(
            "[[1]]請隨時告訴我們，我們會處理[[2]]。", {1: "請隨時告訴我們，我們會處理。", 2: "。"}
        )
        done = translate.run(
            self.JA,
            chat,
            max_retries=1,
            sleep=lambda _: None,
            keep_english=True,
            source=JAPANESE_SOURCE,
        )
        assert [c.zh for c in done] == ["請隨時告訴我們，", "我們會處理。"]
        assert [(c.id, c.start_ms, c.end_ms) for c in done] == [(1, 0, 1000), (2, 1000, 2000)]

    def test_a_cue_with_nothing_to_take_keeps_its_punctuation(self) -> None:
        cues = [
            Cue(1, 0, 1000, "はい", lang="ja", zh="好的"),
            Cue(2, 1000, 2000, "です。", lang="ja", zh="。"),
        ]
        assert [c.zh for c in translate.settle_bare_punctuation(cues, JAPANESE_SOURCE)] == [
            "好的",
            "。",
        ]

    def test_an_english_talk_is_never_settled(self) -> None:
        cues = [Cue(1, 0, 1000, "So, yes", zh="所以，是的"), Cue(2, 1000, 2000, "it is.", zh="。")]
        assert translate.settle_bare_punctuation(cues, ENGLISH_SOURCE) == cues


class TestGlossaryMending:
    GLOSSARY = [translate.GlossaryEntry("東陽テクニカ", "Toyo Corporation")]

    def test_a_japanese_term_the_model_copies_is_replaced_by_its_translation(self) -> None:
        got = check("東陽テクニカの方です。", "是東陽テクニカ的人。", self.GLOSSARY)
        assert got == {1: "是Toyo Corporation的人。"}

    def test_the_japanese_default_glossary_maps_the_garbled_product_name(self) -> None:
        got = check("パフォースを使います。", "使用パフォース。", default_glossary("ja"))
        assert got == {1: "使用Perforce。"}

    def test_an_english_translation_is_left_alone(self) -> None:
        glossary = [translate.GlossaryEntry("tool", "工具")]
        cues = [Cue(1, 0, 1000, "This is a tool for builders.")]
        request = build_request(cues, Batch((Unit(0, 1),)), glossary, 5, ZH_TW)
        text = reply([1], "這是給建造者的 tool。")
        assert parse_reply(text, request, cues, glossary, ZH_TW) == {1: "這是給建造者的 tool。"}


class TestLastResort:
    LONG = (
        "這是一個很長的回覆，說明了很多原文沒有的內容，而且遠遠超過這一句話本來的長度，所以會被拒絕。"
        * 1
    )

    @staticmethod
    def ask(text: str, cues: list[Cue], source: translate.SourceLanguage) -> list[Cue]:
        stubborn = json.dumps({"translations": [{"id": 1, "zh": text}]}, ensure_ascii=False)
        return translate.run(
            cues,
            lambda messages, temperature: stubborn,
            batch_size=1,
            max_retries=1,
            sleep=lambda _: None,
            keep_english=True,
            source=source,
        )

    def test_a_long_japanese_translation_is_kept_over_the_japanese(self) -> None:
        done = self.ask(self.LONG, [Cue(1, 0, 1000, "はい。", lang="ja")], JAPANESE_SOURCE)
        assert done[0].zh == self.LONG

    def test_an_english_cue_that_fails_keeps_its_english(self) -> None:
        done = self.ask(self.LONG, [Cue(1, 0, 1000, "Yes.")], ENGLISH_SOURCE)
        assert done[0].zh == "Yes."
