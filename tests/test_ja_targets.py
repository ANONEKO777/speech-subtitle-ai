# pyright: reportPrivateUsage=false
"""A Japanese talk translated into English, Simplified Chinese and Korean (P26a).

Every sentence of Japanese below is invented. The hashes pinned here are the ones main computed for
the Traditional Chinese flow before the targets existed, so a change to what that flow sends to the
model or keys its cache on fails a test.
"""

from __future__ import annotations

import hashlib
import json
import random
import re
import time
from collections.abc import Callable, Generator, Sequence
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest
from test_api import GUARD, Client, open_client
from test_japanese import ja_settings, whisper_words
from test_pipeline import SETTINGS, Fakes
from test_queue import Power, QueueRig, add, video
from test_summarize import good_map, good_reduce

from backend.core import cue_failures, fonts, pipeline, summarize, translate
from backend.core.ja_routes import ROUTES
from backend.core.ja_terms import JA_TERMS
from backend.core.jobs import JobOptions
from backend.core.languages import LANGUAGES, traditional_chars
from backend.core.languages import get as get_language
from backend.core.model import Cue, Segment, Step
from backend.core.notices import notices_of
from backend.core.pipeline import STEPS, Ports, Settings, derive_key, run
from backend.core.segmenter import merge_words
from backend.core.source_langs import (
    ENGLISH_SOURCE,
    JAPANESE_SOURCE,
    MIXED_SOURCE,
    SourceLanguage,
)
from backend.core.subtitle_io import parse_project, parse_subs, read_text_file, render_burn_ass
from backend.core.target_routes import OnFailure
from backend.core.translate import Batch, Failure, Unit, build_request, parse_reply
from backend.llm.ask import ReplyError
from backend.llm.client import LlmError, Message
from backend.main import AppConfig, create_app

ZH_TW = get_language("zh-TW")
EN = get_language("en")
ZH_CN = get_language("zh-CN")
KO = get_language("ko")
NEW_TARGETS = ("en", "zh-CN", "ko")

BRANCH = "ええと、先月、パワフォースのブランチを切ってシェルブしました。"
SHORT = "はい。"
GOOD = {
    "en": "Last month I created a branch in Perforce and shelved my changes.",
    "zh-CN": "上个月，我在 Perforce 里创建了分支，并且搁置了修改。",
    "ko": "지난달에 Perforce에서 브랜치를 만들고 변경 사항을 셸브했습니다.",
}


