from __future__ import annotations

import json
import logging
import re
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, replace
from importlib.resources import files
from pathlib import Path
from typing import cast

from backend.core.languages import DEFAULT, Density, Language
from backend.core.model import Cue, FormatError
from backend.core.source_langs import ENGLISH_SOURCE, SourceLanguage, is_bare_punctuation
from backend.core.subtitle_io import parse_subs, read_text_file, render_subs, write_text_file
from backend.llm.ask import (
    MAX_RETRIES,
    ChatFn,
    RepliesRejected,
    ReplyError,
    ask,
    parse_json_reply,
)
from backend.llm.client import Message

log = logging.getLogger(__name__)

BATCH_SIZE = 10
CONTEXT_CUES = 5
MAX_UNIT_CUES = 6

_LONG_EN_CHARS = 25
GLOSSARY_MARK = "<<GLOSSARY>>"
_MARKER = re.compile(r"\[\[(\d+)\]\]")


class TranslationError(RuntimeError):
    """A single cue could not be translated, after every retry."""


@dataclass(frozen=True, slots=True)
class GlossaryEntry:
    """A term the translation must treat in a fixed way. An empty `zh` keeps `term` as written, in
    every target language. A `zh` is the fixed translation, in whichever language is the target."""

    term: str
    zh: str = ""

    def __post_init__(self) -> None:
        if not self.term.strip() or "\n" in self.term or "\n" in self.zh:
            raise ValueError(
                f"glossary term and translation must be single non-empty lines: {self}"
            )


_PRODUCT_NAMES = (
    "Cursor, Claude Code, Claude, Copilot, GitHub Copilot, ChatGPT, Codex, Gemini, Windsurf, "
    "Devin, OpenAI, Anthropic, GitHub, VS Code, Xcode, TypeScript, Slack, Docker, Kubernetes, "
    "Figma, Notion"
)
DEFAULT_GLOSSARY: tuple[GlossaryEntry, ...] = tuple(
    GlossaryEntry(name) for name in _PRODUCT_NAMES.split(", ")
)
"""Product names that stay in English in every run. A user's own entries come after them."""

_SOURCE_GLOSSARY: dict[str, tuple[GlossaryEntry, ...]] = {
    "ja": (
        GlossaryEntry("Perforce"),
        GlossaryEntry("P4"),
        GlossaryEntry("P4 MCP"),
        GlossaryEntry("P4 DAM"),
        GlossaryEntry("Helix Swarm"),
        GlossaryEntry("東陽テクニカ", "Toyo Corporation"),
        GlossaryEntry("パフォース", "Perforce"),
        GlossaryEntry("パーフォース", "Perforce"),
        GlossaryEntry("パフォッシャ", "Perforce"),
        GlossaryEntry("パフォーシャ", "Perforce"),
    )
}


_SOURCE_GLOSSARY["ja+en"] = _SOURCE_GLOSSARY["ja"]


def default_glossary(source: str) -> tuple[GlossaryEntry, ...]:
    """The glossary every run of a talk in `source` starts with. The names of the products the
    Japanese test talks are about are in it because speech recognition garbles them."""
    return (*DEFAULT_GLOSSARY, *_SOURCE_GLOSSARY.get(source, ()))


@dataclass(frozen=True, slots=True)
class Unit:
    """Consecutive cues that are one sentence (or a capped piece of one). A unit is translated as
    a whole and split back into cues at the markers the model keeps in its reply."""

    start: int
    stop: int

    def __post_init__(self) -> None:
        if not 0 <= self.start < self.stop:
            raise ValueError(f"empty or negative unit [{self.start}, {self.stop})")

    def __len__(self) -> int:
        return self.stop - self.start


@dataclass(frozen=True, slots=True)
class Batch:
    """Whole units translated in one request, covering positions `start` up to `stop`."""

    units: tuple[Unit, ...]

    def __post_init__(self) -> None:
        if not self.units:
            raise ValueError("empty batch")

    @property
    def start(self) -> int:
        return self.units[0].start

    @property
    def stop(self) -> int:
        return self.units[-1].stop

    def __len__(self) -> int:
        return self.stop - self.start

    def halves(self) -> tuple[Batch, Batch]:
        """Split between units, or inside the one unit a batch holds."""
        unit = self.units[0]
        if len(self.units) > 1:
            mid = len(self.units) // 2
            return Batch(self.units[:mid]), Batch(self.units[mid:])
        mid = unit.start + len(unit) // 2
        return Batch((Unit(unit.start, mid),)), Batch((Unit(mid, unit.stop),))


