"""The W4b sentences, each raised at the site the app raises it from.

`app/src/i18n/notices.w4b.fixture.json` holds, for each scenario, the text and notices this module
produces now (`tests/test_notices_w4b.py` keeps them equal), `before`: the text the same call gave
at commit 96dc7b3, and `zh`: what a window in Traditional Chinese shows. `before` was written by
running this module on a clean export of that commit, so it only calls what both versions have.
The English must equal `before`: the window words these sentences, it does not change them.

Paths are written with `/`, so the fixture is the same on every system.
"""

# pyright: reportUnknownLambdaType=false, reportUnknownArgumentType=false
# pyright: reportPrivateUsage=false

from __future__ import annotations

import hashlib
import io
import os
import subprocess
import sys
import tarfile
import threading
import urllib.error
import wave
import zipfile
from collections.abc import Callable
from dataclasses import asdict, replace
from email.message import Message
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

import pytest
from notice_scenarios import _slashes

from backend import main as app_main
from backend.core import audio, pipeline, queue_runner, summarize, translate, vc_runtime
from backend.core.model import Cue
from backend.core.notices import notices_of
from backend.core.subtitle_io import render_subs
from backend.engines import base, crispasr, table, whispercpp
from backend.engines.table import engine_paths
from backend.llm import client, local_server
from backend.llm.ask import RepliesRejected
from backend.manager import download, platforms, profiles, resolve, selftest, updates
from backend.manager import registry as registry_module
from backend.manager.hardware import Hardware
from backend.manager.profiles import ProfileId
from backend.manager.secrets import SecretError
from backend.manager.selftest_store import SelfTestStore
from backend.manager.settings import LlmSource
from backend.manager.storage import Storage

Entry = dict[str, Any]


def _entry(text: str, found: object) -> Entry:
    """`found` is the notices beside `text`: dataclasses, JSON, or nothing at an older commit."""
    listed: list[Any] = list(cast("Any", found or ()))
    return {"text": text, "notices": [n if isinstance(n, dict) else asdict(n) for n in listed]}


# Group 1: why a profile was chosen.


def _why(selection: profiles.Selection, registry: registry_module.Registry) -> Entry:
    explain = getattr(profiles, "explain", None)
    found = explain(selection, registry).notices if explain else ()
    return _entry(profiles.describe(selection, registry), found)


def _profiles(found: dict[str, Entry]) -> None:
    win = registry_module.load(platform=platforms.WIN_X64)
    mac = registry_module.load(platform=platforms.MACOS_ARM64)

    def pc(vram: int | None, driver: str = "596.36", ram: int = 65536) -> Hardware:
        return Hardware("RTX", vram, driver, ram, 1)

    def apple(ram: int | None) -> Hardware:
        return Hardware(None, None, None, ram, 1, platforms.MACOS_ARM64, "Apple M3")

    hardware = {
        "vramFits24": pc(24564),
        "vramFits8": pc(8192),
        "noGpuLowRam": Hardware(None, None, None, 8192, 1),
        "vramUnknown": pc(None),
        "vramTooSmall": pc(4096),
        "driverTooOld": pc(24564, "500.00"),
    }
    for name, one in hardware.items():
        found[f"why.{name}"] = _why(profiles.select(one, win), win)
    for name, ram in (("memoryFits", 36864), ("memoryUnknown", None), ("memoryTooSmall", 8192)):
        found[f"why.{name}"] = _why(profiles.select(apple(ram), mac), mac)
    found["why.fallbackBlocked"] = _why(
        profiles.selection_for(ProfileId.GPU_24GB, pc(4096, "560.00"), win), win
    )
    for profile_id in ProfileId:
        on_mac = profile_id in profiles.MAC_PROFILES
        registry, one = (mac, apple(36864)) if on_mac else (win, pc(4096))
        found[f"why.chosen.{profile_id.value}"] = _why(
            profiles.selection_for(profile_id, one, registry), registry
        )


# Group 2: the self-test, each report made by `run_selftest` with the real probe.

