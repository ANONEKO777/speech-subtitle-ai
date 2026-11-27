"""The backend sentences the window words in its own language.

A notice is `{code, params, message}`: a stable code, its parameters, and the complete English
sentence. The window words a code it knows from its catalog and shows `message` for one it does
not know, so a text is never blank.

A text that goes to the window can hold notices: it can be one, start with one (`OptionsError: ...`)
or quote one several times (a self-test result). So the sender keeps its English text and sends
the list of notices inside it, outermost first, in a field beside it (`error` and
`error_notices`). The window replaces each notice's `message` inside the text with its wording.

To add a sentence, add a `Template` below, raise it with `noticed`, run
`python scripts/export_notices.py`, and add `notice.<code>` to the four catalogs. The tests fail
until all of that is done.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import asdict, dataclass, field
from types import MappingProxyType
from typing import Any, Literal, Protocol, TypeVar, cast

ParamKind = Literal["text", "list", "language"]
"""`text` is shown as it is. A `list` is joined with the separator of the language that shows it.
A `language` travels as its code, and the window names it."""

ParamValue = str | list[str]


class NamedLanguage(Protocol):
    @property
    def code(self) -> str: ...
    @property
    def name(self) -> str: ...


@dataclass(frozen=True, slots=True)
class Notice:
    code: str
    params: dict[str, ParamValue] = field(default_factory=dict[str, ParamValue])
    message: str = ""


@dataclass(frozen=True, slots=True)
class Template:
    code: str
    english: str
    params: Mapping[str, ParamKind]

    def __call__(self, **given: str | Sequence[str] | NamedLanguage) -> Notice:
        """The notice for these parameters, which must be exactly the template's."""
        if given.keys() != self.params.keys():
            raise TypeError(f"{self.code} takes {sorted(self.params)}, got {sorted(given)}")
        sent: dict[str, ParamValue] = {}
        shown: dict[str, str] = {}
        for name, kind in self.params.items():
            value = given[name]
            if kind == "language":
                language = cast("NamedLanguage", value)
                sent[name], shown[name] = language.code, language.name
            elif kind == "list":
                items = list(cast("Sequence[str]", value))
                sent[name], shown[name] = items, ", ".join(items)
            else:
                sent[name] = shown[name] = str(value)
        return Notice(self.code, sent, self.english.format_map(shown))


_REGISTRY: dict[str, Template] = {}
REGISTRY: Mapping[str, Template] = MappingProxyType(_REGISTRY)


def _template(code: str, english: str, **params: ParamKind) -> Template:
    if code in _REGISTRY:
        raise ValueError(f"the notice code {code!r} is registered twice")
    made = _REGISTRY[code] = Template(code, english, MappingProxyType(params))
    return made


_SUBTITLE_FILES_FINE = "Subtitle files (SRT, ASS) aren't affected, and you can still export them."

