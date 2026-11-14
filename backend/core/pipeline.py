"""The cached, resumable pipeline from a video to subtitles and a summary.

One table (`STEPS`) says, for each step, which steps it reads, which files it writes and what its
cache key is made of. `run` walks the table. A step is skipped when `project.json` says it is done
under the same key and its files exist. Keys chain, so a change reaches exactly the steps that
read from it. Everything that starts a process or touches the network is behind `Ports`.
"""

from __future__ import annotations

import hashlib
import json
import logging
import threading
import time
from collections.abc import Callable, Sequence
from contextlib import AbstractContextManager, ExitStack
from dataclasses import asdict, dataclass, field, replace
from enum import StrEnum
from functools import cache
from importlib.resources import files as package_files
from pathlib import Path

from backend.core import cue_edits, summarize, translate
from backend.core.artifacts import parse_chunks, parse_words, render_chunks, render_words
from backend.core.ja_terms import SOURCE_FIXES
from backend.core.languages import DEFAULT_CODE, ENGLISH, Language
from backend.core.languages import get as get_language
from backend.core.model import (
    DEFAULT_SOURCE,
    Cue,
    Project,
    Segment,
    Step,
    StepState,
    StepStatus,
    Word,
)
from backend.core.segmenter import CueRules, to_cues, to_mixed_cues
from backend.core.source_langs import SourceLanguage, get_source
from backend.core.subtitle_io import (
    parse_project,
    parse_subs,
    read_text_file,
    render_ass,
    render_project,
    render_srt,
    render_subs,
    render_vtt,
    write_text_file,
)
from backend.core.translate import BATCH_SIZE, DEFAULT_GLOSSARY, GlossaryEntry
from backend.core.vad import Chunk, VadParams
from backend.llm.ask import ChatFn
from backend.llm.client import Message

log = logging.getLogger(__name__)

PROJECT_JSON = "project.json"
MIXED_CUT = "pauses-300-guard-tail-1"
UNSPACED_CUT = "numbers-whole-1"
"""How cues of an unspaced language (Japanese) are cut. A talk cut by an older rule is cut again."""
JAPANESE_UNITS = "finals-3"
"""How the cues of a Japanese talk are grouped into sentences for translation."""


class File(StrEnum):
    """The file names in a project folder that depend on neither language. The others are
    `Language.files` and `SourceLanguage.files`."""

    AUDIO = "audio.wav"
    CHUNKS = "chunks.json"
    WORDS = "segments.json"
    SUMMARY_EN = summarize.ENGLISH_SUMMARY_FILE
    AUDIO_STAMP = "audio.wav.src.json"


class PipelineError(Exception):
    """A step failed. `step` is the one that raised, and `__cause__` is its error."""

    def __init__(self, step: Step, message: str) -> None:
        super().__init__(f"{step.value}: {message}")
        self.step = step


class Cancelled(Exception):
    """The cancel event was set. The running step is recorded as failed and a rerun resumes it."""


class NoSpeechError(Exception):
    """The ASR engine returned no words."""


@dataclass(frozen=True, slots=True)
class Settings:
    """Everything that decides what the outputs are. Identities are strings that change when the
    model or runtime does. Nothing here is a path, so every field can be part of a cache key."""

    asr_engine: str
    asr_identity: str
    vad_identity: str
    llm_identity: str
    source_lang: str = DEFAULT_SOURCE
    vad: VadParams = field(default_factory=VadParams)
    cues: CueRules | None = None
    """The cue rules. None takes the source language's own."""
    glossary: tuple[GlossaryEntry, ...] = DEFAULT_GLOSSARY
    target_lang: str = DEFAULT_CODE
    summary_en: bool = False
    batch_size: int = BATCH_SIZE

    def __post_init__(self) -> None:
        source = get_source(self.source_lang)
        if not source.supports(self.lang):
            allowed = ", ".join(sorted(source.targets or ()))
            raise ValueError(
                f"{source.name} speech can be translated into {allowed} for now, "
                f"not {self.target_lang}"
            )

    @property
    def lang(self) -> Language:
        return get_language(self.target_lang)

    @property
    def source(self) -> SourceLanguage:
        return get_source(self.source_lang)

    @property
    def cue_rules(self) -> CueRules:
        return self.cues or self.source.cues

    def rules_of(self, lang: str) -> CueRules:
        """The cue rules for cues spoken in `lang`."""
        return self.cues or self.source.of(lang).cues

    @property
    def summary_langs(self) -> tuple[str, ...]:
        """The summaries to write: one in the target language, and one in English when asked."""
        return (self.target_lang, ENGLISH) if self.summary_en else (self.target_lang,)