@dataclass(frozen=True, slots=True)
class BatchRequest:
    """What goes to the model: the cue ids of each unit, and the messages. The reply must hold
    exactly one entry per unit, keyed by the unit's first cue id."""

    units: tuple[tuple[int, ...], ...]
    messages: tuple[Message, ...]

    @property
    def ids(self) -> tuple[int, ...]:
        return tuple(unit[0] for unit in self.units)


@dataclass(frozen=True, slots=True)
class Progress:
    """Reported after each batch is stored. `done` includes cues translated by an earlier run."""

    done: int
    total: int
    batch_cues: int
    batch_seconds: float
    attempts: int


def sentence_units(
    cues: Sequence[Cue], start: int, stop: int, limit: int, source: SourceLanguage = ENGLISH_SOURCE
) -> list[Unit]:
    """Group `cues[start:stop]` into sentences: a unit ends at a cue that ends a sentence, or after
    `limit` cues when speech runs on without one, or where the language changes."""
    units: list[Unit] = []
    first = start
    for index in range(start, stop):
        ends = source.of(cues[index].lang).sentence_end.search(cues[index].src.rstrip()) is not None
        switches = index + 1 < stop and cues[index + 1].lang != cues[index].lang
        if ends or switches or index + 1 == stop or index + 1 - first == limit:
            units.append(Unit(first, index + 1))
            first = index + 1
    return units


def plan_batches(
    cues: Sequence[Cue],
    size: int = BATCH_SIZE,
    unit_limit: int = MAX_UNIT_CUES,
    source: SourceLanguage = ENGLISH_SOURCE,
) -> list[Batch]:
    """Pack the sentences of each run of untranslated cues into batches of about `size` cues. A
    translated cue ends a run, so a resume asks only for what is missing."""
    if size < 1:
        raise ValueError(f"batch size must be at least 1, got {size}")
    batches: list[Batch] = []
    start: int | None = None
    for index in range(len(cues) + 1):
        open_run = index < len(cues) and not cues[index].zh
        if start is not None and (not open_run or cues[index].lang != cues[start].lang):
            batches.extend(_pack(sentence_units(cues, start, index, unit_limit, source), size))
            start = None
        if open_run and start is None:
            start = index
    return batches


def _pack(units: Sequence[Unit], size: int) -> list[Batch]:
    batches: list[list[Unit]] = []
    cues_in_batch = 0
    for unit in units:
        if batches and cues_in_batch + len(unit) <= size:
            batches[-1].append(unit)
            cues_in_batch += len(unit)
        else:
            batches.append([unit])
            cues_in_batch = len(unit)
    return [Batch(tuple(group)) for group in batches]


def _quoted(text: str) -> str:
    return json.dumps(text, ensure_ascii=False)


def glossary_block(glossary: Sequence[GlossaryEntry]) -> str:
    """The glossary lines for a system prompt, empty when there are no entries."""
    if not glossary:
        return ""
    lines = ["", "Glossary. Whenever one of these terms appears, in any capitalisation:"]
    for entry in glossary:
        if entry.zh:
            lines.append(f"- {_quoted(entry.term)} must be translated as {_quoted(entry.zh)}")
        else:
            lines.append(f"- {_quoted(entry.term)} must stay in its original English spelling")
    return "\n".join(lines)


def system_prompt_template(lang: Language, source: SourceLanguage = ENGLISH_SOURCE) -> str:
    """The system prompt for translating `source` into `lang`, with the glossary still marked by
    `GLOSSARY_MARK`."""
    prompt = lang.prompt
    said = source.prompt
    text = (files("backend.core") / "prompts" / "translate.md").read_text(encoding="utf-8")
    for mark, value in (
        ("<<SRC_ENTRIES>>", said.entries),
        ("<<SRC_RULES>>", said.rules),
        ("<<SRC_LEFTOVER>>", said.leftover),
        ("<<SRC_KEY>>", said.key),
        ("<<SRC>>", said.name),
        ("<<STYLE_RULES>>\n", prompt.style),
        ("<<TARGET>>", prompt.target),
        ("<<REPLY_NAME>>", prompt.reply_name),
        ("<<EXAMPLE>>", source.example(lang)),
        ("<<FILLER_NOT>>", prompt.filler_not),
        ("<<YOU_KNOW>>", prompt.you_know),
        ("<<FILLER_CUE>>", prompt.filler_cue),
        ("<<KEY>>", prompt.key),
        ("<<NAME>>", prompt.name),
    ):
        text = text.replace(mark, value)
    return text


