"""A talk spoken in Japanese and English (`ja+en`): the recognition passes, the cues, the
translation by language and the pipeline, with a fake engine and a fake model."""

from __future__ import annotations

import json
import re
import struct
import threading
import wave
from collections.abc import Callable, Iterable, Sequence
from dataclasses import replace
from pathlib import Path

import numpy as np
import pytest
from test_pipeline import SETTINGS, Fakes
from test_summarize import good_map, good_reduce

from backend.core import translate, vad
from backend.core.artifacts import parse_words, render_words
from backend.core.fonts import burn_font
from backend.core.model import Cue, Segment, Step, Word
from backend.core.pipeline import STEPS, Settings, derive_key, run
from backend.core.segmenter import CueRules, to_mixed_cues
from backend.core.source_langs import (
    ENGLISH_SOURCE,
    JAPANESE_SOURCE,
    MIXED_SOURCE,
    SOURCES,
    get_source,
)
from backend.core.subtitle_io import parse_project, parse_subs, read_text_file, render_subs
from backend.core.vad import Chunk
from backend.engines import mixed
from backend.engines.mixed import Piece
from backend.llm.client import Message

JA, EN = "ja", "en"


def word(text: str, start: int, end: int, lang: str | None = None) -> Word:
    return Word(text, start, end, lang)


def say(*texts: str, start: int = 0, step: int = 300) -> tuple[Word, ...]:
    return tuple(word(t, start + i * step, start + (i + 1) * step) for i, t in enumerate(texts))


class TestTagging:
    def test_kana_and_kanji_are_japanese_and_a_long_latin_run_is_english(self) -> None:
        words = tag_words("本日は", "ありがとう。", "Thank", "you", "so", "much.")
        assert [w.lang for w in words] == [JA, JA, EN, EN, EN, EN]

    def test_a_product_name_inside_a_japanese_sentence_stays_japanese(self) -> None:
        words = tag_words("これは", "Perforce", "です。")
        assert [w.lang for w in words] == [JA, JA, JA]

    def test_a_piece_with_no_japanese_is_english_even_for_one_word(self) -> None:
        assert [w.lang for w in tag_words("OK")] == [EN]

    def test_punctuation_and_digits_go_with_the_word_before(self) -> None:
        words = tag_words("Next", "we", "go", "to", "3.", "。")
        assert words[-2].lang == EN and words[-1].lang == EN

    def test_a_short_english_sentence_after_japanese_is_english(self) -> None:
        words = tag_words("はい。", "Yes", "please.")
        assert [w.lang for w in words] == [JA, EN, EN]


def tag_words(*texts: str) -> list[Word]:
    return mixed.tag_words(say(*texts))


class TestPlausible:
    @pytest.mark.parametrize("text", ["次に。", "Hello there.", "Perforceは便利です。", "No."])
    def test_japanese_and_english_pass(self, text: str) -> None:
        assert mixed.is_plausible(text)

    @pytest.mark.parametrize("text", ["다음에.", "几多钱嘞？", "《星之卡比》系列是。"])
    def test_korean_and_simplified_guesses_do_not(self, text: str) -> None:
        assert not mixed.is_plausible(text)


def silent_wav(path: Path, seconds: int) -> Path:
    with wave.open(str(path), "wb") as out:
        out.setnchannels(1)
        out.setsampwidth(2)
        out.setframerate(16000)
        out.writeframes(struct.pack("<h", 0) * 16000 * seconds)
    return path


Script = Callable[[str, int], Sequence[Segment]]


class FakeEngine:
    """Answers each wav by the language it is asked for and its length in ms."""

    id = "fake"
    supports_word_timestamps = True

    def __init__(self, script: Script) -> None:
        self.script = script
        self.calls: list[tuple[str, tuple[int, ...]]] = []

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
        sizes: list[int] = []
        out: list[list[Segment]] = []
        for path in wav_paths:
            with wave.open(str(path), "rb") as reader:
                ms = reader.getnframes() * 1000 // reader.getframerate()
            sizes.append(ms)
            out.append(list(self.script(language, ms)))
        self.calls.append((language, tuple(sizes)))
        if progress_cb:
            progress_cb(1.0)
        return out


