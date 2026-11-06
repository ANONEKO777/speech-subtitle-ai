from __future__ import annotations

import json
import re
from collections.abc import Callable, Sequence
from pathlib import Path

import pytest

from backend.core import summarize
from backend.core.model import Cue
from backend.core.subtitle_io import render_subs, write_text_file
from backend.core.summarize import (
    CHAPTER_LINK,
    Chapter,
    Gap,
    Line,
    Parts,
    ReduceResult,
    SummaryDoc,
    SummaryError,
    Window,
    chapter_bounds,
    chapter_link,
    clock,
    estimate_tokens,
    make_windows,
    parse_clock,
    parse_map,
    parse_parts,
    parse_reduce,
    render_parts,
    render_summary,
    summarize_file,
    summary_path,
)
from backend.llm.ask import MAX_RETRIES, ReplyError
from backend.llm.client import LlmError, Message

MINUTE = 60_000


def no_sleep(_: float) -> None:
    return None


def talk(minutes: float, cue_s: int = 5) -> list[Line]:
    count = int(minutes * 60 / cue_s)
    return [
        Line(
            i * cue_s * 1000,
            (i + 1) * cue_s * 1000 - 500,
            f"Sentence {i} of the talk is here, and the speaker goes on about it at some length.",
        )
        for i in range(count)
    ]


def talk_cues(minutes: float) -> list[Cue]:
    return [Cue(i, ln.start_ms, ln.end_ms, ln.text) for i, ln in enumerate(talk(minutes), 1)]


def stamps(messages: Sequence[Message], after: str) -> list[str]:
    body = messages[1]["content"].split(after, 1)[1]
    return re.findall(r"^\[([\d:]+)\]", body, re.MULTILINE)


def first_number(pattern: str, text: str) -> str:
    found = re.search(pattern, text)
    assert found
    return found.group(1)


def good_map(messages: Sequence[Message]) -> str:
    user = messages[1]["content"]
    body = user.split("Lines to summarise:", 1)[1].strip().splitlines()
    room = int(first_number(r"at most (\d+) points", user))
    picks = [body[0], body[-1]] if room > 1 and len(body) > 1 else [body[0]]
    points = [{"at": ln[1 : ln.index("]")], "text": f"Point: {ln}"} for ln in picks]
    return json.dumps({"topic": "A topic", "points": points})


def good_reduce(messages: Sequence[Message], lang: str = "zh-TW") -> str:
    user = messages[1]["content"]
    most = int(first_number(r"Write (?:\d+ to )?(\d+) chapter", user))
    notes = stamps(messages, "Notes:")
    most = min(most, len(notes))
    picks = [notes[round(i * (len(notes) - 1) / max(most - 1, 1))] for i in range(most)]
    zh = lang == "zh-TW"
    return json.dumps(
        {
            "one_liner": "這場演講談信任。" if zh else "The talk is about trust.",
            "chapters": [
                {"at": at, "title": f"章節{n}" if zh else f"Chapter {n}", "summary": "內容。"}
                for n, at in enumerate(picks, 1)
            ],
            "key_points": ["信任很重要。" if zh else "Trust matters."],
            "takeaways": [],
        },
        ensure_ascii=False,
    )


class FakeLlm:
    def __init__(self, script: Callable[[int, Sequence[Message]], str | None] | None = None):
        self.script = script
        self.calls: list[list[Message]] = []
        self.temperatures: list[float] = []

    def __call__(self, messages: Sequence[Message], temperature: float) -> str:
        self.calls.append(list(messages))
        self.temperatures.append(temperature)
        reply = self.script(len(self.calls), messages) if self.script else None
        if reply is not None:
            return reply
        if "Part " in messages[1]["content"][:20]:
            return good_map(messages)
        lang = "zh-TW" if "Traditional Chinese" in messages[0]["content"] else "en"
        return good_reduce(messages, lang)

    def kinds(self) -> list[str]:
        return ["map" if c[1]["content"].startswith("Part ") else "reduce" for c in self.calls]


def window(lines: Sequence[Line], context: Sequence[Line] = ()) -> Window:
    return Window(0, tuple(context), tuple(lines))


def test_windows_tile_the_transcript_and_stay_near_the_token_target() -> None:
    lines = talk(40)
    windows = make_windows(lines, window_tokens=3000, overlap_tokens=200)
    assert [ln for w in windows for ln in w.lines] == lines
    assert len(windows) > 3
    for w in windows:
        cost = sum(estimate_tokens(summarize.render_line(ln)) for ln in (*w.context, *w.lines))
        assert 2700 <= cost <= 3000 or w is windows[-1]
        assert cost <= 3000


