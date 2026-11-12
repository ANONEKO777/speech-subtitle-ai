from __future__ import annotations

import hashlib
import json
import logging
import math
import re
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field, replace
from importlib.resources import files
from pathlib import Path
from typing import Literal, cast

from backend.core.language_prompts import EN_SUMMARY, SummaryText
from backend.core.languages import DEFAULT_CODE, ENGLISH, get
from backend.core.model import Cue, FormatError
from backend.core.source_langs import ENGLISH_SOURCE, SourceLanguage
from backend.core.subtitle_io import parse_subs, read_text_file, write_text_file
from backend.core.translate import GlossaryEntry, glossary_block
from backend.llm.ask import (
    MAX_RETRIES,
    ChatFn,
    RepliesRejected,
    ReplyError,
    ask,
    json_chat,
    parse_json_reply,
)
from backend.llm.client import LlmConfig, Message

log = logging.getLogger(__name__)

Lang = str
"""A language code from `backend.core.languages`, or "en" for the English summary."""
Stage = Literal["map", "reduce"]

WINDOW_TOKENS = 3000
OVERLAP_TOKENS = 200
CONTEXT_TOKENS = 8192
MAX_REQUEST_FRACTION = 0.75
REPLY_MAX_TOKENS = 2048
_ECHO_CHARS = 1800
CHARS_PER_TOKEN = 3.5
WORDS_PER_POINT = 25
MAX_POINTS = 8
MAX_CHAPTERS = 7
MIN_LONG_CHAPTERS = 3
CHAPTER_MS = 180_000
NOTES_PER_CHAPTER = 2
LAST_CHAPTER_FROM = 0.75
TWO_CHAPTER_FROM = 0.5
_MAX_POINT_CHARS = 400
_MAX_TITLE_CHARS = 100
_MAX_LINE_CHARS = 500
_MAX_KEY_POINTS = 10
_MAX_TAKEAWAYS = 5
_STATE_VERSION = 1
_GLOSSARY_MARK = "<<GLOSSARY>>"
_LANGUAGE_MARK = "<<LANGUAGE>>"
_CLOCK = re.compile(r"\[?(?:(\d+):)?(\d{1,2}):(\d{2})\]?")
CHAPTER_LINK = re.compile(r"\[(?:\d+:)?\d{2}:\d{2}\]\(#t=(\d+)\)")

ENGLISH_SUMMARY_FILE = "summary.en.md"


def _summary_text(lang: Lang) -> SummaryText:
    return EN_SUMMARY if lang == ENGLISH else get(lang).summary


class SummaryError(RuntimeError):
    """The summary cannot be made: no transcript, no usable map result, or a reduce that fails."""


@dataclass(frozen=True, slots=True)
class Line:
    start_ms: int
    end_ms: int
    text: str


@dataclass(frozen=True, slots=True)
class Window:
    """What one map call reads. `lines` are summarised, and `context` repeats the tail of the
    previous window so a point that straddles the cut is not lost. Windows tile the transcript:
    no line is in two `lines`."""

    index: int
    context: tuple[Line, ...]
    lines: tuple[Line, ...]

    def __post_init__(self) -> None:
        if not self.lines:
            raise ValueError("a window needs at least one line")

    @property
    def start_ms(self) -> int:
        return self.lines[0].start_ms

    @property
    def end_ms(self) -> int:
        return self.lines[-1].end_ms


@dataclass(frozen=True, slots=True)
class Point:
    at_ms: int
    text: str


@dataclass(frozen=True, slots=True)
class MapResult:
    start_ms: int
    end_ms: int
    topic: str
    points: tuple[Point, ...]


@dataclass(frozen=True, slots=True)
class Chapter:
    start_ms: int
    title: str
    summary: str


@dataclass(frozen=True, slots=True)
class ReduceResult:
    one_liner: str
    chapters: tuple[Chapter, ...]
    key_points: tuple[str, ...]
    takeaways: tuple[str, ...]
    degraded: bool = False
    """True when the reply broke the language check and was kept anyway, so its text may be in
    the wrong script or language."""