PROGRAM = Path("/vst/program.exe")


class _Program:
    """Stands in for `subprocess.Popen`: it ends as `how` says without starting anything."""

    def __init__(self, how: str) -> None:
        self.how, self.waits = how, 0
        self.returncode = 3 if how in ("exits", "silent") else 0

    def communicate(self, timeout: float | None = None) -> tuple[bytes, None]:
        self.waits += 1
        if self.how == "hangs" and self.waits == 1:
            raise subprocess.TimeoutExpired("program", timeout or 0)
        said = {"exits": b"ggml error\nno kernel image", "cudaOk": b"CUDA0", "noCuda": b"none"}
        return said.get(self.how, b""), None

    def kill(self) -> None:
        pass


def _start(gpu: str, cpu: str) -> Callable[..., _Program]:
    """`gpu` and `cpu` say how a program ends on that device. A CPU command is told apart from a
    GPU one by its flags."""

    def popen(command: list[str], **_kwargs: object) -> _Program:
        how = cpu if "-ng" in command or "--version" in command else gpu
        if how == "missing":
            raise OSError("The system cannot find the file specified")
        return _Program(how)

    return popen


def _report(
    name: str,
    profile_id: ProfileId,
    tmp: Path,
    found: dict[str, Entry],
    *,
    gpu: str = "cudaOk",
    cpu: str = "ok",
    absent: tuple[str, ...] = (),
    simulate: bool = False,
) -> None:
    registry = registry_module.load(platform=platforms.WIN_X64)
    profile = next(p for p in profiles.profiles_for(platforms.WIN_X64) if p.id is profile_id)
    model = tmp / "model.bin"
    model.write_bytes(b"x")

    def executable(runtime_id: str, *_rest: object) -> Path | None:
        return None if runtime_id.endswith(absent or ("\0",)) else PROGRAM

    with pytest.MonkeyPatch.context() as mp:
        mp.delenv("VST_SIMULATE_NO_VCRUNTIME", raising=False)
        if simulate:
            mp.setenv(selftest.FAULT_ENV, "1")
        else:
            mp.delenv(selftest.FAULT_ENV, raising=False)
        mp.setattr(vc_runtime, "require", lambda _error: None)
        mp.setattr(selftest, "runtime_executable", executable)
        mp.setattr(Storage, "model_file", lambda *_a: model)
        mp.setattr(selftest, "adopt", lambda _proc: None)
        mp.setattr(selftest.subprocess, "Popen", _start(gpu, cpu))
        report = asdict(selftest.run_selftest(profile, registry, Storage(tmp), SelfTestStore(tmp)))
    found[f"{name}.message"] = _entry(report["message"], report.get("message_notices"))
    if report["fallback"]:
        fallback = report["fallback"]
        found[f"{name}.reason"] = _entry(fallback["reason"], fallback.get("reason_notices"))
    for index, stage in enumerate(report["stages"]):
        found[f"{name}.stage{index}"] = _entry(stage["detail"], stage.get("detail_notices"))


def _selftests(found: dict[str, Entry], tmp: Path) -> None:
    gpu, cpu = ProfileId.GPU_24GB, ProfileId.CPU
    _report("selftest.passedGpu", gpu, tmp, found)
    _report("selftest.passedCpu", cpu, tmp, found)
    _report("selftest.exits", cpu, tmp, found, cpu="exits")
    _report("selftest.exitsSilently", cpu, tmp, found, cpu="silent")
    _report("selftest.hangs", cpu, tmp, found, cpu="hangs")
    _report("selftest.cannotStart", cpu, tmp, found, cpu="missing")
    _report("selftest.fellBack", gpu, tmp, found, simulate=True)
    _report("selftest.bothFail", gpu, tmp, found, gpu="noCuda", cpu="exits")
    _report("selftest.noCpuRuntime", gpu, tmp, found, simulate=True, absent=("cpu",))
    _report("selftest.notInstalled", cpu, tmp, found, absent=("cpu",))


# Group 3: the update check.

