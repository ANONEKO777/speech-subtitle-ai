from __future__ import annotations

import json
import re
from collections.abc import Sequence
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from test_api import GUARD, Client, Rig, events, make_project, open_client, start_job
from test_pipeline import SETTINGS, Fakes
from test_summarize import good_map, good_reduce

from backend import cli
from backend.core import fillers, translate
from backend.core.languages import (
    DEFAULT,
    DEFAULT_CODE,
    LANGUAGES,
    Language,
    UnknownLanguage,
    get,
    traditional_chars,
)
from backend.core.model import Cue, Step, StepState, StepStatus
from backend.core.pipeline import STEPS, Settings, derive_key, run
from backend.core.subtitle_io import parse_project, parse_subs, read_text_file, render_project
from backend.core.translate import Batch, GlossaryEntry, Unit, build_request, parse_reply
from backend.llm import client
from backend.llm.ask import ReplyError
from backend.llm.client import LlmConfig, Message
from backend.main import AppConfig, create_app

CODES = ["zh-TW", "zh-CN", "ja", "ko", "es", "fr", "de", "pt", "it", "ru", "vi", "th", "id"]
SAMPLE = {
    "zh-TW": "這是翻譯過的句子，內容很清楚。",
    "zh-CN": "这是翻译过的句子，内容很清楚。",
    "ja": "これは翻訳された文で、内容ははっきりしています。",
    "ko": "이것은 번역된 문장이고 내용이 분명합니다.",
    "es": "Esta es la frase traducida y el contenido queda muy claro.",
    "fr": "Voici la phrase traduite et le contenu reste très clair.",
    "de": "Dies ist der übersetzte Satz und der Inhalt bleibt sehr klar.",
    "pt": "Esta é a frase traduzida e o conteúdo fica muito claro.",
    "it": "Questa è la frase tradotta e il contenuto resta molto chiaro.",
    "ru": "Это переведённое предложение, и содержание очень понятно.",
    "vi": "Đây là câu đã dịch và nội dung rất rõ ràng.",
    "th": "นี่คือประโยคที่แปลแล้วและเนื้อหาชัดเจนมาก",
    "id": "Ini adalah kalimat yang diterjemahkan dan isinya sangat jelas.",
}
ENGLISH_CUE = "So last month I did something that nobody in the room expected at all."
KEY_PINS_ON_MAIN = {
    "translate": "470695698a2e4c50f063b829d5847133",
    "export": "99051ccc9882909f6e4798adf47ffc2b",
    "summarize": "097bc4a1f0bb9b8dd04c0f2f6e269c0f",
    "summarize_en": "024d31a4fa42ffb129452f9ddbff0764",
}
ORIGINAL_PROMPT_DIGEST = "cd6c00ea812beda5"


@pytest.fixture
def video(tmp_path: Path) -> Path:
    path = tmp_path / "talk.mp4"
    path.write_bytes(b"not a real video")
    return path


@pytest.fixture
def folder(tmp_path: Path) -> Path:
    return tmp_path / "project"


def keys_of(settings: Settings) -> dict[str, str]:
    keys: dict[Step, str] = {}
    for spec in STEPS:
        keys[spec.step] = derive_key(spec, settings, "vid", keys)
    return {step.value: key for step, key in keys.items()}


def test_the_table_has_the_thirteen_languages_with_unique_names_and_files() -> None:
    assert list(LANGUAGES) == CODES
    assert DEFAULT.code == DEFAULT_CODE == "zh-TW"
    names = [name for lang in LANGUAGES.values() for name in vars_of(lang)]
    assert len(names) == len(set(names))
    for lang in LANGUAGES.values():
        assert lang.name and lang.native and lang.file_code == lang.code


def vars_of(lang: Language) -> list[str]:
    files = lang.files
    return [files.subs, files.srt, files.ass, files.vtt, files.summary, files.summary_parts]