@dataclass(frozen=True, slots=True)
class LlmSession:
    """The chat functions of one open LLM. Summary replies are capped, translations are not."""

    translate: ChatFn
    summarize: ChatFn


ProgressCb = Callable[[float], None]


@dataclass(frozen=True, slots=True)
class Ports:
    """What touches a process, the GPU or the network. Tests replace these."""

    extract_audio: Callable[[Path, Path, threading.Event], None]
    split_vad: Callable[[Path], list[Chunk]]
    transcribe: Callable[[Path, Sequence[Chunk], ProgressCb, threading.Event], list[Word]]
    open_llm: Callable[[threading.Event], AbstractContextManager[LlmSession]]


@dataclass(frozen=True, slots=True)
class Progress:
    step: Step
    fraction: float
    message: str = ""


@dataclass(frozen=True, slots=True)
class StepReport:
    step: Step
    ran: bool
    seconds: float


@dataclass(frozen=True, slots=True)
class RunReport:
    steps: tuple[StepReport, ...]
    total_s: float
    edits_kept: int = 0
    edits_unmatched: int = 0
    summary_degraded: bool = False

    @property
    def ran(self) -> tuple[Step, ...]:
        return tuple(r.step for r in self.steps if r.ran)

    @property
    def overhead_s(self) -> float:
        """Total time minus the time inside step bodies."""
        return self.total_s - sum(r.seconds for r in self.steps)

    def describe(self) -> str:
        rows = [
            f"{r.step.value:<10} {'ran' if r.ran else 'cached':<7} {r.seconds:8.1f} s"
            for r in self.steps
        ]
        rows.append(f"{'overhead':<10} {'':<7} {self.overhead_s:8.1f} s")
        rows.append(f"{'total':<10} {'':<7} {self.total_s:8.1f} s")
        if self.edits_kept or self.edits_unmatched:
            rows.append(
                f"kept {self.edits_kept} edited cues, {self.edits_unmatched} edits did not fit"
            )
        if self.summary_degraded:
            rows.append("summary degraded: it failed the language check and was kept anyway")
        return "\n".join(rows)


@dataclass(frozen=True, slots=True)
class _Ctx:
    """What a step body gets."""

    step: Step
    dir: Path
    video: Path
    settings: Settings
    ports: Ports
    cancel: threading.Event
    report: Callable[[Step, float, str], None]
    llm: Callable[[], LlmSession]
    notes: dict[str, int]

    def path(self, name: str) -> Path:
        return self.dir / name

    def progress(self, fraction: float, message: str = "") -> None:
        if self.cancel.is_set():
            raise Cancelled(f"{self.step.value} was cancelled")
        self.report(self.step, min(max(fraction, 0.0), 0.99), message)


@dataclass(frozen=True, slots=True)
class _StepSpec:
    step: Step
    version: int
    needs: tuple[Step, ...]
    outputs: Callable[[Settings], tuple[str, ...]]
    key_parts: Callable[[Settings, str], object]
    body: Callable[[_Ctx], None]
    partials: Callable[[Settings], tuple[str, ...]] = lambda s: ()


def _read(ctx: _Ctx, name: str) -> str:
    return read_text_file(ctx.path(name))


def _audio(ctx: _Ctx) -> None:
    ctx.ports.extract_audio(ctx.video, ctx.path(File.AUDIO), ctx.cancel)


def _vad(ctx: _Ctx) -> None:
    chunks = ctx.ports.split_vad(ctx.path(File.AUDIO))
    write_text_file(ctx.path(File.CHUNKS), render_chunks(chunks))


