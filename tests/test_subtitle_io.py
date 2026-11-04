import os
import random
import stat
import sys
import threading
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any, cast

import pytest

from backend.core import model
from backend.core.model import Cue, FormatError, Project, Segment, Step, StepState, StepStatus, Word
from backend.core.subtitle_io import (
    parse_ass,
    parse_project,
    parse_srt,
    parse_subs,
    parse_vtt,
    read_text_file,
    render_ass,
    render_project,
    render_srt,
    render_subs,
    render_vtt,
    write_text_file,
)

GOLDEN = Path(__file__).parent / "golden"

SAMPLE = [
    Cue(1, 0, 2400, "Good morning, everyone.", "大家早安。"),
    Cue(
        2,
        2600,
        6125,
        "Today I want to talk about\nthree ideas that changed my work.",
        "今天我想談談\n改變我工作方式的三個想法。",
    ),
    Cue(
        3,
        3_723_456,
        3_726_789,
        'Over an hour in, we revisit <the plan> & the "numbers".',
        "一小時後，我們回頭看看〈計畫〉與「數字」。",
    ),
    Cue(4, 36_000_000, 36_002_500, "Q&A time 😀 {applause}"),
]
SAMPLE_EN_ONLY = [Cue(c.id, c.start_ms, c.end_ms, c.en) for c in SAMPLE]
SAMPLE_ZH_ONLY = [Cue(c.id, c.start_ms, c.end_ms, "", c.zh) for c in SAMPLE]
SAMPLE_AT_CENTISECONDS = [
    Cue(1, 0, 2400, SAMPLE[0].en, SAMPLE[0].zh),
    Cue(2, 2600, 6130, SAMPLE[1].en, SAMPLE[1].zh),
    Cue(3, 3_723_460, 3_726_790, SAMPLE[2].en, SAMPLE[2].zh),
    Cue(4, 36_000_000, 36_002_500, SAMPLE[3].en),
]


def parse_en_srt(text: str) -> list[Cue]:
    return parse_srt(text, "en")


def parse_en_vtt(text: str) -> list[Cue]:
    return parse_vtt(text, "en")


def render_en_srt(cues: list[Cue]) -> str:
    return render_srt(cues, "en")


def render_bilingual_vtt(cues: list[Cue]) -> str:
    return render_vtt(cues, "bilingual")


def render_empty_srt() -> str:
    return render_srt([], "bilingual")


def render_empty_vtt() -> str:
    return render_vtt([], "bilingual")


def render_empty_ass() -> str:
    return render_ass([])


def render_empty_subs() -> str:
    return render_subs([])


def float_ms() -> Any:
    return 1.5


def golden_bytes(name: str) -> bytes:
    return (GOLDEN / name).read_bytes()


def golden_text(name: str) -> str:
    return read_text_file(GOLDEN / name)


ROUND_TRIPS: list[tuple[str, Callable[[str], object], Callable[[object], str]]] = [
    ("en.srt", lambda t: parse_srt(t, "en"), lambda v: render_srt(cast("list[Cue]", v), "en")),
    ("zh-TW.srt", lambda t: parse_srt(t, "zh"), lambda v: render_srt(cast("list[Cue]", v), "zh")),
    ("en.vtt", lambda t: parse_vtt(t, "en"), lambda v: render_vtt(cast("list[Cue]", v), "en")),
    ("bilingual.ass", parse_ass, lambda v: render_ass(cast("list[Cue]", v))),
    ("subs.zh-TW.json", parse_subs, lambda v: render_subs(cast("list[Cue]", v))),
    ("subs.en.json", parse_subs, lambda v: render_subs(cast("list[Cue]", v))),
    ("project.json", parse_project, lambda v: render_project(cast("Project", v))),
]


@pytest.mark.parametrize(("name", "parse", "render"), ROUND_TRIPS, ids=[r[0] for r in ROUND_TRIPS])
def test_golden_round_trip_is_byte_identical(
    name: str, parse: Callable[[str], object], render: Callable[[object], str]
) -> None:
    assert render(parse(golden_text(name))).encode("utf-8") == golden_bytes(name)


def test_golden_files_keep_their_exact_bytes() -> None:
    assert golden_bytes("en.bom-crlf.srt").startswith(b"\xef\xbb\xbf1\r\n")
    assert golden_bytes("en.bom-crlf.vtt").startswith(b"\xef\xbb\xbfWEBVTT\r\n")
    assert golden_bytes("bilingual.bom-crlf.ass").startswith(b"\xef\xbb\xbf[Script Info]\r\n")
    for name in ("en.srt", "zh-TW.srt", "en.vtt", "bilingual.ass", "project.json"):
        assert b"\r" not in golden_bytes(name)
        assert not golden_bytes(name).startswith(b"\xef\xbb\xbf")


def test_golden_samples_parse_to_the_expected_cues() -> None:
    assert parse_srt(golden_text("en.srt"), "en") == SAMPLE_EN_ONLY
    assert parse_srt(golden_text("zh-TW.srt"), "zh") == SAMPLE_ZH_ONLY
    assert parse_vtt(golden_text("en.vtt"), "en") == SAMPLE_EN_ONLY
    assert parse_ass(golden_text("bilingual.ass")) == SAMPLE_AT_CENTISECONDS
    assert parse_subs(golden_text("subs.zh-TW.json")) == SAMPLE
    assert parse_subs(golden_text("subs.en.json")) == SAMPLE_EN_ONLY