REMOTE = "https://example.test/registry.json"


def _said(carrier: object) -> Entry:
    """A report or an item: its `message`, and the notices a newer commit sends beside it."""
    return _entry(carrier.message, getattr(carrier, "message_notices", ()))  # pyright: ignore


def _raised(call: Callable[[], object]) -> Entry:
    """What `call` raises, with the notices it or its causes carry."""
    try:
        call()
    except Exception as exc:
        return _entry(str(exc), notices_of(exc))
    raise AssertionError("nothing was raised")


def _updates(found: dict[str, Entry]) -> None:
    bundled = registry_module.load(platform=platforms.WIN_X64)
    first, second = list(bundled.models.values())[:2]
    newer = replace(
        bundled, models={**bundled.models, first.id: replace(first, version="v9", sha256="f" * 64)}
    )
    installed: dict[str, object] = {}

    def record(ok: bool = True, version: str = first.version, sha: str = first.sha256) -> object:
        return SimpleNamespace(ok=ok, version=version, sha256=sha)

    inv: Any = SimpleNamespace(
        registry=bundled,
        manifest=SimpleNamespace(get=lambda asset_id: installed.get(asset_id)),
        is_installed=lambda asset_id: asset_id in installed,
    )

    def item(name: str, remote: registry_module.Registry | None = None) -> None:
        url = REMOTE if remote else None
        found[f"updates.item.{name}"] = _said(updates._item(inv, first.id, remote, url))

    item("notInstalled")
    found["updates.noRemote"] = _said(updates.check_updates(inv, None))
    installed[first.id] = None
    item("unrecorded")
    installed[first.id] = record(ok=False)
    item("checkFailed")
    tool = next(iter(bundled.runtimes))
    for name, held in (("runtimeUnrecorded", None), ("runtimeCheckFailed", record(ok=False))):
        installed[tool] = held
        found[f"updates.item.{name}"] = _said(updates._item(inv, tool, None, None))
    del installed[tool]
    installed[first.id] = record()
    item("matchesBundle")
    item("matchesRemote", bundled)
    item("needsApp", newer)
    found["updates.allMatch"] = _said(updates.check_updates(inv, REMOTE, lambda _url: bundled))
    installed[first.id] = record(version="v0", sha="0" * 64)
    installed[second.id] = record(version="v0", sha="0" * 64)
    item("older")
    found["updates.available"] = _said(updates.check_updates(inv, None))

    def reading(name: str, answer: Callable[..., object]) -> None:
        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(updates.urllib.request, "urlopen", answer)
            found[f"updates.read.{name}"] = _raised(lambda: updates.fetch_registry(REMOTE))

    def fails(error: Exception) -> Callable[..., object]:
        def open_it(*_args: object, **_kwargs: object) -> object:
            raise error

        return open_it

    reading("http", fails(urllib.error.HTTPError(REMOTE, 404, "Not Found", Message(), None)))
    reading("connect", fails(urllib.error.URLError("refused")))
    reading("invalid", lambda *_a, **_k: io.BytesIO(b"<html>"))
    reading("failed", fails(TimeoutError("timed out")))


# Group 4: downloads.

ORIGIN = "https://origin.test/tool.zip"


class _Answer(io.BytesIO):
    """An HTTP response that holds `body` and claims the headers it is given."""

    def __init__(self, body: bytes, headers: dict[str, str] | None = None) -> None:
        super().__init__(body)
        self.status, self.headers = 200, headers or {}


class _Volume:
    def __str__(self) -> str:
        return "/vst"

    def stat(self) -> object:
        return SimpleNamespace(st_dev=1)


def _download_failed(call: Callable[[], object]) -> Entry:
    try:
        call()
    except download.DownloadError as exc:
        failure = exc.failure
        return _entry(failure.message, getattr(failure, "message_notices", ()))
    raise AssertionError("the download did not fail")


def _tar(*members: tarfile.TarInfo) -> bytes:
    held = io.BytesIO()
    with tarfile.open(fileobj=held, mode="w:gz") as archive:
        for member in members:
            archive.addfile(member)
    return held.getvalue()