def _asr(ctx: _Ctx) -> None:
    chunks = parse_chunks(_read(ctx, File.CHUNKS))
    words = ctx.ports.transcribe(ctx.path(File.AUDIO), chunks, ctx.progress, ctx.cancel)
    if not words:
        raise NoSpeechError("the ASR engine found no speech in this audio")
    write_text_file(ctx.path(File.WORDS), render_words(ctx.settings.asr_engine, words))


def _segment(ctx: _Ctx) -> None:
    words = parse_words(_read(ctx, File.WORDS))
    text = " ".join(w.text for w in words)
    segment = Segment(text, words[0].start_ms, words[-1].end_ms, tuple(words))
    settings = ctx.settings
    if settings.source.mixed:
        rules = {member.code: settings.rules_of(member.code) for member in settings.source.members}
        cues = to_mixed_cues([segment], rules)
    else:
        cues = to_cues([segment], settings.cue_rules, settings.source_lang)
    write_text_file(ctx.path(ctx.settings.source.files.subs), render_subs(cues))


def _translate(ctx: _Ctx) -> None:
    translate.translate_file(
        ctx.path(ctx.settings.source.files.subs),
        ctx.path(ctx.settings.lang.files.subs),
        ctx.llm().translate,
        ctx.settings.glossary,
        batch_size=ctx.settings.batch_size,
        on_progress=lambda p: ctx.progress(p.done / max(p.total, 1)),
        keep_english=True,
        lang=ctx.settings.lang,
        source_lang=ctx.settings.source,
    )
    kept = cue_edits.reapply(ctx.dir, ctx.settings.lang)
    ctx.notes["edits_kept"] = kept.kept
    ctx.notes["edits_unmatched"] = kept.unmatched


def write_exports(
    folder: Path, cues: Sequence[Cue], lang: Language, source: SourceLanguage
) -> None:
    files = lang.files
    write_text_file(folder / source.files.srt, render_srt(cues, "en"))
    write_text_file(folder / files.srt, render_srt(cues, "zh"))
    write_text_file(folder / files.ass, render_ass(cues, lang.wrap))
    write_text_file(folder / files.vtt, render_vtt(cues, "bilingual"))


def _export(ctx: _Ctx) -> None:
    lang = ctx.settings.lang
    write_exports(ctx.dir, parse_subs(_read(ctx, lang.files.subs)), lang, ctx.settings.source)


def _summarize(ctx: _Ctx) -> None:
    summarize.summarize_file(
        ctx.path(ctx.settings.source.files.subs),
        ctx.path(ctx.settings.lang.files.summary),
        ctx.llm().summarize,
        ctx.settings.summary_langs,
        ctx.settings.glossary,
        source_lang=ctx.settings.source,
        on_progress=lambda p: ctx.progress(p.done / max(p.total, 1), p.stage),
        on_degraded=lambda lang: ctx.notes.update(summary_degraded=1),
    )


@cache
def _prompt_digest(*names: str) -> str:
    digest = hashlib.blake2b(digest_size=8)
    for name in names:
        digest.update((package_files("backend.core") / "prompts" / name).read_bytes())
    return digest.hexdigest()


@cache
def _translate_prompt_digest(code: str, source: str) -> str:
    """The digest of the translation prompt for talks in `source` as `code` sees it, glossary left
    unfilled."""
    language = get_language(code)
    chosen = get_source(source)
    text = "".join(
        translate.system_prompt_template(language, member)
        + (repr(member.terms) if member.terms else "")
        + (repr(SOURCE_FIXES) if member.fix_from_source else "")
        for member in chosen.members or (chosen,)
    )
    return hashlib.blake2b(text.encode("utf-8"), digest_size=8).hexdigest()


def _lang_key(settings: Settings) -> dict[str, str]:
    """The target language, for the cache keys that depend on it. The default language adds
    nothing, so a project made before languages existed stays cached."""
    return {} if settings.lang.is_default else {"lang": settings.target_lang}


def _source_key(settings: Settings) -> dict[str, str]:
    """The source language, for the cache keys that depend on it. English adds nothing, so a
    project made before there were other languages stays cached."""
    return {} if settings.source_lang == DEFAULT_SOURCE else {"source": settings.source_lang}