def test_the_default_language_keeps_the_file_names_of_the_first_release() -> None:
    files = DEFAULT.files
    assert (files.subs, files.srt, files.ass, files.vtt, files.summary) == (
        "subs.zh-TW.json",
        "zh-TW.srt",
        "bilingual.ass",
        "bilingual.vtt",
        "summary.md",
    )
    ja = get("ja").files
    assert (ja.srt, ja.ass, ja.vtt, ja.summary) == (
        "ja.srt",
        "bilingual.en-ja.ass",
        "bilingual.en-ja.vtt",
        "summary.ja.md",
    )


def test_an_unknown_code_names_the_ones_that_exist() -> None:
    with pytest.raises(UnknownLanguage, match="zh-TW, zh-CN, ja"):
        get("xx")


def test_the_default_prompt_is_the_one_the_first_release_sent() -> None:
    import hashlib

    template = translate.system_prompt_template(DEFAULT)
    assert hashlib.blake2b(template.encode(), digest_size=8).hexdigest() == ORIGINAL_PROMPT_DIGEST


@pytest.mark.parametrize("code", CODES)
def test_every_prompt_is_filled_in(code: str) -> None:
    lang = get(code)
    text = translate.system_prompt_template(lang)
    assert not re.search(r"<<(?!GLOSSARY)", text)
    assert lang.prompt.target in text
    assert f'"{lang.prompt.key}"' in text
    assert lang.prompt.example in text


def test_the_default_language_cache_keys_are_the_ones_main_computed() -> None:
    keys = keys_of(Settings(asr_engine="e", asr_identity="a", vad_identity="v", llm_identity="l"))
    for step in ("translate", "export", "summarize"):
        assert keys[step] == KEY_PINS_ON_MAIN[step]
    both = keys_of(
        Settings(
            asr_engine="e", asr_identity="a", vad_identity="v", llm_identity="l", summary_en=True
        )
    )
    assert both["summarize"] == KEY_PINS_ON_MAIN["summarize_en"]


def test_the_language_reaches_exactly_translate_export_and_summarize() -> None:
    base = keys_of(SETTINGS)
    for code in CODES[1:]:
        other = keys_of(replace(SETTINGS, target_lang=code))
        assert {s for s in base if base[s] != other[s]} == {"translate", "export", "summarize"}
    ja, ko = (
        keys_of(replace(SETTINGS, target_lang="ja")),
        keys_of(replace(SETTINGS, target_lang="ko")),
    )
    assert ja["translate"] != ko["translate"]


def test_a_setting_with_an_unknown_language_is_refused() -> None:
    with pytest.raises(UnknownLanguage):
        replace(SETTINGS, target_lang="klingon")


@pytest.mark.parametrize(
    ("code", "text", "problem"),
    [
        ("zh-TW", "这是一个测试，没有问题。", "Simplified"),
        ("zh-TW", ENGLISH_CUE, "not translated"),
        ("zh-CN", "這是一個測試，沒有問題。", "Traditional"),
        ("zh-CN", ENGLISH_CUE, "not translated"),
        ("ja", ENGLISH_CUE, "not translated"),
        ("ja", "这是一个测试，没有问题，我们继续吧。", "no kana"),
        ("ja", "이것은 테스트입니다 그리고 계속합니다", "Hangul"),
        ("ko", ENGLISH_CUE, "not translated"),
        ("ko", "これは翻訳された文です、続けます。", "Japanese kana"),
        ("th", ENGLISH_CUE, "not translated"),
        ("ru", ENGLISH_CUE, "not translated"),
        ("ru", "Это предложение 这是一个测试", "Chinese"),
        ("es", ENGLISH_CUE, "still English"),
        ("fr", "This is the sentence that we have and it is clear", "still English"),
        ("de", "Das ist ein Satz und 这是一个测试", "Chinese"),
        ("id", "Ini kalimat dengan Привет", "Cyrillic"),
    ],
)
def test_a_reply_in_the_wrong_script_or_still_english_is_refused(
    code: str, text: str, problem: str
) -> None:
    found = get(code).problem(text, ENGLISH_CUE)
    assert found is not None
    assert problem in found