def _system_prompt(
    glossary: Sequence[GlossaryEntry], lang: Language, source: SourceLanguage
) -> str:
    template = system_prompt_template(lang, source)
    return template.replace(GLOSSARY_MARK, glossary_block(glossary)).rstrip() + "\n"


def _mark(cue_id: int) -> str:
    return f"[[{cue_id}]]"


def _marked(cues: Sequence[Cue], source: SourceLanguage) -> str:
    if len(cues) == 1:
        return source.flat(cues[0].src)
    separator = " " if source.spaced else ""
    return separator.join(f"{_mark(cue.id)}{source.flat(cue.src)}" for cue in cues)


def build_request(
    cues: Sequence[Cue],
    batch: Batch,
    glossary: Sequence[GlossaryEntry] = (),
    context: int = CONTEXT_CUES,
    lang: Language = DEFAULT,
    source: SourceLanguage = ENGLISH_SOURCE,
) -> BatchRequest:
    groups = [cues[unit.start : unit.stop] for unit in batch.units]
    source = source.of(cues[batch.start].lang)
    same = [i for i, cue in enumerate(cues) if cue.lang == cues[batch.start].lang]
    before = [cues[i].src for i in same if i < batch.start][-context:] if context else []
    after = [cues[i].src for i in same if i >= batch.stop][:context]
    body = {
        "context_before": source.prose(before),
        "context_after": source.prose(after),
        "translate": [
            {"id": group[0].id, source.prompt.key: _marked(group, source)} for group in groups
        ],
    }
    return BatchRequest(
        tuple(tuple(cue.id for cue in group) for group in groups),
        (
            {"role": "system", "content": _system_prompt(glossary, lang, source)},
            {"role": "user", "content": json.dumps(body, ensure_ascii=False)},
        ),
    )


def _reply_entries(text: str, key: str) -> list[object]:
    doc = parse_json_reply(text)
    if isinstance(doc, dict):
        doc = cast("dict[str, object]", doc).get("translations")
    if not isinstance(doc, list):
        raise ReplyError(f'the reply must be {{"translations": [{{"id": n, "{key}": "..."}}]}}')
    return cast("list[object]", doc)


def _clean(
    lang: Language,
    zh: str,
    en: str,
    source: SourceLanguage,
    glossary: Sequence[GlossaryEntry] = (),
) -> str:
    zh = source.clean(lang.clean(lang.terms_from(source.code, zh), en))
    if source.mends_glossary:
        for entry in glossary:
            if entry.zh:
                zh = zh.replace(entry.term, entry.zh)
    lines = (line.strip() for line in zh.replace("\r", "\n").split("\n"))
    return "\n".join(line for line in lines if line)


def _check_text(lang: Language, cue_id: int, zh: str, en: str, source: SourceLanguage) -> None:
    if not zh:
        raise ReplyError(f"cue {cue_id} has an empty translation of {_quoted(en)}")
    if source.rejects_bare_punctuation and is_bare_punctuation(zh) and not is_bare_punctuation(en):
        raise ReplyError(
            f"cue {cue_id} has only punctuation; translate its own words {_quoted(en)}"
        )
    if problem := lang.problem(zh, en) or source.problem(zh):
        raise ReplyError(f"cue {cue_id} {problem}")
    density = source.density or lang.density
    if len(zh) > density.max_per_en_char * len(en) + density.slack:
        raise ReplyError(
            f"cue {cue_id} is far longer than its {source.name}; translate only that cue"
        )
    if len(en) > _LONG_EN_CHARS and len(zh) < density.min_per_en_char * len(en):
        raise ReplyError(f"cue {cue_id} is far shorter than its {source.name}; translate all of it")


def _check_glossary(
    cue_id: int, zh: str, en: str, glossary: Sequence[GlossaryEntry], lang: Language
) -> None:
    for entry in glossary:
        if entry.zh:
            continue
        term = re.escape(entry.term)
        if re.search(
            rf"(?<![A-Za-z0-9]){term}(?![A-Za-z0-9])", en, re.IGNORECASE
        ) and not lang.keeps(entry.term, zh):
            raise ReplyError(
                f"cue {cue_id} must keep {_quoted(entry.term)} in its original English spelling, "
                f"as in {_quoted(en)}"
            )