def sha(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def blake(value: object) -> str:
    text = json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.blake2b(text.encode(), digest_size=8).hexdigest()


def routed(code: str) -> SourceLanguage:
    return JAPANESE_SOURCE.toward(get_language(code))


def system_prompt(code: str, text: str = BRANCH) -> str:
    cues = [Cue(1, 0, 3000, text, lang="ja")]
    batch = translate.plan_batches(cues, source=routed(code))[0]
    glossary = translate.default_glossary("ja")
    request = build_request(cues, batch, glossary, lang=get_language(code), source=routed(code))
    return request.messages[0]["content"]


def read(code: str, reply: str, text: str = BRANCH) -> dict[int, str]:
    lang, source = get_language(code), routed(code)
    cues = [Cue(1, 0, 3000, text, lang="ja")]
    request = build_request(cues, Batch((Unit(0, 1),)), (), lang=lang, source=source)
    body = json.dumps({"translations": [{"id": 1, lang.prompt.key: reply}]}, ensure_ascii=False)
    return parse_reply(body, request, cues, (), lang, source)


def refused(code: str, reply: str, text: str = BRANCH) -> str:
    with pytest.raises(ReplyError) as caught:
        read(code, reply, text)
    return str(caught.value)


class TestTable:
    def test_a_japanese_talk_has_four_targets_and_korean_is_experimental(self) -> None:
        assert JAPANESE_SOURCE.targets == {"zh-TW", "en", "zh-CN", "ko"}
        assert JAPANESE_SOURCE.allowed_targets() == "zh-TW, zh-CN, en, ko"
        assert JAPANESE_SOURCE.targets is not None
        assert {
            c: JAPANESE_SOURCE.experimental(get_language(c)) for c in JAPANESE_SOURCE.targets
        } == {
            "zh-TW": False,
            "en": False,
            "zh-CN": False,
            "ko": True,
        }

    def test_the_other_nine_languages_are_not_targets_of_a_japanese_talk(self) -> None:
        for code in ("es", "fr", "de", "pt", "it", "ru", "vi", "th", "id", "ja"):
            assert not JAPANESE_SOURCE.supports(get_language(code)), code

    def test_a_mixed_talk_still_has_traditional_chinese_only(self) -> None:
        assert MIXED_SOURCE.allowed_targets() == "zh-TW"

    def test_english_speech_has_every_language_but_english(self) -> None:
        assert not ENGLISH_SOURCE.supports(EN)
        assert "en" not in ENGLISH_SOURCE.allowed_targets().split(", ")
        assert len(ENGLISH_SOURCE.supported_targets()) == len(LANGUAGES) - 1

    def test_a_row_exists_for_each_new_target_and_a_target_is_a_data_change(self) -> None:
        assert set(ROUTES) == set(NEW_TARGETS)
        assert [ROUTES[c].experimental for c in NEW_TARGETS] == [False, False, True]
        assert ROUTES["ko"].on_failure is OnFailure.ENGLISH_PIVOT
        assert ROUTES["en"].on_failure is ROUTES["zh-CN"].on_failure is OnFailure.LEAVE_EMPTY
        assert JAPANESE_SOURCE.on_failure is OnFailure.KEEP_SOURCE

    def test_the_first_target_is_the_source_itself(self) -> None:
        assert JAPANESE_SOURCE.toward(ZH_TW) is JAPANESE_SOURCE
        assert ENGLISH_SOURCE.toward(KO) is ENGLISH_SOURCE
        assert MIXED_SOURCE.toward(EN) is MIXED_SOURCE

    def test_a_routed_source_keeps_its_files_cue_rules_and_sentence_ends(self) -> None:
        for code in NEW_TARGETS:
            source = routed(code)
            assert source.files == JAPANESE_SOURCE.files
            assert source.cues == JAPANESE_SOURCE.cues
            assert source.sentence_end == JAPANESE_SOURCE.sentence_end
            assert source.repair is None and source.fix_from_source is None
            assert source.toward(get_language(code)) == source


class TestPrompt:
    @pytest.mark.parametrize("code", NEW_TARGETS)
    def test_the_target_has_its_own_worked_example_and_no_taiwan_rule(self, code: str) -> None:
        text = system_prompt(code)
        assert ROUTES[code].example in text
        assert ROUTES[code].example != JAPANESE_SOURCE.prompt.examples["zh-TW"]
        scrubbed = text.replace("(not 儲存倉)", "").replace("not Taiwan wording", "")
        for taiwan in ("Traditional form", "Taiwan", "儲存倉", "通關", "整備", "為了解決這個問題"):
            assert taiwan not in scrubbed, taiwan
        assert not re.search(r"<<(?!GLOSSARY)", text)

    @pytest.mark.parametrize("code", NEW_TARGETS)
    def test_the_rules_about_speech_stay(self, code: str) -> None:
        text = system_prompt(code)
        for kept in (
            "ええと",
            "Japanese often leaves the subject out",
            "51.9% stays 51.9%",
            "stays in Latin letters",
            "Never leave a name in kana",
            "mishearings",
        ):
            assert kept in text, kept

    def test_the_prompt_of_the_first_target_is_byte_for_byte_what_main_sent(self) -> None:
        text = system_prompt("zh-TW")
        assert sha(JAPANESE_SOURCE.prompt.rules)[:16] == "32d5dae24e41cbd1"
        assert "Write every Japanese kanji in its Traditional form as used in Taiwan" in text
        assert "A code repository is 儲存倉 (not 倉庫 or 儲存庫)" in text
        assert "Translate a loanword by meaning when Taiwan has a common word for it" in text
        assert "a link such as 為了解決這個問題 or 因此" in text
        assert ROUTES["en"].rules not in text

    def test_english_asks_for_english_and_latin_letters_for_a_name(self) -> None:
        text = system_prompt("en")
        assert "into English." in text
        assert "Write English only. Never leave a kana or a kanji" in text
        assert "when English has a common word for it" in text

    def test_simplified_chinese_gets_mainland_wording_and_simplified_kanji(self) -> None:
        text = system_prompt("zh-CN")
        assert "into Simplified Chinese as used in Mainland China" in text
        assert "気 becomes 气" in text and "支持 (not 支援)" in text
        assert "Traditional form as used in Taiwan" not in text

    def test_korean_gets_the_formal_style_only_and_no_kana_or_hanja(self) -> None:
        text = system_prompt("ko")
        assert "합니다 endings only, never the 해요" in text
        assert "never kana and never Chinese characters" in text

    @pytest.mark.parametrize("code", NEW_TARGETS)
    def test_the_worked_example_is_a_reply_the_checks_accept(self, code: str) -> None:
        lang = get_language(code)
        reply = json.loads(ROUTES[code].example)["translations"]
        assert [e["id"] for e in reply] == [7, 9]
        assert all(set(e) == {"id", lang.prompt.key} for e in reply)
        for entry in reply:
            text = re.sub(r"\[\[\d+\]\]", "", entry[lang.prompt.key])
            assert lang.check(text, "", True) is None
            assert routed(code).problem(text) is None

    def test_a_term_the_text_has_is_told_in_the_form_of_the_target(self) -> None:
        text = BRANCH
        assert '"シェルブ" must be translated as "shelve"' in system_prompt("en", text)
        assert '"シェルブ" must be translated as "搁置"' in system_prompt("zh-CN", text)
        assert '"シェルブ" must be translated as "擱置"' in system_prompt("zh-TW", text)
        assert '"ブランチ" must be translated as "branch"' in system_prompt("en", text)
        assert "擱置" not in system_prompt("en", text) and "shelve" not in system_prompt(
            "zh-TW", text
        )

    def test_the_perforce_words_have_a_form_in_english_and_simplified_chinese(self) -> None:
        said = {
            "シェルブ": ("shelve", "搁置"),
            "ストリーム": ("stream", "Stream"),
            "ブランチ": ("branch", "分支"),
            "ワークスペース": ("workspace", "工作区"),
            "チェンジリスト": ("changelist", "变更列表"),
            "サブミット": ("submit", "提交"),
            "シンク": ("sync", "同步"),
        }
        for ja, (en, zh) in said.items():
            for code, form in (("en", en), ("zh-CN", zh)):
                terms = {t.said.split(" (")[0]: t.zh for t in routed(code).terms}
                assert terms[ja] == form, (code, ja)

    def test_シンク_is_sync_and_シンクロ_is_not(self) -> None:
        sync = next(t for t in routed("en").terms if t.zh == "sync")
        assert sync.in_source("P4でシンクします")
        assert not sync.in_source("シンクロナイズ") and not sync.in_source("アシンク")

    def test_the_product_names_are_in_every_target(self) -> None:
        for code in NEW_TARGETS:
            names = {t.zh for t in routed(code).terms}
            assert {"ChatGPT", "Claude Code", "Claude", "Visual Studio Code", "Copilot"} <= names

    def test_the_taiwan_term_table_is_not_given_to_another_target(self) -> None:
        assert not re.search("[぀-ヿ一-鿿]", "".join(t.zh for t in routed("en").terms))
        assert not traditional_chars("".join(t.zh for t in routed("zh-CN").terms))
        assert JAPANESE_SOURCE.terms == JA_TERMS


class TestChecks:
    @pytest.mark.parametrize("code", NEW_TARGETS)
    def test_a_good_reply_passes_and_is_returned_as_written(self, code: str) -> None:
        assert read(code, GOOD[code]) == {1: GOOD[code]}

    def test_english_has_no_kana_and_no_kanji(self) -> None:
        assert "kana" in refused("en", "Last month I made the ブランチ in Perforce.")
        assert "Japanese kana" in refused("en", "Last month I made a branch, ええと, in Perforce.")
        assert "Japanese kana" in refused("en", GOOD["en"] + "。ね")
        assert "contains" in refused("en", "Last month I made a 分支 in Perforce.")

    def test_a_reply_left_in_japanese_is_not_english(self) -> None:
        assert "contains" in refused("en", BRANCH)

    def test_an_english_reply_for_a_japanese_cue_with_words_needs_latin_letters(self) -> None:
        assert "not translated into English" in refused("en", "12")
        assert read("en", "OK.", SHORT) == {1: "OK."}
        assert "only punctuation" in refused("en", "。", SHORT)

    def test_a_reply_left_in_english_is_refused_by_simplified_chinese_and_korean(self) -> None:
        assert "not translated into Simplified Chinese" in refused(
            "zh-CN", "Last month I created a branch in Perforce and shelved my changes."
        )
        assert "not translated into Korean" in refused(
            "ko", "Last month I created a branch in Perforce and shelved my changes."
        )

    def test_simplified_chinese_has_no_kana_no_japanese_kanji_and_no_traditional_characters(
        self,
    ) -> None:
        assert "Japanese kana" in refused("zh-CN", "上个月我创建了ブランチ并搁置了修改。")
        assert "Japanese kana" in refused("zh-CN", "上个月我创建了分支ね。")
        assert "Japanese kanji forms 気" in refused("zh-CN", "上个月我创建了分支并搁置了修気。")
        assert "Traditional characters" in refused("zh-CN", "上個月我建立了分支並擱置了修改。")

    @pytest.mark.parametrize(
        ("taiwan", "mainland"),
        [
            ("支援", "支持"),
            ("影像", "视频"),
            ("软体", "软件"),
            ("伺服器", "服务器"),
            ("档案", "文件"),
        ],
    )
    def test_simplified_chinese_refuses_a_taiwan_form_the_character_check_cannot_see(
        self, taiwan: str, mainland: str
    ) -> None:
        wrong = f"上个月我在这个{taiwan}里创建了分支并搁置了修改。"
        assert "Taiwan wording" in refused("zh-CN", wrong)
        assert read("zh-CN", wrong.replace(taiwan, mainland))

    def test_the_traditional_spelling_of_the_source_code_is_caught_by_its_characters(self) -> None:
        assert "Traditional characters" in refused(
            "zh-CN", "我们改了原始碼并搁置了修改，上个月的事。"
        )

    def test_korean_has_hangul_and_no_kana_no_hanja(self) -> None:
        assert "Japanese kana" in refused("ko", "지난달에 ブランチ를 만들고 셸브했습니다.")
        assert "Japanese kana" in refused("ko", "지난달에 브랜치를 만들고 셸브했습니다ね.")
        assert "Chinese" in refused("ko", "지난달에 分支를 만들고 셸브했습니다.")

    def test_a_korean_reply_with_a_latin_syllable_in_a_hangul_word_is_refused(self) -> None:
        assert "Latin letters inside a Hangul word" in refused(
            "ko", "지난달에 리lease 브랜치를 만들고 셸브했습니다."
        )
        assert read("ko", "지난달에 PR을 올리고 Perforce를 썼습니다.")

    def test_an_english_sentence_left_in_korean_or_chinese_is_refused(self) -> None:
        tail = (
            "Perforce official implementation. Following this flow, the left side is what you use"
        )
        assert "English text" in refused("ko", f"지난달에 브랜치를 만들었습니다 {tail}")
        assert "English text" in refused("zh-CN", f"上个月我创建了分支并搁置了修改 {tail}")

    def test_product_and_feature_names_in_latin_letters_are_not_an_english_sentence(self) -> None:
        names = "Visual Studio Code와 GitHub Copilot Chat Extension 그리고 Model Context Protocol"
        assert read("ko", f"지난달에 {names}을 썼습니다", BRANCH * 2)
        assert read(
            "zh-CN",
            "上个月我用了 Visual Studio Code 和 GitHub Copilot Chat Extension 创建分支。",
            BRANCH * 2,
        )

    def test_a_cue_with_few_characters_may_come_back_as_a_mark(self) -> None:
        for code, text in (("en", "OK."), ("zh-CN", "好。"), ("ko", "네.")):
            assert read(code, text, SHORT)

    def test_a_long_cue_must_hold_the_script_of_its_target(self) -> None:
        for code in ("zh-CN", "ko"):
            assert "not translated" in refused(code, "Perforce, P4, PR, MCP, AI")

    def test_the_script_check_is_what_the_registry_has_for_the_first_target(self) -> None:
        assert JAPANESE_SOURCE.needs_script is None
        assert read("zh-TW", "上個月，我在 Perforce 裡建立了分支並擱置了修改。")
        assert read("zh-TW", "Last month I created a branch.") == {
            1: "Last month I created a branch."
        }

    def test_the_first_target_still_refuses_kana_and_japanese_kanji(self) -> None:
        source = JAPANESE_SOURCE
        assert source.problem("上個月ね") is not None
        assert source.problem("上個月氣") is None
        assert source.problem("上個月気") is not None


class TestLength:
    def test_the_limits_are_one_and_a_half_times_the_measured_90th_percentile(self) -> None:
        measured = {"en": 2.78, "zh-CN": 0.90, "ko": 1.28}
        for code, p90 in measured.items():
            limit = ROUTES[code].density.max_per_en_char
            assert limit == pytest.approx(1.5 * p90, abs=0.06), code
            assert ROUTES[code].density.slack == 8

    @pytest.mark.parametrize("code", NEW_TARGETS)
    def test_each_target_has_its_own_limit_and_it_is_checked_at_the_edge(self, code: str) -> None:
        density = ROUTES[code].density
        edge = int(density.max_per_en_char * len(BRANCH) + density.slack)
        char = {"en": "a", "zh-CN": "字", "ko": "가"}[code]
        assert read(code, char * edge)
        assert "longer" in refused(code, char * (edge + 1))

    def test_the_first_target_keeps_its_limit_and_english_would_not_fit_in_it(self) -> None:
        assert (
            JAPANESE_SOURCE.density is not None and JAPANESE_SOURCE.density.max_per_en_char == 1.1
        )
        assert "longer" in refused("zh-TW", "字" * 60)
        english = "a" * round(len(BRANCH) * 2.0)
        assert read("en", english)
        assert len(english) > JAPANESE_SOURCE.density.max_per_en_char * len(BRANCH) + 8

    def test_a_cue_of_a_few_characters_is_not_held_to_the_minimum(self) -> None:
        assert read("en", "OK.", SHORT) == {1: "OK."}

    @pytest.mark.parametrize("code", NEW_TARGETS)
    def test_a_translation_far_shorter_than_the_cue_is_refused(self, code: str) -> None:
        text = BRANCH * 2
        assert "shorter" in refused(code, {"en": "Yes.", "zh-CN": "是。", "ko": "네."}[code], text)

    def test_a_long_english_cue_wraps_with_the_existing_renderer(self) -> None:
        from backend.core.subtitle_io import ASS_ZH_LINE_COLUMNS, wrap_line

        cue = "So last month I created a branch in Perforce and shelved my changes to share them"
        lines = wrap_line(cue, EN.wrap)
        assert len(lines) == 3 and all(len(line) <= ASS_ZH_LINE_COLUMNS for line in lines)
        assert "".join(lines) == cue


class RoutedChat:
    """A server that answers each target as the test says: the Korean prompt gets `korean`, the
    English prompt `english`, and any other target `other`."""

    def __init__(self, **replies: str | Callable[[str], str]) -> None:
        self.replies = replies
        self.targets: list[str] = []

    def __call__(self, messages: Sequence[Message], temperature: float) -> str:
        system = messages[0]["content"]
        code = next(
            (
                c
                for c in ("ko", "zh-CN", "en", "zh-TW")
                if f"into {get_language(c).prompt.target}." in system
            ),
            "zh-TW",
        )
        self.targets.append(code)
        reply = self.replies[code]
        entries = json.loads(messages[1]["content"])["translate"]
        key = get_language(code).prompt.key
        text = reply(entries[0]["ja"]) if callable(reply) else reply
        return json.dumps(
            {"translations": [{"id": entries[0]["id"], key: text}]}, ensure_ascii=False
        )


def run_one(code: str, chat: RoutedChat, text: str = BRANCH) -> tuple[list[Cue], list[Failure]]:
    failures: list[Failure] = []
    cues = translate.run(
        [Cue(1, 0, 3000, text, lang="ja")],
        chat,
        translate.default_glossary("ja"),
        max_retries=1,
        keep_english=True,
        lang=get_language(code),
        source=JAPANESE_SOURCE,
        on_failure=failures.append,
        sleep=lambda _s: None,
    )
    return cues, failures


class TestFailedCues:
    def test_a_korean_cue_that_keeps_failing_is_translated_into_english_alone(self) -> None:
        chat = RoutedChat(ko="지난달에 ブランチ를 만들었습니다.", en=GOOD["en"])
        cues, failures = run_one("ko", chat)
        assert cues[0].zh == GOOD["en"]
        assert failures == [Failure(1, english=True)]
        assert chat.targets[-1] == "en" and chat.targets.count("ko") == 2

    def test_the_english_of_a_failed_korean_cue_is_checked_too(self) -> None:
        chat = RoutedChat(ko="ブランチ", en="Last month I made a ブランチ and shelved it.")
        cues, failures = run_one("ko", chat)
        assert cues[0].zh == ""
        assert failures == [Failure(1, english=False)]

    def test_a_failed_cue_never_shows_the_japanese_in_a_new_target(self) -> None:
        for code, bad in (("ko", "ブランチ"), ("zh-CN", "ブランチ"), ("en", "ブランチ")):
            chat = RoutedChat(ko=bad, **{"zh-CN": bad, "en": bad})
            cues, failures = run_one(code, chat)
            assert cues[0].zh != BRANCH and not re.search("[ぁ-ヿ]", cues[0].zh), code
            assert [f.cue_id for f in failures] == [1], code

    def test_english_and_simplified_chinese_leave_a_failed_cue_empty_and_count_it(self) -> None:
        for code in ("en", "zh-CN"):
            chat = RoutedChat(**{"zh-CN": "ブランチ", "en": "ブランチ"})
            cues, failures = run_one(code, chat)
            assert cues[0].zh == ""
            assert failures == [Failure(1, english=False)]
            assert set(chat.targets) == {code}

    def test_the_first_target_keeps_the_japanese_as_it_always_did_and_reports_nothing(self) -> None:
        chat = RoutedChat(**{"zh-TW": "こんにちは"})
        cues, failures = run_one("zh-TW", chat)
        assert cues[0].zh == BRANCH
        assert failures == []

    def test_a_good_reply_reports_no_failure(self) -> None:
        for code in NEW_TARGETS:
            cues, failures = run_one(code, RoutedChat(**{c: GOOD[c] for c in NEW_TARGETS}))
            assert cues[0].zh == GOOD[code] and failures == []

    def test_the_english_cue_is_a_pivot_of_the_same_unit_not_a_summary_of_its_neighbours(
        self,
    ) -> None:
        seen: list[str] = []

        def english(ja: str) -> str:
            seen.append(ja)
            return GOOD["en"]

        run_one("ko", RoutedChat(ko="ブランチ", en=english))
        assert seen == [BRANCH]


SUMMARY_TEXT = {"Simplified Chinese": "这场演讲谈信任。", "Korean": "이 발표는 신뢰를 다룹니다."}


class TargetFakes(Fakes):
    """Answers each target in its own script and the reduce call in the language it is asked for."""

    def translate(self, messages: Sequence[Message], temperature: float) -> str:
        self.translate_calls += 1
        system = messages[0]["content"]
        code = next(
            c
            for c in ("ko", "zh-CN", "en", "zh-TW")
            if f"into {get_language(c).prompt.target}." in system
        )
        sample = {"zh-TW": "譯", "zh-CN": "译", "en": "word ", "ko": "번역 "}[code]
        stop = "。" if code.startswith("zh") else "."
        entries = json.loads(messages[1]["content"])["translate"]
        out: list[dict[str, object]] = []
        for entry in entries:
            pieces = re.split(r"(\[\[\d+\]\])", entry["ja"])
            text = "".join(
                p
                if re.fullmatch(r"\[\[\d+\]\]", p)
                else (sample * len(p))[: max(4, len(p) // 2)].strip() + stop
                for p in pieces
                if p.strip()
            )
            out.append({"id": entry["id"], get_language(code).prompt.key: text})
        return json.dumps({"translations": out}, ensure_ascii=False)

    def summarize(self, messages: Sequence[Message], temperature: float) -> str:
        if messages[1]["content"].startswith("Part "):
            self.asked.append(messages[0]["content"])
            return good_map(messages)
        system = messages[0]["content"]
        if "Traditional Chinese" in system:
            return good_reduce(messages, "zh-TW")
        doc = json.loads(good_reduce(messages, "en"))
        text = next((t for name, t in SUMMARY_TEXT.items() if name in system), None)
        if text:
            doc["one_liner"] = doc["key_points"][0] = text
            for chapter in doc["chapters"]:
                chapter["title"], chapter["summary"] = text[:6], text
        return json.dumps(doc, ensure_ascii=False)


def target_fakes(kind: type[TargetFakes] = TargetFakes) -> TargetFakes:
    words = merge_words([Segment("", 0, 1, tuple(whisper_words("ja")))])
    return kind(words=words)


def stat(folder: Path, names: Sequence[str]) -> dict[str, tuple[int, int]]:
    return {n: ((s := (folder / n).stat()).st_mtime_ns, s.st_size) for n in names}


class TestProject:
    @pytest.fixture
    def project(self, tmp_path: Path) -> tuple[Path, Path]:
        video = tmp_path / "talk.mp4"
        video.write_bytes(b"x")
        return video, tmp_path / "project"

    def test_four_targets_live_side_by_side_and_none_overwrites_another(
        self, project: tuple[Path, Path]
    ) -> None:
        video, folder = project
        fakes = target_fakes()
        for code in ("zh-TW", "en", "zh-CN", "ko"):
            run(video, folder, ja_settings(target_lang=code), fakes.ports())
        text: dict[str, str] = {}
        for code in ("zh-TW", "en", "zh-CN", "ko"):
            files = get_language(code).files
            for name in (files.subs, files.srt, files.ass, files.vtt, files.summary):
                assert (folder / name).is_file(), name
            text[code] = "".join(c.zh for c in parse_subs(read_text_file(folder / files.subs)))
        assert len(set(text.values())) == 4
        assert re.search("[A-Za-z]", text["en"]) and not re.search("[ぁ-ヿ一-鿿]", text["en"])
        assert re.search("[가-힣]", text["ko"]) and "译" in text["zh-CN"] and "譯" in text["zh-TW"]
        assert (folder / "bilingual.src-en.ass").is_file() and (folder / "bilingual.ass").is_file()
        assert (folder / "ja.srt").is_file() and not (folder / "subs.src.json").exists()

    def test_a_new_target_reruns_only_the_translation_and_below(
        self, project: tuple[Path, Path]
    ) -> None:
        video, folder = project
        fakes = target_fakes()
        first = run(video, folder, ja_settings(), fakes.ports())
        assert first.ran == tuple(Step)
        before = stat(folder, ("audio.wav", "chunks.json", "segments.json", "subs.ja.json"))
        for code in NEW_TARGETS:
            report = run(video, folder, ja_settings(target_lang=code), fakes.ports())
            assert report.ran == (Step.TRANSLATE, Step.EXPORT, Step.SUMMARIZE), code
        assert (fakes.extracted, fakes.split, fakes.transcribed) == (1, 1, 1)
        assert stat(folder, ("audio.wav", "chunks.json", "segments.json", "subs.ja.json")) == before

    def test_every_target_is_cached_after_its_run_and_all_are_kept_in_the_project(
        self, project: tuple[Path, Path]
    ) -> None:
        video, folder = project
        fakes = target_fakes()
        for code in ("zh-TW", *NEW_TARGETS):
            run(video, folder, ja_settings(target_lang=code), fakes.ports())
        asked = fakes.translate_calls
        for code in ("zh-TW", *NEW_TARGETS):
            assert run(video, folder, ja_settings(target_lang=code), fakes.ports()).ran == ()
        assert fakes.translate_calls == asked
        state = parse_project(read_text_file(folder / "project.json"))
        assert state.active_lang == "ko" and set(state.parked) == {"zh-TW", "en", "zh-CN"}

    def test_the_translation_of_each_target_carries_its_own_cache_key(self) -> None:
        keys = {
            code: derive_keys(ja_settings(target_lang=code)) for code in ("zh-TW", *NEW_TARGETS)
        }
        for step in ("translate", "export", "summarize"):
            assert len({k[step] for k in keys.values()}) == 4, step
        for step in ("audio", "vad", "asr", "segment"):
            assert len({k[step] for k in keys.values()}) == 1, step

    def test_the_cache_key_of_an_old_japanese_traditional_chinese_project_is_what_main_made(
        self,
    ) -> None:
        settings = Settings("e", "a", "v", "l", source_lang="ja")
        assert derive_keys(settings) == {
            "audio": "a5890e8fdc0d66b9ae85e292b03caac0",
            "vad": "385eedf77f0318d194d945f0f0a855a3",
            "asr": "fc5bab4cdfbf1544f5687a147a2bb9ef",
            "segment": "f7370dd392937231c16315bac6faaec0",
            "translate": "e83ae550f61bcbce2694dbf193056ad6",
            "export": "c8b508d0f3b707a3b192b55c61e1bbc0",
            "summarize": "a6a2861d5abbe4087242fee969af1c30",
        }
        assert derive_keys(replace(settings, summary_en=True))["summarize"] == (
            "cde5aa48f726b5cb1c4d7c25ab84ef61"
        )
        assert pipeline._translate_prompt_digest("zh-TW", "ja") == "dc414767fe70bfb8"
        assert pipeline._translate_prompt_digest("zh-TW", "ja+en") == "6327fe6cb944686c"

    def test_the_requests_of_the_first_target_are_the_ones_main_sent(self) -> None:
        lines = (
            "ええと、先月、パワフォースのブランチを切ってシェルブしました。",
            "ストリームの設定をチェンジリストにまとめて、サブミットします。",
            "二千件のPRを出しました。51.9%でした。",
            "で、あの、ファイルをロックしてマージします。",
            "ありがとうございます。",
            "VSコードとクロードコードを使います。",
        )
        random.seed(11)
        cues = [
            Cue(
                i,
                i * 1500,
                i * 1500 + 1400,
                random.choice(lines) + random.choice(["", "ね。", "よ。", "です。"]),
                lang="ja",
            )
            for i in range(1, 70)
        ]
        batches = translate.plan_batches(cues, 20, 6, JAPANESE_SOURCE)
        requests = [
            build_request(cues, b, translate.default_glossary("ja"), 5, ZH_TW, JAPANESE_SOURCE)
            for b in batches
        ]
        assert blake([r.messages for r in requests]) == "451552bd554a3ee7"
        assert (
            blake(
                [
                    (u.start, u.stop)
                    for u in translate.sentence_units(cues, 0, len(cues), 6, JAPANESE_SOURCE)
                ]
            )
            == "bd7cc05334b36ba1"
        )

    def test_a_map_prompt_of_each_target_is_the_one_a_run_asks(
        self, project: tuple[Path, Path]
    ) -> None:
        video, folder = project
        fakes = target_fakes()
        for code, wanted in (("ko", "Korean"), ("zh-CN", "Simplified"), ("en", "in English")):
            fakes.asked.clear()
            run(video, folder, ja_settings(target_lang=code), fakes.ports())
            maps = [text for text in fakes.asked if "take notes on one part" in text]
            assert maps and all(wanted in text for text in maps), code
            assert not any("Traditional Chinese as used in Taiwan" in text for text in maps), code

    def test_the_translation_key_follows_the_rules_of_the_target(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        before = pipeline._translate_prompt_digest("en", "ja")
        edited = replace(ROUTES["en"], rules=ROUTES["en"].rules + "\n- A new rule.")
        patched = replace(JAPANESE_SOURCE, routes={**ROUTES, "en": edited})

        def get_patched(_code: str) -> SourceLanguage:
            return patched

        monkeypatch.setattr(pipeline, "get_source", get_patched)
        pipeline._translate_prompt_digest.cache_clear()
        try:
            assert pipeline._translate_prompt_digest("en", "ja") != before
            assert pipeline._translate_prompt_digest("zh-TW", "ja") == "dc414767fe70bfb8"
        finally:
            monkeypatch.undo()
            pipeline._translate_prompt_digest.cache_clear()
        assert pipeline._translate_prompt_digest("en", "ja") == before

    def test_a_target_the_source_does_not_have_is_refused_with_the_ones_it_has(self) -> None:
        with pytest.raises(ValueError, match="zh-TW, zh-CN, en, ko, not fr"):
            ja_settings(target_lang="fr")

    def test_an_english_summary_is_not_asked_twice_for_an_english_target(self) -> None:
        assert ja_settings(target_lang="en", summary_en=True).summary_langs == ("en",)
        assert ja_settings(target_lang="ko", summary_en=True).summary_langs == ("ko", "en")
        assert SETTINGS.summary_langs == ("zh-TW",)

    def test_a_job_reports_the_cues_that_failed_every_attempt(
        self, project: tuple[Path, Path]
    ) -> None:
        from backend.core.jobs import _report_json

        video, folder = project

        class Failing(TargetFakes):
            def translate(self, messages: Sequence[Message], temperature: float) -> str:
                entries = json.loads(messages[1]["content"])["translate"]
                body = [{"id": e["id"], "text": "ブランチ"} for e in entries]
                return json.dumps({"translations": body}, ensure_ascii=False)

        fakes = target_fakes(Failing)
        report = run(video, folder, ja_settings(target_lang="en"), fakes.ports())
        cues = parse_subs(read_text_file(folder / "subs.en.json"))
        assert report.failed_cues == tuple(c.id for c in cues) and report.english_cues == ()
        assert all(c.zh == "" for c in cues)
        assert "cues failed every attempt" in report.describe()
        assert _report_json(report)["failed_cues"] == list(report.failed_cues)

    def test_the_failed_cues_stay_with_the_project_until_its_translation_runs_again(
        self, project: tuple[Path, Path]
    ) -> None:
        from backend.api.projects import _failed_cues_json
        from backend.core.projects import ProjectInfo

        video, folder = project

        class Failing(TargetFakes):
            def translate(self, messages: Sequence[Message], temperature: float) -> str:
                if "into English" not in messages[0]["content"]:
                    return super().translate(messages, temperature)
                entries = json.loads(messages[1]["content"])["translate"]
                body = [{"id": e["id"], "text": "ブランチ"} for e in entries]
                return json.dumps({"translations": body}, ensure_ascii=False)

        fakes = target_fakes(Failing)

        def seen() -> dict[str, Any]:
            state = parse_project(read_text_file(folder / "project.json"))
            return _failed_cues_json(ProjectInfo("p", folder, state, {}))

        run(video, folder, ja_settings(target_lang="en"), fakes.ports())
        ids = [c.id for c in parse_subs(read_text_file(folder / "subs.en.json"))]
        assert seen() == {"en": {"failed": ids, "english": []}}
        run(video, folder, ja_settings(target_lang="zh-CN"), fakes.ports())
        assert seen() == {"en": {"failed": ids, "english": []}}
        run(video, folder, ja_settings(target_lang="en"), fakes.ports())
        assert seen() == {"en": {"failed": ids, "english": []}}
        assert not (folder / "failures.zh-CN.json").exists()

    def test_a_translation_that_ran_again_without_failures_clears_the_list(
        self, tmp_path: Path
    ) -> None:
        cue_failures.write(tmp_path, EN, [3, 1], [3])
        assert cue_failures.read(tmp_path, EN) == cue_failures.CueFailures((1, 3), (3,))
        cue_failures.write(tmp_path, EN, [], [])
        assert cue_failures.read(tmp_path, EN) == cue_failures.CueFailures()
        assert not cue_failures.read(tmp_path, EN)

    @pytest.mark.parametrize(
        "text", ["", "not json", "[1, 2]", '{"failed": "x", "english": [true]}']
    )
    def test_a_damaged_list_of_failed_cues_is_no_list(self, tmp_path: Path, text: str) -> None:
        (tmp_path / "failures.en.json").write_text(text)
        assert cue_failures.read(tmp_path, EN) == cue_failures.CueFailures()


def derive_keys(settings: Settings) -> dict[str, str]:
    keys: dict[Step, str] = {}
    for spec in STEPS:
        keys[spec.step] = derive_key(spec, settings, "1:2", keys)
    return {step.value: key for step, key in keys.items()}


class TestSummary:
    def window(self) -> summarize.Window:
        lines = [summarize.Line(0, 1000, "今日は晴れです。")]
        return summarize.make_windows(lines, chars_per_token=1.2)[0]

    def test_the_first_target_keeps_its_notes_prompt_byte_for_byte(self) -> None:
        system = summarize.map_messages(self.window(), 1, JAPANESE_SOURCE)[0]["content"]
        assert system == summarize._template("summarize_map_ja.md")
        assert "Traditional Chinese" in system

    @pytest.mark.parametrize(
        ("code", "wanted", "limit"),
        [
            ("en", "Write every field in English", "35 words"),
            ("zh-CN", "Simplified Chinese as used in Mainland China", "60 Chinese characters"),
            ("ko", "Write every field in Korean", "60 Korean characters"),
        ],
    )
    def test_each_new_target_takes_its_notes_in_its_own_language(
        self, code: str, wanted: str, limit: str
    ) -> None:
        system = summarize.map_messages(self.window(), 1, routed(code))[0]["content"]
        assert wanted in system and f"at most {limit}" in system
        assert "Traditional" not in system.replace("never in Traditional characters", "")
        assert not re.search(r"<<[A-Z_]+>>", system)

    def test_the_notes_prompt_of_a_target_is_in_its_cache_key(self) -> None:
        digests = {
            code: pipeline._summary_prompt_digest(ja_settings(target_lang=code))
            for code in ("zh-TW", *NEW_TARGETS)
        }
        assert len(set(digests.values())) == 4

    def test_a_note_in_kana_is_refused_for_every_target(self) -> None:
        window = self.window()
        body = json.dumps({"topic": "Topic", "points": [{"at": "00:00", "text": "ブランチ"}]})
        for code in NEW_TARGETS:
            with pytest.raises(ReplyError, match="kana"):
                summarize.parse_map(body, window, routed(code))


class TestFonts:
    def lookup(
        self, installed: dict[str, set[str]], calls: list[str] | None = None
    ) -> fonts.Lookup:
        def lookup(chars: Any) -> Callable[[str], tuple[Path, set[str]] | None]:
            wanted = set(chars)
            if calls is not None:
                calls.append("".join(sorted(wanted)))

            def find(family: str) -> tuple[Path, set[str]] | None:
                return (Path(family), wanted & installed[family]) if family in installed else None

            return find

        return lookup

    def cues(self, text: str) -> list[Cue]:
        return [Cue(1, 0, 1000, "こんにちは", lang="ja", zh=text)]

    def test_korean_is_burned_in_a_font_that_has_hangul(self) -> None:
        assert KO.fonts == ("Malgun Gothic",)
        assert (
            fonts.target_font(self.cues("안녕하세요"), KO, self.lookup({"Malgun Gothic": set()}))
            == "Malgun Gothic"
        )

    def test_a_pc_without_a_korean_font_gets_a_message_that_names_the_language(self) -> None:
        with pytest.raises(fonts.FontMissing, match="Korean") as caught:
            fonts.target_font(self.cues("안녕하세요"), KO, self.lookup({}))
        [notice] = notices_of(caught.value)
        assert (notice.code, notice.params["language"]) == ("fonts.noTargetFont", "ko")
        assert "Malgun Gothic" in str(caught.value)

    def test_a_missing_glyph_is_named(self) -> None:
        with pytest.raises(fonts.FontMissing, match="뷁"):
            fonts.target_font(self.cues("안녕 뷁"), KO, self.lookup({"Malgun Gothic": {"뷁"}}))

    def test_chinese_and_english_are_not_looked_up_and_keep_their_font(self) -> None:
        calls: list[str] = []
        for lang in (ZH_TW, ZH_CN, EN):
            font = fonts.target_font(self.cues("héllo 你好"), lang, self.lookup({}, calls))
            assert font == "Microsoft JhengHei"
        assert calls == []

    def test_russian_is_burned_in_a_font_that_has_cyrillic(self) -> None:
        assert (
            fonts.target_font(
                self.cues("Привет"), get_language("ru"), self.lookup({"Arial": set()})
            )
            == "Arial"
        )

    def test_a_korean_project_without_hangul_still_gets_the_korean_font(self) -> None:
        assert fonts.target_font(self.cues("OK"), KO, self.lookup({})) == "Malgun Gothic"

    def test_the_burned_subtitle_names_the_font_of_the_translation(self) -> None:
        cues = self.cues("안녕하세요")
        text = render_burn_ass(
            cues,
            KO.wrap,
            mode="both",
            zh_first=True,
            size_ratio=0.05,
            color="#ffffff",
            target_font="Malgun Gothic",
        )
        assert "Style: Zh,Malgun Gothic," in text
        default = render_burn_ass(
            cues, ZH_TW.wrap, mode="both", zh_first=True, size_ratio=0.05, color="#ffffff"
        )
        assert "Style: Zh,Microsoft JhengHei," in default

    def test_the_fonts_of_this_pc_draw_hangul_cyrillic_and_latin(self) -> None:
        if not fonts.sys.platform.startswith("win"):
            pytest.skip("the registry of installed fonts is a Windows one")
        for lang, sample in ((KO, "안녕하세요 Hello"), (get_language("ru"), "Привет Hello")):
            found = fonts.windows_coverage(sample)(lang.fonts[0])
            if found is None:
                pytest.skip(f"{lang.fonts[0]} is not installed here")
            assert not found[1], lang.code


class TestGapsOfTheFirstRelease:
    """What the independent verifier's mutants of P26a showed no test pinned."""

    def test_the_glyph_message_of_a_target_font_names_the_language(self) -> None:
        with pytest.raises(fonts.FontMissing) as caught:
            fonts.target_font(
                TestFonts().cues("안녕 뷁"), KO, TestFonts().lookup({"Malgun Gothic": {"뷁"}})
            )
        [notice] = notices_of(caught.value)
        assert (notice.code, notice.params["language"]) == ("fonts.missingTargetGlyphs", "ko")
        assert "Korean" in str(caught.value) and "Malgun Gothic" in str(caught.value)

    def test_the_burned_subtitle_of_a_target_is_looked_up_for_that_target(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from backend.api.player import StillBody, _look

        installed: dict[str, set[str]] = {
            "Malgun Gothic": set(),
            "Yu Gothic": set(),
            "Microsoft JhengHei": set(),
        }
        lookup = TestFonts().lookup(installed)
        monkeypatch.setattr(fonts.target_font, "__defaults__", (lookup,))
        monkeypatch.setattr(fonts.burn_font, "__defaults__", (lookup,))
        body = StillBody(time_s=0)
        korean = [Cue(1, 0, 1000, "こんにちは", lang="ja", zh="안녕하세요")]
        assert _look(body, korean, KO).target_font == "Malgun Gothic"
        assert _look(body, korean, ZH_TW).target_font == "Microsoft JhengHei"

    def test_a_pc_without_the_korean_font_refuses_the_burn_with_a_422_naming_the_language(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from fastapi import HTTPException

        from backend.api.player import StillBody, _look

        lookup = TestFonts().lookup({"Yu Gothic": set()})
        monkeypatch.setattr(fonts.target_font, "__defaults__", (lookup,))
        monkeypatch.setattr(fonts.burn_font, "__defaults__", (lookup,))
        korean = [Cue(1, 0, 1000, "こんにちは", lang="ja", zh="안녕하세요")]
        with pytest.raises(HTTPException) as caught:
            _look(StillBody(time_s=0), korean, KO)
        assert caught.value.status_code == 422 and "Korean" in str(caught.value.detail)
        assert [n.params.get("language") for n in notices_of(caught.value.__cause__)] == ["ko"]

    def test_four_english_words_are_a_sentence_and_three_are_not(self) -> None:
        for code, start in (
            ("ko", "지난달에 브랜치를 만들었습니다"),
            ("zh-CN", "上个月我创建了分支并搁置"),
        ):
            assert "English text" in refused(code, f"{start} use the left side"), code
            assert read(code, f"{start} use the left"), code

    def test_four_english_words_with_fewer_than_three_plain_lowercase_ones_are_names(self) -> None:
        text = "지난달에 Visual Studio Code is 브랜치를 만들었습니다"
        assert read("ko", text, BRANCH * 2)

    @pytest.mark.parametrize("code", NEW_TARGETS)
    def test_half_width_kana_are_kana(self, code: str) -> None:
        said = {
            "en": "Last month I made a ﾌﾞﾗﾝﾁ in Perforce.",
            "zh-CN": "上个月我创建了ﾌﾞﾗﾝﾁ。",
            "ko": "지난달에 ﾌﾞﾗﾝﾁ를 만들었습니다.",
        }
        assert "kana" in refused(code, said[code])

    @pytest.mark.parametrize(
        ("taiwan", "mainland"),
        [
            ("支援", "支持"),
            ("影像", "视频"),
            ("软体", "软件"),
            ("资讯", "信息"),
            ("程式", "程序"),
            ("伺服器", "服务器"),
            ("网路", "网络"),
            ("档案", "文件"),
            ("使用者", "用户"),
            ("滑鼠", "鼠标"),
            ("记忆体", "内存"),
            ("预设", "默认"),
            ("最佳化", "优化"),
            ("资料库", "数据库"),
            ("部落格", "博客"),
        ],
    )
    def test_every_taiwan_form_of_the_list_is_refused_in_simplified_chinese(
        self, taiwan: str, mainland: str
    ) -> None:
        wrong = f"上个月我在这个{taiwan}里创建了分支并搁置了修改。"
        assert taiwan in refused("zh-CN", wrong)
        assert read("zh-CN", wrong.replace(taiwan, mainland))

    @pytest.mark.parametrize("code", ["zh-CN", "ko"])
    def test_the_katakana_middle_dot_becomes_the_middle_dot_in_zh_cn_and_korean(
        self, code: str
    ) -> None:
        reply = {
            "zh-CN": "上个月我用了乔治・华盛顿创建分支并搁置了修改。",
            "ko": "지난달에 조지・워싱턴과 브랜치를 만들었습니다.",
        }[code]
        (text,) = read(code, reply).values()
        assert "・" not in text and "·" in text

    def test_the_english_of_a_failed_korean_cue_is_asked_again_when_a_reply_is_refused(
        self,
    ) -> None:
        asked: list[str] = []

        def english(ja: str) -> str:
            asked.append(ja)
            return "Last month I made a ブランチ." if len(asked) == 1 else GOOD["en"]

        chat = RoutedChat(ko="ブランチ", en=english)
        cues, failures = run_one("ko", chat)
        assert cues[0].zh == GOOD["en"] and failures == [Failure(1, english=True)]
        assert len(asked) == 2


@pytest.fixture
def api(tmp_path: Path) -> Generator[Client]:
    rig = QueueRig()
    with open_client(create_app(AppConfig(tmp_path / "data", GUARD, rig.resolve))) as client:
        yield client


class TestApi:
    def test_each_source_lists_its_targets_with_names_and_the_experimental_flag(
        self, api: Client
    ) -> None:
        body = api.get("/api/languages").json()
        by_code = {s["code"]: s["targets"] for s in body["sources"]}
        ja = {t["code"]: t for t in by_code["ja"]}
        assert list(ja) == ["zh-TW", "zh-CN", "en", "ko"]
        assert {c: t["experimental"] for c, t in ja.items()} == {
            "zh-TW": False,
            "zh-CN": False,
            "en": False,
            "ko": True,
        }
        assert ja["en"]["name"] == "English" and ja["ko"]["native_name"] == "한국어"
        assert [t["code"] for t in by_code["ja+en"]] == ["zh-TW"]
        en = {t["code"]: t for t in by_code["en"]}
        assert "en" not in en and en["ko"]["experimental"] and en["th"]["experimental"]
        assert not en["es"]["experimental"]
        assert {lang["code"] for lang in body["languages"]} == set(LANGUAGES)

    def test_a_job_for_a_japanese_talk_accepts_each_new_target(self) -> None:
        from backend.api.jobs import JobBody

        for code in NEW_TARGETS:
            assert JobBody(source_lang="ja", target_lang=code).options().target_lang == code

    def test_a_job_refuses_a_target_the_source_does_not_have_and_names_the_ones_it_has(
        self, api: Client, tmp_path: Path
    ) -> None:
        path = tmp_path / "talk.mp4"
        path.write_bytes(b"x")
        pid = api.post("/api/projects", json={"video_path": str(path)}).json()["id"]
        refused = api.post(
            f"/api/projects/{pid}/jobs", json={"source_lang": "ja", "target_lang": "fr"}
        )
        assert refused.status_code == 422
        assert "zh-TW, zh-CN, en, ko" in refused.text and "not fr" in refused.text
        english = api.post(
            f"/api/projects/{pid}/jobs", json={"source_lang": "en", "target_lang": "en"}
        )
        assert english.status_code == 422 and "not en" in english.text

    def test_the_languages_a_report_names_reach_the_job_result(self) -> None:
        from backend.core.jobs import _report_json
        from backend.core.pipeline import RunReport

        report = RunReport((), 1.0, failed_cues=(3, 5), english_cues=(5,))
        assert _report_json(report)["failed_cues"] == [3, 5]
        assert _report_json(report)["english_cues"] == [5]
        assert _report_json(RunReport((), 1.0))["failed_cues"] == []


class TargetRig(QueueRig):
    """Asks for the target of each queue item, and a Korean translation fails."""

    def resolve(self, options: JobOptions, folder: Path) -> tuple[Settings, Ports]:
        return (
            replace(SETTINGS, target_lang=options.target_lang, source_lang=options.source_lang),
            self.ports(),
        )

    def translate(self, messages: Sequence[Message], temperature: float) -> str:
        if "into Korean" in messages[0]["content"]:
            raise LlmError("the server went away", retryable=False)
        return super().translate(messages, temperature)


@pytest.fixture
def queue_client(tmp_path: Path) -> Generator[tuple[Client, TargetRig]]:
    rig = TargetRig()
    app = create_app(
        AppConfig(
            tmp_path / "data",
            GUARD,
            rig.resolve,
            power=Power(),
            countdown_s=0.05,
            probe=lambda _p: 60.0,
        )
    )
    with open_client(app) as client:
        yield client, rig


class TestQueue:
    def test_several_targets_are_queued_one_after_the_other_for_each_video(
        self, queue_client: tuple[Client, TargetRig], tmp_path: Path
    ) -> None:
        client, _ = queue_client
        client.post("/api/queue/pause")
        one, two = video(tmp_path, "one"), video(tmp_path, "two")
        added = add(
            client, one, two, target_langs=["zh-CN", "en", "ko"], options={"source_lang": "ja"}
        )
        assert [(Path(i["video_path"]).stem, i["target_lang"]) for i in added["added"]] == [
            ("one", "zh-CN"),
            ("one", "en"),
            ("one", "ko"),
            ("two", "zh-CN"),
            ("two", "en"),
            ("two", "ko"),
        ]
        assert {i["source_lang"] for i in added["added"]} == {"ja"}
        assert [i["position"] for i in added["added"]] == sorted(
            i["position"] for i in added["added"]
        )

    def test_an_item_can_name_its_own_targets_and_the_request_names_the_default_ones(
        self, queue_client: tuple[Client, TargetRig], tmp_path: Path
    ) -> None:
        client, _ = queue_client
        client.post("/api/queue/pause")
        a, b = video(tmp_path, "a"), video(tmp_path, "b")
        response = client.post(
            "/api/queue/items",
            json={
                "items": [{"path": str(a), "target_langs": ["en", "ko"]}, {"path": str(b)}],
                "target_langs": ["zh-CN"],
                "options": {"source_lang": "ja"},
            },
        )
        assert response.status_code == 201, response.text
        assert [
            (Path(i["video_path"]).stem, i["target_lang"]) for i in response.json()["added"]
        ] == [
            ("a", "en"),
            ("a", "ko"),
            ("b", "zh-CN"),
        ]

    def test_a_target_the_source_has_not_refuses_the_whole_request_and_names_the_ones_it_has(
        self, queue_client: tuple[Client, TargetRig], tmp_path: Path
    ) -> None:
        client, _ = queue_client
        clip = video(tmp_path, "clip")
        response = client.post(
            "/api/queue/items",
            json={
                "items": [{"path": str(clip), "target_langs": ["en", "fr"]}],
                "options": {"source_lang": "ja"},
            },
        )
        assert response.status_code == 422
        assert "zh-TW, zh-CN, en, ko" in response.text and "not fr" in response.text
        assert client.get("/api/queue").json()["items"] == []

    @pytest.mark.parametrize(
        "body",
        [
            {"target_lang": "en", "target_langs": ["ko"]},
            {"target_langs": []},
            {"target_langs": ["en", "en"]},
            {"target_langs": ["xx"]},
        ],
    )
    def test_a_bad_list_of_targets_is_a_422(
        self, queue_client: tuple[Client, TargetRig], tmp_path: Path, body: dict[str, Any]
    ) -> None:
        client, _ = queue_client
        clip = video(tmp_path, "clip")
        response = client.post(
            "/api/queue/items",
            json={"items": [{"path": str(clip), **body}], "options": {"source_lang": "ja"}},
        )
        assert response.status_code == 422
        assert client.get("/api/queue").json()["items"] == []

    def test_one_failing_target_does_not_stop_the_others_and_the_speech_runs_once(
        self, queue_client: tuple[Client, TargetRig], tmp_path: Path
    ) -> None:
        client, rig = queue_client
        clip = video(tmp_path, "talk")
        add(client, clip, target_langs=["zh-CN", "ko", "zh-TW"])
        deadline = time.monotonic() + 15
        items: list[dict[str, Any]] = []
        while time.monotonic() < deadline:
            items = client.get("/api/queue").json()["items"]
            if items and all(i["state"] in ("done", "failed") for i in items):
                break
            time.sleep(0.02)
        by_target = {i["target_lang"]: i for i in items}
        assert {t: i["state"] for t, i in by_target.items()} == {
            "zh-CN": "done",
            "ko": "failed",
            "zh-TW": "done",
        }
        assert rig.order == ["talk"]
        assert "went away" in by_target["ko"]["last_error"]
        folder = next((tmp_path / "data").rglob("zh-CN.srt")).parent
        assert (folder / "zh-TW.srt").is_file() and not (folder / "ko.srt").exists()