def segment(*words: Word) -> Segment:
    return Segment(" ".join(w.text for w in words), words[0].start_ms, words[-1].end_ms, words)


class TestPasses:
    def test_a_short_piece_written_in_korean_is_recognised_again_in_japanese(
        self, tmp_path: Path
    ) -> None:
        wav = silent_wav(tmp_path / "a.wav", 10)

        def script(language: str, ms: int) -> list[Segment]:
            text = "次に。" if language == "ja" else "다음에."
            return [segment(word(text, 0, ms - 100))]

        engine = FakeEngine(script)
        words = mixed.transcribe_mixed(engine, wav, [Chunk(1000, 1900)])
        assert [(w.text, w.lang) for w in words] == [("次に。", JA)]
        assert [language for language, _ in engine.calls] == ["auto", "ja"]

    def test_one_latin_word_in_a_short_piece_is_japanese_when_japanese_decodes_to_japanese(
        self, tmp_path: Path
    ) -> None:
        wav = silent_wav(tmp_path / "a.wav", 10)

        def script(language: str, ms: int) -> list[Segment]:
            return [segment(word("全員が。" if language == "ja" else "sempre", 0, ms - 100))]

        words = mixed.transcribe_mixed(FakeEngine(script), wav, [Chunk(0, 1200)])
        assert [w.text for w in words] == ["全員が。"]

    def test_a_real_english_word_stays_english_when_japanese_would_write_it_in_latin_too(
        self, tmp_path: Path
    ) -> None:
        wav = silent_wav(tmp_path / "a.wav", 10)

        def script(language: str, ms: int) -> list[Segment]:
            return [segment(word("No.", 0, ms - 100))]

        words = mixed.transcribe_mixed(FakeEngine(script), wav, [Chunk(0, 1200)])
        assert [(w.text, w.lang) for w in words] == [("No.", EN)]

    def test_english_after_japanese_with_no_pause_is_found_by_the_tail_pass(
        self, tmp_path: Path
    ) -> None:
        wav = silent_wav(tmp_path / "a.wav", 20)

        def script(language: str, ms: int) -> list[Segment]:
            if ms == 8000:
                return [segment(word("今日は", 0, 400), word("晴れです。", 400, 2000))]
            return [segment(word("It", 0, 300), word("is", 300, 600), word("sunny.", 600, 1500))]

        engine = FakeEngine(script)
        words = mixed.transcribe_mixed(engine, wav, [Chunk(1000, 9000)])
        assert [(w.text, w.lang) for w in words] == [
            ("今日は", JA),
            ("晴れです。", JA),
            ("It", EN),
            ("is", EN),
            ("sunny.", EN),
        ]
        assert words[2].start_ms == 1000 + 2000
        assert engine.calls[-1] == ("auto", (6000,))

    def test_a_tail_shorter_than_the_limit_is_not_recognised_again(self) -> None:
        piece = Piece(Chunk(0, 1900), say("ああ", start=0, step=500))
        assert mixed.tail_chunk(piece) is None
        long_piece = Piece(Chunk(0, 8000), say("ああ", start=0, step=500))
        assert mixed.tail_chunk(long_piece) == Chunk(500, 8000)

    def test_a_tail_that_comes_back_implausible_is_dropped(self, tmp_path: Path) -> None:
        wav = silent_wav(tmp_path / "a.wav", 20)

        def script(language: str, ms: int) -> list[Segment]:
            if ms == 8000:
                return [segment(word("今日は", 0, 400))]
            return [segment(word("처음에.", 0, 400))]

        words = mixed.transcribe_mixed(FakeEngine(script), wav, [Chunk(0, 8000)])
        assert [w.text for w in words] == ["今日は"]