def _split_at_markers(
    unit_id: int,
    zh: str,
    cue_ids: tuple[int, ...],
    english: Mapping[int, str],
    lang: Language,
    source: SourceLanguage,
    glossary: Sequence[GlossaryEntry],
) -> dict[int, str]:
    if len(cue_ids) == 1:
        text = _MARKER.sub("", zh)
        return {cue_ids[0]: _clean(lang, text, english[cue_ids[0]], source, glossary)}
    zh = lang.terms_from(source.code, zh)
    marks = list(_MARKER.finditer(zh))
    found = [int(m.group(1)) for m in marks]
    if found != list(cue_ids):
        wanted = " ".join(map(_mark, cue_ids))
        lost = "".join(
            f" {_mark(i)} is missing, and the {source.name} after it is {_quoted(english[i])}."
            for i in cue_ids
            if i not in found
        )
        raise ReplyError(
            f"entry {unit_id} must contain the markers {wanted} once each, in that order, "
            f"but contains {' '.join(map(_mark, found)) or 'none'}.{lost}"
        )
    if zh[: marks[0].start()].strip():
        raise ReplyError(f"entry {unit_id} has text before {_mark(cue_ids[0])}")
    ends = [m.start() for m in marks[1:]] + [len(zh)]
    return {
        cue_id: _clean(lang, zh[mark.end() : end], english[cue_id], source, glossary)
        for cue_id, mark, end in zip(cue_ids, marks, ends, strict=True)
    }


def parse_reply(
    text: str,
    request: BatchRequest,
    cues: Sequence[Cue],
    glossary: Sequence[GlossaryEntry] = (),
    lang: Language = DEFAULT,
    source: SourceLanguage = ENGLISH_SOURCE,
) -> dict[int, str]:
    """Return one cleaned translation for each cue of the request, or raise `ReplyError`.

    A glossary term kept in English must appear in the `zh` of each cue whose English has it."""
    wanted = set(request.ids)
    wanted_cues = {cue_id for unit in request.units for cue_id in unit}
    english = {cue.id: cue.src for cue in cues if cue.id in wanted_cues}
    found: dict[int, str] = {}
    extra: list[int] = []
    duplicate: list[int] = []
    for position, item in enumerate(_reply_entries(text, lang.prompt.key)):
        if not isinstance(item, dict):
            raise ReplyError(f"entry {position} is not an object")
        entry = cast("dict[str, object]", item)
        key = lang.prompt.key
        cue_id, zh = entry.get("id"), entry.get(key)
        if type(cue_id) is not int or not isinstance(zh, str):
            raise ReplyError(f'entry {position} must have an integer "id" and a string "{key}"')
        if cue_id not in wanted:
            extra.append(cue_id)
        elif cue_id in found:
            duplicate.append(cue_id)
        else:
            found[cue_id] = zh
    missing = [cue_id for cue_id in request.ids if cue_id not in found]
    problems = [
        f"{name} ids {ids}"
        for name, ids in (("missing", missing), ("unexpected", extra), ("duplicate", duplicate))
        if ids
    ]
    if problems:
        raise ReplyError(f"expected {len(request.ids)} entries; " + ", ".join(problems))
    cleaned: dict[int, str] = {}
    for unit in request.units:
        cleaned.update(
            _split_at_markers(unit[0], found[unit[0]], unit, english, lang, source, glossary)
        )
    for cue_id, zh in cleaned.items():
        _check_text(lang, cue_id, zh, english[cue_id], source)
        _check_glossary(cue_id, zh, english[cue_id], glossary, lang)
    return cleaned


_CLAUSE_BREAK = re.compile(r"[，、；：,;]")
_SENTENCE_MARKS = "。！？…!?."