def _member(name: str, kind: bytes, link: str = "") -> tarfile.TarInfo:
    member = tarfile.TarInfo(name)
    member.type, member.linkname = kind, link
    return member


def _downloads(found: dict[str, Entry], tmp: Path) -> None:
    folder = tmp / "downloads"
    folder.mkdir()
    body = b"0123456789"
    digest = hashlib.sha256(body).hexdigest()
    policy = download.RetryPolicy(max_failures=0, backoff_s=0)

    def fetched(name: str, answer: object, *, held: bytes | None = None, sha: str = digest) -> None:
        item = download.Item(ORIGIN, folder / f"{name}.bin", sha, len(body))
        if held is not None:
            download.part_of(item.dest).write_bytes(held)
        job = download.Job(download.Plan(name, (item,)))
        job.try_start()

        def opener(_request: object, _timeout: float) -> object:
            if isinstance(answer, Exception):
                raise answer
            return answer

        found[f"download.{name}"] = _download_failed(
            lambda: download.fetch(item, job, ORIGIN, opener, policy)
        )

    def http(status: int) -> Exception:
        return urllib.error.HTTPError(ORIGIN, status, "x", Message(), io.BytesIO())

    fetched("http404", http(404))
    fetched("busyServer", http(503))
    fetched("rangeRefused", http(416), held=body[:4])
    fetched("cutShort", _Answer(body[:3]))
    fetched("wrongSize", _Answer(body, {"Content-Length": "7"}))
    fetched("hashMismatch", _Answer(body), sha="0" * 64)

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(download, "_anchor", lambda _folder: _Volume())
        mp.setattr(download.shutil, "disk_usage", lambda _p: SimpleNamespace(free=1000))
        found["download.noSpace"] = _download_failed(
            lambda: download.check_space([(folder, 3 << 20)])
        )

    def disk(name: str, error: OSError) -> None:
        failed = download._disk_failure(error).failure
        found[f"download.{name}"] = _entry(failed.message, getattr(failed, "message_notices", ()))

    disk("locked", PermissionError(13, "denied", "/vst/llama-server.exe"))
    disk("lockedMoving", PermissionError(13, "denied", "/vst/runtime", None, "/vst/runtime.old"))
    disk("lockedUnknown", PermissionError(13, "denied"))
    disk("writeFailed", OSError(28, "No space left on device"))

    zipped = io.BytesIO()
    with zipfile.ZipFile(zipped, "w") as archive:
        archive.writestr("../evil.exe", b"x")
    with zipfile.ZipFile(zipped) as archive:
        found["download.unsafePath"] = _download_failed(
            lambda: download.safe_members(archive, folder)
        )
    tars = {
        "unsafeLink": _member("bin/tool", tarfile.SYMTYPE, "/etc/passwd"),
        "unsafeLinkEntry": _member("bin/tool", tarfile.LNKTYPE, "."),
        "unsupportedEntry": _member("bin/pipe", tarfile.FIFOTYPE),
        "missingLinkTarget": _member("bin/tool", tarfile.LNKTYPE, "bin/absent"),
    }
    job = download.Job(download.Plan("tar", ()))
    for name, member in tars.items():
        path = folder / f"{name}.tar.gz"
        path.write_bytes(_tar(member))
        found[f"download.{name}"] = _download_failed(
            lambda p=path, n=name: download.extract_tar(p, folder / f"out-{n}", job)
        )
    empty = folder / "empty.zip"
    with zipfile.ZipFile(empty, "w") as archive:
        archive.writestr("readme.txt", b"x")
    item = download.Item(ORIGIN, empty, "0", 1)
    plan = download.Plan("empty", (item,), unpack_to=folder / "runtime", entry_point="tool.exe")
    found["download.noEntryPoint"] = _download_failed(
        lambda: download.unpack(plan, download.Job(plan))
    )


# Group 5: a run that failed.


