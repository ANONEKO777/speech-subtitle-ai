from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field, replace
from enum import StrEnum
from types import MappingProxyType

from backend.core.languages import DEFAULT_CODE

SCHEMA_VERSION = 1


class FormatError(ValueError):
    """A subtitle or project file could not be parsed, or a value cannot be written to one."""


def _check_ms(name: str, value: int) -> None:
    if type(value) is not int or value < 0:
        raise ValueError(f"{name} must be a non-negative int of milliseconds, got {value!r}")


def _check_span(start_ms: int, end_ms: int) -> None:
    _check_ms("start_ms", start_ms)
    _check_ms("end_ms", end_ms)
    if end_ms < start_ms:
        raise ValueError(f"end_ms {end_ms} is before start_ms {start_ms}")


def _check_text(name: str, text: str) -> None:
    if "\r" in text:
        raise ValueError(f"{name} contains a carriage return: {text!r}")
    if text and any(line != line.strip() or not line for line in text.split("\n")):
        raise ValueError(
            f"{name} has a blank line or a line with leading/trailing whitespace: {text!r}"
        )
    try:
        text.encode("utf-8")
    except UnicodeEncodeError as exc:
        raise ValueError(f"{name} contains a lone surrogate at index {exc.start}") from exc


@dataclass(frozen=True, slots=True)
class Word:
    text: str
    start_ms: int
    end_ms: int

    def __post_init__(self) -> None:
        _check_span(self.start_ms, self.end_ms)


@dataclass(frozen=True, slots=True)
class Segment:
    """One ASR result. `words` is None when the engine gives no word timestamps."""

    text: str
    start_ms: int
    end_ms: int
    words: tuple[Word, ...] | None = None

    def __post_init__(self) -> None:
        _check_span(self.start_ms, self.end_ms)


@dataclass(frozen=True, slots=True)
class Cue:
    """One subtitle entry. `zh` is empty until the cue is translated."""

    id: int
    start_ms: int
    end_ms: int
    en: str
    zh: str = ""

    def __post_init__(self) -> None:
        if type(self.id) is not int or self.id < 0:
            raise ValueError(f"id must be a non-negative int, got {self.id!r}")
        _check_span(self.start_ms, self.end_ms)
        _check_text("en", self.en)
        _check_text("zh", self.zh)


class Step(StrEnum):
    AUDIO = "audio"
    VAD = "vad"
    ASR = "asr"
    SEGMENT = "segment"
    TRANSLATE = "translate"
    EXPORT = "export"
    SUMMARIZE = "summarize"


LANG_STEPS = (Step.TRANSLATE, Step.EXPORT, Step.SUMMARIZE)
"""The steps whose outputs belong to one target language. Every other step is the same for all."""


class StepStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"


@dataclass(frozen=True, slots=True)
class StepState:
    status: StepStatus = StepStatus.PENDING
    updated_at_ms: int | None = None
    error: str | None = None
    key: str | None = None
    """The cache key of the run this state describes. `done` means the outputs match it."""

    def __post_init__(self) -> None:
        if self.updated_at_ms is not None:
            _check_ms("updated_at_ms", self.updated_at_ms)
        if (self.error is not None) != (self.status is StepStatus.FAILED):
            raise ValueError("error is set if and only if status is failed")


Migration = Callable[[dict[str, object]], dict[str, object]]

_MIGRATIONS: dict[int, Migration] = {}


def _lang_states(states: Mapping[Step, StepState]) -> Mapping[Step, StepState]:
    return MappingProxyType({step: states.get(step, StepState()) for step in LANG_STEPS})


@dataclass(frozen=True, slots=True)
class Project:
    """`steps` holds the state of every step for the language the project was last worked on,
    `active_lang`. The states of the language steps of every other language wait in `parked`, so
    one project keeps a translation per language and a change of language loses none."""

    video_path: str
    steps: Mapping[Step, StepState] = field(default_factory=dict[Step, StepState])
    schema_version: int = SCHEMA_VERSION
    active_lang: str = DEFAULT_CODE
    parked: Mapping[str, Mapping[Step, StepState]] = field(
        default_factory=dict[str, Mapping[Step, StepState]]
    )

    def __post_init__(self) -> None:
        if self.schema_version != SCHEMA_VERSION:
            raise ValueError(
                f"schema_version {self.schema_version} is not the current {SCHEMA_VERSION}; "
                "run Project.migrate on the raw data first"
            )
        if not self.video_path:
            raise ValueError("video_path is empty")
        steps: dict[Step, StepState] = {step: self.steps.get(step, StepState()) for step in Step}
        object.__setattr__(self, "steps", MappingProxyType(steps))
        parked = {
            lang: _lang_states(states)
            for lang, states in self.parked.items()
            if lang != self.active_lang
        }
        object.__setattr__(self, "parked", MappingProxyType(parked))

    def with_step(self, step: Step, state: StepState) -> Project:
        return replace(self, steps={**self.steps, step: state})

    def state(self, step: Step, lang: str) -> StepState:
        """The state of `step` as it stands for the target language `lang`."""
        if step not in LANG_STEPS or lang == self.active_lang:
            return self.steps[step]
        return self.parked.get(lang, _lang_states({}))[step]

    def activate(self, lang: str) -> Project:
        """Make `lang` the active language, parking the language steps of the one it replaces."""
        if lang == self.active_lang:
            return self
        parked = {
            **self.parked,
            self.active_lang: _lang_states(self.steps),
        }
        incoming = parked.pop(lang, _lang_states({}))
        steps = {**self.steps, **incoming}
        return replace(self, steps=steps, active_lang=lang, parked=parked)

    def languages(self) -> dict[str, Mapping[Step, StepState]]:
        """The language steps of every language that has any state, the active one first."""
        found = {self.active_lang: _lang_states(self.steps)}
        found.update(self.parked)
        return found

    @staticmethod
    def migrate(raw: Mapping[str, object]) -> dict[str, object]:
        version = raw.get("schema_version")
        if version is None:
            raise FormatError("project has no schema_version")
        if type(version) is not int or version < 1:
            raise FormatError(f"schema_version must be a positive int, got {version!r}")
        if version > SCHEMA_VERSION:
            raise FormatError(
                f"project schema_version {version} is newer than supported {SCHEMA_VERSION}"
            )
        data = dict(raw)
        while version < SCHEMA_VERSION:
            data = _MIGRATIONS[version](data)
            version += 1
            data["schema_version"] = version
        return data