@pytest.mark.parametrize("code", CODES)
def test_the_sample_sentence_passes_its_own_check_and_the_others_mostly_do_not(code: str) -> None:
    assert get(code).problem(SAMPLE[code], ENGLISH_CUE) is None


def test_every_non_latin_language_refuses_the_sample_of_a_different_script() -> None:
    for code in ("zh-TW", "zh-CN", "ja", "ko", "th", "ru"):
        for other in ("es", "fr", "de"):
            assert get(code).problem(SAMPLE[other], ENGLISH_CUE) is not None


def test_names_and_short_cues_need_no_script() -> None:
    names = "Claude Code, Cursor, Windsurf, Copilot."
    for code in ("ja", "ko", "th", "ru", "es"):
        assert get(code).problem(names, names) is None
        assert get(code).problem("OK", "OK, yes") is None


def test_simplified_characters_are_not_in_the_traditional_table() -> None:
    assert traditional_chars("这是一个测试，没有问题。矽谷") == []
    assert traditional_chars("這是一個測試") == sorted(set("這個測試"))


@pytest.mark.parametrize("code", CODES)
def test_the_terms_and_cleaning_hooks_leave_a_clean_reply_alone(code: str) -> None:
    lang = get(code)
    assert lang.clean(SAMPLE[code], ENGLISH_CUE) == SAMPLE[code]
    assert lang.terms(SAMPLE[code]) == SAMPLE[code]


def test_taiwan_vocabulary_is_applied_to_traditional_chinese_only() -> None:
    mainland = "使用者的視頻和軟件"
    assert get("zh-TW").terms(mainland) == "使用者的影片和軟體"
    assert get("zh-CN").terms("视频和软件") == "视频和软件"
    assert get("ja").terms(mainland) == mainland


def test_latin_fillers_are_dropped_for_scripts_where_they_cannot_be_words_only() -> None:
    assert get("ja").clean("uh、これはテストです", "uh, this is a test") == "これはテストです"
    assert get("pt").clean("um dia eu voltei", "one day I came back") == "um dia eu voltei"
    assert get("ru").clean("Hmm, это тест", "hmm this is a test") == "это тест"


def test_markdown_emphasis_is_stripped_in_every_language() -> None:
    assert get("es").clean("Usa **Cursor** hoy", "Use Cursor today") == "Usa Cursor hoy"


YOU_KNOW = [
    ("you know,", "你知道，", "嗯，"),
    ("you know", "你知", "嗯，"),
    ("so, you know, we shipped it", "所以，你知道，我們出貨了", "所以，我們出貨了"),
    ("and then, you know, it broke", "然後，你知，它壞了", "然後，它壞了"),
    ("you know, the kind of equipment", "你知道，那種設備", "那種設備"),
    (
        "in a high trust environment, you know",
        "一個高信任度的環境，你知不知道",
        "一個高信任度的環境，",
    ),
]
REAL_QUESTIONS = [
    ("do you know the answer?", "你知道答案嗎？"),
    ("Do you know what happened?", "你知道發生了什麼事嗎"),
    ("you know that it works", "你知道它可以運作"),
    ("I think you know the answer", "我想你知道答案"),
    ("you know?", "你知道，"),
]


@pytest.mark.parametrize(("en", "zh", "clean"), YOU_KNOW)
def test_the_you_know_filler_variants_are_dropped_when_the_english_is_the_filler(
    en: str, zh: str, clean: str
) -> None:
    assert fillers.drop_fillers(zh, en) == clean


@pytest.mark.parametrize(("en", "zh"), REAL_QUESTIONS)
def test_a_real_do_you_know_is_kept(en: str, zh: str) -> None:
    assert fillers.drop_fillers(zh, en) == zh