def test_windows_overlap_by_a_few_lines_of_the_previous_window() -> None:
    windows = make_windows(talk(40), window_tokens=3000, overlap_tokens=200)
    assert windows[0].context == ()
    for before, after in zip(windows, windows[1:], strict=False):
        assert after.context
        assert after.context == before.lines[-len(after.context) :]
        extra = sum(estimate_tokens(summarize.render_line(ln)) for ln in after.context)
        assert extra <= 200
        assert len(after.context) < len(before.lines) / 4


def test_a_line_longer_than_the_window_still_gets_a_window_and_the_walk_ends() -> None:
    lines = [Line(0, 1000, "word " * 2000), Line(1000, 2000, "short.")]
    windows = make_windows(lines, window_tokens=300, overlap_tokens=50)
    assert [w.lines for w in windows] == [(lines[0],), (lines[1],)]


def test_overlap_must_be_smaller_than_the_window() -> None:
    with pytest.raises(ValueError, match="smaller"):
        make_windows(talk(1), window_tokens=100, overlap_tokens=100)


def test_a_short_talk_is_one_window() -> None:
    assert len(make_windows(talk(0.25))) == 1


@pytest.mark.parametrize(
    ("ms", "text"), [(0, "00:00"), (754_000, "12:34"), (3_599_999, "59:59"), (3_723_000, "1:02:03")]
)
def test_clock_and_parse_clock_round_trip(ms: int, text: str) -> None:
    assert clock(ms) == text
    assert parse_clock(text) == ms // 1000 * 1000
    assert parse_clock(f"[{text}]") == ms // 1000 * 1000


@pytest.mark.parametrize("bad", ["", "12", "99:99", "1:75:00", "ab:cd", "12:3", "twelve"])
def test_parse_clock_rejects_what_is_not_a_time(bad: str) -> None:
    with pytest.raises(ReplyError):
        parse_clock(bad)


def test_chapter_timestamps_are_links_a_player_can_read_back() -> None:
    assert chapter_link(754_000) == "[12:34](#t=754)"
    assert chapter_link(754_999) == "[12:34](#t=754)"
    assert chapter_link(3_723_000) == "[1:02:03](#t=3723)"
    assert [m.group(1) for m in CHAPTER_LINK.finditer("x [12:34](#t=754) [00:00](#t=0)")] == [
        "754",
        "0",
    ]


def test_chapter_counts_grow_with_the_length_and_are_three_to_seven_for_a_long_talk() -> None:
    assert chapter_bounds(57 * MINUTE) == (3, 7)
    assert chapter_bounds(10 * MINUTE) == (3, 3)
    assert chapter_bounds(15_000) == (1, 1)
    bounds = [chapter_bounds(second * 1000) for second in range(0, 3 * 3600, 5)]
    assert all(1 <= least <= most <= 7 for least, most in bounds)
    assert all(a[1] <= b[1] and a[0] <= b[0] for a, b in zip(bounds, bounds[1:], strict=False))


@pytest.mark.parametrize("seconds", [353, 362, 420, 480])
def test_a_talk_of_six_to_eight_minutes_may_have_two_or_more_chapters(seconds: int) -> None:
    least, most = chapter_bounds(seconds * 1000, note_count=8)
    assert most == round(seconds / 180) >= 2
    assert least == most


def test_a_talk_of_twenty_one_minutes_or_more_keeps_asking_for_three_to_seven() -> None:
    for minutes in range(21, 181):
        assert chapter_bounds(minutes * MINUTE, note_count=32) == (3, 7)


def test_the_notes_limit_the_chapters_to_what_they_can_fill() -> None:
    assert chapter_bounds(57 * MINUTE, note_count=5) == (2, 2)
    assert chapter_bounds(57 * MINUTE, note_count=1) == (1, 1)
    assert chapter_bounds(57 * MINUTE, note_count=0) == (1, 1)


MAP_LINES = [Line(i * 5000, i * 5000 + 4500, f"line {i} has some words") for i in range(30)]


def map_reply(*points: tuple[str, str], topic: str = "Topic") -> str:
    return json.dumps({"topic": topic, "points": [{"at": a, "text": t} for a, t in points]})


def test_map_result_holds_the_window_range_and_points_snapped_to_a_line_start() -> None:
    w = window(MAP_LINES[10:20])
    result = parse_map(map_reply(("00:59", "Second."), ("00:51", "First.")), w)
    assert (result.start_ms, result.end_ms) == (50_000, 99_500)
    assert [(p.at_ms, p.text) for p in result.points] == [(50_000, "First."), (55_000, "Second.")]