def _ended(code: int = 0, out: str = "", err: str = "") -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(["tool"], code, out, err)


def _wav(path: Path, rate: int = 16000, frames: int = 16000) -> Path:
    with wave.open(str(path), "wb") as sink:
        sink.setnchannels(1)
        sink.setsampwidth(2)
        sink.setframerate(rate)
        sink.writeframes(b"\0\0" * frames)
    return path


class _Child:
    """Stands in for a running program: what it writes on stderr and how it ends."""

    def __init__(self, *_args: object, code: int = 0, said: bytes = b"", **_kwargs: object) -> None:
        self.returncode, self.pid = code, 1
        self.stderr = io.BytesIO(said)

    def __enter__(self) -> _Child:
        return self

    def __exit__(self, *_args: object) -> None:
        pass

    def poll(self) -> int | None:
        return self.returncode

    def wait(self, timeout: float | None = None) -> int:
        return self.returncode

    def kill(self) -> None:
        pass

    def terminate(self) -> None:
        pass


def _refuses(*_args: object, **_kwargs: object) -> object:
    raise OSError("Access is denied")


def _audio_failures(found: dict[str, Entry]) -> None:
    video = Path("talk.mp4")
    for system in ("win32", "darwin"):
        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(audio.shutil, "which", lambda *_a, **_k: None)
            found[f"audio.toolMissing.{system}"] = _raised(
                lambda s=system: audio.find_tool("ffmpeg", system=s)
            )
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(audio.subprocess, "Popen", _Child)
        mp.setattr(audio.process_guard, "adopt", lambda _proc: None)
        mp.setattr(audio, "_PROBE_TIMEOUT_S", 0.0)
        found["audio.toolTimedOut"] = _raised(
            lambda: audio._require_audio_stream(video, Path("ffprobe"), None)
        )
    for name, ended in (
        ("probeFailed", _ended(1, err="moov atom not found")),
        ("noAudioTrack", _ended(0)),
    ):
        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(audio, "_run", lambda *_a, _e=ended, **_k: _e)
            found[f"audio.{name}"] = _raised(
                lambda: audio._require_audio_stream(video, Path("ffprobe"), None)
            )
    for name, err in (("ffmpegStopped", "Invalid data"), ("ffmpegStoppedSilent", "")):
        failed = audio._ffmpeg_failure(video, _ended(1, err=err))
        found[f"audio.{name}"] = _entry(str(failed), notices_of(failed))
    _wav(Path("slow.wav"), rate=8000)
    Path("noise.wav").write_bytes(b"not a wav file at all")
    whole = _wav(Path("cut.wav")).read_bytes()
    Path("cut.wav").write_bytes(whole[:-100])
    for name in ("slow", "noise", "cut"):
        found[f"audio.wav.{name}"] = _raised(lambda n=name: audio.wav_duration_ms(Path(f"{n}.wav")))
    Path("empty.wav").write_bytes(b"RIFF\x04\0\0\0WAVE")

    class _Header:
        def __enter__(self) -> _Header:
            return self

        def __exit__(self, *_args: object) -> None:
            pass

        def getframerate(self) -> int:
            return 16000

        def getnchannels(self) -> int:
            return 1

        def getsampwidth(self) -> int:
            return 2

        def getnframes(self) -> int:
            return 0

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(audio.wave, "open", lambda *_a: _Header())
        found["audio.wav.noData"] = _raised(lambda: audio.wav_duration_ms(Path("empty.wav")))
    found["audio.videoNotFound"] = _raised(lambda: audio.extract(Path("gone.mp4"), Path("out.wav")))


def _pipeline_failures(found: dict[str, Entry], tmp: Path) -> None:
    from test_pipeline import SETTINGS, Fakes

    video = tmp / "talk.mp4"
    video.write_bytes(b"x")
    silent = replace(Fakes().ports(), transcribe=lambda *_a: [])
    found["pipeline.noSpeech"] = _raised(
        lambda: pipeline.run(video, tmp / "project", SETTINGS, silent)
    )