def test_you_know_variants_stay_without_an_english_cue() -> None:
    assert fillers.drop_fillers("你知道，我們出貨了") == "你知道，我們出貨了"
    assert fillers.drop_fillers("所以你知道這件事") == "所以你知道這件事"


def test_the_chinese_languages_share_the_filler_cleaning() -> None:
    for code in ("zh-TW", "zh-CN"):
        assert get(code).clean("然后，你知道，它坏了", "and then, you know, it broke") == (
            "然后，它坏了"
        )


def reply_for(code: str, text: str, en: str = ENGLISH_CUE) -> dict[int, str]:
    lang = get(code)
    cues = [Cue(1, 0, 3000, en)]
    request = build_request(cues, Batch((Unit(0, 1),)), lang=lang)
    body = json.dumps({"translations": [{"id": 1, lang.prompt.key: text}]}, ensure_ascii=False)
    return parse_reply(body, request, cues, lang=lang)


@pytest.mark.parametrize("code", CODES)
def test_a_reply_is_read_under_the_languages_own_key(code: str) -> None:
    assert reply_for(code, SAMPLE[code]) == {1: SAMPLE[code]}
    other = "text" if get(code).prompt.key == "zh" else "zh"
    cues = [Cue(1, 0, 3000, ENGLISH_CUE)]
    request = build_request(cues, Batch((Unit(0, 1),)), lang=get(code))
    wrong = json.dumps({"translations": [{"id": 1, other: SAMPLE[code]}]}, ensure_ascii=False)
    with pytest.raises(ReplyError, match="string"):
        parse_reply(wrong, request, cues, lang=get(code))


def test_the_request_names_the_language_and_the_marker_example() -> None:
    cues = [Cue(1, 0, 3000, ENGLISH_CUE)]
    request = build_request(cues, Batch((Unit(0, 1),)), lang=get("ja"))
    system = request.messages[0]["content"]
    assert "Japanese (日本語)" in system
    assert '"text": "the Japanese translation of entry 12"' in system
    assert "Traditional" not in system


def test_a_reply_is_checked_for_length_against_the_languages_density() -> None:
    short = "Es"
    with pytest.raises(ReplyError, match="shorter"):
        reply_for("es", short, ENGLISH_CUE)
    long = ("Esta frase es muy larga y sigue y sigue sin parar. " * 8).strip()
    with pytest.raises(ReplyError, match="longer"):
        reply_for("es", long, "So last month I did it.")


def test_glossary_keep_english_terms_apply_in_every_language() -> None:

    cues = [Cue(1, 0, 3000, "I opened Cursor and shipped the feature today for everyone.")]
    glossary = (GlossaryEntry("Cursor"),)
    for code in CODES:
        lang = get(code)
        request = build_request(cues, Batch((Unit(0, 1),)), glossary, lang=lang)
        assert "must stay in its original English spelling" in request.messages[0]["content"]
        body = json.dumps(
            {"translations": [{"id": 1, lang.prompt.key: SAMPLE[code]}]}, ensure_ascii=False
        )
        with pytest.raises(ReplyError, match="Cursor"):
            parse_reply(body, request, cues, glossary, lang)
        kept = f"Cursor {SAMPLE[code]}"
        body = json.dumps({"translations": [{"id": 1, lang.prompt.key: kept}]}, ensure_ascii=False)
        assert parse_reply(body, request, cues, glossary, lang) == {1: kept}


