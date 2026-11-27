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

ParamKind = Literal["text", "list", "clauses", "language"]
"""`text` is shown as it is. A `list` is joined with the separator of the language that shows it,
and `clauses`, items that hold their own punctuation, with the stronger one (`; ` in English).
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
            elif kind in ("list", "clauses"):
                items = list(cast("Sequence[str]", value))
                sent[name], shown[name] = items, (", " if kind == "list" else "; ").join(items)
            else:
                sent[name] = shown[name] = str(value)
        return Notice(self.code, sent, self.english.format_map(shown))


_REGISTRY: dict[str, Template] = {}
REGISTRY: Mapping[str, Template] = MappingProxyType(_REGISTRY)


def _template(code: str, english: str, /, **params: ParamKind) -> Template:
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

# The self-test (`manager/selftest.py`): a program that did not run, what each stage said, and the
# sentences around them. A wrapper quotes the stage sentences in a text parameter, and the window
# words them because each is a notice of its own, listed after the wrapper.
PROGRAM_CANNOT_START = _template(
    "program.cannotStart", "cannot start {program}: {error}", program="text", error="text"
)
PROGRAM_TIMED_OUT = _template(
    "program.timedOut", "{program} did not finish in {seconds} s", program="text", seconds="text"
)
PROGRAM_EXITED = _template(
    "selftest.exited",
    "{program} exited with code {code}: {output}",
    program="text",
    code="text",
    output="text",
)
PROGRAM_EXITED_SILENT = _template(
    "selftest.exitedSilent",
    "{program} exited with code {code}: no output",
    program="text",
    code="text",
)
ASR_STAGE_FAILED = _template(
    "selftest.asrFailed", "ASR ({runtime}): {detail}", runtime="text", detail="text"
)
LLM_STAGE_FAILED = _template(
    "selftest.llmFailed", "LLM ({runtime}): {detail}", runtime="text", detail="text"
)
SIMULATED_CUDA_FAILURE = _template(
    "selftest.simulated", "CUDA failed to initialise (simulated by {variable})", variable="text"
)
WHISPER_USED_THE_CPU = _template(
    "selftest.whisperUsedCpu", "whisper.cpp ran without the CUDA backend and used the CPU instead"
)
NO_CUDA_DEVICE = _template("selftest.noCudaDevice", "llama-server lists no CUDA device")
HEARD_SILENCE = _template("selftest.asrNote", "transcribed one second of silence")
SEES_CUDA = _template("selftest.cudaSeen", "llama-server sees a CUDA device")
LLAMA_STARTS = _template("selftest.llamaStarts", "llama-server starts")
STAGE_NOT_INSTALLED = _template("selftest.notInstalled", "not installed: {missing}", missing="list")
SELFTEST_PASSED = _template("selftest.passed", "Self-test passed on {device}.", device="text")
SELFTEST_FAILED = _template("selftest.failed", "Self-test failed: {failures}.", failures="clauses")
_FELL_BACK = "The GPU backend failed: {failures}. The CPU backend is used instead."
GPU_FELL_BACK = _template("selftest.gpuFellBack", _FELL_BACK, failures="clauses")
FELL_BACK_AND_PASSED = _template(
    "selftest.fellBackPassed", _FELL_BACK + " The CPU self-test passed.", failures="clauses"
)
FELL_BACK_AND_UNUSABLE = _template(
    "selftest.fellBackUnusable",
    _FELL_BACK + " The CPU backend is not usable either: {cpuFailures}.",
    failures="clauses",
    cpuFailures="clauses",
)
NO_CPU_FALLBACK = _template(
    "selftest.noCpuRuntime",
    "GPU failed and the CPU runtime is not installed. GPU: {failures}. Download {download} to "
    "have a CPU fallback.",
    failures="clauses",
    download="list",
)

# The update check (`manager/updates.py`): the summary, each item's state, and why a remote
# registry could not be read.
UPDATES_AVAILABLE = _template("updates.available", "Updates available for {assets}.", assets="list")
UPDATES_ALL_MATCH = _template(
    "updates.allMatch", "Everything installed matches the remote registry at {url}.", url="text"
)
UPDATES_NO_REMOTE = _template(
    "updates.noRemote",
    "No remote registry is configured; compared with the registry shipped with this app.",
)
ITEM_NOT_INSTALLED = _template("updates.itemNotInstalled", "not installed")
# A model row has Verify and Re-download, a runtime row only Re-download, so each names its own.
_COMPARE = "; verify or re-download it to compare with registry version {version}"
_COMPARE_RUNTIME = "; re-download it to compare with registry version {version}"
_CHECK_FAILED, _UNRECORDED = (
    "installed, but its last check failed",
    "installed, but its version was not recorded",
)
ITEM_CHECK_FAILED = _template("updates.itemCheckFailed", _CHECK_FAILED + _COMPARE, version="text")
ITEM_UNRECORDED = _template("updates.itemUnrecorded", _UNRECORDED + _COMPARE, version="text")
RUNTIME_CHECK_FAILED = _template(
    "updates.runtimeCheckFailed", _CHECK_FAILED + _COMPARE_RUNTIME, version="text"
)
RUNTIME_UNRECORDED = _template(
    "updates.runtimeUnrecorded", _UNRECORDED + _COMPARE_RUNTIME, version="text"
)
ITEM_MATCHES_REMOTE = _template(
    "updates.itemMatchesRemote",
    "registry version {version} installed, remote registry {url} agrees",
    version="text",
    url="text",
)
ITEM_MATCHES_BUNDLE = _template(
    "updates.itemNoRemote",
    "registry version {version} installed, no remote configured",
    version="text",
)
ITEM_NEEDS_APP = _template(
    "updates.itemNeedsApp",
    "installed {installed}, remote registry lists {remote}; this app ships {shipped}, so "
    "update the app to get it",
    installed="text",
    remote="text",
    shipped="text",
)
ITEM_OLDER = _template(
    "updates.itemOlder",
    "installed {installed}, the registry has {available}",
    installed="text",
    available="text",
)
_UNREADABLE = "could not read the registry at {url}: "
REGISTRY_HTTP = _template(
    "updates.readHttp", _UNREADABLE + "HTTP {status}", url="text", status="text"
)
REGISTRY_UNREACHABLE = _template(
    "updates.readConnect", _UNREADABLE + "cannot connect ({reason})", url="text", reason="text"
)
REGISTRY_INVALID = _template(
    "updates.readInvalid",
    _UNREADABLE + "it is not a valid registry ({error})",
    url="text",
    error="text",
)
REGISTRY_UNREADABLE = _template(
    "updates.readFailed", _UNREADABLE + "{error}", url="text", error="text"
)

# Downloads (`manager/download.py`): why one failed. A file another program holds is also what
# any route answers (`api/deps.py`).
NOT_ENOUGH_SPACE = _template(
    "download.noSpace",
    "Not enough free disk space on {folder}: need {needed} more, {free} is free.",
    folder="text",
    needed="text",
    free="text",
)
DOWNLOAD_HTTP = _template(
    "download.http", "{url} answered HTTP {status}", url="text", status="text"
)
WRONG_SIZE = _template(
    "download.wrongSize",
    "{url} sends {sent} bytes, expected {expected}",
    url="text",
    sent="text",
    expected="text",
)
_IS_LOCKED = (
    " is locked by another program. Close the program that holds it, such as a running "
    "transcription or LLM server, a command window or a File Explorer window open in that "
    "folder, then try again."
)
LOCKED = _template("download.locked", "{path}" + _IS_LOCKED, path="text")
LOCKED_WHILE_MOVING = _template(
    "download.lockedMoving",
    "{path} (while moving it to {target})" + _IS_LOCKED,
    path="text",
    target="text",
)
LOCKED_SOMEWHERE = _template(
    "download.lockedUnknown", "a file or folder of the runtime or model" + _IS_LOCKED
)
DISK_WRITE_FAILED = _template("download.writeFailed", "disk write failed: {error}", error="text")
DOWNLOAD_INTERRUPTED = _template(
    "download.interrupted",
    "Download interrupted and not recovered after {retries} retries ({reason}). The partial "
    "file is kept; start the download again to continue.",
    retries="text",
    reason="text",
)
RESUME_REFUSED = _template("download.rangeRefused", "server refused the resume range, restarting")
CONNECTION_CUT = _template("download.cutShort", "connection closed before the whole file arrived")
HASH_MISMATCH = _template(
    "download.hashMismatch",
    "{file} failed its SHA256 check (expected {expected}, got {actual}); the download was deleted.",
    file="text",
    expected="text",
    actual="text",
)
UNSAFE_PATH = _template("download.unsafePath", "unsafe path in archive: {name}", name="text")
UNSAFE_LINK = _template(
    "download.unsafeLink", "unsafe link in archive: {name} -> {target}", name="text", target="text"
)
UNSAFE_LINK_ENTRY = _template(
    "download.unsafeLinkEntry", "unsafe link in archive: {name}", name="text"
)
UNSUPPORTED_ENTRY = _template(
    "download.unsupportedEntry", "unsupported entry in archive: {name}", name="text"
)
LINK_TO_NOTHING = _template(
    "download.missingLinkTarget", "link to a missing file: {name}", name="text"
)
ARCHIVE_LACKS_PROGRAM = _template(
    "download.noEntryPoint", "archive does not contain {file}", file="text"
)

# A run that failed. The audio step (`core/audio.py`).
_FIND_FFMPEG = "{tool} was not found. Install "
TOOL_MISSING = _template(
    "audio.toolMissing",
    _FIND_FFMPEG + "ffmpeg, add it to PATH, or set {variable}.",
    tool="text",
    variable="text",
)
TOOL_MISSING_MAC = _template(
    "audio.toolMissingMac",
    _FIND_FFMPEG + "it with `brew install ffmpeg`, or set {variable}.",
    tool="text",
    variable="text",
)
TOOL_TIMED_OUT = _template(
    "audio.toolTimedOut",
    "{tool} on {video} did not finish in {seconds} s; stopped it",
    tool="text",
    video="text",
    seconds="text",
)
WAV_WRONG_FORMAT = _template(
    "audio.wrongFormat", "{file} is not 16 kHz mono 16-bit PCM", file="text"
)
WAV_UNREADABLE = _template(
    "audio.unreadableWav", "{file} is not a readable wav file: {error}", file="text", error="text"
)
WAV_NO_DATA = _template(
    "audio.noDataChunk", "{file} is not a readable wav file: no data chunk", file="text"
)
WAV_CUT_SHORT = _template(
    "audio.wavCutShort",
    "{file} is cut short: {actual} bytes, its header promises {promised}",
    file="text",
    actual="text",
    promised="text",
)
PROBE_FAILED = _template(
    "audio.probeFailed", "ffprobe could not read {video}: {detail}", video="text", detail="text"
)
NO_AUDIO_TRACK = _template("audio.noAudioTrack", "{video} has no audio track", video="text")
_STOPPED = "ffmpeg stopped on {video} (exit code {status}): "
FFMPEG_STOPPED = _template(
    "audio.ffmpegStopped", _STOPPED + "{detail}", video="text", status="text", detail="text"
)
FFMPEG_STOPPED_SILENTLY = _template(
    "audio.ffmpegStoppedSilent",
    _STOPPED + "no error output, so it was probably killed or ran out of memory",
    video="text",
    status="text",
)
VIDEO_NOT_FOUND = _template("audio.videoNotFound", "video not found: {video}", video="text")

# The video of a job or a batch item, and the batch itself (`api/jobs.py`, `core/queue_runner.py`).
VIDEO_GONE = _template("video.gone", "the video is gone: {video}", video="text")
BATCH_CRASHED = _template("queue.crashed", "the batch crashed")
NO_SPEECH = _template("pipeline.noSpeech", "the ASR engine found no speech in this audio")

# Speech recognition (`engines/`).
_OUTPUT = "engine output {file} "
ENGINE_OUTPUT_MISSING = _template(
    "engine.outputMissing", _OUTPUT + "was not written: {error}", file="text", error="text"
)
ENGINE_OUTPUT_NOT_UTF8 = _template(
    "engine.outputNotUtf8", _OUTPUT + "is not valid UTF-8 at byte {byte}", file="text", byte="text"
)
ENGINE_OUTPUT_NOT_JSON = _template(
    "engine.outputNotJson", _OUTPUT + "is not valid JSON: {error}", file="text", error="text"
)
ENGINE_OUTPUT_NOT_OBJECT = _template(
    "engine.outputNotObject", _OUTPUT + "is not a JSON object", file="text"
)
ENGINE_FILE_MISSING: Mapping[str, Template] = MappingProxyType(
    {
        label: _template(
            f"engine.{code}Missing", "{engine}: " + label + " not found: {path}",
            engine="text", path="text",
        )
        for label, code in (("binary", "program"), ("model", "model"), ("aligner", "aligner"))
    }
)  # fmt: skip
"""By the name of the file in `SubprocessEngine.required_files`."""
ENGINE_NON_ASCII_PATH = _template(
    "engine.nonAsciiPath",
    "{engine} cannot open a path with non-ASCII characters: {path}",
    engine="text",
    path="text",
)
ENGINE_CANNOT_START = _template(
    "engine.cannotStart",
    "{engine}: cannot start {program}: {error}",
    engine="text",
    program="text",
    error="text",
)
ENGINE_TIMED_OUT = _template(
    "engine.timedOut", "{engine} did not finish in {seconds} s", engine="text", seconds="text"
)
ENGINE_EXITED = _template(
    "engine.exited",
    "{engine} exited with code {status}: {output}",
    engine="text",
    status="text",
    output="text",
)
ENGINE_EXITED_SILENTLY = _template(
    "engine.exitedSilent",
    "{engine} exited with code {status}: no output",
    engine="text",
    status="text",
)
BAD_WHISPER_JSON = _template(
    "engine.badWhisperJson",
    "unexpected whisper.cpp JSON in {file}: {error}",
    file="text",
    error="text",
)
BAD_CRISPASR_JSON = _template(
    "engine.badCrispJson", "unexpected CrispASR JSON in {file}: {error}", file="text", error="text"
)

# The built-in LLM server (`llm/local_server.py`) and the chat endpoint (`llm/client.py`).
SERVER_PROGRAM_MISSING = _template(
    "server.programMissing", "llama-server not found: {path}", path="text"
)
SERVER_MODEL_MISSING = _template("server.modelMissing", "LLM model not found: {path}", path="text")
SERVER_EXITED = _template(
    "server.exited",
    "llama-server exited with code {status}; see {log}",
    status="text",
    log="text",
)
SERVER_NOT_READY = _template(
    "server.notReady",
    "llama-server was not ready after {seconds} s; see {log}",
    seconds="text",
    log="text",
)
_NO_COMPLETION = "{url} did not return a chat completion: "
LLM_REPLY_NOT_JSON = _template(
    "llm.notJson", _NO_COMPLETION + "body is not JSON ({error})", url="text", error="text"
)
LLM_REPLY_NO_CONTENT = _template(
    "llm.noContent", _NO_COMPLETION + "no choices[0].message.content string", url="text"
)
LLM_REDIRECTED = _template(
    "llm.redirected",
    "{url} redirected to {location}; redirects are not followed",
    url="text",
    location="text",
)
LLM_HTTP = _template(
    "llm.http", "{url} answered HTTP {status}: {detail}", url="text", status="text", detail="text"
)
LLM_TIMED_OUT = _template(
    "llm.timedOut", "no answer from {url} within {seconds} s", url="text", seconds="text"
)
LLM_UNREACHABLE = _template(
    "llm.unreachable",
    "cannot reach the LLM server at {url}: {reason}",
    url="text",
    reason="text",
)
LLM_KEY_UNSENDABLE = _template(
    "llm.keyUnsendable",
    "the API key holds a space, a line break or another character that cannot be sent; "
    "enter the key again",
)

# Translation and the summary. A `reason` or `reply` is what the check of the model's answer said
# back to the model, shown as it is.
CUE_NOT_TRANSLATED = _template(
    "translate.cueFailed",
    "cue {cue} could not be translated after {attempts} attempts: {reason}",
    cue="text",
    attempts="text",
    reason="text",
)
CANNOT_RESUME = _template(
    "translate.cannotResume",
    "{file}: cannot resume from this file ({error})",
    file="text",
    error="text",
)
SUMMARY_TOO_LARGE = _template(
    "summary.tooLarge",
    "{label} needs about {tokens} tokens, over {limit} of the {context} token context",
    label="text",
    tokens="text",
    limit="text",
    context="text",
)
SUMMARY_NOT_WRITTEN = _template(
    "summary.notWritten",
    "the summary could not be written: {reason}; the last reply: {reply}",
    reason="text",
    reply="text",
)
SUMMARY_NO_TEXT = _template("summary.noText", "the transcript has no text to summarise")
SUMMARY_NO_PART = _template("summary.noPart", "no part of the talk could be summarised")


# Refusals before a run (`manager/resolve.py`, `main.py`): a program or model that is not there,
# a choice this computer cannot run, a saved key that cannot be read.
def _not_found(code: str, what: str) -> Template:
    return _template(f"resolve.{code}", what + " not found: {path}", path="text")


def _engine_file_not_found(code: str, what: str) -> Template:
    return _template(
        f"resolve.{code}", "{engine} " + what + " not found: {path}", engine="text", path="text"
    )


ASR_PROGRAM_NOT_FOUND = _engine_file_not_found("programMissing", "program")
ASR_MODEL_NOT_FOUND = _engine_file_not_found("modelMissing", "model")
ASR_ALIGNER_NOT_FOUND = _engine_file_not_found("alignerMissing", "aligner model")
VAD_NOT_FOUND = _not_found("vadMissing", "VAD model")
VAD_NOT_FOUND_HINT = _not_found("vadMissingHint", "VAD model (see --vad-model)")
LLAMA_SERVER_NOT_FOUND = _not_found("serverMissing", "llama-server program (see --llama-server)")
LLM_FILE_NOT_FOUND = _not_found("llmFileMissing", "LLM model file")
LLM_MODEL_NOT_FOUND = _template(
    "resolve.llmModelMissing", "LLM model {model} not found: {path}", model="text", path="text"
)
# Only the talk in Japanese and English names its own engine (`tests/test_notices_w4b.py`).
_MIXED_NEEDS = "Japanese and English talks need the Qwen3-ASR engine, which "
MIXED_HAS_NO_CPU_BUILD = _template(
    "resolve.mixedNoCpu",
    _MIXED_NEEDS + "has no CPU build. Turn off CPU mode, or choose one language",
)
MIXED_NOT_INSTALLED = _template(
    "resolve.mixedNotInstalled",
    _MIXED_NEEDS + "is installed only with the 24 GB profile: {detail}",
    detail="text",
)
SAVED_KEY_UNREADABLE = _template(
    "resolve.keyUnreadable", "cannot read the saved API key: {error}", error="text"
)

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