def _engine_failures(found: dict[str, Entry]) -> None:
    Path("latin.json").write_bytes(b"\xff\xfe")
    Path("broken.json").write_text("{", encoding="utf-8")
    Path("list.json").write_text("[]", encoding="utf-8")
    Path("odd.json").write_text('{"transcription": [{}]}', encoding="utf-8")
    Path("wordless.json").write_text('{"transcription": [{"text": "x"}]}', encoding="utf-8")
    for name in ("absent", "latin", "broken", "list"):
        found[f"engine.output.{name}"] = _raised(lambda n=name: base.read_json(Path(f"{n}.json")))
    for file in ("whisper", "crisp", "model.bin", "aligner.bin", "mod\u00e8le.bin"):
        Path(file).write_bytes(b"x")
    _wav(Path("speech.wav"))
    here, gone = Path("model.bin"), Path("gone")
    whisper = whispercpp.WhisperCppEngine(Path("whisper"), here)
    crisp = crispasr.CrispAsrEngine(Path("crisp"), here, Path("aligner.bin"))
    cases = {
        "programMissing": whispercpp.WhisperCppEngine(gone, here),
        "modelMissing": whispercpp.WhisperCppEngine(Path("whisper"), gone),
        "alignerMissing": crispasr.CrispAsrEngine(Path("crisp"), here, gone),
        "nonAsciiPath": crispasr.CrispAsrEngine(
            Path("crisp"), Path("mod\u00e8le.bin"), Path("aligner.bin")
        ),
    }
    for name, engine in cases.items():
        found[f"engine.{name}"] = _raised(lambda e=engine: e.transcribe(Path("speech.wav")))
    runs: dict[str, tuple[Callable[..., object], float | None]] = {
        "cannotStart": (_refuses, None),
        "timedOut": (_Child, -1.0),
        "exited": (lambda *a, **k: _Child(code=3, said=b"out of memory\n"), None),
        "exitedSilent": (lambda *a, **k: _Child(code=3), None),
    }
    for name, (popen, timeout) in runs.items():
        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(vc_runtime, "require", lambda _error: None)
            mp.setattr(base.subprocess, "Popen", popen)
            mp.setattr(base.process_guard, "adopt", lambda _proc: None)
            whisper.timeout_s = timeout
            found[f"engine.{name}"] = _raised(lambda: whisper.transcribe(Path("speech.wav")))
    for name, engine, output in (
        ("badWhisperJson", whisper, "odd.json"),
        ("badCrispJson", crisp, "wordless.json"),
    ):
        found[f"engine.{name}"] = _raised(lambda e=engine, o=output: e.parse(Path(o)))


def _server_failures(found: dict[str, Entry]) -> None:
    program, gguf = Path("llama-server"), Path("qwen.gguf")

    def start(wait: float = 5.0) -> object:
        server = local_server.LlamaServer(
            program, gguf, log_path=Path("llama.log"), startup_timeout_s=wait
        )
        return server.__enter__()

    found["server.programMissing"] = _raised(start)
    program.write_bytes(b"x")
    found["server.modelMissing"] = _raised(start)
    gguf.write_bytes(b"x")

    class _Job:
        def adopt(self, _proc: object) -> None:
            pass

        def close(self) -> None:
            pass

    starts: tuple[tuple[str, Callable[..., object], float], ...] = (
        ("cannotStart", _refuses, 5.0),
        ("exited", lambda *a, **k: _Child(code=1), 5.0),
        ("notReady", _Child, 0.0),
    )
    for name, popen, wait in starts:
        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(vc_runtime, "require", lambda _error: None)
            mp.setattr(local_server.subprocess, "Popen", popen)
            mp.setattr(local_server, "KillOnClose", _Job)
            found[f"server.{name}"] = _raised(lambda w=wait: start(w))