class MultiLanguageLlm(Fakes):
    """Answers in the language the system prompt asks for, and counts the asks per language."""

    def __init__(self) -> None:
        super().__init__()
        self.langs: list[str] = []

    def lang_of(self, system: str) -> str:
        for code, lang in LANGUAGES.items():
            if lang.prompt.target in system or lang.summary.rule in system:
                return code
        return "en"

    def translate(self, messages: Sequence[Message], temperature: float) -> str:
        code = self.lang_of(messages[0]["content"])
        self.langs.append(code)
        key = get(code).prompt.key
        entries = json.loads(messages[1]["content"])["translate"]
        out: list[dict[str, Any]] = []
        for entry in entries:
            marks = re.findall(r"\[\[\d+\]\]", entry["en"])
            pieces = [f"{m}{SAMPLE[code][:6]}" for m in marks] or [SAMPLE[code][:12]]
            out.append({"id": entry["id"], key: "".join(pieces)})
        return json.dumps({"translations": out}, ensure_ascii=False)

    def summarize(self, messages: Sequence[Message], temperature: float) -> str:
        if messages[1]["content"].startswith("Part "):
            return good_map(messages)
        code = self.lang_of(messages[0]["content"])
        doc = json.loads(good_reduce(messages, "en"))
        if code != "en":
            text = SAMPLE[code]
            doc["one_liner"] = text
            doc["key_points"] = [text]
            for chapter in doc["chapters"]:
                chapter["title"], chapter["summary"] = text[:8], text
        return json.dumps(doc, ensure_ascii=False)


def stat(folder: Path, names: Sequence[str]) -> dict[str, tuple[int, int]]:
    return {n: ((s := (folder / n).stat()).st_mtime_ns, s.st_size) for n in names}


ASR_FILES = ("audio.wav", "chunks.json", "segments.json", "subs.en.json")


def test_changing_the_language_reruns_translate_export_and_summarize_and_keeps_the_rest(
    video: Path,
    folder: Path,
) -> None:
    fakes = MultiLanguageLlm()
    assert run(video, folder, SETTINGS, fakes.ports()).ran == tuple(Step)
    before = stat(folder, ASR_FILES)
    zh_files = {n: (folder / n).read_bytes() for n in ("zh-TW.srt", "bilingual.ass", "summary.md")}

    ja = replace(SETTINGS, target_lang="ja")
    assert run(video, folder, ja, fakes.ports()).ran == (
        Step.TRANSLATE,
        Step.EXPORT,
        Step.SUMMARIZE,
    )
    assert (fakes.extracted, fakes.split, fakes.transcribed) == (1, 1, 1)
    assert stat(folder, ASR_FILES) == before
    for name in ("ja.srt", "bilingual.en-ja.ass", "bilingual.en-ja.vtt", "summary.ja.md"):
        assert (folder / name).is_file(), name
    assert {n: (folder / n).read_bytes() for n in zh_files} == zh_files
    ja_cues = parse_subs(read_text_file(folder / "subs.ja.json"))
    en_cues = parse_subs(read_text_file(folder / "subs.en.json"))
    assert [(c.id, c.start_ms, c.end_ms, c.en) for c in ja_cues] == [
        (c.id, c.start_ms, c.end_ms, c.en) for c in en_cues
    ]
    assert all(get("ja").problem(c.zh, c.en) is None for c in ja_cues)
    assert set(fakes.langs[-len(ja_cues) :]) <= {"zh-TW", "ja"}

    asked = len(fakes.langs)
    assert run(video, folder, SETTINGS, fakes.ports()).ran == ()
    assert run(video, folder, ja, fakes.ports()).ran == ()
    assert len(fakes.langs) == asked
    project = parse_project(read_text_file(folder / "project.json"))
    assert project.active_lang == "ja"
    assert set(project.parked) == {"zh-TW"}
    assert all(s.status is StepStatus.DONE for s in project.parked["zh-TW"].values())


def test_several_languages_live_in_one_project_and_each_summary_names_its_language(
    video: Path,
    folder: Path,
) -> None:
    fakes = MultiLanguageLlm()
    for code in ("ja", "es", "zh-CN"):
        run(video, folder, replace(SETTINGS, target_lang=code, summary_en=True), fakes.ports())
    for code in ("ja", "es", "zh-CN"):
        files = get(code).files
        for name in (files.subs, files.srt, files.ass, files.vtt, files.summary):
            assert (folder / name).is_file(), name
        assert SAMPLE[code] in (folder / files.summary).read_text(encoding="utf-8")
    assert (folder / "summary.en.md").is_file()
    assert not (folder / "zh-TW.srt").exists()
    project = parse_project(read_text_file(folder / "project.json"))
    assert project.active_lang == "zh-CN"
    assert set(project.parked) == {"zh-TW", "ja", "es"}
    assert set(project.languages()) == {"zh-TW", "ja", "es", "zh-CN"}