def _rules_key(rules: CueRules) -> dict[str, object]:
    """The cue rules for a cache key. The two fields that only unspaced text uses are left out
    while they are at their defaults, so the key of an English project is what it was."""
    key = asdict(rules)
    if not rules.unspaced:
        del key["unspaced"]
    else:
        key["cut"] = UNSPACED_CUT
    if rules.max_cps == CueRules().max_cps:
        del key["max_cps"]
    return key


def _units_key(settings: Settings) -> dict[str, str]:
    """How sentences are grouped for translation. English adds nothing, so its key is unchanged."""
    return {} if settings.source_lang == DEFAULT_SOURCE else {"units": JAPANESE_UNITS}


def _cut_key(settings: Settings) -> dict[str, str]:
    """A talk in two languages is cut at its pauses and recognised in passes (`engines.mixed`).
    The label changes when those rules do, so the chunks and the words are made again."""
    return {"cut": MIXED_CUT} if settings.source.mixed else {}


def _segment_rules_key(settings: Settings) -> object:
    if not settings.source.mixed:
        return _rules_key(settings.cue_rules)
    return {m.code: _rules_key(settings.rules_of(m.code)) for m in settings.source.members}


def _glossary(settings: Settings) -> list[dict[str, str]]:
    return [asdict(entry) for entry in settings.glossary]


def _summary_files(settings: Settings) -> tuple[str, ...]:
    return tuple(
        File.SUMMARY_EN.value if lang == ENGLISH else settings.lang.files.summary
        for lang in settings.summary_langs
    )


def _summary_partials(settings: Settings) -> tuple[str, ...]:
    files = settings.lang.files
    return (files.summary, File.SUMMARY_EN.value, files.summary_parts)


STEPS: tuple[_StepSpec, ...] = (
    _StepSpec(
        Step.AUDIO,
        1,
        (),
        lambda s: (File.AUDIO.value,),
        lambda s, video: {"video": video},
        _audio,
        partials=lambda s: (File.AUDIO_STAMP.value,),
    ),
    _StepSpec(
        Step.VAD,
        1,
        (Step.AUDIO,),
        lambda s: (File.CHUNKS.value,),
        lambda s, video: {"vad": s.vad_identity, "params": asdict(s.vad), **_cut_key(s)},
        _vad,
    ),
    _StepSpec(
        Step.ASR,
        1,
        (Step.VAD,),
        lambda s: (File.WORDS.value,),
        lambda s, video: {
            "engine": s.asr_engine,
            "model": s.asr_identity,
            "lang": s.source_lang,
            **_cut_key(s),
        },
        _asr,
    ),
    _StepSpec(
        Step.SEGMENT,
        1,
        (Step.ASR,),
        lambda s: (s.source.files.subs,),
        lambda s, video: {"rules": _segment_rules_key(s)},
        _segment,
    ),
    _StepSpec(
        Step.TRANSLATE,
        2,
        (Step.SEGMENT,),
        lambda s: (s.lang.files.subs,),
        lambda s, video: {
            "llm": s.llm_identity,
            "glossary": _glossary(s),
            "batch": s.batch_size,
            "prompt": _translate_prompt_digest(s.target_lang, s.source_lang),
            **_units_key(s),
            **_source_key(s),
            **_lang_key(s),
        },
        _translate,
    ),
    _StepSpec(
        Step.EXPORT,
        1,
        (Step.TRANSLATE,),
        lambda s: (s.source.files.srt, s.lang.files.srt, s.lang.files.ass, s.lang.files.vtt),
        lambda s, video: _lang_key(s),
        _export,
    ),
    _StepSpec(
        Step.SUMMARIZE,
        1,
        (Step.SEGMENT,),
        _summary_files,
        lambda s, video: {
            "llm": s.llm_identity,
            "langs": list(s.summary_langs),
            "glossary": _glossary(s),
            "prompt": _prompt_digest(s.source.summary_map, "summarize_reduce.md"),
            **_source_key(s),
            "map_text": hashlib.blake2b(
                "|".join(summarize.MAP_FRAMING).encode("utf-8"), digest_size=8
            ).hexdigest(),
        },
        _summarize,
        partials=_summary_partials,
    ),
)


def _check_table() -> None:
    assert [spec.step for spec in STEPS] == list(Step), "STEPS must list every Step in order"
    seen: set[Step] = set()
    for spec in STEPS:
        assert set(spec.needs) <= seen, f"{spec.step} needs a step that comes later"
        seen.add(spec.step)