def _chat_failures(found: dict[str, Entry]) -> None:
    config = client.LlmConfig("http://127.0.0.1:9/v1", "m", timeout_s=30.0)
    moved = Message()
    moved["Location"] = "https://elsewhere.test/"

    def http(status: int, reason: str, headers: Message, body: bytes = b"") -> Exception:
        return urllib.error.HTTPError(config.chat_url, status, reason, headers, io.BytesIO(body))

    answers: dict[str, object] = {
        "notJson": b"<html>",
        "noContent": b"{}",
        "redirected": http(302, "Found", moved),
        "http": http(500, "Internal Server Error", Message(), b"model crashed"),
        "timedOut": urllib.error.URLError(TimeoutError()),
        "unreachable": urllib.error.URLError("connection refused"),
    }
    for name, answer in answers.items():

        def open_it(*_args: object, _answer: object = answer, **_kwargs: object) -> object:
            if isinstance(_answer, Exception):
                raise _answer
            return io.BytesIO(cast("bytes", _answer))

        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(client, "_opener", lambda _c, o=open_it: SimpleNamespace(open=o))
            found[f"llm.{name}"] = _raised(
                lambda: client.chat(config, [{"role": "user", "content": "hi"}])
            )


def _text_failures(found: dict[str, Entry]) -> None:
    def garbage(*_args: object) -> str:
        return "no"

    cues = [Cue(1, 0, 1000, "Hello there")]
    found["translate.cueFailed"] = _raised(lambda: translate.run(cues, garbage, max_retries=0))
    Path("source.json").write_text(render_subs(cues), encoding="utf-8")
    Path("partial.json").write_text("{", encoding="utf-8")
    found["translate.cannotResume"] = _raised(
        lambda: translate.translate_file(Path("source.json"), Path("partial.json"), garbage)
    )
    lines = summarize.lines_from_cues(cues)
    found["summary.noText"] = _raised(lambda: summarize.run([], garbage))
    found["summary.noPart"] = _raised(
        lambda: summarize.run(lines, garbage, max_retries=0, sleep=lambda _s: None)
    )
    found["summary.tooLarge"] = _raised(lambda: summarize.run(lines, garbage, context_tokens=10))
    notes = summarize.MapResult(0, 1000, "a topic", (summarize.Point(0, "a point"),))
    job = summarize.ReduceInput("zh-TW", 0, 1000, (notes,), (), ())

    def rejected(*_args: object) -> object:
        raise RepliesRejected("the topic is empty", 1, "no")

    asker: Any = SimpleNamespace(ask_reduce=rejected)
    found["summary.notWritten"] = _raised(
        lambda: summarize._Run.ask_reduce_or_fall_back(asker, job, [], "reduce zh-TW")
    )


def _batch_failures(found: dict[str, Entry]) -> None:
    item: Any = SimpleNamespace(video_path="gone.mp4")
    _state, text, listed = queue_runner.QueueRunner._execute(cast("Any", None), item)
    found["batch.videoGone"] = _entry(str(text), listed)
    saved: list[tuple[object, ...]] = []
    runner: Any = SimpleNamespace(
        _lock=threading.RLock(),
        _current="a",
        _store=SimpleNamespace(finish=lambda *args: saved.append(args)),
    )
    queue_runner.QueueRunner._abandon_current(runner)
    _id, _state2, _when, said, *rest = saved[0]
    found["batch.crashed"] = _entry(str(said), rest[0] if rest else ())


def _processing(found: dict[str, Entry], tmp: Path) -> None:
    folder = tmp / "run"
    folder.mkdir()
    with pytest.MonkeyPatch.context() as mp:
        mp.chdir(folder)
        _audio_failures(found)
        _engine_failures(found)
        _server_failures(found)
        _chat_failures(found)
        _text_failures(found)
        _batch_failures(found)
    _pipeline_failures(found, folder)


# Group 6: refusals before a run.