def test_a_project_that_never_left_the_default_language_serialises_as_before(
    video: Path,
    folder: Path,
) -> None:
    run(video, folder, SETTINGS, Fakes().ports())
    raw = json.loads((folder / "project.json").read_text(encoding="utf-8"))
    assert set(raw) == {"schema_version", "video_path", "steps"}
    project = parse_project(read_text_file(folder / "project.json"))
    assert render_project(project) == (folder / "project.json").read_text(encoding="utf-8")


def test_a_corrupt_project_language_is_a_format_error() -> None:
    from backend.core.model import FormatError

    text = json.dumps(
        {
            "schema_version": 1,
            "video_path": "v",
            "steps": {},
            "active_lang": "tlh",
        }
    )
    with pytest.raises(FormatError, match="unknown target language"):
        parse_project(text)


def test_activating_a_language_parks_and_restores_its_steps() -> None:
    from backend.core.model import Project

    done = StepState(StepStatus.DONE, 5, None, "k")
    project = Project("v").with_step(Step.TRANSLATE, done).with_step(Step.AUDIO, done)
    ja = project.activate("ja")
    assert ja.steps[Step.TRANSLATE] == StepState()
    assert ja.steps[Step.AUDIO] == done
    assert ja.state(Step.TRANSLATE, "zh-TW") == done
    assert ja.activate("zh-TW").steps[Step.TRANSLATE] == done
    back = ja.activate("zh-TW")
    assert (back.steps, back.active_lang) == (project.steps, project.active_lang)


def test_the_seed_is_sent_with_every_request_body() -> None:
    config = LlmConfig("http://127.0.0.1:1", "m", extra_body={"seed": client.LLM_SEED})
    body = json.loads(client._request_body(config, [], 0.0, True, None))  # pyright: ignore[reportPrivateUsage]
    assert body["seed"] == client.LLM_SEED
    assert body["temperature"] == 0.0


def test_the_cli_takes_lang_and_refuses_an_unknown_one(capsys: pytest.CaptureFixture[str]) -> None:
    assert cli.build_parser().parse_args(["talk.mp4"]).lang == "zh-TW"
    assert cli.build_parser().parse_args(["talk.mp4", "--lang", "ja"]).lang == "ja"
    with pytest.raises(SystemExit):
        cli.build_parser().parse_args(["talk.mp4", "--lang", "xx"])
    assert "invalid choice" in capsys.readouterr().err


class LanguageRig(Rig):
    def resolve(self, options: Any, folder: Path) -> tuple[Settings, Any]:
        settings, ports = super().resolve(options, folder)
        return replace(settings, target_lang=options.target_lang), ports


@pytest.fixture
def lang_client(tmp_path: Path) -> Any:
    rig = LanguageRig()
    rig.translate = MultiLanguageLlm().translate  # type: ignore[method-assign]
    app = create_app(AppConfig(tmp_path / "data", GUARD, rig.resolve))
    with open_client(app) as c:
        c.rig = rig
        yield c


def test_the_api_lists_the_languages(lang_client: Client) -> None:
    body = lang_client.get("/api/languages").json()
    assert body["default"] == "zh-TW"
    assert [lang["code"] for lang in body["languages"]] == CODES
    ja = next(lang for lang in body["languages"] if lang["code"] == "ja")
    assert ja["native_name"] == "日本語"
    assert ja["files"]["subtitles"] == "ja.srt"
    anonymous: Any = TestClient(lang_client.app)
    assert anonymous.get("/api/languages").status_code == 401