VC_RUNTIME_MISSING = _template(
    "runtime.vcMissing",
    "This computer doesn't have the Microsoft Visual C++ Redistributable (x64), so the speech "
    "recognition and translation programs can't start. Go to {url} to download and install "
    '"vc_redist.x64.exe", then try again.',
    url="text",
)
LOCAL_BUILD = _template(
    "runtime.localBuild",
    "There's no ready-made {engine} program to download for this platform, so you need to build "
    "it once on this computer. In the project folder, run {script} (the steps are in "
    "docs/MACOS.md). The built {program} goes in {folder}. The app also finds it on your PATH.",
    engine="text",
    script="text",
    program="text",
    folder="text",
)
FOUND_ELSEWHERE = _template(
    "runtime.foundElsewhere",
    "The app didn't delete {program}: it was found in {where}, not in the app's runtimes folder "
    "({folder}). To remove it, do that yourself (if you installed it with Homebrew, use brew "
    "uninstall).",
    program="text",
    where="text",
    folder="text",
)
NO_JAPANESE_FONT = _template(
    "fonts.noJapaneseWindows",
    "This computer has no font that can show Japanese subtitles (tried {fonts}), so burned-in "
    "Japanese would turn into empty boxes. Install a Japanese font (such as Yu Gothic or "
    'Meiryo) in "Settings > Personalization > Fonts", or add the Japanese supplemental fonts '
    'in "Settings > System > Optional features", then try again. ' + _SUBTITLE_FILES_FINE,
    fonts="list",
)
NO_JAPANESE_FONT_MACOS = _template(
    "fonts.noJapaneseMac",
    "This Mac has no font that can show Japanese subtitles (tried {fonts}), so burned-in "
    "Japanese would turn into empty boxes. Install a Japanese font (such as Hiragino Sans or "
    "Yu Gothic) with Font Book, then try again. " + _SUBTITLE_FILES_FINE,
    fonts="list",
)
MISSING_GLYPHS = _template(
    "fonts.missingGlyphs",
    "The font {font} has no glyphs for these characters: {chars}. The burned-in subtitles would "
    "show empty boxes. Install a font that has these characters, then try again. "
    + _SUBTITLE_FILES_FINE,
    font="text",
    chars="text",
)
MISSING_TARGET_GLYPHS = _template(
    "fonts.missingTargetGlyphs",
    "The font {font} is missing glyphs that the {language} subtitles need: {chars}. The "
    "burned-in subtitles would show empty boxes. Install a font that supports {language}, then "
    "try again. " + _SUBTITLE_FILES_FINE,
    font="text",
    language="language",
    chars="text",
)
NO_TARGET_FONT = _template(
    "fonts.noTargetFont",
    "This computer has no font that can show {language} subtitles (tried {fonts}), so the "
    "burned-in subtitles would show empty boxes. Install a font that supports {language}, then "
    "try again. " + _SUBTITLE_FILES_FINE,
    language="language",
    fonts="list",
)
NO_H264_WINDOWS = _template(
    "render.noH264Windows",
    "Windows on this computer has no H.264 encoder, so the subtitles can't be burned into the "
    'video. In "Settings > System > Optional features", install "Media Feature Pack" (only '
    "Windows N and KN editions need it), or run Windows Update, then try again. "
    + _SUBTITLE_FILES_FINE,
)
NO_H264_MACOS = _template(
    "render.noH264Mac",
    "The ffmpeg on this Mac has no usable H.264 encoder, so the subtitles can't be burned into "
    "the video. In Terminal, run brew install ffmpeg to install the full ffmpeg, then try "
    "again. " + _SUBTITLE_FILES_FINE,
)
UNSUPPORTED_PLATFORM = _template(
    "platform.unsupported",
    "This app runs only on Windows (64-bit) and on Macs with Apple silicon (M1 or later). This "
    "computer is {system} {machine}. Intel Macs and Linux aren't supported yet.",
    system="text",
    machine="text",
)
CLOUD_KEY_UNAVAILABLE = _template(
    "secrets.cloudKeyUnavailable",
    "This version can't save a cloud API key on a Mac yet. Use the local model (the default) or "
    "Ollama instead. Saving cloud keys will come later.",
)

# Why a profile was chosen (`manager/profiles.py`). The block has one sentence on each line, so each
# line is a whole notice. The padding after the colon lines the English up in its fixed-width box.
PROFILE_LABELS: Mapping[str, Template] = MappingProxyType(
    {
        name: _template(f"profile.label.{name}", english)
        for name, english in (
            ("gpu-24gb", "24 GB VRAM, default"),
            ("gpu-8gb", "8 GB VRAM"),
            ("cpu", "CPU only, no GPU acceleration"),
            ("metal-32gb", "Apple silicon, 32 GB or more, one model at a time"),
            ("metal-32gb-parallel", "Apple silicon, 32 GB or more, both models at once"),
            ("metal-16gb", "Apple silicon, 16 GB"),
            ("apple-cpu", "Apple silicon, CPU only, no GPU acceleration"),
        )
    }
)
"""A profile's name. It is also its `label`, so the line that quotes it gets it worded too."""
PROFILE_LINE = _template(
    "profile.line", "Profile:       {profile} ({label})", profile="text", label="text"
)


def _why(code: str, reason: str) -> Template:
    return _template(f"profile.why.{code}", f"Why:           {reason}")


WHY_VRAM_FITS = _why("vramFits", "The GPU has enough VRAM for this profile.")
WHY_NO_NVIDIA_GPU = _why("noNvidiaGpu", "No NVIDIA GPU was found, so GPU runtimes are not used.")
WHY_VRAM_UNKNOWN = _why("vramUnknown", "An NVIDIA GPU was found but its VRAM could not be read.")
WHY_VRAM_TOO_SMALL = _why(
    "vramTooSmall", "The GPU has less VRAM than the smallest GPU profile needs."
)
WHY_USER_CHOICE = _why("userChoice", "You chose this profile.")
WHY_MEMORY_FITS = _why(
    "memoryFits", "This profile was chosen by the Mac's unified memory size, not by a measurement."
)
WHY_MEMORY_UNKNOWN = _why("memoryUnknown", "The Mac's memory size could not be read.")
WHY_MEMORY_TOO_SMALL = _why(
    "memoryTooSmall", "The Mac has less memory than the smallest Metal profile needs."
)
DRIVER_TOO_OLD = _template(
    "profile.driverTooOld",
    "Driver:        {installed} is too old for the {profile} profile. Update the NVIDIA driver "
    "to {required} or newer. The CUDA Toolkit is not needed.",
    installed="text",
    profile="text",
    required="text",
)