_check_table()


def derive_key(spec: _StepSpec, settings: Settings, video: str, upstream: dict[Step, str]) -> str:
    """The step's cache key: its version, its own settings, and the keys of the steps it reads."""
    material = [
        spec.step.value,
        spec.version,
        spec.key_parts(settings, video),
        [upstream[need] for need in spec.needs],
    ]
    text = json.dumps(material, sort_keys=True, ensure_ascii=True, separators=(",", ":"))
    return hashlib.blake2b(text.encode("ascii"), digest_size=16).hexdigest()


def _video_fingerprint(video: Path) -> str:
    stat = video.stat()
    return f"{stat.st_size}:{stat.st_mtime_ns}"


def _now_ms() -> int:
    return time.time_ns() // 1_000_000


class _Store:
    """The only writer of `project.json`."""

    def __init__(self, folder: Path, video: Path) -> None:
        self.path = folder / PROJECT_JSON
        folder.mkdir(parents=True, exist_ok=True)
        previous = parse_project(read_text_file(self.path)) if self.path.is_file() else None
        video_path = str(video.absolute())
        self.project = replace(previous, video_path=video_path) if previous else Project(video_path)

    def activate(self, lang: str) -> None:
        """Make `lang` the language this run works on, keeping the other languages' states."""
        if lang != self.project.active_lang:
            self.project = self.project.activate(lang)
            write_text_file(self.path, render_project(self.project))

    def use_source(self, code: str) -> None:
        """Make `code` the language of the talk this run works on."""
        if code != self.project.source_lang:
            self.project = replace(self.project, source_lang=code)
            write_text_file(self.path, render_project(self.project))

    def reset(self, step: Step) -> None:
        self.project = self.project.with_step(step, StepState())
        write_text_file(self.path, render_project(self.project))

    def touch(self, step: Step) -> None:
        state = replace(self.project.steps[step], updated_at_ms=_now_ms())
        self.project = self.project.with_step(step, state)
        write_text_file(self.path, render_project(self.project))

    def mark(
        self,
        step: Step,
        status: StepStatus,
        key: str,
        error: str | None = None,
        *,
        degraded: bool = False,
    ) -> None:
        state = StepState(status, _now_ms(), error, key, degraded)
        self.project = self.project.with_step(step, state)
        write_text_file(self.path, render_project(self.project))


def _kept_for_other_languages(name: str, state: StepState, source: SourceLanguage) -> bool:
    """The source files do not depend on the target language, and a project holds one language
    after another. The source srt is rewritten by every export, so it is never deleted. The
    English summary is kept when this language has not run the step yet, because another language
    made it."""
    return name == source.files.srt or (name == File.SUMMARY_EN and state.key is None)


def _plan(
    store: _Store, folder: Path, settings: Settings, video: str
) -> tuple[dict[Step, str], dict[Step, bool]]:
    """Work out every step's key and whether it is fresh, and fix `project.json` up front.

    A step whose key changed has its files and partial files deleted and goes back to pending.
    A step that was done but reads from a step that is not fresh goes back to pending too, keeping
    its key, so no step claims to be done over inputs that are out of date. Doing this before the
    first step runs means a run that stops early still leaves an honest `project.json`."""
    keys: dict[Step, str] = {}
    fresh: dict[Step, bool] = {}
    for spec in STEPS:
        key = derive_key(spec, settings, video, keys)
        keys[spec.step] = key
        state = store.project.steps[spec.step]
        outputs = spec.outputs(settings)
        if state.key != key:
            for stale in (*outputs, *spec.partials(settings)):
                if not _kept_for_other_languages(stale, state, settings.source):
                    (folder / stale).unlink(missing_ok=True)
            if state.status is not StepStatus.PENDING or state.key is not None:
                store.reset(spec.step)
        fresh[spec.step] = (
            state.key == key
            and state.status is StepStatus.DONE
            and all((folder / name).is_file() for name in outputs)
            and all(fresh[need] for need in spec.needs)
        )
        if state.status is StepStatus.DONE and state.key == key and not fresh[spec.step]:
            store.mark(spec.step, StepStatus.PENDING, key)
    return keys, fresh