def test_a_job_body_is_validated_against_the_registry(
    lang_client: Client,
    video: Path,
) -> None:
    pid = make_project(lang_client, video)
    bad = lang_client.post(f"/api/projects/{pid}/jobs", json={"target_lang": "tlh"})
    assert bad.status_code == 422
    assert "unknown target language" in bad.text
    assert start_job(lang_client, pid, target_lang="ja")["status"] in {"queued", "running"}


def test_subtitles_and_summary_routes_take_a_language(
    lang_client: Client,
    video: Path,
) -> None:
    rig: LanguageRig = lang_client.rig  # type: ignore[attr-defined]
    rig.summarize = MultiLanguageLlm().summarize  # type: ignore[method-assign]
    pid = make_project(lang_client, video)
    events(lang_client, start_job(lang_client, pid)["id"])
    events(lang_client, start_job(lang_client, pid, target_lang="ja")["id"])
    info: dict[str, Any] = lang_client.get(f"/api/projects/{pid}").json()
    folder = Path(info["folder"])
    assert info["active_lang"] == "ja"
    assert set(info["languages"]) == {"ja", "zh-TW"}
    assert info["languages"]["zh-TW"]["translate"]["status"] == "done"
    for target, name in (("ja", "ja.srt"), ("zh-TW", "zh-TW.srt")):
        got = lang_client.get(f"/api/projects/{pid}/subtitles?lang=zh&target_lang={target}")
        assert got.content == (folder / name).read_bytes()
    default = lang_client.get(f"/api/projects/{pid}/subtitles?lang=zh")
    assert default.content == (folder / "ja.srt").read_bytes()
    ass = lang_client.get(f"/api/projects/{pid}/subtitles?lang=bilingual&format=ass&target_lang=ja")
    assert ass.content == (folder / "bilingual.en-ja.ass").read_bytes()
    assert lang_client.get(f"/api/projects/{pid}/subtitles?target_lang=ko").status_code == 409
    assert lang_client.get(f"/api/projects/{pid}/subtitles?target_lang=xx").status_code == 422
    for code, name in (("ja", "summary.ja.md"), ("zh-TW", "summary.md")):
        got = lang_client.get(f"/api/projects/{pid}/summary?lang={code}")
        assert got.content == (folder / name).read_bytes()
    assert (
        lang_client.get(f"/api/projects/{pid}/summary").content
        == (folder / "summary.ja.md").read_bytes()
    )
    assert lang_client.get(f"/api/projects/{pid}/summary?lang=xx").status_code == 422
    assert lang_client.get(f"/api/projects/{pid}/summary?lang=ko").status_code == 409


def test_a_corrected_translation_is_saved_to_its_own_language(
    lang_client: Client,
    video: Path,
) -> None:
    pid = make_project(lang_client, video)
    events(lang_client, start_job(lang_client, pid)["id"])
    events(lang_client, start_job(lang_client, pid, target_lang="ja")["id"])
    folder = Path(lang_client.get(f"/api/projects/{pid}").json()["folder"])
    ja_before = (folder / "ja.srt").read_bytes()
    cues = lang_client.get(f"/api/projects/{pid}/subtitles?format=json&target_lang=zh-TW").json()[
        "cues"
    ]
    cues[0]["zh"] = "人工校對。"
    put = lang_client.put(f"/api/projects/{pid}/subtitles?target_lang=zh-TW", json={"cues": cues})
    assert put.status_code == 200, put.text
    assert "人工校對。" in (folder / "zh-TW.srt").read_text(encoding="utf-8")
    assert (folder / "ja.srt").read_bytes() == ja_before
    assert put.json()["active_lang"] == "zh-TW"