@pytest.mark.parametrize(
    ("reply", "message"),
    [
        ("not json", "not valid JSON"),
        ("[]", "JSON object"),
        (json.dumps({"points": []}), "topic"),
        (json.dumps({"topic": "t", "points": []}), "at least 1"),
        (map_reply(("00:10", "Before the window.")), "outside the lines"),
        (map_reply(("03:00", "After the window.")), "outside the lines"),
        (map_reply(("fifty", "Bad time.")), "not a time"),
        (map_reply(("00:55", " ")), "text"),
    ],
)
def test_malformed_map_replies_are_rejected_with_a_reason(reply: str, message: str) -> None:
    with pytest.raises(ReplyError, match=message):
        parse_map(reply, window(MAP_LINES[10:20]))


def test_a_map_reply_with_too_many_points_keeps_an_even_spread_with_both_ends() -> None:
    lines = window(MAP_LINES[:30])
    limit = summarize.max_points(lines)
    many = [(clock(MAP_LINES[i].start_ms), f"p{i}") for i in range(30)]
    result = parse_map(map_reply(*many), lines)
    assert len(result.points) == limit
    assert result.points[0].text == "p0"
    assert result.points[-1].text == "p29"
    picked = [int(p.text[1:]) for p in result.points]
    assert picked == sorted(set(picked))
    steps = [b - a for a, b in zip(picked, picked[1:], strict=False)]
    assert max(steps) - min(steps) <= 1


def test_thin_leaves_a_short_list_alone_and_handles_one_slot() -> None:
    points = [summarize.Point(i, str(i)) for i in range(5)]
    assert summarize.thin(points, 5) == tuple(points)
    assert summarize.thin(points, 1) == (points[0],)
    assert summarize.thin(points, 2) == (points[0], points[4])


def test_a_fenced_reply_with_a_think_block_is_accepted() -> None:
    reply = "<think>hm</think>\n```json\n" + map_reply(("00:55", "Point.")) + "\n```"
    assert parse_map(reply, window(MAP_LINES[10:20])).points[0].text == "Point."


def test_a_bad_map_reply_is_retried_with_the_reason_and_a_warmer_temperature() -> None:
    llm = FakeLlm(lambda n, m: "garbage" if n == 1 else None)
    doc = summarize.run(talk(0.5), llm, "en", sleep=no_sleep)
    assert llm.kinds() == ["map", "map", "reduce"]
    retry = llm.calls[1]
    assert retry[2] == {"role": "assistant", "content": "garbage"}
    assert "not valid JSON" in retry[3]["content"]
    assert llm.temperatures[:2] == [0.0, 0.3]
    assert doc.result.chapters[0].title == "Chapter 1"


def test_a_map_call_that_always_fails_is_listed_as_a_gap_not_invented() -> None:
    lines = talk(40)
    third = make_windows(lines)[2]

    def script(n: int, messages: Sequence[Message]) -> str | None:
        user = messages[1]["content"]
        starts = user.split("Lines to summarise:")[1].split("\n")[1] if "Part " in user else ""
        return "bad" if starts.startswith(f"[{clock(third.start_ms)}]") else None

    llm = FakeLlm(script)
    doc = summarize.run(lines, llm, "en", sleep=no_sleep)
    assert doc.gaps == (Gap(third.start_ms, third.end_ms),)
    assert llm.kinds().count("map") == len(make_windows(lines)) + MAX_RETRIES
    reduce_user = llm.calls[-1][1]["content"]
    assert f"Missing: {clock(third.start_ms)}-{clock(third.end_ms)}" in reduce_user
    text = render_summary(doc)
    assert f"## Not covered\n\n- {clock(third.start_ms)} - {clock(third.end_ms)}" in text
    assert len(CHAPTER_LINK.findall(text)) == len(doc.result.chapters)


def test_a_summary_with_no_usable_map_result_raises() -> None:
    with pytest.raises(SummaryError, match="no part"):
        summarize.run(talk(0.5), FakeLlm(lambda n, m: "bad"), sleep=no_sleep)


def test_an_empty_transcript_raises() -> None:
    with pytest.raises(SummaryError, match="no text"):
        summarize.run([], FakeLlm())


def test_a_server_that_stays_down_raises_its_error_and_keeps_finished_maps() -> None:
    parts = Parts()
    saved: list[int] = []

    def script(n: int, messages: Sequence[Message]) -> str | None:
        if n >= 3:
            raise LlmError("http://llm.test answered HTTP 503", retryable=True)
        return None

    with pytest.raises(LlmError, match="503"):
        summarize.run(
            talk(40),
            FakeLlm(script),
            parts=parts,
            checkpoint=lambda p: saved.append(len(p.maps)),
            sleep=no_sleep,
        )
    assert saved == [1, 2]
    assert len(parts.maps) == 2