def settle_bare_punctuation(cues: Sequence[Cue], source: SourceLanguage) -> list[Cue]:
    """Give a cue whose translation is only punctuation the last clause of the cue before it.

    The model puts the whole sentence in the first cue of a split sentence and leaves a bare 「。」
    for the next. The text of the cue before is cut at its last clause break, and the part after
    the break goes in front of the punctuation. Timestamps and ids never change. A cue that has no
    cue before it, or one whose neighbour has no break to cut at, keeps what it has."""
    settled = list(cues)
    for index in range(1, len(settled)):
        cue, before = settled[index], settled[index - 1]
        if not source.of(cue.lang).rejects_bare_punctuation or before.lang != cue.lang:
            continue
        if not cue.zh or not is_bare_punctuation(cue.zh) or is_bare_punctuation(cue.src):
            continue
        breaks = [m.end() for m in _CLAUSE_BREAK.finditer(before.zh)]
        cut = next((at for at in reversed(breaks) if not is_bare_punctuation(before.zh[at:])), None)
        if cut is None or not before.zh[:cut].strip():
            continue
        log.warning("cue %d is only punctuation; took the end of cue %d", cue.id, before.id)
        settled[index - 1] = replace(before, zh=before.zh[:cut].rstrip())
        tail = before.zh[cut:].lstrip()
        ended = tail[-1] in _SENTENCE_MARKS and set(cue.zh) <= set(_SENTENCE_MARKS)
        settled[index] = replace(cue, zh=tail if ended else tail + cue.zh)
    return settled


def resume_from(cues: Sequence[Cue], previous: Sequence[Cue]) -> list[Cue]:
    """Carry a translation over only when the cue is otherwise identical to the one translated."""
    done = {cue.id: cue for cue in previous if cue.zh}
    return [
        replace(cue, zh=old.zh)
        if (old := done.get(cue.id)) and replace(old, zh="") == replace(cue, zh="")
        else cue
        for cue in cues
    ]


class _Run:
    def __init__(
        self,
        cues: Sequence[Cue],
        chat: ChatFn,
        glossary: Sequence[GlossaryEntry],
        *,
        context: int,
        max_retries: int,
        checkpoint: Callable[[list[Cue]], None] | None,
        on_progress: Callable[[Progress], None] | None,
        sleep: Callable[[float], None],
        keep_english: bool,
        lang: Language,
        source: SourceLanguage,
    ) -> None:
        self.keep_english = keep_english
        self.lang = lang
        self.source = source
        self.cues = list(cues)
        self.chat = chat
        self.glossary = glossary
        self.context = context
        self.max_retries = max_retries
        self.checkpoint = checkpoint
        self.on_progress = on_progress
        self.sleep = sleep

    def source_of(self, batch: Batch) -> SourceLanguage:
        """The language the cues of `batch` were spoken in. A batch never holds two."""
        return self.source.of(self.cues[batch.start].lang)

    def translate(self, batch: Batch) -> None:
        source = self.source_of(batch)
        request = build_request(self.cues, batch, self.glossary, self.context, self.lang, source)
        started = time.monotonic()
        first, last = self.cues[batch.start].id, self.cues[batch.stop - 1].id
        try:
            translations, attempts = ask(
                self.chat,
                request.messages,
                lambda text: parse_reply(
                    text, request, self.cues, self.glossary, self.lang, source
                ),
                reprompt=lambda reason: (
                    f"That reply was rejected: {reason}. Reply again with the "
                    f'complete JSON for all {len(request.ids)} entries in "translate".'
                ),
                label=f"cues {first}-{last}",
                retries=self.max_retries,
                sleep=self.sleep,
            )
        except RepliesRejected as exc:
            if len(batch) == 1 and self.keep_english:
                self.keep_english_cue(batch, exc, started)
                return
            if len(batch) == 1:
                raise TranslationError(
                    f"cue {first} could not be translated after {exc.attempts} attempts: "
                    f"{exc.reason}"
                ) from exc
            log.warning(
                "cues %d-%d failed %d attempts; splitting the batch", first, last, exc.attempts
            )
            for half in batch.halves():
                self.translate(half)
            return
        self.store(batch, translations, started, attempts)

    def keep_english_cue(self, batch: Batch, exc: RepliesRejected, started: float) -> None:
        """A cue that failed every attempt keeps its English. The glossary check is never relaxed:
        a language that spells a term differently says so in `Language.spellings`."""
        cue = self.cues[batch.start]
        if (repaired := self.repaired(batch, exc.reply)) is not None:
            log.warning("cue %d: kept the last reply after %s", cue.id, exc.reason)
            self.store(batch, repaired, started, exc.attempts)
            return
        log.warning(
            "cue %d could not be translated after %d attempts (%s); keeping its %s",
            cue.id,
            exc.attempts,
            exc.reason,
            self.source_of(batch).name,
        )
        self.store(batch, {cue.id: cue.src}, started, 0)

    def repaired(self, batch: Batch, reply: str) -> dict[int, str] | None:
        """The last reply of a cue that failed every attempt, after the source language's repair
        (a name left in kana is written in Latin letters), when it then passes the checks of the
        script. Its length is not checked: a translation that runs long serves a reader better
        than the Japanese does. A reply that is only punctuation passes here and is settled with its
        neighbour once every cue is translated (`settle_bare_punctuation`). English has no repair,
        so it keeps its English."""
        source = self.source_of(batch)
        if source.repair is None:
            return None
        repair = source.repair

        def clean(text: str) -> str:
            return repair(source.clean(text))

        mended = replace(
            source,
            clean=clean,
            density=Density(1000.0, 10_000, 0.0),
            rejects_bare_punctuation=False,
        )
        request = build_request(self.cues, batch, self.glossary, self.context, self.lang, mended)
        try:
            return parse_reply(reply, request, self.cues, self.glossary, self.lang, mended)
        except ReplyError:
            return None

    def store(
        self, batch: Batch, translations: dict[int, str], started: float, attempts: int
    ) -> None:
        for index in range(batch.start, batch.stop):
            cue = self.cues[index]
            self.cues[index] = replace(cue, zh=translations[cue.id])
        if self.checkpoint:
            self.checkpoint(list(self.cues))
        elapsed = time.monotonic() - started
        log.info(
            "cues %d-%d translated in %.1f s",
            self.cues[batch.start].id,
            self.cues[batch.stop - 1].id,
            elapsed,
        )
        if self.on_progress:
            done = sum(1 for cue in self.cues if cue.zh)
            self.on_progress(Progress(done, len(self.cues), len(batch), elapsed, attempts))