@dataclass(frozen=True, slots=True)
class Gap:
    start_ms: int
    end_ms: int


@dataclass(frozen=True, slots=True)
class SummaryDoc:
    lang: Lang
    result: ReduceResult
    gaps: tuple[Gap, ...] = ()


@dataclass(slots=True)
class Parts:
    """Finished model calls kept between runs. A map result is keyed by the digest of its request
    and a reduce result by language, with the digest of its request."""

    maps: dict[str, MapResult] = field(default_factory=dict[str, MapResult])
    reduces: dict[Lang, tuple[str, ReduceResult]] = field(
        default_factory=dict[Lang, tuple[str, ReduceResult]]
    )


@dataclass(frozen=True, slots=True)
class Progress:
    stage: Stage
    done: int
    total: int
    seconds: float


def summary_chat(config: LlmConfig) -> ChatFn:
    """`json_chat` with the reply capped at the share of the context that a request leaves free."""
    return json_chat(config, max_tokens=REPLY_MAX_TOKENS)


def clock(ms: int) -> str:
    seconds = ms // 1000
    hours, rest = divmod(seconds, 3600)
    minutes, secs = divmod(rest, 60)
    return f"{hours}:{minutes:02d}:{secs:02d}" if hours else f"{minutes:02d}:{secs:02d}"


def chapter_link(ms: int) -> str:
    return f"[{clock(ms)}](#t={ms // 1000})"


def parse_clock(text: str) -> int:
    match = _CLOCK.fullmatch(text.strip())
    if not match:
        raise ReplyError(f"{text!r} is not a time like 12:34 or 1:02:03")
    hours, minutes, seconds = (int(part or 0) for part in match.groups())
    if seconds > 59 or (hours and minutes > 59):
        raise ReplyError(f"{text!r} is not a valid time")
    return ((hours * 60 + minutes) * 60 + seconds) * 1000


def estimate_tokens(text: str, chars_per_token: float = CHARS_PER_TOKEN) -> int:
    return math.ceil(len(text) / chars_per_token)


def render_line(line: Line) -> str:
    return f"[{clock(line.start_ms)}] {' '.join(line.text.split())}"


def lines_from_cues(cues: Sequence[Cue]) -> list[Line]:
    return [Line(cue.start_ms, cue.end_ms, cue.src) for cue in cues if cue.src.strip()]


def make_windows(
    lines: Sequence[Line],
    window_tokens: int = WINDOW_TOKENS,
    overlap_tokens: int = OVERLAP_TOKENS,
    chars_per_token: float = CHARS_PER_TOKEN,
) -> list[Window]:
    """Cut `lines` into windows of about `window_tokens` that each start with up to
    `overlap_tokens` of the lines before them."""
    if overlap_tokens >= window_tokens:
        raise ValueError(
            f"overlap {overlap_tokens} must be smaller than the window {window_tokens}"
        )
    sizes = [estimate_tokens(render_line(line), chars_per_token) for line in lines]
    windows: list[Window] = []
    start = 0
    while start < len(lines):
        first, carried = start, 0
        while first > 0 and carried + sizes[first - 1] <= overlap_tokens:
            first -= 1
            carried += sizes[first]
        stop, used = start, carried
        while stop < len(lines) and (stop == start or used + sizes[stop] <= window_tokens):
            used += sizes[stop]
            stop += 1
        windows.append(Window(len(windows), tuple(lines[first:start]), tuple(lines[start:stop])))
        start = stop
    return windows