def reduce_job(maps: int = 4, minutes: int = 40) -> summarize.ReduceInput:
    span = minutes * MINUTE
    parts = tuple(
        summarize.MapResult(
            i * span // maps,
            (i + 1) * span // maps,
            f"topic {i}",
            tuple(
                summarize.Point(i * span // maps + 7000 + k * 60_000, f"note {i}.{k}")
                for k in range(4)
            ),
        )
        for i in range(maps)
    )
    return summarize.ReduceInput("en", 0, span, parts, (), ())


def reduce_reply(chapters: list[tuple[str, str]], **fields: object) -> str:
    doc: dict[str, object] = {
        "one_liner": "About trust.",
        "chapters": [{"at": a, "title": t, "summary": "S."} for a, t in chapters],
        "key_points": ["Trust matters."],
        "takeaways": [],
        **fields,
    }
    return json.dumps(doc)


FOUR = [("00:00", "A"), ("10:07", "B"), ("20:07", "C"), ("30:07", "D")]


@pytest.mark.parametrize("first_cue_ms", [390, 685_280])
def test_the_first_chapter_may_start_at_the_whole_second_before_an_off_second_first_cue(
    first_cue_ms: int,
) -> None:
    span = 40 * MINUTE
    notes = [first_cue_ms + n * 10 * MINUTE + 7000 for n in range(4)]
    spare = [at + 60_000 for at in notes]
    maps = (
        summarize.MapResult(
            first_cue_ms,
            first_cue_ms + span,
            "t",
            tuple(summarize.Point(at, "n") for at in sorted([*notes, *spare])),
        ),
    )
    job = summarize.ReduceInput("en", first_cue_ms, first_cue_ms + span, maps, (), ())
    chapters = [(clock(first_cue_ms), "A"), *((clock(at), "B") for at in notes[1:])]
    result = parse_reduce(reduce_reply(chapters), job)
    assert result.chapters[0].start_ms == first_cue_ms
    early = [("00:00", "A"), *chapters[1:]]
    if first_cue_ms >= MINUTE:
        with pytest.raises(ReplyError, match="outside the talk"):
            parse_reduce(reduce_reply(early), job)


def test_reduce_snaps_chapters_to_note_times_and_starts_the_first_at_the_beginning() -> None:
    result = parse_reduce(
        reduce_reply([("00:03", "A"), ("10:09", "B"), ("20:00", "C"), ("30:30", "D")]),
        reduce_job(),
    )
    assert [c.start_ms for c in result.chapters] == [0, 607_000, 1_207_000, 1_807_000]


@pytest.mark.parametrize(
    ("chapters", "message"),
    [
        (FOUR[:2], "3 to 7"),
        ([(f"{i}:07", "x") for i in range(10, 90, 10)], "3 to 7"),
        ([("00:00", "A"), ("10:07", "B"), ("20:07", "C")], "final quarter"),
        ([("00:00", "A"), ("30:07", "B"), ("30:07", "C"), ("30:07", "D")], "different times"),
        ([("00:00", "A"), ("30:07", "B"), ("20:07", "C"), ("10:07", "D")], "different times"),
        ([("00:00", "A"), ("10:07", "B"), ("20:07", "C"), ("99:00", "D")], "outside the talk"),
    ],
)
def test_reduce_rejects_bad_chapter_lists(chapters: list[tuple[str, str]], message: str) -> None:
    with pytest.raises(ReplyError, match=message):
        parse_reduce(reduce_reply(chapters), reduce_job())


@pytest.mark.parametrize(
    "fields",
    [{"one_liner": ""}, {"key_points": []}, {"key_points": [""]}, {"takeaways": ["x"] * 6}],
)
def test_reduce_rejects_missing_or_empty_fields(fields: dict[str, object]) -> None:
    with pytest.raises(ReplyError):
        parse_reduce(reduce_reply(FOUR, **fields), reduce_job())


def test_chinese_output_must_be_traditional_chinese_with_taiwan_terms() -> None:
    job = reduce_job()
    job = summarize.ReduceInput("zh-TW", 0, job.end_ms, job.maps, (), ())
    zh: dict[str, object] = {"key_points": ["信任。"], "one_liner": "這支視頻談信任。"}
    chapters = [{"at": a, "title": t, "summary": "內容。"} for a, t in FOUR]
    with pytest.raises(ReplyError, match="Simplified"):
        parse_reduce(json.dumps({**zh, "chapters": chapters, "key_points": ["这是信任。"]}), job)
    with pytest.raises(ReplyError, match="Traditional Chinese"):
        parse_reduce(reduce_reply(FOUR, one_liner="About trust."), job)
    fixed = parse_reduce(json.dumps({**zh, "chapters": chapters}), job)
    assert fixed.one_liner == "這支影片談信任。"


def test_a_short_talk_gets_one_chapter_without_the_last_quarter_rule() -> None:
    lines = talk(0.25)
    llm = FakeLlm()
    doc = summarize.run(lines, llm, "en", sleep=no_sleep)
    assert [c.start_ms for c in doc.result.chapters] == [0]
    assert "Write 1 chapter." in llm.calls[-1][1]["content"]


def test_the_reduce_prompt_names_the_chapter_count_the_language_and_the_glossary() -> None:
    job = reduce_job()
    glossary = (summarize.GlossaryEntry("Grok", ""), summarize.GlossaryEntry("PR", "合併請求"))
    zh = summarize.ReduceInput("zh-TW", 0, job.end_ms, job.maps, (), glossary)
    system, user = (m["content"] for m in summarize.reduce_messages(zh))
    assert "Traditional Chinese" in system
    assert '"PR" must be translated as "合併請求"' in system
    assert "<<" not in system
    assert "Write 3 to 7 chapters." in user
    assert "== 00:00-10:00 | topic 0\n[00:07] note 0.0" in user
    english = summarize.reduce_messages(job)[0]["content"]
    assert "Write every field in English." in english


def test_a_request_over_three_quarters_of_the_context_is_refused_before_sending() -> None:
    llm = FakeLlm()
    with pytest.raises(SummaryError, match="75%"):
        summarize.run(talk(40), llm, context_tokens=3000, sleep=no_sleep)
    assert llm.calls == []


def test_every_request_in_a_real_size_run_fits_the_context_budget() -> None:
    llm = FakeLlm()
    summarize.run(talk(57), llm, context_tokens=8192, sleep=no_sleep)
    assert llm.kinds().count("reduce") == 1
    for call in llm.calls:
        tokens = sum(estimate_tokens(m["content"]) for m in call)
        assert tokens <= 0.75 * 8192


def test_a_runaway_reply_is_not_echoed_back_in_the_retry() -> None:
    runaway = json.dumps({"topic": "t", "points": [{"at": "99:00", "text": "x" * 40}] * 60})
    llm = FakeLlm(lambda n, m: runaway if n == 1 else None)
    summarize.run(talk(0.5), llm, "en", sleep=no_sleep)
    retry = llm.calls[1]
    assert [m["role"] for m in retry] == ["system", "user", "user"]
    assert "outside the lines" in retry[2]["content"]
    assert len(retry) == len(llm.calls[0]) + 1


def doc_for(lang: summarize.Lang = "zh-TW", gaps: tuple[Gap, ...] = ()) -> SummaryDoc:
    result = ReduceResult(
        "一句話。",
        (Chapter(0, "開場", "介紹。"), Chapter(754_000, "主題", "細節。")),
        ("觀點一。", "觀點二。"),
        ("金句。",),
    )
    return SummaryDoc(lang, result, gaps)


def test_summary_markdown_follows_spec_section_8_3() -> None:
    assert render_summary(doc_for()) == (
        "# 重點整理\n\n> 一句話。\n\n## 章節\n\n"
        "- [00:00](#t=0) **開場**：介紹。\n- [12:34](#t=754) **主題**：細節。\n\n"
        "## 關鍵觀點\n\n- 觀點一。\n- 觀點二。\n\n## 結論與金句\n\n- 金句。\n"
    )


def test_the_takeaways_section_is_left_out_when_there_are_none() -> None:
    doc = doc_for()
    bare = SummaryDoc("en", ReduceResult(doc.result.one_liner, doc.result.chapters, ("a",), ()))
    text = render_summary(bare)
    assert "## Takeaways" not in text
    assert text.startswith(
        "# Summary\n\n> 一句話。\n\n## Chapters\n\n- [00:00](#t=0) **開場**: 介紹。"
    )


def test_summary_files_sit_beside_each_other() -> None:
    dest = Path("p") / "summary.md"
    assert summary_path(dest, "zh-TW") == dest
    assert summary_path(dest, "en") == Path("p") / "summary.en.md"


def test_parts_survive_a_round_trip_and_unreadable_parts_are_empty() -> None:
    job = reduce_job()
    parts = Parts({"k": job.maps[0]}, {"en": ("d", doc_for().result)})
    assert parse_parts(render_parts(parts)) == parts
    for bad in (
        "",
        "{",
        "[]",
        '{"version": 9}',
        '{"version": 1, "maps": {"k": {}}, "reduces": {}}',
    ):
        assert parse_parts(bad) == Parts()


def write_source(directory: Path, minutes: float) -> Path:
    source = directory / "subs.en.json"
    write_text_file(source, render_subs(talk_cues(minutes)))
    return source


def test_summarize_file_writes_summary_md_with_clickable_chapters(tmp_path: Path) -> None:
    source = write_source(tmp_path, 40)
    llm = FakeLlm()
    written = summarize_file(source, tmp_path / "summary.md", llm)
    assert written == [tmp_path / "summary.md"]
    text = written[0].read_text(encoding="utf-8")
    assert text.startswith("# 重點整理\n\n> 這場演講談信任。\n\n## 章節\n\n")
    links = CHAPTER_LINK.findall(text)
    assert 3 <= len(links) <= 7
    assert links[0] == "0"
    assert int(links[-1]) >= 0.75 * 40 * 60 - 5
    assert "## 關鍵觀點" in text


def test_a_second_run_asks_for_nothing(tmp_path: Path) -> None:
    source = write_source(tmp_path, 40)
    dest = tmp_path / "summary.md"
    first = FakeLlm()
    summarize_file(source, dest, first)
    before = dest.read_bytes()
    second = FakeLlm()
    summarize_file(source, dest, second)
    assert second.calls == []
    assert dest.read_bytes() == before
    assert first.kinds().count("reduce") == 1


def test_a_run_after_a_crash_asks_only_for_the_missing_windows(tmp_path: Path) -> None:
    source = write_source(tmp_path, 40)
    dest = tmp_path / "summary.md"

    def dies_on_the_third_map(n: int, messages: Sequence[Message]) -> str | None:
        if n == 3:
            raise LlmError("cannot reach the LLM server", retryable=False)
        return None

    with pytest.raises(LlmError):
        summarize_file(source, dest, FakeLlm(dies_on_the_third_map))
    assert not dest.exists()
    resumed = FakeLlm()
    summarize_file(source, dest, resumed)
    windows = len(make_windows(talk(40)))
    assert resumed.kinds() == ["map"] * (windows - 2) + ["reduce"]
    assert dest.exists()


def test_english_summary_reuses_the_map_notes_and_adds_only_a_reduce(tmp_path: Path) -> None:
    source = write_source(tmp_path, 40)
    dest = tmp_path / "summary.md"
    summarize_file(source, dest, FakeLlm())
    llm = FakeLlm()
    written = summarize_file(source, dest, llm, langs=("zh-TW", "en"))
    assert written == [dest, tmp_path / "summary.en.md"]
    assert llm.kinds() == ["reduce"]
    english = (tmp_path / "summary.en.md").read_text(encoding="utf-8")
    assert english.startswith("# Summary\n\n> The talk is about trust.")


def test_changed_subtitles_invalidate_only_the_windows_they_touch(tmp_path: Path) -> None:
    source = write_source(tmp_path, 40)
    dest = tmp_path / "summary.md"
    summarize_file(source, dest, FakeLlm())
    cues = talk_cues(40)
    cues[-1] = Cue(cues[-1].id, cues[-1].start_ms, cues[-1].end_ms, "A different last line.")
    write_text_file(source, render_subs(cues))
    llm = FakeLlm()
    summarize_file(source, dest, llm)
    assert llm.kinds() == ["map", "reduce"]


def test_the_state_file_drops_notes_of_windows_that_no_longer_exist(tmp_path: Path) -> None:
    source = write_source(tmp_path, 40)
    dest = tmp_path / "summary.md"
    summarize_file(source, dest, FakeLlm())
    write_source(tmp_path, 25)
    summarize_file(source, dest, FakeLlm())
    kept = parse_parts((tmp_path / "summary.parts.json").read_text(encoding="utf-8"))
    assert len(kept.maps) == len(make_windows(talk(25)))


def test_a_fifteen_second_clip_gets_one_chapter(tmp_path: Path) -> None:
    source = write_source(tmp_path, 0.25)
    summarize_file(source, tmp_path / "summary.md", FakeLlm())
    text = (tmp_path / "summary.md").read_text(encoding="utf-8")
    assert len(CHAPTER_LINK.findall(text)) == 1


def front_loaded_map(messages: Sequence[Message], extra: int = 0) -> str:
    """What the 8B model does with a window: all its notes from the first minutes of the part."""
    user = messages[1]["content"]
    body = user.split("Lines to summarise:", 1)[1].strip().splitlines()
    room = int(first_number(r"at most (\d+) points", user))
    points = [
        {"at": ln[1 : ln.index("]")], "text": f"Point: {ln}"}
        for ln in body[: min(len(body), room + extra)]
    ]
    return json.dumps({"topic": "A topic", "points": points})


def front_loaded(extra: int = 0) -> FakeLlm:
    def script(_: int, messages: Sequence[Message]) -> str | None:
        return (
            front_loaded_map(messages, extra)
            if messages[1]["content"].startswith("Part ")
            else None
        )

    return FakeLlm(script)


@pytest.mark.parametrize("extra", [0, 8])
@pytest.mark.parametrize("minutes", [1, 3, 5, 6, 7, 8, 10, 15, 20, 30, 40, 57])
def test_a_summary_is_written_at_every_length_even_when_the_notes_stop_early(
    tmp_path: Path, minutes: int, extra: int
) -> None:
    llm = front_loaded(extra)
    summarize_file(write_source(tmp_path, minutes), tmp_path / "summary.md", llm, ["zh-TW", "en"])
    most = chapter_bounds(minutes * MINUTE)[1]
    for name in ("summary.md", "summary.en.md"):
        links = CHAPTER_LINK.findall((tmp_path / name).read_text(encoding="utf-8"))
        assert 1 <= len(links) <= most
    assert llm.kinds().count("reduce") == 2


def test_the_notes_of_the_failed_six_minute_nasa_clip_make_one_chapter() -> None:
    notes = [308, 308, 3858, 6138, 13158, 24198, 35236, 46896]
    maps = (
        summarize.MapResult(308, 362_046, "NASA", tuple(summarize.Point(n, "n") for n in notes)),
    )
    job = summarize.ReduceInput("en", 308, 362_046, maps, (), ())
    assert job.bounds == (1, 1)
    assert len(parse_reduce(reduce_reply([("00:00", "A")]), job).chapters) == 1
    with pytest.raises(ReplyError, match="1 to 1"):
        parse_reduce(reduce_reply([("00:00", "A"), ("00:46", "B")]), job)


def notes_job(minutes: int, note_minutes: list[int]) -> summarize.ReduceInput:
    points = tuple(summarize.Point(m * MINUTE, f"note {m}") for m in note_minutes)
    maps = (summarize.MapResult(0, minutes * MINUTE, "topic", points),)
    return summarize.ReduceInput("en", 0, minutes * MINUTE, maps, (), ())


def test_chapters_must_still_reach_the_last_quarter_of_the_talk() -> None:
    job = reduce_job()
    with pytest.raises(ReplyError, match="final quarter"):
        parse_reduce(reduce_reply([("00:00", "A"), ("10:07", "B"), ("20:07", "C")]), job)


def test_notes_that_reach_the_last_quarter_of_the_talk_keep_the_full_floor() -> None:
    job = notes_job(60, [0, 10, 20, 30, 42, 50, 55])
    assert job.last_chapter_from == 45 * MINUTE
    with pytest.raises(ReplyError, match="45:00 or later"):
        parse_reduce(reduce_reply([("00:00", "A"), ("20:00", "B"), ("42:00", "C")]), job)
    ok = parse_reduce(reduce_reply([("00:00", "A"), ("20:00", "B"), ("50:00", "C")]), job)
    assert ok.chapters[-1].start_ms == 50 * MINUTE


def test_notes_that_stop_early_move_the_floor_to_the_last_quarter_of_their_reach() -> None:
    job = notes_job(20, [0, 2, 4, 6, 7, 8])
    assert job.bounds == (3, 3)
    assert job.last_chapter_from == 6 * MINUTE
    ok = parse_reduce(reduce_reply([("00:00", "A"), ("04:00", "B"), ("06:00", "C")]), job)
    assert ok.chapters[-1].start_ms == 6 * MINUTE


def test_a_talk_of_two_chapters_needs_the_second_one_in_its_second_half() -> None:
    job = notes_job(6, [0, 1, 2, 3, 4, 5])
    assert job.bounds == (2, 2)
    assert job.last_chapter_from == 3 * MINUTE
    ok = parse_reduce(reduce_reply([("00:00", "A"), ("03:00", "B")]), job)
    assert ok.chapters[-1].start_ms == 3 * MINUTE
    with pytest.raises(ReplyError, match="final half.*Notes from there on: 03:00, 04:00, 05:00"):
        parse_reduce(reduce_reply([("00:00", "A"), ("02:00", "B")]), job)


def test_the_chapter_count_follows_how_far_the_notes_reach() -> None:
    assert notes_job(6, [0, 1, 2, 3, 4, 5]).bounds == (2, 2)
    assert notes_job(6, [0, 1]).bounds == (1, 1)


def test_half_a_chapter_rounds_up() -> None:
    assert chapter_bounds(450_000)[1] == 3
    assert chapter_bounds(270_000)[1] == 2
    assert chapter_bounds(90_000)[1] == 1


def test_a_map_call_names_the_times_to_take_notes_at() -> None:
    lines = [summarize.Line(i * 5000, i * 5000 + 4000, "word " * 40) for i in range(120)]
    window = summarize.make_windows(lines)[0]
    user = summarize.map_messages(window, 1)[1]["content"]
    count = summarize.max_points(window)
    assert f"at most {count} points" in user
    times = user.split("these times: ", 1)[1].split(".\n", 1)[0].split(", ")
    assert len(times) == count
    assert times[0] == summarize.clock(window.start_ms)


def never_fits(_: int, messages: Sequence[Message]) -> str | None:
    if messages[1]["content"].startswith("Part ") or "Write 1 chapter" in messages[1]["content"]:
        return None
    return reduce_reply([("00:00", "A"), ("00:07", "B"), ("00:07", "C")])


def too_early(_: int, messages: Sequence[Message]) -> str | None:
    user = messages[1]["content"]
    if user.startswith("Part ") or "Write 1 chapter" in user:
        return None
    count = int(first_number(r"Write (\d+)", user.replace(" to ", " ")))
    early = stamps(messages, "Notes:")[:count]
    return reduce_reply([(at, "X") for at in early])


def test_a_last_chapter_the_model_keeps_starting_early_is_moved_to_a_late_note(
    tmp_path: Path,
) -> None:
    llm = FakeLlm(too_early)
    summarize_file(write_source(tmp_path, 40), tmp_path / "summary.md", llm, ["en"])
    text = (tmp_path / "summary.en.md").read_text(encoding="utf-8")
    starts = [int(t) for t in CHAPTER_LINK.findall(text)]
    assert len(starts) >= 3
    assert starts[-1] >= 30 * 60
    assert llm.kinds().count("reduce") == MAX_RETRIES + 1


def test_when_every_reply_breaks_the_chapter_rules_one_chapter_is_asked_for(tmp_path: Path) -> None:
    llm = FakeLlm(never_fits)
    source = write_source(tmp_path, 12)
    dest = tmp_path / "summary.md"
    summarize_file(source, dest, llm)
    assert len(CHAPTER_LINK.findall(dest.read_text(encoding="utf-8"))) == 1
    assert llm.kinds().count("reduce") == MAX_RETRIES + 1 + 1
    assert "Write 1 chapter." in llm.calls[-1][1]["content"]
    again = FakeLlm()
    summarize_file(source, dest, again)
    assert again.calls == []


def test_a_failure_of_the_one_chapter_request_too_raises_and_keeps_the_notes(
    tmp_path: Path,
) -> None:
    llm = FakeLlm(lambda _, m: None if m[1]["content"].startswith("Part ") else "not json")
    dest = tmp_path / "summary.md"
    with pytest.raises(SummaryError, match="not valid JSON"):
        summarize_file(write_source(tmp_path, 12), dest, llm)
    assert not dest.exists()
    assert parse_parts((tmp_path / "summary.parts.json").read_text(encoding="utf-8")).maps


def test_a_talk_that_can_only_have_one_chapter_does_not_ask_twice(tmp_path: Path) -> None:
    llm = FakeLlm(lambda _, m: None if m[1]["content"].startswith("Part ") else "not json")
    with pytest.raises(SummaryError):
        summarize_file(write_source(tmp_path, 2), tmp_path / "summary.md", llm)
    assert llm.kinds().count("reduce") == MAX_RETRIES + 1


def test_a_glyph_the_model_keeps_writing_does_not_cost_the_whole_summary(tmp_path: Path) -> None:
    def simplified(_: int, messages: Sequence[Message]) -> str | None:
        if messages[1]["content"].startswith("Part "):
            return None
        good = json.loads(good_reduce(messages))
        good["key_points"] = ["阿耳忒弥斯計畫很重要。"]
        return json.dumps(good, ensure_ascii=False)

    llm = FakeLlm(simplified)
    dest = tmp_path / "summary.md"
    summarize_file(write_source(tmp_path, 12), dest, llm)
    text = dest.read_text(encoding="utf-8")
    assert "弥" in text
    assert len(CHAPTER_LINK.findall(text)) == 1
    assert llm.kinds().count("reduce") == 2 * (MAX_RETRIES + 1)


def test_a_summary_kept_despite_its_language_is_marked_degraded_and_stays_so(
    tmp_path: Path,
) -> None:
    def english(_: int, messages: Sequence[Message]) -> str | None:
        if messages[1]["content"].startswith("Part "):
            return None
        good = json.loads(good_reduce(messages))
        good["key_points"] = ["The program matters to everyone."]
        return json.dumps(good)

    dest = tmp_path / "summary.md"
    source = write_source(tmp_path, 12)
    seen: list[str] = []
    summarize_file(source, dest, FakeLlm(english), on_degraded=seen.append)
    assert seen == ["zh-TW"]
    assert '"degraded": true' in (tmp_path / "summary.parts.json").read_text(encoding="utf-8")
    again: list[str] = []
    summarize_file(source, dest, FakeLlm(), on_degraded=again.append)
    assert again == ["zh-TW"]


def test_a_summary_that_passes_its_language_check_is_not_degraded(tmp_path: Path) -> None:
    seen: list[str] = []
    summarize_file(
        write_source(tmp_path, 12), tmp_path / "summary.md", FakeLlm(), on_degraded=seen.append
    )
    assert seen == []
    assert "degraded" not in (tmp_path / "summary.parts.json").read_text(encoding="utf-8")