def run(
    cues: Sequence[Cue],
    chat: ChatFn,
    glossary: Sequence[GlossaryEntry] = (),
    *,
    batch_size: int = BATCH_SIZE,
    context: int = CONTEXT_CUES,
    max_retries: int = MAX_RETRIES,
    checkpoint: Callable[[list[Cue]], None] | None = None,
    on_progress: Callable[[Progress], None] | None = None,
    sleep: Callable[[float], None] = time.sleep,
    keep_english: bool = False,
    lang: Language = DEFAULT,
    source: SourceLanguage = ENGLISH_SOURCE,
) -> list[Cue]:
    """Translate every cue whose `zh` is empty into `lang` and return all cues, timing and `en`
    unchanged. The `zh` field holds the translation whatever the language is.

    Cues are sent as whole sentences, each cue marked inside its sentence, and the translation is
    cut back into cues at the markers. A batch whose replies fail `max_retries` retries is split in
    half, and a lone sentence is split between cues. A single cue that still fails raises
    `TranslationError`, unless `keep_english` is set: then that cue keeps its English as its `zh`
    and the run goes on. A server that fails every attempt raises its `LlmError` at once, because
    splitting cannot help. Cues stored before a failure stay stored: `checkpoint` has already
    seen them.
    """
    job = _Run(
        cues,
        chat,
        glossary,
        context=context,
        max_retries=max_retries,
        checkpoint=checkpoint,
        on_progress=on_progress,
        sleep=sleep,
        keep_english=keep_english,
        lang=lang,
        source=source,
    )
    for batch in plan_batches(job.cues, batch_size, source=source):
        job.translate(batch)
    return settle_bare_punctuation(job.cues, source)


def translate_file(
    source: Path,
    dest: Path,
    chat: ChatFn,
    glossary: Sequence[GlossaryEntry] = (),
    *,
    batch_size: int = BATCH_SIZE,
    on_progress: Callable[[Progress], None] | None = None,
    keep_english: bool = False,
    lang: Language = DEFAULT,
    source_lang: SourceLanguage = ENGLISH_SOURCE,
) -> list[Cue]:
    """Translate `source` (a subs json) into `dest`, saving `dest` after every batch.

    Running again after a crash or a failure reads `dest` and asks only for the cues it lacks.
    """
    cues = parse_subs(read_text_file(source))
    if dest.exists():
        try:
            cues = resume_from(cues, parse_subs(read_text_file(dest)))
        except FormatError as exc:
            raise FormatError(f"{dest}: cannot resume from this file ({exc})") from exc

    def save(state: list[Cue]) -> None:
        write_text_file(dest, render_subs(state))

    result = run(
        cues,
        chat,
        glossary,
        batch_size=batch_size,
        checkpoint=save,
        on_progress=on_progress,
        keep_english=keep_english,
        lang=lang,
        source=source_lang,
    )
    save(result)
    return result