def _stage_template(code: str, start: str) -> Template:
    return _template(
        f"profile.{code}",
        start + "{model} via {engine} ({runtime}) on {device}",
        model="text",
        engine="text",
        runtime="text",
        device="text",
    )


ASR_LINE = _stage_template("asr", "ASR:           ")
ASR_FALLBACK_LINE = _stage_template("asrFallback", "ASR fallback:  ")
LLM_LINE = _stage_template("llm", "Local LLM:     ")
ASR_FALLBACK_BLOCKED = _template(
    "profile.asrFallbackBlocked",
    "ASR fallback:  unavailable, driver {installed} < {required}; update the NVIDIA driver "
    "(CUDA Toolkit not needed)",
    installed="text",
    required="text",
)
ONE_STAGE_AT_A_TIME = _template(
    "profile.oneAtATime",
    "Stages:        run one after the other; the ASR exits before the LLM loads",
)
LLM_CONTEXT_CAPPED = _template(
    "profile.llmContext", "LLM context:   capped at {tokens} tokens", tokens="text"
)
LOW_RAM = _template(
    "profile.lowRam",
    "RAM warning:   {installed} MiB is below the {recommended} MiB the local 8B model needs; "
    "use a cloud LLM or expect swapping",
    installed="text",
    recommended="text",
)
CLOUD_LLM_RECOMMENDED = _template(
    "profile.cloudRecommended", "Cloud LLM:     recommended, only after you opt in"
)
CLOUD_LLM_OPTIONAL = _template("profile.cloudOptional", "Cloud LLM:     optional")

_NOTICE = "_notice"
E = TypeVar("E", bound=BaseException)


def noticed(error: Callable[[str], E], notice: Notice) -> E:
    """An `error` whose text is the notice's English sentence and that remembers the notice."""
    made = error(notice.message)
    setattr(made, _NOTICE, notice)
    return made


def notices_of(exc: BaseException | None, text: str | None = None) -> tuple[Notice, ...]:
    """The notices inside `text` (by default `str(exc)`) that `exc`, or an exception it was
    raised from, carries. Outermost first. So a handler that wraps an error in new words, as
    `SettingsError(str(exc)) from exc` does, passes the notice on without doing anything."""
    shown = str(exc) if text is None else text
    found: list[Notice] = []
    seen: set[int] = set()
    while exc is not None and id(exc) not in seen:
        seen.add(id(exc))
        notice = getattr(exc, _NOTICE, None)
        if isinstance(notice, Notice) and notice.message in shown:
            found.append(notice)
        exc = exc.__cause__ or (None if exc.__suppress_context__ else exc.__context__)
    return unique(found)


def unique(notices: Iterable[Notice]) -> tuple[Notice, ...]:
    """Each notice once, in the order first seen: the window replaces every occurrence."""
    kept: list[Notice] = []
    for notice in notices:
        if notice not in kept:
            kept.append(notice)
    return tuple(kept)


def to_json(notices: Iterable[Notice]) -> list[dict[str, Any]]:
    return [asdict(notice) for notice in notices]


def from_json(raw: object) -> tuple[Notice, ...]:
    """Notices read back from a file. A value that is not one is left out, and the text beside it
    is then shown as it was stored, so a damaged or older file never fails to load for this."""
    if not isinstance(raw, list):
        return ()
    found: list[Notice] = []
    for item in cast("list[object]", raw):
        if not isinstance(item, dict):
            continue
        entry = cast("dict[str, object]", item)
        code, message, params = entry.get("code"), entry.get("message"), entry.get("params")
        if isinstance(code, str) and isinstance(message, str) and isinstance(params, dict):
            found.append(Notice(code, cast("dict[str, ParamValue]", params), message))
    return tuple(found)


SHELL_PREFIX = "VST_NOTICE "


def notice_lines(notices: Iterable[Notice]) -> list[str]:
    """One stderr line for each notice of a backend that stops before it is ready. The shell
    takes these lines out of the output it shows and sends the notices to the window with it."""
    return [SHELL_PREFIX + json.dumps(one) for one in to_json(notices)]


def registry_file() -> str:
    """The text of `app/src/i18n/notices.backend.json`, the registry as the window reads it."""
    made = {
        code: {"english": one.english, "params": dict(one.params)}
        for code, one in sorted(REGISTRY.items())
    }
    return json.dumps(made, ensure_ascii=False, indent=2) + "\n"