def test_bilingual_srt_and_vtt_are_written_chinese_first() -> None:
    assert render_srt(SAMPLE, "bilingual").encode("utf-8") == golden_bytes("bilingual.srt")
    assert render_vtt(SAMPLE, "bilingual").encode("utf-8") == golden_bytes("bilingual.vtt")


@pytest.mark.parametrize(
    ("bom_crlf", "plain", "parse"),
    [
        ("en.bom-crlf.srt", "en.srt", parse_en_srt),
        ("en.bom-crlf.vtt", "en.vtt", parse_en_vtt),
        ("bilingual.bom-crlf.ass", "bilingual.ass", parse_ass),
    ],
)
def test_bom_and_crlf_input_parses_like_the_plain_file(
    bom_crlf: str, plain: str, parse: Callable[[str], list[Cue]]
) -> None:
    from_file = parse(golden_text(bom_crlf))
    assert from_file == parse(golden_text(plain))
    assert from_file[0].en == "Good morning, everyone."
    raw = golden_bytes(bom_crlf).decode("utf-8")
    assert raw.startswith("\ufeff")
    assert parse(raw) == from_file


def test_cr_only_line_endings_are_accepted() -> None:
    text = golden_text("en.srt").replace("\n", "\r")
    assert parse_srt(text, "en") == SAMPLE_EN_ONLY


def test_times_beyond_one_hour_keep_integer_milliseconds() -> None:
    srt = render_srt(SAMPLE, "en")
    assert "01:02:03,456 --> 01:02:06,789" in srt
    assert "10:00:00,000 --> 10:00:02,500" in srt
    over_100h = Cue(1, 360_000_000, 360_000_001, "late")
    assert "100:00:00,000 --> 100:00:00,001" in render_srt([over_100h], "en")
    assert parse_srt(render_srt([over_100h], "en"), "en") == [
        Cue(1, 360_000_000, 360_000_001, "late")
    ]
    assert parse_vtt(render_vtt([over_100h], "en"), "en")[0].end_ms == 360_000_001


@pytest.mark.parametrize(
    ("render", "parse"),
    [
        (render_empty_srt, parse_en_srt),
        (render_empty_vtt, parse_en_vtt),
        (render_empty_ass, parse_ass),
        (render_empty_subs, parse_subs),
    ],
    ids=["srt", "vtt", "ass", "subs"],
)
def test_empty_subtitles_round_trip(
    render: Callable[[], str], parse: Callable[[str], list[Cue]]
) -> None:
    text = render()
    assert parse(text) == []
    assert text == "" or text.endswith("\n")


def test_empty_srt_and_blank_input_parse_to_no_cues() -> None:
    assert parse_srt("", "en") == []
    assert parse_srt("\n\n  \n", "en") == []
    assert parse_srt("\ufeff", "en") == []


def test_cue_without_text_round_trips() -> None:
    cues = [Cue(1, 0, 1000, ""), Cue(2, 2000, 3000, "text"), Cue(3, 4000, 5000, "")]
    assert parse_srt(render_srt(cues, "en"), "en") == cues
    assert parse_vtt(render_vtt(cues, "en"), "en") == cues


def test_zero_length_cue_is_allowed() -> None:
    assert parse_srt("1\n00:00:01,000 --> 00:00:01,000\nx\n", "en") == [Cue(1, 1000, 1000, "x")]


def test_srt_accepts_missing_indexes_dot_separators_and_padding_whitespace() -> None:
    text = (
        "\ufeff00:00:01.500 --> 00:00:02.000\n  first  \n \t \n"
        "7\n00:00:03,000 --> 00:00:04,000 X1:0\nsecond\n"
    )
    assert parse_srt(text, "zh") == [
        Cue(1, 1500, 2000, "", "first"),
        Cue(7, 3000, 4000, "", "second"),
    ]


def test_vtt_accepts_short_timestamps_settings_notes_and_tags() -> None:
    text = (
        "WEBVTT - a title\n\nNOTE written by hand\nstill the note\n\n"
        "STYLE\n::cue { color: red }\n\n"
        "intro\n00:01.000 --> 00:02.500 align:start\n<c.yellow>Tom &amp; Jerry</c> &lt;3\n\n"
        "01:00:00.000 --> 01:00:01.000\n<v Roger>Hello</v>\n"
    )
    assert parse_vtt(text, "en") == [
        Cue(1, 1000, 2500, "Tom & Jerry <3"),
        Cue(2, 3_600_000, 3_601_000, "Hello"),
    ]


def test_vtt_escapes_markup_characters_on_write() -> None:
    vtt = render_vtt([Cue(1, 0, 1000, "a<b>&amp;")], "en")
    assert "a&lt;b&gt;&amp;amp;" in vtt
    assert parse_vtt(vtt, "en") == [Cue(1, 0, 1000, "a<b>&amp;")]


def test_ass_times_are_rounded_to_centiseconds_half_up() -> None:
    cues = [Cue(1, 1234, 1235, "x"), Cue(2, 1236, 3_599_999, "y")]
    ass = render_ass(cues)
    assert "0:00:01.23,0:00:01.24,Zh,1" in ass
    assert "0:00:01.24,1:00:00.00,Zh,2" in ass


def test_ass_escapes_braces_and_newlines() -> None:
    cue = Cue(1, 0, 1000, "{a}\nb", "{b}")
    ass = render_ass([cue])
    assert "\\{b\\}\\N{\\rEn}\\{a\\}\\Nb" in ass
    assert parse_ass(ass) == [cue]