def save_edited_cues(folder: Path, cues: Sequence[Cue], lang: Language) -> None:
    """Store cues a person corrected in `lang`: its translated cue file, every export built from
    it, and the export step's time in `project.json`, where `lang` becomes the active language.
    The steps keep their keys, so a later run with the same settings skips them and the edits
    stay. The caller makes sure no run is using `folder`."""
    store = _Store(folder, Path(parse_project(read_text_file(folder / PROJECT_JSON)).video_path))
    store.activate(lang.code)
    write_text_file(folder / lang.files.subs, render_subs(cues))
    write_exports(folder, cues, lang, get_source(store.project.source_lang))
    store.touch(Step.EXPORT)


def run(
    video: Path,
    folder: Path,
    settings: Settings,
    ports: Ports,
    *,
    progress: Callable[[Progress], None] | None = None,
    cancel: threading.Event | None = None,
) -> RunReport:
    """Bring `folder` up to date for `video`. Running again with nothing changed does no work.

    A step runs when it is not done under its current key, when a file it writes is missing, or
    when a step it reads ran in this call. When the key changed, its old files, and the partial
    files a resume would trust, are deleted before the new key is recorded. A step that stops
    halfway keeps its key, so the next call resumes it. The LLM server starts only when a step
    needs it, after ASR has ended, and stops before this function returns.
    """
    started = time.perf_counter()
    stop = cancel or threading.Event()
    store = _Store(folder, video)
    fingerprint = _video_fingerprint(video)

    def report(step: Step, fraction: float, message: str) -> None:
        if progress:
            progress(Progress(step, fraction, message))

    reports: list[StepReport] = []
    summary_degraded = False
    notes: dict[str, int] = {}
    store.use_source(settings.source_lang)
    store.activate(settings.target_lang)
    keys, fresh = _plan(store, folder, settings, fingerprint)
    with ExitStack() as stack:
        opened: list[LlmSession] = []

        def llm() -> LlmSession:
            """Chat functions that open the LLM on their first call, so a step whose work is all
            cached never starts the server."""

            def lazy(pick: Callable[[LlmSession], ChatFn]) -> ChatFn:
                def chat(messages: Sequence[Message], temperature: float) -> str:
                    if not opened:
                        opened.append(stack.enter_context(ports.open_llm(stop)))
                    return pick(opened[0])(messages, temperature)

                return chat

            return LlmSession(lazy(lambda s: s.translate), lazy(lambda s: s.summarize))

        for spec in STEPS:
            key = keys[spec.step]
            if fresh[spec.step]:
                reports.append(StepReport(spec.step, False, 0.0))
                report(spec.step, 1.0, "cached")
                continue
            if stop.is_set():
                raise Cancelled("cancelled before " + spec.step.value)
            store.mark(spec.step, StepStatus.RUNNING, key)
            report(spec.step, 0.0, "")
            step_started = time.perf_counter()
            try:
                spec.body(_Ctx(spec.step, folder, video, settings, ports, stop, report, llm, notes))
            except BaseException as exc:
                cancelled = stop.is_set() or isinstance(exc, KeyboardInterrupt | Cancelled)
                store.mark(
                    spec.step,
                    StepStatus.FAILED,
                    key,
                    "cancelled" if cancelled else f"{type(exc).__name__}: {exc}",
                )
                if cancelled and isinstance(exc, Exception) and not isinstance(exc, Cancelled):
                    raise Cancelled(f"{spec.step.value} was cancelled") from exc
                if isinstance(exc, Exception) and not isinstance(exc, Cancelled):
                    raise PipelineError(spec.step, str(exc) or type(exc).__name__) from exc
                raise
            seconds = time.perf_counter() - step_started
            degraded = bool(notes.pop("summary_degraded", 0))
            store.mark(spec.step, StepStatus.DONE, key, degraded=degraded)
            summary_degraded = summary_degraded or degraded
            reports.append(StepReport(spec.step, True, seconds))
            report(spec.step, 1.0, "")
    return RunReport(
        tuple(reports),
        time.perf_counter() - started,
        notes.get("edits_kept", 0),
        notes.get("edits_unmatched", 0),
        summary_degraded,
    )