def _missing_files(found: dict[str, Entry]) -> None:
    registry = registry_module.load(platform=platforms.WIN_X64)
    storage = Storage(Path("data"))
    whisper = engine_paths(whispercpp.ENGINE_ID, storage, registry=registry)
    crisp = engine_paths(crispasr.ENGINE_ID, storage, registry=registry)

    def refused(name: str, call: Callable[[], object]) -> None:
        found[f"refuse.{name}"] = _raised(call)

    def asr(source: str = "en", cpu: bool = False) -> object:
        asked = resolve.Request(source_lang=source, cpu=cpu)
        return resolve._asr(asked, storage, registry)

    def put(path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"x")

    refused("asrProgram", asr)
    refused("mixedNoCpu", lambda: asr("ja+en", cpu=True))
    refused("mixedNotInstalled", lambda: asr("ja+en"))
    put(whisper.binary)
    refused("asrModel", asr)
    put(crisp.binary)
    put(crisp.model)
    refused("aligner", lambda: asr("ja+en"))

    def vad(path: Path | None = None) -> object:
        return resolve._vad_model(resolve.Request(vad_model=path), storage, registry)

    refused("vad", lambda: vad(Path("silero.onnx")))
    refused("vadDefault", vad)

    def llm(**asked: Any) -> object:
        return resolve._local_llm(resolve.Request(**asked), storage, registry)

    refused("llamaServer", llm)
    server = Path("llama-server")
    put(server)
    refused("llmFile", lambda: llm(llama_server=server, llm="missing.gguf"))
    refused("llmModel", lambda: llm(llama_server=server))


def _saved_key(found: dict[str, Entry], tmp: Path) -> None:
    def unreadable(_name: str) -> str:
        raise SecretError("Windows DPAPI failed (error 13)")

    cloud: Any = SimpleNamespace(llm=SimpleNamespace(source=LlmSource.CLOUD))
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(app_main, "load_settings", lambda _folder: cloud)
        mp.setattr(
            app_main, "default_secret_store", lambda _folder: SimpleNamespace(get=unreadable)
        )
        found["refuse.savedKey"] = _raised(lambda: app_main._configured_llm(tmp))


def _video_gone(found: dict[str, Entry], tmp: Path) -> None:
    from test_api import GUARD, Rig, make_project, open_client

    video = tmp / "gone.mp4"
    video.write_bytes(b"x")
    config = app_main.AppConfig(tmp / "app-data", GUARD, Rig().resolve)
    with open_client(app_main.create_app(config)) as c:
        project = make_project(c, video)
        video.unlink()
        reply = c.post(f"/api/projects/{project}/jobs", json={}).json()
    said = _entry(reply["detail"], reply.get("notices"))
    found["refuse.videoGone"] = _replaced(said, str(video), "/vst/gone.mp4")


def _replaced(value: Any, old: str, new: str) -> Any:
    if isinstance(value, str):
        return value.replace(old, new)
    if isinstance(value, dict):
        entries = cast("dict[str, object]", value)
        return {key: _replaced(item, old, new) for key, item in entries.items()}
    if isinstance(value, list):
        return [_replaced(item, old, new) for item in cast("list[object]", value)]
    return value


def _refusals(found: dict[str, Entry], tmp: Path) -> None:
    folder = tmp / "refuse"
    folder.mkdir()
    windows = profiles.runtime_set(platforms.WIN_X64)
    with pytest.MonkeyPatch.context() as mp:
        mp.chdir(folder)
        mp.setattr(table, "runtime_set", lambda: windows)
        mp.setattr(resolve, "runtime_set", lambda: windows)
        _missing_files(found)
    _saved_key(found, folder)
    _video_gone(found, folder)


def collect(tmp: Path) -> dict[str, Entry]:
    found: dict[str, Entry] = {}
    _profiles(found)
    _selftests(found, tmp)
    _updates(found)
    _downloads(found, tmp)
    _processing(found, tmp)
    _refusals(found, tmp)
    return {name: _slashes(entry) for name, entry in found.items()}


if __name__ == "__main__":
    import json
    import tempfile

    with tempfile.TemporaryDirectory(dir=os.environ.get("VST_SCRATCH")) as folder:
        made = json.dumps(collect(Path(folder)), ensure_ascii=False, indent=2)
        sys.stdout.buffer.write(made.encode("utf-8"))