def chapter_bounds(duration_ms: int, note_count: int | None = None) -> tuple[int, int]:
    """How many chapters a summary of `duration_ms` may hold: about one per `CHAPTER_MS`, at most
    `MAX_CHAPTERS`, and no more than `note_count` notes can fill at `NOTES_PER_CHAPTER` each. The
    least is `MIN_LONG_CHAPTERS` or the most when that is smaller. A half chapter rounds up."""
    most = min(MAX_CHAPTERS, max(1, (duration_ms + CHAPTER_MS // 2) // CHAPTER_MS))
    if note_count is not None:
        most = min(most, max(1, note_count // NOTES_PER_CHAPTER))
    return min(MIN_LONG_CHAPTERS, most), most


def _template(name: str) -> str:
    return (files("backend.core") / "prompts" / name).read_text(encoding="utf-8")


def max_points(window: Window, source: SourceLanguage = ENGLISH_SOURCE) -> int:
    words = sum(source.words(line.text) for line in window.lines)
    return min(MAX_POINTS, max(1, round(words / WORDS_PER_POINT)))


_MAP_HEAD = (
    "Part {part} of {total}, from {start} to {end}. Write at most {count} points, one from "
    "about each of these times: {times}."
)
_MAP_CONTEXT = "Earlier lines, only for context. Do not take notes on them:"
_MAP_LINES = "Lines to summarise:"
MAP_FRAMING = (_MAP_HEAD, _MAP_CONTEXT, _MAP_LINES)
"""The map prompt's text that lives in code rather than in `summarize_map.md`. The summarize
step's cache key digests it, so editing it re-runs the summaries."""


def map_messages(
    window: Window, total: int, source: SourceLanguage = ENGLISH_SOURCE
) -> tuple[Message, ...]:
    """Naming the times to take notes at is what spreads them: asked only to spread them, the
    model spent all its points on the first minutes of a part, however long."""
    count = max_points(window, source)
    span = window.end_ms - window.start_ms
    times = ", ".join(clock(window.start_ms + i * span // count) for i in range(count))
    body = [
        _MAP_HEAD.format(
            part=window.index + 1,
            total=total,
            start=clock(window.start_ms),
            end=clock(window.end_ms),
            count=count,
            times=times,
        )
    ]
    if window.context:
        body += ["", _MAP_CONTEXT]
        body += [render_line(line) for line in window.context]
    body += ["", _MAP_LINES, *(render_line(line) for line in window.lines)]
    return (
        Message(role="system", content=_template(source.summary_map)),
        Message(role="user", content="\n".join(body)),
    )


def _object(doc: object, what: str) -> dict[str, object]:
    if not isinstance(doc, dict):
        raise ReplyError(f"the reply must be a JSON object holding {what}")
    return cast("dict[str, object]", doc)


def _text(value: object, name: str, limit: int) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ReplyError(f'"{name}" must be a non-empty string')
    text = " ".join(value.split())
    if len(text) > limit:
        raise ReplyError(f'"{name}" is {len(text)} characters long; keep it under {limit}')
    return text


def _list(value: object, name: str) -> list[object]:
    if not isinstance(value, list):
        raise ReplyError(f'"{name}" must be a list')
    return cast("list[object]", value)


def parse_map(text: str, window: Window, source: SourceLanguage = ENGLISH_SOURCE) -> MapResult:
    """The notes of one window. The notes are in the language of the summary, so a source whose
    text must not show in it (Japanese kana) rejects a note that copies the speaker's words."""
    doc = _object(parse_json_reply(text), '"topic" and "points"')
    topic = _text(doc.get("topic"), "topic", _MAX_TITLE_CHARS)
    if problem := source.problem(topic):
        raise ReplyError(f'"topic" {problem}')
    raw = _list(doc.get("points"), "points")
    if not raw:
        raise ReplyError('"points" must hold at least 1 point, but holds none')
    starts = [line.start_ms for line in window.lines]
    low, high = window.start_ms // 1000 * 1000, window.end_ms + 999
    points: list[Point] = []
    for position, item in enumerate(raw):
        entry = _object(item, f"point {position}")
        at_ms = parse_clock(str(entry.get("at")))
        if not low <= at_ms <= high:
            raise ReplyError(
                f"point {position} is at {clock(at_ms)}, outside the lines to summarise "
                f"({clock(window.start_ms)} to {clock(window.end_ms)})"
            )
        snapped = max((start for start in starts if start <= at_ms), default=starts[0])
        note = _text(entry.get("text"), "text", _MAX_POINT_CHARS)
        if problem := source.problem(note):
            raise ReplyError(f"point {position} {problem}")
        points.append(Point(snapped, note))
    points.sort(key=lambda point: point.at_ms)
    return MapResult(window.start_ms, window.end_ms, topic, thin(points, max_points(window)))


def thin(points: Sequence[Point], limit: int) -> tuple[Point, ...]:
    """At most `limit` of `points`, evenly spread and keeping the first and the last. A model
    that writes more notes than asked, and again after being told, has still taken valid notes."""
    if len(points) <= limit:
        return tuple(points)
    if limit == 1:
        return (points[0],)
    last = len(points) - 1
    return tuple(points[round(i * last / (limit - 1))] for i in range(limit))


@dataclass(frozen=True, slots=True)
class ReduceInput:
    lang: Lang
    start_ms: int
    end_ms: int
    maps: tuple[MapResult, ...]
    gaps: tuple[Gap, ...]
    glossary: tuple[GlossaryEntry, ...]
    source: SourceLanguage = ENGLISH_SOURCE

    @property
    def span_ms(self) -> int:
        return self.end_ms - self.start_ms

    single_chapter: bool = False
    check_language: bool = True
    snap_last: bool = False
    """Move a last chapter that starts too early to the first note that is late enough."""

    @property
    def note_times(self) -> list[int]:
        return sorted({point.at_ms for part in self.maps for point in part.points})

    @property
    def reach_ms(self) -> int:
        """How far into the talk the notes go."""
        return self.note_times[-1] - self.start_ms

    @property
    def bounds(self) -> tuple[int, int]:
        if self.single_chapter:
            return 1, 1
        return chapter_bounds(min(self.span_ms, self.reach_ms), len(self.note_times))

    @property
    def last_chapter_share(self) -> float:
        """How far into the talk the last chapter starts at the earliest. Of two chapters of
        about three minutes each the second starts around the middle, so a talk that holds at
        most two asks for the second half, and every other talk for the final quarter."""
        return TWO_CHAPTER_FROM if self.bounds[1] == 2 else LAST_CHAPTER_FROM

    @property
    def last_chapter_from(self) -> int:
        """The earliest start of the last chapter: `last_chapter_share` of the talk, or, when the
        notes stop before that, the same share of what the notes reach."""
        talk = self.start_ms + round(self.last_chapter_share * self.span_ms)
        if self.note_times[-1] >= talk:
            return talk
        return self.start_ms + round(self.last_chapter_share * self.reach_ms)


def reduce_messages(job: ReduceInput) -> tuple[Message, ...]:
    least, most = job.bounds
    count = f"{least} to {most}" if least != most else str(most)
    body = [
        f"The talk is {clock(job.span_ms)} long, from {clock(job.start_ms)} to "
        f"{clock(job.end_ms)}. Write {count} chapter{'s' if most > 1 else ''}.",
        "",
        "Notes:",
    ]
    for part in job.maps:
        body.append(f"== {clock(part.start_ms)}-{clock(part.end_ms)} | {part.topic}")
        body += [f"[{clock(point.at_ms)}] {point.text}" for point in part.points]
    for gap in job.gaps:
        body.append(
            f"Missing: {clock(gap.start_ms)}-{clock(gap.end_ms)} could not be read; no notes."
        )
    system = (
        _template("summarize_reduce.md")
        .replace(_LANGUAGE_MARK, _summary_text(job.lang).rule)
        .replace(_GLOSSARY_MARK, glossary_block(job.glossary))
        .rstrip()
        + "\n"
    )
    return (Message(role="system", content=system), Message(role="user", content="\n".join(body)))


def _localised(
    job: ReduceInput, value: object, name: str, limit: int, *, prose: bool = True
) -> str:
    text = _text(value, name, limit)
    if job.lang == ENGLISH:
        return text
    language = get(job.lang)
    text = job.source.clean(language.terms_from(job.source.code, text))
    if not job.check_language:
        return text
    if problem := language.prose_problem(text) if prose else language.title_problem(text):
        raise ReplyError(f'"{name}" {problem}')
    if problem := job.source.problem(text):
        raise ReplyError(f'"{name}" {problem}')
    return text


def _strings(job: ReduceInput, value: object, name: str, low: int, high: int) -> tuple[str, ...]:
    items = _list(value, name)
    if not low <= len(items) <= high:
        raise ReplyError(f'"{name}" must hold {low} to {high} entries, but holds {len(items)}')
    return tuple(_localised(job, item, name, _MAX_LINE_CHARS) for item in items)


def parse_reduce(text: str, job: ReduceInput) -> ReduceResult:
    doc = _object(parse_json_reply(text), '"one_liner", "chapters", "key_points", "takeaways"')
    one_liner = _localised(job, doc.get("one_liner"), "one_liner", _MAX_LINE_CHARS)
    least, most = job.bounds
    raw = _list(doc.get("chapters"), "chapters")
    if not least <= len(raw) <= most:
        raise ReplyError(f'"chapters" must hold {least} to {most} chapters, but holds {len(raw)}')
    notes = job.note_times
    chapters: list[Chapter] = []
    for position, item in enumerate(raw):
        entry = _object(item, f"chapter {position}")
        at_ms = parse_clock(str(entry.get("at")))
        if not job.start_ms // 1000 * 1000 <= at_ms <= job.end_ms + 999:
            raise ReplyError(
                f"chapter {position} starts at {clock(at_ms)}, outside the talk "
                f"({clock(job.start_ms)} to {clock(job.end_ms)})"
            )
        start_ms = job.start_ms if position == 0 else min(notes, key=lambda t: abs(t - at_ms))
        chapters.append(
            Chapter(
                start_ms,
                _localised(job, entry.get("title"), "title", _MAX_TITLE_CHARS, prose=False),
                _localised(job, entry.get("summary"), "summary", _MAX_LINE_CHARS),
            )
        )
    starts = [chapter.start_ms for chapter in chapters]
    if any(later <= earlier for earlier, later in zip(starts, starts[1:], strict=False)):
        raise ReplyError(
            "chapters must start at different times, in order, each at a time that appears in "
            "the notes; the chapters start at " + ", ".join(clock(start) for start in starts)
        )
    last_from = job.last_chapter_from
    if job.snap_last and len(chapters) > 1 and starts[-1] < last_from:
        late = next((t for t in notes if t >= last_from), None)
        if late is not None:
            chapters[-1] = replace(chapters[-1], start_ms=late)
            starts[-1] = late
    if len(chapters) > 1 and starts[-1] < last_from:
        later = ", ".join(clock(t) for t in [t for t in notes if t >= last_from][:6])
        raise ReplyError(
            f"the last chapter starts at {clock(starts[-1])}, but it must start in the final "
            f"{'half' if job.last_chapter_share < 0.75 else 'quarter'}, at {clock(last_from)} "
            f"or later. Spread the chapters over all the notes. Notes from there on: {later}"
        )
    return ReduceResult(
        one_liner,
        tuple(chapters),
        _strings(job, doc.get("key_points"), "key_points", 1, _MAX_KEY_POINTS),
        _strings(job, doc.get("takeaways", []), "takeaways", 0, _MAX_TAKEAWAYS),
    )


def render_summary(doc: SummaryDoc) -> str:
    text = _summary_text(doc.lang)
    title, chapters, key_points = text.title, text.chapters, text.key_points
    takeaways, missing, sep = text.takeaways, text.missing, text.separator
    result = doc.result
    out = [f"# {title}", "", f"> {result.one_liner}", "", f"## {chapters}", ""]
    out += [
        f"- {chapter_link(chapter.start_ms)} **{chapter.title}**{sep}{chapter.summary}"
        for chapter in result.chapters
    ]
    out += ["", f"## {key_points}", "", *(f"- {point}" for point in result.key_points)]
    if result.takeaways:
        out += ["", f"## {takeaways}", "", *(f"- {item}" for item in result.takeaways)]
    if doc.gaps:
        out += ["", f"## {missing}", ""]
        out += [f"- {clock(gap.start_ms)} - {clock(gap.end_ms)}" for gap in doc.gaps]
    return "\n".join(out) + "\n"


def summary_path(dest: Path, lang: Lang) -> Path:
    """`dest` holds the summary in the target language, and `summary.en.md` beside it the English
    one."""
    return dest.with_name(ENGLISH_SUMMARY_FILE) if lang == ENGLISH else dest


def reprompt(reason: str) -> str:
    return f"Your last reply was rejected: {reason}. Reply again with the complete JSON object."


def _digest(messages: Sequence[Message]) -> str:
    return hashlib.sha256(json.dumps(messages, ensure_ascii=False).encode()).hexdigest()[:16]


def _map_json(part: MapResult) -> dict[str, object]:
    return {
        "start_ms": part.start_ms,
        "end_ms": part.end_ms,
        "topic": part.topic,
        "points": [{"at_ms": p.at_ms, "text": p.text} for p in part.points],
    }


def _reduce_json(result: ReduceResult) -> dict[str, object]:
    return {
        "one_liner": result.one_liner,
        "chapters": [
            {"start_ms": c.start_ms, "title": c.title, "summary": c.summary}
            for c in result.chapters
        ],
        "key_points": list(result.key_points),
        "takeaways": list(result.takeaways),
        **({"degraded": True} if result.degraded else {}),
    }


def render_parts(parts: Parts) -> str:
    doc = {
        "version": _STATE_VERSION,
        "maps": {key: _map_json(part) for key, part in parts.maps.items()},
        "reduces": {
            lang: {"digest": digest, "result": _reduce_json(result)}
            for lang, (digest, result) in parts.reduces.items()
        },
    }
    return json.dumps(doc, ensure_ascii=False, indent=1) + "\n"


def _load_map(raw: Mapping[str, object]) -> MapResult:
    points = cast("list[Mapping[str, object]]", raw["points"])
    return MapResult(
        cast("int", raw["start_ms"]),
        cast("int", raw["end_ms"]),
        cast("str", raw["topic"]),
        tuple(Point(cast("int", p["at_ms"]), cast("str", p["text"])) for p in points),
    )


def _load_reduce(raw: Mapping[str, object]) -> ReduceResult:
    chapters = cast("list[Mapping[str, object]]", raw["chapters"])
    return ReduceResult(
        cast("str", raw["one_liner"]),
        tuple(
            Chapter(cast("int", c["start_ms"]), cast("str", c["title"]), cast("str", c["summary"]))
            for c in chapters
        ),
        tuple(cast("list[str]", raw["key_points"])),
        tuple(cast("list[str]", raw["takeaways"])),
        raw.get("degraded") is True,
    )


def parse_parts(text: str) -> Parts:
    """Read saved parts. Anything unreadable gives no parts."""
    try:
        doc = cast("dict[str, object]", json.loads(text))
        if doc["version"] != _STATE_VERSION:
            return Parts()
        maps = cast("dict[str, Mapping[str, object]]", doc["maps"])
        reduces = cast("dict[Lang, Mapping[str, object]]", doc["reduces"])
        return Parts(
            {key: _load_map(raw) for key, raw in maps.items()},
            {
                lang: (
                    cast("str", raw["digest"]),
                    _load_reduce(cast("Mapping[str, object]", raw["result"])),
                )
                for lang, raw in reduces.items()
            },
        )
    except (ValueError, KeyError, TypeError, AttributeError):
        return Parts()


class _Run:
    def __init__(
        self,
        chat: ChatFn,
        parts: Parts,
        *,
        context_tokens: int,
        max_retries: int,
        checkpoint: Callable[[Parts], None] | None,
        on_progress: Callable[[Progress], None] | None,
        sleep: Callable[[float], None],
        source: SourceLanguage,
    ) -> None:
        self.source = source
        self.chat = chat
        self.parts = parts
        self.context_tokens = context_tokens
        self.max_retries = max_retries
        self.checkpoint = checkpoint
        self.on_progress = on_progress
        self.sleep = sleep

    def check_size(self, messages: Sequence[Message], label: str) -> None:
        per_token = self.source.chars_per_token
        tokens = sum(estimate_tokens(message["content"], per_token) for message in messages)
        share = tokens / self.context_tokens
        log.info("%s request about %d tokens, %.0f%% of the context", label, tokens, share * 100)
        if share > MAX_REQUEST_FRACTION:
            raise SummaryError(
                f"{label} needs about {tokens} tokens, over {MAX_REQUEST_FRACTION:.0%} of the "
                f"{self.context_tokens} token context"
            )

    def map_window(
        self, window: Window, messages: Sequence[Message], total: int
    ) -> MapResult | None:
        key = _digest(messages)
        if cached := self.parts.maps.get(key):
            return cached
        label = f"map {window.index + 1}/{total}"
        self.check_size(messages, label)
        started = time.monotonic()
        try:
            part, _ = ask(
                self.chat,
                messages,
                lambda text: parse_map(text, window, self.source),
                reprompt=reprompt,
                label=label,
                retries=self.max_retries,
                echo_limit=_ECHO_CHARS,
                sleep=self.sleep,
            )
        except RepliesRejected as exc:
            log.warning("%s gave up after %d attempts: %s", label, exc.attempts, exc.reason)
            return None
        self.parts.maps[key] = part
        if self.checkpoint:
            self.checkpoint(self.parts)
        if self.on_progress:
            done = window.index + 1
            self.on_progress(Progress("map", done, total, time.monotonic() - started))
        return part

    def ask_reduce(self, job: ReduceInput, messages: Sequence[Message], label: str) -> ReduceResult:
        result, _ = ask(
            self.chat,
            messages,
            lambda text: parse_reduce(text, job),
            reprompt=reprompt,
            label=label,
            retries=self.max_retries,
            echo_limit=_ECHO_CHARS,
            sleep=self.sleep,
        )
        return result

    def ask_reduce_or_fall_back(
        self, job: ReduceInput, messages: Sequence[Message], label: str
    ) -> ReduceResult:
        """Ask for the summary; when no reply passes, give up chapters before giving up the
        summary. First the last reply with its last chapter moved to the first late enough note,
        for a model that keeps starting it a few seconds early. Then one chapter, which needs no
        placement. Then the last reply as it is, with
        its language checks waived: a summary with one wrong glyph in a transliterated name serves
        the reader better than none, and the model repeats such a glyph however it is told. That
        result is marked `degraded`, and never passes for a normal one."""
        try:
            return self.ask_reduce(job, messages, label)
        except RepliesRejected as exc:
            failure = exc
        log.warning("%s gave up after %d attempts: %s", label, failure.attempts, failure.reason)
        if job.bounds != (1, 1):
            try:
                result = parse_reduce(failure.reply, replace(job, snap_last=True))
            except ReplyError:
                pass
            else:
                log.warning("%s: moved the last chapter to a late enough note", label)
                return result
            job = replace(job, single_chapter=True)
            try:
                return self.ask_reduce(job, reduce_messages(job), f"{label} (1 chapter)")
            except RepliesRejected as exc:
                failure = exc
            log.warning("%s (1 chapter) gave up: %s", label, failure.reason)
        try:
            result = parse_reduce(failure.reply, replace(job, check_language=False))
        except ReplyError as exc:
            raise SummaryError(
                f"the summary could not be written: {failure.reason}; the last reply: {exc}"
            ) from exc
        log.warning(
            "%s: using the last reply without its language check (%s)", label, failure.reason
        )
        return replace(result, degraded=True)

    def reduce(self, job: ReduceInput) -> ReduceResult:
        messages = reduce_messages(job)
        key = _digest(messages)
        cached = self.parts.reduces.get(job.lang)
        if cached and cached[0] == key:
            return cached[1]
        self.check_size(messages, f"reduce {job.lang}")
        started = time.monotonic()
        result = self.ask_reduce_or_fall_back(job, messages, f"reduce {job.lang}")
        self.parts.reduces[job.lang] = (key, result)
        if self.checkpoint:
            self.checkpoint(self.parts)
        if self.on_progress:
            self.on_progress(Progress("reduce", 1, 1, time.monotonic() - started))
        return result


def run(
    lines: Sequence[Line],
    chat: ChatFn,
    lang: Lang = DEFAULT_CODE,
    glossary: Sequence[GlossaryEntry] = (),
    *,
    parts: Parts | None = None,
    context_tokens: int = CONTEXT_TOKENS,
    window_tokens: int = WINDOW_TOKENS,
    overlap_tokens: int = OVERLAP_TOKENS,
    max_retries: int = MAX_RETRIES,
    checkpoint: Callable[[Parts], None] | None = None,
    on_progress: Callable[[Progress], None] | None = None,
    sleep: Callable[[float], None] = time.sleep,
    source: SourceLanguage = ENGLISH_SOURCE,
) -> SummaryDoc:
    """Summarise `lines` in `lang`: a map call per window, then one reduce call over the notes.

    A window whose notes keep failing validation is listed as a gap in the document. A server
    that stays down raises its `LlmError`. Every finished call is in `parts` and was passed to
    `checkpoint`, and a call whose request is unchanged is not asked again.
    """
    if not lines:
        raise SummaryError("the transcript has no text to summarise")
    windows = make_windows(lines, window_tokens, overlap_tokens, source.chars_per_token)
    job = _Run(
        chat,
        parts if parts is not None else Parts(),
        context_tokens=context_tokens,
        max_retries=max_retries,
        checkpoint=checkpoint,
        on_progress=on_progress,
        sleep=sleep,
        source=source,
    )
    requests = [map_messages(window, len(windows), source) for window in windows]
    live = {_digest(messages) for messages in requests}
    job.parts.maps = {key: part for key, part in job.parts.maps.items() if key in live}
    results = [
        job.map_window(window, messages, len(windows))
        for window, messages in zip(windows, requests, strict=True)
    ]
    maps = tuple(part for part in results if part)
    gaps = tuple(
        Gap(window.start_ms, window.end_ms)
        for window, part in zip(windows, results, strict=True)
        if part is None
    )
    if not maps:
        raise SummaryError("no part of the talk could be summarised")
    reduce_job = ReduceInput(
        lang, lines[0].start_ms, lines[-1].end_ms, maps, gaps, tuple(glossary), source
    )
    return SummaryDoc(lang, job.reduce(reduce_job), gaps)


def summarize_file(
    source: Path,
    dest: Path,
    chat: ChatFn,
    langs: Sequence[Lang] = (DEFAULT_CODE,),
    glossary: Sequence[GlossaryEntry] = (),
    *,
    context_tokens: int = CONTEXT_TOKENS,
    on_progress: Callable[[Progress], None] | None = None,
    on_degraded: Callable[[Lang], None] | None = None,
    source_lang: SourceLanguage = ENGLISH_SOURCE,
) -> list[Path]:
    """Summarise the English of `source` (a subs json) into `dest`, in the language `langs` names,
    and, for `en`, into `summary.en.md` beside it. Finished model calls are kept in the
    `.parts.json` file named after `dest`, so a run after a crash or a failure asks only for
    what is missing, and a run with nothing new asks for nothing. `on_degraded` gets each language
    whose summary was kept despite failing its language check."""
    lines = lines_from_cues(parse_subs(read_text_file(source)))
    state = dest.with_name(f"{dest.stem}.parts.json")
    parts = Parts()
    if state.exists():
        try:
            parts = parse_parts(read_text_file(state))
        except FormatError:
            parts = Parts()

    def save(current: Parts) -> None:
        write_text_file(state, render_parts(current))

    written: list[Path] = []
    for lang in langs:
        doc = run(
            lines,
            chat,
            lang,
            glossary,
            parts=parts,
            context_tokens=context_tokens,
            checkpoint=save,
            on_progress=on_progress,
            source=source_lang,
        )
        path = summary_path(dest, lang)
        write_text_file(path, render_summary(doc))
        written.append(path)
        if doc.result.degraded and on_degraded:
            on_degraded(lang)
    save(parts)
    return written