class TestChunks:
    @staticmethod
    def probs(spans: Sequence[tuple[int, int]], total_ms: int) -> vad.Probs:
        values = np.zeros(total_ms // vad.FRAME_MS + 1, dtype=np.float32)
        for start, end in spans:
            values[start // vad.FRAME_MS : end // vad.FRAME_MS] = 0.9
        return values

    def test_a_pause_of_300_ms_or_more_separates_two_chunks(self) -> None:
        probs = self.probs([(1000, 3000), (3500, 5000)], 8000)
        chunks = vad.plan_pauses(probs, 8000)
        assert len(chunks) == 2
        assert chunks[0].start_ms < 1000 and chunks[1].end_ms > 5000

    def test_speech_under_half_a_second_is_dropped_and_a_very_long_run_is_cut(self) -> None:
        assert vad.plan_pauses(self.probs([(1000, 1400)], 4000), 4000) == []
        chunks = vad.plan_pauses(self.probs([(0, 40_000)], 41_000), 41_000)
        assert len(chunks) > 1 and all(c.duration_ms <= vad.PAUSE_MAX_MS for c in chunks)


RULES = {JA: JAPANESE_SOURCE.cues, EN: ENGLISH_SOURCE.cues}


class TestMixedCues:
    def test_cues_never_hold_two_languages_even_with_no_pause(self) -> None:
        words = [
            *(word(t, i * 200, i * 200 + 200, JA) for i, t in enumerate("今日は晴れです。")),
            word("It", 1700, 1900, EN),
            word("is", 1900, 2100, EN),
            word("sunny.", 2100, 2500, EN),
        ]
        cues = to_mixed_cues([Segment("", 0, 2500, tuple(words))], RULES)
        assert [c.lang for c in cues] == [JA, EN]
        assert [c.id for c in cues] == [1, 2]
        assert cues[1].src == "It is sunny."
        assert cues[0].end_ms <= cues[1].start_ms

    def test_each_language_uses_its_own_line_width(self) -> None:
        ja = [word("あ" * 5, i * 500, i * 500 + 500, JA) for i in range(8)]
        en = [word("word", 5000 + i * 300, 5300 + i * 300, EN) for i in range(6)]
        cues = to_mixed_cues([Segment("", 0, 7000, tuple(ja + en))], RULES)
        ja_cues = [c for c in cues if c.lang == JA]
        assert ja_cues and all(
            unspaced_columns(line) <= 40 for c in ja_cues for line in c.src.split("\n")
        )
        assert any(c.lang == EN for c in cues)

    def test_words_survive_the_segment_file_with_their_language(self) -> None:
        words = [word("今日", 0, 200, JA), word("hello", 300, 500, EN)]
        assert parse_words(render_words("e", words)) == words
        plain = render_words("e", [word("hi", 0, 100)])
        assert "lang" not in plain


def unspaced_columns(text: str) -> int:
    from backend.core import unspaced

    return unspaced.columns(text)


MIXED_SETTINGS = replace(SETTINGS, source_lang="ja+en")


def mixed_words() -> list[Word]:
    ja = "本日はカメラについてお話しします。"
    en = "Today I will talk about the camera."
    out: list[Word] = []
    at = 0
    for _ in range(3):
        for char in ja:
            out.append(word(char, at, at + 150, JA))
            at += 150
        at += 100
        for token in en.split():
            out.append(word(token, at, at + 250, EN))
            at += 250
        at += 100
    return out


class MixedFakes(Fakes):
    def translate(self, messages: Sequence[Message], temperature: float) -> str:
        self.translate_calls += 1
        self.asked.append(messages[0]["content"])
        entries = json.loads(messages[1]["content"])["translate"]
        out: list[dict[str, object]] = []
        for entry in entries:
            text = entry.get("ja") or entry.get("en")
            pieces = re.split(r"(\[\[\d+\]\])", text)
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


class TestPipeline:
    def run_it(
        self, tmp_path: Path, settings: Settings = MIXED_SETTINGS
    ) -> tuple[Path, MixedFakes]:
        video, folder = tmp_path / "talk.mp4", tmp_path / "project"
        video.write_bytes(b"x")
        fakes = MixedFakes(words=mixed_words())
        run(video, folder, settings, fakes.ports())
        return folder, fakes

    def test_a_mixed_project_writes_one_source_file_with_a_language_on_every_cue(
        self, tmp_path: Path
    ) -> None:
        folder, _ = self.run_it(tmp_path)
        for name in ("subs.src.json", "src.srt", "subs.zh-TW.json", "zh-TW.srt", "summary.md"):
            assert (folder / name).is_file(), name
        for name in ("subs.en.json", "subs.ja.json", "en.srt", "ja.srt"):
            assert not (folder / name).exists(), name
        cues = parse_subs(read_text_file(folder / "subs.zh-TW.json"))
        assert {c.lang for c in cues} == {JA, EN}
        assert all(c.zh for c in cues)
        langs = [c.lang for c in cues]
        assert langs.count(JA) >= 3 and langs.count(EN) >= 3
        assert parse_project(read_text_file(folder / "project.json")).source_lang == "ja+en"

    def test_each_cue_is_translated_with_the_prompt_of_its_language(self, tmp_path: Path) -> None:
        _, fakes = self.run_it(tmp_path)
        prompts = [p for p in fakes.asked if "translate" in p.lower() and "{" in p]
        assert any("Japanese comes from speech recognition" in p for p in prompts)
        assert any("English comes from speech recognition" in p for p in prompts)

    def test_both_prompts_carry_the_same_glossary(self) -> None:
        glossary = (
            translate.GlossaryEntry("Kirby", "卡比"),
            translate.GlossaryEntry("カービィ", "卡比"),
        )
        ja = translate.build_request(
            [Cue(1, 0, 1000, "カービィです。", lang=JA)],
            translate.Batch((translate.Unit(0, 1),)),
            glossary,
            source=MIXED_SOURCE,
        )
        en = translate.build_request(
            [Cue(1, 0, 1000, "Kirby is here.", lang=EN)],
            translate.Batch((translate.Unit(0, 1),)),
            glossary,
            source=MIXED_SOURCE,
        )
        for request in (ja, en):
            system = request.messages[0]["content"]
            assert '"Kirby" must be translated as "卡比"' in system
            assert '"カービィ" must be translated as "卡比"' in system
        assert '"ja"' in ja.messages[1]["content"] and '"en"' in en.messages[1]["content"]

    def test_batches_never_mix_languages_and_context_comes_from_the_same_language(self) -> None:
        cues = [
            Cue(1, 0, 1000, "前の文です。", lang=JA),
            Cue(2, 1000, 2000, "The previous sentence.", lang=EN),
            Cue(3, 2000, 3000, "次の文です。", lang=JA),
            Cue(4, 3000, 4000, "The next sentence.", lang=EN),
        ]
        batches = translate.plan_batches(cues, 10, source=MIXED_SOURCE)
        assert [(b.start, b.stop) for b in batches] == [(0, 1), (1, 2), (2, 3), (3, 4)]
        request = translate.build_request(cues, batches[2], (), 5, source=MIXED_SOURCE)
        body = json.loads(request.messages[1]["content"])
        assert body["context_before"] == "前の文です。"
        assert "previous" not in body["context_before"]

    def test_the_japanese_checks_apply_to_japanese_cues_only(self) -> None:
        cues = [
            Cue(1, 0, 1000, "カメラです。", lang=JA),
            Cue(2, 1000, 2000, "It is a camera.", lang=EN),
        ]

        def check(index: int, zh: str) -> dict[int, str]:
            batch = translate.Batch((translate.Unit(index, index + 1),))
            request = translate.build_request(cues, batch, (), source=MIXED_SOURCE)
            text = json.dumps(
                {"translations": [{"id": cues[index].id, "zh": zh}]}, ensure_ascii=False
            )
            return translate.parse_reply(
                text, request, cues, (), source=MIXED_SOURCE.of(cues[index].lang)
            )

        with pytest.raises(translate.ReplyError, match="kana"):
            check(0, "這是カメラ。")
        assert check(1, "這是一台相機。") == {2: "這是一台相機。"}

    def test_a_second_run_does_nothing_and_a_new_llm_reruns_only_the_language_steps(
        self, tmp_path: Path
    ) -> None:
        video, folder = tmp_path / "talk.mp4", tmp_path / "project"
        video.write_bytes(b"x")
        fakes = MixedFakes(words=mixed_words())
        run(video, folder, MIXED_SETTINGS, fakes.ports())
        assert run(video, folder, MIXED_SETTINGS, fakes.ports()).ran == ()
        report = run(video, folder, replace(MIXED_SETTINGS, llm_identity="b"), fakes.ports())
        assert report.ran == (Step.TRANSLATE, Step.EXPORT, Step.SUMMARIZE)

    def test_the_summary_notes_are_asked_for_japanese_and_english_talk(
        self, tmp_path: Path
    ) -> None:
        _, fakes = self.run_it(tmp_path)
        assert any("spoken in Japanese and English" in text for text in fakes.asked)


class TestCacheKeys:
    @staticmethod
    def keys(settings: Settings) -> dict[Step, str]:
        out: dict[Step, str] = {}
        for spec in STEPS:
            out[spec.step] = derive_key(spec, settings, "1:2", out)
        return out

    def test_only_the_mixed_source_changes_keys_and_english_and_japanese_keep_theirs(self) -> None:
        base = Settings("e", "a", "v", "l")
        english = self.keys(base)
        japanese = self.keys(replace(base, source_lang="ja"))
        mixed_keys = self.keys(replace(base, source_lang="ja+en"))
        assert all(english[s] != mixed_keys[s] for s in (Step.VAD, Step.ASR, Step.TRANSLATE))
        assert english[Step.AUDIO] == mixed_keys[Step.AUDIO]
        assert japanese[Step.VAD] == english[Step.VAD]
        assert japanese[Step.ASR] != english[Step.ASR]

    def test_the_japanese_keys_are_what_p23a_made(self) -> None:
        base = Settings("e", "a", "v", "l", source_lang="ja")
        keys = self.keys(base)
        assert keys[Step.VAD] == self.keys(replace(base, source_lang="en"))[Step.VAD]


class TestTable:
    def test_the_mixed_source_names_its_members_and_its_engine(self) -> None:
        source = get_source("ja+en")
        assert source is SOURCES["ja+en"] and source.mixed
        assert source.of("en") is ENGLISH_SOURCE and source.of("ja") is JAPANESE_SOURCE
        assert JAPANESE_SOURCE.of("ja") is JAPANESE_SOURCE and not JAPANESE_SOURCE.mixed
        assert source.files.subs == "subs.src.json" and source.files.srt == "src.srt"
        assert source.targets == frozenset({"zh-TW"})

    def test_the_engine_id_in_the_table_is_the_real_one(self) -> None:
        from backend.engines.crispasr import ENGINE_ID

        assert MIXED_SOURCE.asr_engine == ENGINE_ID

    def test_a_window_of_mixed_text_is_sized_by_its_japanese_and_its_english(self) -> None:
        assert MIXED_SOURCE.words("Today I will talk") == 4
        assert MIXED_SOURCE.words("あいうえ") == 2


class TestBurnFont:
    def test_the_font_check_looks_at_the_japanese_part_only(self) -> None:
        cues = [
            Cue(1, 0, 1000, "カメラです。", lang=JA),
            Cue(2, 1000, 2000, "It is a camera.", lang=EN),
        ]
        asked: list[set[str]] = []

        def lookup(chars: Iterable[str]) -> Callable[[str], tuple[Path, set[str]] | None]:
            asked.append(set(chars))
            return lambda family: (Path(family), set())

        assert burn_font(cues, lookup) == "Yu Gothic"
        assert asked == [set("カメラです。")]
        assert burn_font([cues[1]], lookup) == "Arial"


def test_the_cue_json_of_a_mixed_file_keeps_english_cues_in_the_old_shape() -> None:
    cues = [
        Cue(1, 0, 1000, "カメラです。", "相機。", JA),
        Cue(2, 1000, 2000, "A camera.", "相機。", EN),
    ]
    rows = json.loads(render_subs(cues))["cues"]
    assert rows[0]["lang"] == JA and "en" not in rows[0]
    assert rows[1]["en"] == "A camera." and "lang" not in rows[1]
    assert parse_subs(render_subs(cues)) == cues


def test_rules_are_per_language_in_the_settings() -> None:
    assert MIXED_SETTINGS.rules_of(JA) == JAPANESE_SOURCE.cues
    assert MIXED_SETTINGS.rules_of(EN) == CueRules()