ASS_BACKSLASH_TEXTS = [
    "C:\\path\\file",
    "C:\\New\\new\\hello",
    "\\h \\N \\n",
    "trailing\\",
    "trailing\\\nnext line",
    "\\\\N",
    "\\{x\\} {y}",
    "\\\u2060N",
    "\\",
]


@pytest.mark.parametrize("text", ASS_BACKSLASH_TEXTS)
def test_ass_writes_any_backslash_and_reads_it_back(text: str) -> None:
    cue = Cue(1, 0, 1000, text, text)
    assert parse_ass(render_ass([cue])) == [cue]


def test_ass_keeps_a_backslash_from_becoming_a_line_break_in_libass() -> None:
    ass = render_ass([Cue(1, 0, 1000, "C:\\New\\hello", "C:\\path")])
    assert "C:\\path\\N{\\rEn}C:\\\u2060New\\\u2060hello" in ass
    assert "\\N{\\rEn}C:\\New" not in ass


def test_a_bad_cue_does_not_block_the_rest_of_an_ass_export() -> None:
    cues = [Cue(1, 0, 1000, "fine"), Cue(2, 1000, 2000, "C:\\new\\Name"), Cue(3, 2000, 3000, "ok")]
    assert [c.en for c in parse_ass(render_ass(cues))] == ["fine", "C:\\new\\Name", "ok"]


def test_ass_keeps_cue_ids_and_reads_foreign_name_columns() -> None:
    cues = [Cue(10, 0, 1000, "a", "甲"), Cue(20, 1000, 2000, "b")]
    assert [c.id for c in parse_ass(render_ass(cues))] == [10, 20]
    foreign = render_ass(cues).replace(",Zh,10,", ",Zh,Narrator,")
    assert [c.id for c in parse_ass(foreign)] == [1, 20]


def test_ass_ignores_comments_other_sections_and_inline_tags() -> None:
    text = render_ass([Cue(1, 0, 1000, "a", "甲")]).replace("\\N{\\rEn}", "\\N{\\an8\\i1}{\\rEn}")
    text += "Comment: 0,0:00:00.00,0:00:01.00,Zh,9,0,0,0,,{\\rEn}ignored\n"
    assert parse_ass(text) == [Cue(1, 0, 1000, "a", "甲")]


@pytest.mark.parametrize(
    ("text", "match"),
    [
        ("1\n00:00:01,000 --> 00:00:00,500\nx\n", "line 1.*before start"),
        ("1\n00:00:01,000 -> 00:00:02,000\nx\n", "line 1.*timing"),
        ("1\n00:61:01,000 --> 00:62:02,000\nx\n", "line 1.*below 60"),
        ("1\n00:00:01,000 --> 00:00:02,000\nx\n\n2\nnot a time\ny\n", "line 5.*timing"),
        (
            "1\n00:00:01,000 --> 00:00:02,000\nx\n\n1\n00:00:03,000 --> 00:00:04,000\ny\n",
            "duplicate",
        ),
        ("justtext\n", "line 1.*timing"),
    ],
)
def test_malformed_srt_names_the_line(text: str, match: str) -> None:
    with pytest.raises(FormatError, match=match):
        parse_srt(text, "en")


@pytest.mark.parametrize(
    "text",
    ["", "00:00:01.000 --> 00:00:02.000\nx\n", "WEBVTTX\n\n"],
)
def test_vtt_without_a_webvtt_header_is_rejected(text: str) -> None:
    with pytest.raises(FormatError, match="WEBVTT"):
        parse_vtt(text, "en")


ASS_FORMAT_LINE = (
    "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
)


@pytest.mark.parametrize(
    ("old", "new", "match"),
    [
        ("{\\rEn}", "", "not a bilingual file"),
        ("0:00:02.40", "0:00:02.4", "bad ASS time"),
        ("0:00:02.40", "0:00:99.00", "bad ASS time"),
        (ASS_FORMAT_LINE, "", "Format"),
        ("Zh,1,0,0,0,,", "Zh,1,0,0,", "fields"),
        ("0:00:00.00,0:00:02.40", "0:00:03.00,0:00:02.40", "line .*before start"),
    ],
)
def test_malformed_ass_is_rejected(old: str, new: str, match: str) -> None:
    with pytest.raises(FormatError, match=match):
        parse_ass(golden_text("bilingual.ass").replace(old, new))


def test_read_text_file_strips_bom_and_rejects_invalid_utf8(tmp_path: Path) -> None:
    bom = tmp_path / "bom.srt"
    bom.write_bytes(b"\xef\xbb\xbf1\r\n00:00:00,000 --> 00:00:01,000\r\n\xe5\xa4\xa7\r\n")
    text = read_text_file(bom)
    assert text.startswith("1\r\n")
    assert parse_srt(text, "zh") == [Cue(1, 0, 1000, "", "大")]
    bad = tmp_path / "bad.srt"
    bad.write_bytes(b"1\n\xff\xfe\n")
    with pytest.raises(FormatError, match="not valid UTF-8"):
        read_text_file(bad)


def test_write_text_file_replaces_atomically_and_keeps_utf8_exact(tmp_path: Path) -> None:
    target = tmp_path / "out.ass"
    target.write_bytes(b"old")
    text = render_ass(SAMPLE)
    write_text_file(target, text)
    assert target.read_bytes() == golden_bytes("bilingual.ass")
    assert [p.name for p in tmp_path.iterdir()] == ["out.ass"]
    assert parse_ass(read_text_file(target))[3].en == "Q&A time 😀 {applause}"