def test_the_english_files_survive_a_switch_of_language(video: Path, folder: Path) -> None:
    fakes = MultiLanguageLlm()
    both = replace(SETTINGS, summary_en=True)
    run(video, folder, both, fakes.ports())
    english = {n: (folder / n).read_bytes() for n in ("en.srt", "summary.en.md")}
    seen: list[bool] = []
    original = fakes.translate

    def translate(messages: Sequence[Message], temperature: float) -> str:
        seen.append(all((folder / n).is_file() for n in english))
        return original(messages, temperature)

    fakes.translate = translate  # type: ignore[method-assign]
    run(video, folder, replace(both, target_lang="ja"), fakes.ports())
    assert seen
    assert all(seen)
    assert {n: (folder / n).read_bytes() for n in english} == english
    run(video, folder, replace(SETTINGS, target_lang="fr"), fakes.ports())
    assert {n: (folder / n).read_bytes() for n in english} == english


@pytest.mark.parametrize("code", [c for c in CODES if c not in ("pt", "de")])
def test_a_standalone_um_or_uh_is_dropped_in_every_language_where_it_is_not_a_word(
    code: str,
) -> None:
    assert get(code).clean("qui um rendent uh la chose", "who um make uh the thing") == (
        "qui rendent la chose"
    )


def test_um_is_kept_where_it_is_a_word_unless_it_is_the_english_filler_set_off() -> None:
    for code in ("pt", "de"):
        clean = get(code).clean
        assert clean("um dia eu voltei", "one day I came back") == "um dia eu voltei"
        assert clean("um dia eu voltei", "um one day I came back") == "um dia eu voltei"
        assert clean("Um, eu voltei, uh, cedo", "Um I came back uh early") == "eu voltei, cedo"
        assert clean("uh um projeto", "um a project") == "um projeto"


def test_korean_and_thai_are_labelled_experimental_and_the_api_says_so(lang_client: Client) -> None:
    body = lang_client.get("/api/languages").json()
    quality = {lang["code"]: lang["quality"] for lang in body["languages"]}
    assert {c for c, q in quality.items() if q == "experimental"} == {"ko", "th"}
    assert set(quality.values()) == {"stable", "experimental"}


@pytest.mark.parametrize(
    ("code", "spelling"), [("ja", "カーソル エージェント の 問題"), ("ko", "커서 에이전트 창")]
)
def test_a_keep_english_term_may_be_kept_in_the_languages_own_script(
    code: str, spelling: str
) -> None:
    cue = Cue(1, 0, 2000, "issues we saw in the cursor agent window and lessons came out")
    replies = iter([spelling] * 8)

    def chat(messages: Sequence[Message], temperature: float) -> str:
        return json.dumps(
            {"translations": [{"id": 1, get(code).prompt.key: next(replies)}]}, ensure_ascii=False
        )

    out = translate.run(
        [cue],
        chat,
        [GlossaryEntry("Cursor")],
        keep_english=True,
        lang=get(code),
        sleep=lambda s: None,
    )
    assert out[0].zh == spelling


@pytest.mark.parametrize("code", ["zh-TW", "zh-CN", "es"])
def test_a_renamed_term_is_never_accepted_where_no_spelling_is_listed(code: str) -> None:
    cue = Cue(1, 0, 2000, "issues we saw in the cursor agent window and lessons came out")
    zh = {"zh-TW": "我們在游標代理視窗看到的問題", "zh-CN": "我们在光标代理窗口看到的问题"}.get(
        code, "problemas que vimos en la ventana del agente"
    )
    asked = 0

    def chat(messages: Sequence[Message], temperature: float) -> str:
        nonlocal asked
        asked += 1
        return json.dumps(
            {"translations": [{"id": 1, get(code).prompt.key: zh}]}, ensure_ascii=False
        )

    out = translate.run(
        [cue],
        chat,
        [GlossaryEntry("Cursor")],
        keep_english=True,
        lang=get(code),
        sleep=lambda s: None,
    )
    assert out[0].zh == cue.en
    assert asked == 4


def test_a_dropped_um_between_a_comma_and_a_word_leaves_one_space() -> None:
    clean = get("de").clean
    assert clean("Plus, um, Sie können", "Plus, um, you can") == "Plus, Sie können"
    assert clean("Um, Sie können", "Um, you can") == "Sie können"