def _replace_always_denied(src: Any, dst: Any) -> None:
    raise PermissionError(13, "Access is denied", str(dst))


def test_write_text_file_fsyncs_before_replacing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[str] = []
    real_fsync, real_replace = os.fsync, os.replace

    def recording_fsync(fd: int) -> None:
        calls.append("fsync")
        real_fsync(fd)

    def recording_replace(src: Any, dst: Any) -> None:
        calls.append("replace")
        real_replace(src, dst)

    monkeypatch.setattr(os, "fsync", recording_fsync)
    monkeypatch.setattr(os, "replace", recording_replace)
    write_text_file(tmp_path / "out.srt", "x")
    assert calls == ["fsync", "replace"]


def test_write_text_file_retries_while_the_target_is_denied(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = tmp_path / "project.json"
    target.write_bytes(b"old")
    real_replace = os.replace
    denied = [3]

    def flaky_replace(src: Any, dst: Any) -> None:
        if denied[0]:
            denied[0] -= 1
            raise PermissionError(13, "Access is denied", str(dst))
        real_replace(src, dst)

    sleeps: list[float] = []
    monkeypatch.setattr(os, "replace", flaky_replace)
    monkeypatch.setattr(time, "sleep", sleeps.append)
    write_text_file(target, "new")
    assert target.read_bytes() == b"new"
    assert [p.name for p in tmp_path.iterdir()] == ["project.json"]
    assert len(sleeps) == 3 and sleeps == sorted(sleeps) and 0 < sum(sleeps) < 2


def test_write_text_file_gives_up_with_a_clear_error_and_keeps_the_old_content(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = tmp_path / "project.json"
    target.write_bytes(b"old")
    sleeps: list[float] = []
    monkeypatch.setattr(os, "replace", _replace_always_denied)
    monkeypatch.setattr(time, "sleep", sleeps.append)
    with pytest.raises(PermissionError, match=r"project\.json.*open in another program"):
        write_text_file(target, "new")
    assert target.read_bytes() == b"old"
    assert [p.name for p in tmp_path.iterdir()] == ["project.json"]
    assert 0 < sum(sleeps) < 2


def test_write_text_file_does_not_touch_the_target_when_the_write_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = tmp_path / "out.srt"
    target.write_bytes(b"old")

    def broken_fsync(fd: int) -> None:
        raise OSError(28, "No space left on device")

    monkeypatch.setattr(os, "fsync", broken_fsync)
    with pytest.raises(OSError, match="No space"):
        write_text_file(target, "new")
    assert target.read_bytes() == b"old"
    assert [p.name for p in tmp_path.iterdir()] == ["out.srt"]


@pytest.mark.skipif(sys.platform != "win32", reason="Windows blocks replacing an open file")
def test_write_text_file_waits_out_a_real_reader_on_windows(tmp_path: Path) -> None:
    target = tmp_path / "project.json"
    target.write_bytes(b"old")
    reader = target.open("rb")
    timer = threading.Timer(0.15, reader.close)
    timer.start()
    try:
        write_text_file(target, "new")
    finally:
        timer.join()
        reader.close()
    assert target.read_bytes() == b"new"
    assert [p.name for p in tmp_path.iterdir()] == ["project.json"]


@pytest.mark.skipif(sys.platform != "win32", reason="Windows blocks replacing an open file")
def test_write_text_file_reports_a_file_that_stays_open_on_windows(tmp_path: Path) -> None:
    target = tmp_path / "project.json"
    target.write_bytes(b"old")
    with target.open("rb"), pytest.raises(PermissionError, match="open in another program"):
        write_text_file(target, "new")
    assert target.read_bytes() == b"old"
    assert [p.name for p in tmp_path.iterdir()] == ["project.json"]


def test_project_requires_schema_version() -> None:
    with pytest.raises(FormatError, match="no schema_version"):
        parse_project('{"video_path": "a.mp4", "steps": {}}')
    with pytest.raises(FormatError, match="no schema_version"):
        parse_subs('{"cues": []}')


@pytest.mark.parametrize("version", ['"1"', "0", "-1", "true", "1.0", "null"])
def test_project_rejects_a_bad_schema_version(version: str) -> None:
    doc = f'{{"schema_version": {version}, "video_path": "a.mp4", "steps": {{}}}}'
    with pytest.raises(FormatError, match="schema_version"):
        parse_project(doc)


def test_project_from_a_newer_app_is_rejected_not_downgraded() -> None:
    with pytest.raises(FormatError, match="newer than supported"):
        parse_project('{"schema_version": 99, "video_path": "a.mp4", "steps": {}}')


def test_migrate_upgrades_one_version_at_a_time(monkeypatch: pytest.MonkeyPatch) -> None:
    def v1_to_v2(raw: dict[str, object]) -> dict[str, object]:
        raw["video_path"] = raw.pop("video")
        return raw

    def v2_to_v3(raw: dict[str, object]) -> dict[str, object]:
        raw["steps"] = {}
        return raw

    monkeypatch.setattr(model, "SCHEMA_VERSION", 3)
    monkeypatch.setattr(model, "_MIGRATIONS", {1: v1_to_v2, 2: v2_to_v3})
    old = {"schema_version": 1, "video": "a.mp4"}
    assert Project.migrate(old) == {"schema_version": 3, "video_path": "a.mp4", "steps": {}}
    assert old == {"schema_version": 1, "video": "a.mp4"}
    project = parse_project('{"schema_version": 1, "video": "a.mp4"}')
    assert project.schema_version == 3
    assert project.video_path == "a.mp4"
    assert all(state == StepState() for state in project.steps.values())


def test_current_project_migrates_to_itself() -> None:
    raw: dict[str, object] = {
        "schema_version": model.SCHEMA_VERSION,
        "video_path": "a.mp4",
        "steps": {},
    }
    assert Project.migrate(raw) == raw


@pytest.mark.parametrize(
    ("text", "match"),
    [
        ("[]", "must be a JSON object"),
        ("{", "invalid JSON"),
        ('{"schema_version": 1, "video_path": "a", "steps": {}, "extra": 1}', "exactly the keys"),
        ('{"schema_version": 1, "video_path": 3, "steps": {}}', "video_path must be a string"),
        ('{"schema_version": 1, "video_path": "", "steps": {}}', "video_path is empty"),
        ('{"schema_version": 1, "video_path": "a", "steps": {"nope": {}}}', "unknown step"),
        (
            '{"schema_version": 1, "video_path": "a", "steps": {"asr": {"status": "weird",'
            ' "updated_at_ms": null, "error": null}}}',
            "steps.asr",
        ),
        (
            '{"schema_version": 1, "video_path": "a", "steps": {"asr": {"status": "failed",'
            ' "updated_at_ms": null, "error": null}}}',
            "steps.asr.*error",
        ),
        (
            '{"schema_version": 1, "video_path": "a", "steps": {"asr": {"status": "done",'
            ' "updated_at_ms": 1.5, "error": null}}}',
            "updated_at_ms must be an integer",
        ),
    ],
)
def test_malformed_project_json_is_rejected(text: str, match: str) -> None:
    with pytest.raises(FormatError, match=match):
        parse_project(text)


@pytest.mark.parametrize(
    ("cue", "match"),
    [
        ('{"id": 1, "start_ms": 0, "end_ms": 5, "en": "a"}', "exactly the keys"),
        ('{"id": true, "start_ms": 0, "end_ms": 5, "en": "a", "zh": ""}', r"cues\[0\].id"),
        ('{"id": 1, "start_ms": 0.5, "end_ms": 5, "en": "a", "zh": ""}', "start_ms"),
        ('{"id": 1, "start_ms": 9, "end_ms": 5, "en": "a", "zh": ""}', "before start"),
        ('{"id": 1, "start_ms": 0, "end_ms": 5, "en": "a\\n\\nb", "zh": ""}', "blank line"),
        ('{"id": 1, "start_ms": 0, "end_ms": 5, "en": 7, "zh": ""}', "en must be a string"),
    ],
)
def test_malformed_subs_json_names_the_cue(cue: str, match: str) -> None:
    with pytest.raises(FormatError, match=match):
        parse_subs(f'{{"schema_version": 1, "cues": [{cue}]}}')


def test_subs_json_rejects_an_unsupported_schema_version() -> None:
    with pytest.raises(FormatError, match="unsupported subs schema_version 2"):
        parse_subs('{"schema_version": 2, "cues": []}')


def test_project_defaults_every_step_to_pending_and_is_immutable() -> None:
    project = Project("a.mp4")
    assert list(project.steps) == list(Step)
    assert all(state.status is StepStatus.PENDING for state in project.steps.values())
    with pytest.raises(TypeError):
        cast("dict[Step, StepState]", project.steps)[Step.ASR] = StepState(StepStatus.DONE, 1)
    done = StepState(StepStatus.DONE, 5)
    updated = project.with_step(Step.ASR, done)
    assert updated.steps[Step.ASR] == done
    assert project.steps[Step.ASR] == StepState()
    assert updated.steps[Step.AUDIO] == StepState()


def test_project_round_trips_through_json() -> None:
    project = Project("D:/v/talk.mp4").with_step(
        Step.TRANSLATE, StepState(StepStatus.FAILED, 7, "boom")
    )
    assert parse_project(render_project(project)) == project


@pytest.mark.parametrize(
    "build",
    [
        lambda: Cue(-1, 0, 1, "x"),
        lambda: Cue(True, 0, 1, "x"),
        lambda: Cue(1, -1, 1, "x"),
        lambda: Cue(1, 5, 4, "x"),
        lambda: Cue(1, 0, float_ms(), "x"),
        lambda: Cue(1, 0, 1, "a\r\nb"),
        lambda: Cue(1, 0, 1, "a\n\nb"),
        lambda: Cue(1, 0, 1, "a\n"),
        lambda: Cue(1, 0, 1, "a", "  \n"),
        lambda: Cue(1, 0, 1, " a"),
        lambda: Cue(1, 0, 1, "a "),
        lambda: Cue(1, 0, 1, "a\n b"),
        lambda: Cue(1, 0, 1, "a \nb"),
        lambda: Cue(1, 0, 1, "a", "　你好"),
        lambda: Cue(1, 0, 1, "a", "你好　"),
        lambda: Cue(1, 0, 1, "a", "你\n\t好"),
        lambda: Cue(1, 0, 1, "a\ud800"),
        lambda: Cue(1, 0, 1, "a", "\udfff"),
        lambda: Word("a", 3, 2),
        lambda: Segment("a", -1, 2),
        lambda: StepState(StepStatus.DONE, error="x"),
        lambda: StepState(StepStatus.FAILED),
        lambda: StepState(StepStatus.DONE, -1),
        lambda: Project(""),
        lambda: Project("a", schema_version=model.SCHEMA_VERSION + 1),
    ],
)
def test_model_rejects_illegal_values(build: Callable[[], object]) -> None:
    with pytest.raises(ValueError):
        build()


def test_segment_words_are_optional() -> None:
    assert Segment("hi", 0, 10).words is None
    segment = Segment("hi there", 0, 10, (Word("hi", 0, 4), Word("there", 5, 10)))
    assert segment.words is not None and segment.words[1].end_ms == 10


def _random_text(rng: random.Random) -> str:
    alphabet = "abc XYZ,.!?'\"<>&{}-0123456789 é中文，。「」😀"
    lines: list[str] = []
    for _ in range(rng.randint(0, 2)):
        line = "".join(rng.choice(alphabet) for _ in range(rng.randint(1, 30))).strip()
        if line:
            lines.append(line)
    return "\n".join(lines)


def _random_cues(seed: int, *, centiseconds: bool) -> list[Cue]:
    rng = random.Random(seed)
    cues: list[Cue] = []
    clock = 0
    step = 10 if centiseconds else 1
    for cue_id in range(1, 60):
        start = clock + rng.randint(0, 5000) // step * step
        end = start + rng.randint(1, 8000) // step * step
        cues.append(Cue(cue_id * 3, start, end, _random_text(rng), _random_text(rng)))
        clock = end
    return cues


@pytest.mark.parametrize("seed", range(5))
def test_random_cues_survive_every_format(seed: int) -> None:
    cues = _random_cues(seed, centiseconds=False)
    en_only = [Cue(c.id, c.start_ms, c.end_ms, c.en) for c in cues]
    assert parse_subs(render_subs(cues)) == cues
    assert parse_srt(render_srt(cues, "en"), "en") == en_only
    assert parse_vtt(render_vtt(cues, "en"), "en") == en_only
    assert parse_ass(render_ass(_random_cues(seed, centiseconds=True))) == _random_cues(
        seed, centiseconds=True
    )


def test_vtt_with_a_text_identifier_then_numeric_ids_still_loads() -> None:
    text = (
        "WEBVTT\n\nintro\n00:00:00.000 --> 00:00:01.000\na\n\n"
        "1\n00:00:01.000 --> 00:00:02.000\nb\n\n00:00:02.000 --> 00:00:03.000\nc\n"
    )
    assert parse_vtt(text, "en") == [
        Cue(2, 0, 1000, "a"),
        Cue(1, 1000, 2000, "b"),
        Cue(3, 2000, 3000, "c"),
    ]


def test_srt_with_a_missing_number_then_number_one_still_loads() -> None:
    text = "00:00:00,000 --> 00:00:01,000\na\n\n1\n00:00:01,000 --> 00:00:02,000\nb\n"
    assert parse_srt(text, "en") == [Cue(2, 0, 1000, "a"), Cue(1, 1000, 2000, "b")]


def test_ass_with_a_text_name_then_numeric_ids_still_loads() -> None:
    cues = [Cue(1, 0, 1000, "a"), Cue(2, 1000, 2000, "b")]
    foreign = render_ass(cues).replace(",Zh,2,", ",Zh,1,").replace(",Zh,1,0", ",Zh,Narrator,0", 1)
    assert [c.id for c in parse_ass(foreign)] == [2, 1]


def test_ids_without_an_explicit_number_count_up_from_the_lowest_free_one() -> None:
    text = (
        "00:00:00,000 --> 00:00:01,000\na\n\n5\n00:00:01,000 --> 00:00:02,000\nb\n\n"
        "00:00:02,000 --> 00:00:03,000\nc\n\n2\n00:00:03,000 --> 00:00:04,000\nd\n"
    )
    assert [c.id for c in parse_srt(text, "en")] == [1, 5, 3, 2]
    assert [c.id for c in parse_srt(text.replace("5\n", "").replace("2\n", ""), "en")] == [
        1,
        2,
        3,
        4,
    ]


def test_explicit_duplicate_ids_are_still_rejected() -> None:
    vtt = "WEBVTT\n\n7\n00:00:00.000 --> 00:00:01.000\na\n\n7\n00:00:01.000 --> 00:00:02.000\nb\n"
    with pytest.raises(FormatError, match="duplicate cue id 7"):
        parse_vtt(vtt, "en")
    ass = render_ass([Cue(1, 0, 1000, "a"), Cue(2, 1000, 2000, "b")]).replace(",Zh,2,", ",Zh,1,")
    with pytest.raises(FormatError, match="duplicate cue id 1"):
        parse_ass(ass)


@pytest.mark.parametrize(
    "render",
    [
        render_en_srt,
        render_bilingual_vtt,
        render_ass,
        render_subs,
    ],
    ids=["srt", "vtt", "ass", "subs"],
)
def test_writers_reject_duplicate_ids_instead_of_writing_an_unreadable_file(
    render: Callable[[list[Cue]], str],
) -> None:
    with pytest.raises(FormatError, match="duplicate cue id 1"):
        render([Cue(1, 0, 1000, "a"), Cue(1, 1000, 2000, "b")])


def test_readers_strip_padding_whitespace_at_the_boundary_including_ideographic_space() -> None:
    srt = "1\n00:00:00,000 --> 00:00:01,000\n\u3000你好\u3000\n 世界\t\n"
    assert parse_srt(srt, "zh") == [Cue(1, 0, 1000, "", "你好\n世界")]
    vtt = "WEBVTT\n\n00:00.000 --> 00:01.000\n\u3000a \u3000\n"
    assert parse_vtt(vtt, "en") == [Cue(1, 0, 1000, "a")]
    ass = render_ass([Cue(1, 0, 1000, "x", "y")]).replace(
        "y\\N{\\rEn}x", "\u3000y \\N \u3000z\\N\\N{\\rEn} x\\N  w "
    )
    assert parse_ass(ass) == [Cue(1, 0, 1000, "x\nw", "y\nz")]


def test_a_cue_built_from_raw_asr_text_cannot_drift_through_a_format() -> None:
    with pytest.raises(ValueError, match="whitespace"):
        Cue(1, 0, 1000, " Hello world.")


def test_subs_json_rejects_padded_text_and_lone_surrogates_as_format_errors() -> None:
    padded = '{"id": 1, "start_ms": 0, "end_ms": 5, "en": " a", "zh": ""}'
    with pytest.raises(FormatError, match=r"cues\[0\].*whitespace"):
        parse_subs(f'{{"schema_version": 1, "cues": [{padded}]}}')
    lone = '{"id": 1, "start_ms": 0, "end_ms": 5, "en": "a\\ud800", "zh": ""}'
    with pytest.raises(FormatError, match=r"cues\[0\].*surrogate"):
        parse_subs(f'{{"schema_version": 1, "cues": [{lone}]}}')


def test_project_json_rejects_a_lone_surrogate_in_the_video_path() -> None:
    with pytest.raises(FormatError, match="video_path.*surrogate"):
        parse_project('{"schema_version": 1, "video_path": "a\\udc80.mp4", "steps": {}}')


def test_write_text_file_reports_a_lone_surrogate_as_a_format_error(tmp_path: Path) -> None:
    target = tmp_path / "out.json"
    target.write_bytes(b"old")
    with pytest.raises(FormatError, match="UTF-8"):
        write_text_file(target, render_project(Project("a\ud800.mp4")))
    assert target.read_bytes() == b"old"
    assert [p.name for p in tmp_path.iterdir()] == ["out.json"]


def _vtt_body(*lines: str) -> str:
    return "WEBVTT\n\n00:00.000 --> 00:01.000\n" + "\n".join(lines) + "\n"


def test_vtt_keeps_a_bare_less_than_instead_of_swallowing_text_up_to_the_next_greater_than() -> (
    None
):
    assert parse_vtt(_vtt_body("if a<b and c>d then"), "en")[0].en == "if a<b and c>d then"
    assert parse_vtt(_vtt_body("Use <foo> and <3 you>"), "en")[0].en == "Use <foo> and <3 you>"


def test_vtt_strips_only_the_real_webvtt_tags() -> None:
    line = (
        "<v.loud Bob><c.yellow.bg_blue>One</c> <i>two</i> <b>three</b> <u>four</u>"
        "<00:00.200> <lang en>five</lang> <ruby>six<rt>ok</rt></ruby></v>"
        "<01:02:03.456>!"
    )
    assert parse_vtt(_vtt_body(line), "en")[0].en == "One two three four five sixok!"


def test_vtt_decodes_html_character_references_once() -> None:
    cue = parse_vtt(_vtt_body("it&#39;s&nbsp;fine &lrm;ok &#x4F60;&#22909; &copy;"), "en")[0]
    assert cue.en == "it's\u00a0fine \u200eok 你好 ©"
    assert parse_vtt(_vtt_body("&amp;lt;b&amp;gt; &amp;amp;"), "en")[0].en == "&lt;b&gt; &amp;"


def test_vtt_leaves_an_ampersand_that_is_not_a_complete_reference_alone() -> None:
    cue = parse_vtt(_vtt_body("AT&T R&D a&param=1 &copy &nope; &#; &#x;"), "en")[0]
    assert cue.en == "AT&T R&D a&param=1 &copy &nope; &#; &#x;"


def test_vtt_round_trips_text_that_looks_like_markup_or_references() -> None:
    for text in ("a<b and c>d", "x &lt; y", "&amp;lt;", "<c>not a tag</c>", "&#39; &nbsp;"):
        cue = Cue(1, 0, 1000, text)
        assert parse_vtt(render_vtt([cue], "en"), "en") == [cue]


@pytest.mark.parametrize(
    "timing",
    [
        "00:00:61,000 --> 00:00:62,000",
        "00:00:01,000 --> 00:00:60,000",
        "00:60:00,000 --> 00:61:00,000",
        "9x00:00:01,000 --> 00:00:02,000",
        "00:00:01,000 --> 00:00:02,000x",
        "00:00:01,000 --> 00:00:02,0000",
    ],
)
def test_srt_and_vtt_reject_out_of_range_or_padded_timing_lines(timing: str) -> None:
    with pytest.raises(FormatError, match="line 1"):
        parse_srt(f"1\n{timing}\nx\n", "en")
    with pytest.raises(FormatError, match="line 3"):
        parse_vtt(f"WEBVTT\n\n{timing}\nx\n", "en")


@pytest.mark.parametrize("missing", ["Start", "End", "Text"])
def test_ass_format_line_without_a_required_column_is_a_format_error(missing: str) -> None:
    ass = golden_text("bilingual.ass")
    columns = ASS_FORMAT_LINE.removeprefix("Format: ").strip().split(", ")
    broken = "Format: " + ", ".join(c for c in columns if c != missing) + "\n"
    with pytest.raises(FormatError, match=f"no .*{missing}"):
        parse_ass(ass.replace(ASS_FORMAT_LINE, broken))


def test_ass_without_a_name_column_numbers_the_cues() -> None:
    ass = golden_text("bilingual.ass")
    no_name = ASS_FORMAT_LINE.replace(" Name,", "")
    body = ass.replace(ASS_FORMAT_LINE, no_name)
    for cue_id in range(1, 5):
        body = body.replace(f",Zh,{cue_id},", ",Zh,")
    assert [c.id for c in parse_ass(body)] == [1, 2, 3, 4]


@pytest.mark.parametrize("version", ["true", "false", "1.0", '"1"', "0", "null"])
def test_subs_json_rejects_a_non_integer_schema_version(version: str) -> None:
    with pytest.raises(FormatError, match="schema_version"):
        parse_subs(f'{{"schema_version": {version}, "cues": []}}')


def test_ass_times_must_be_exactly_h_mm_ss_cc() -> None:
    ass = golden_text("bilingual.ass")
    for bad in ("x0:00:02.40", "0:00:02.40x", "0:00:02.400"):
        with pytest.raises(FormatError, match="bad ASS time"):
            parse_ass(ass.replace("0:00:02.40", bad, 1))


def test_vtt_turns_encoded_line_breaks_into_line_breaks_instead_of_rejecting_the_file() -> None:
    cue = parse_vtt(_vtt_body("first&#13;&#10;second&#x0D;&#xA;third&#10;&#10;fourth"), "en")[0]
    assert cue.en == "first\nsecond\nthird\nfourth"


def test_vtt_drops_an_encoded_line_break_at_the_edge_of_a_line() -> None:
    cue = parse_vtt(_vtt_body("&#13;hello&#10;", "&#10;&#13;world&#13;"), "en")[0]
    assert cue.en == "hello\nworld"


def test_vtt_cue_made_only_of_encoded_line_breaks_parses_as_empty() -> None:
    assert parse_vtt(_vtt_body("&#13;&#10;"), "en")[0].en == ""


def test_write_text_file_fails_fast_on_a_read_only_target(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = tmp_path / "out.srt"
    target.write_bytes(b"old")
    target.chmod(stat.S_IREAD)
    if os.access(target, os.W_OK):
        pytest.skip("this account can write read-only files")
    sleeps: list[float] = []
    monkeypatch.setattr(os, "replace", _replace_always_denied)
    monkeypatch.setattr(time, "sleep", sleeps.append)
    try:
        with pytest.raises(PermissionError, match=r"out\.srt.*read-only") as info:
            write_text_file(target, "new")
        assert "another program" not in str(info.value)
        assert sleeps == []
        assert target.read_bytes() == b"old"
        assert [p.name for p in tmp_path.iterdir()] == ["out.srt"]
    finally:
        target.chmod(stat.S_IWRITE | stat.S_IREAD)


def test_write_text_file_names_the_target_when_its_folder_is_missing(tmp_path: Path) -> None:
    target = tmp_path / "gone" / "out.srt"
    with pytest.raises(FileNotFoundError) as info:
        write_text_file(target, "new")
    assert str(target) in str(info.value)
    assert ".tmp" not in str(info.value)
    assert list(tmp_path.iterdir()) == []


@pytest.mark.skipif(sys.platform != "win32", reason="POSIX replaces a read-only file")
def test_write_text_file_reports_a_real_read_only_file_on_windows(tmp_path: Path) -> None:
    target = tmp_path / "out.srt"
    target.write_bytes(b"old")
    target.chmod(stat.S_IREAD)
    try:
        with pytest.raises(PermissionError, match="read-only"):
            write_text_file(target, "new")
    finally:
        target.chmod(stat.S_IWRITE | stat.S_IREAD)
    assert target.read_bytes() == b"old"


@pytest.mark.skipif(sys.platform != "win32", reason="POSIX replaces a directory only when empty")
def test_write_text_file_names_a_directory_target(tmp_path: Path) -> None:
    target = tmp_path / "out.srt"
    target.mkdir()
    with pytest.raises(PermissionError, match="folder"):
        write_text_file(target, "new")
    assert [p.name for p in tmp_path.iterdir()] == ["out.srt"]


def test_write_text_file_asks_for_umask_governed_permissions(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    modes: list[int] = []
    real_open = os.open

    def recording_open(path: Any, flags: int, mode: int = 0o777, **kwargs: Any) -> int:
        modes.append(mode)
        return real_open(path, flags, mode, **kwargs)

    monkeypatch.setattr(os, "open", recording_open)
    write_text_file(tmp_path / "out.srt", "x")
    assert modes == [0o666]


@pytest.mark.skipif(sys.platform == "win32", reason="Windows has no POSIX permission bits")
@pytest.mark.parametrize("umask", [0o022, 0o077, 0o002])
def test_write_text_file_leaves_a_file_with_normal_permissions(tmp_path: Path, umask: int) -> None:
    old = os.umask(umask)
    try:
        write_text_file(tmp_path / "out.srt", "x")
    finally:
        os.umask(old)
    assert stat.S_IMODE((tmp_path / "out.srt").stat().st_mode) == 0o666 & ~umask
