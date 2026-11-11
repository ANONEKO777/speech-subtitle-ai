from __future__ import annotations

import json
import logging
import queue
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from abc import ABC, abstractmethod
from collections import deque
from collections.abc import Callable, Generator, Iterator, Sequence
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Protocol, cast

from backend.core import process_guard, vc_runtime
from backend.core.audio import wav_duration_ms
from backend.core.model import Segment, Word
from backend.manager.profiles import Device

ProgressCb = Callable[[float], None]

DEFAULT_TIMEOUT_BASE_S = 600.0
DEFAULT_TIMEOUT_PER_AUDIO_S = 4.0
_POLL_S = 0.05
_KILL_WAIT_S = 5.0
log = logging.getLogger(__name__)
_STDERR_TAIL_LINES = 12
_MAX_COMMAND_CHARS = 24_000
_MAX_ANNOTATION_WORDS = 4
_FALLBACK_TEMP = "vst-tmp"


class EngineError(Exception):
    pass


class EngineUnavailableError(EngineError):
    pass


class EngineFailedError(EngineError):
    pass


class EngineTimeoutError(EngineError):
    pass


class EngineCancelled(EngineError):
    pass


class EngineOutputError(EngineError):
    pass


class ASREngine(Protocol):
    id: str
    supports_word_timestamps: bool

    def is_available(self) -> bool: ...

    def transcribe(
        self,
        wav_path: Path,
        language: str = "en",
        progress_cb: ProgressCb | None = None,
        cancel: threading.Event | None = None,
    ) -> list[Segment]: ...

    def transcribe_many(
        self,
        wav_paths: Sequence[Path],
        language: str = "en",
        progress_cb: ProgressCb | None = None,
        cancel: threading.Event | None = None,
    ) -> list[list[Segment]]: ...


class MonotonicProgress:
    def __init__(self, durations_s: Sequence[float], callback: ProgressCb | None) -> None:
        self._durations = list(durations_s)
        self._total = sum(self._durations) or 1.0
        self._callback = callback
        self._current = -1
        self._within = 0.0
        self._last = -1.0
        self._emit(0.0)

    def start_file(self) -> None:
        self._current = min(self._current + 1, len(self._durations) - 1)
        self._within = 0.0

    def within_file(self, fraction: float) -> None:
        if self._current < 0:
            return
        self._within = min(max(fraction, self._within), 1.0)
        done = sum(self._durations[: self._current])
        self._emit((done + self._within * self._durations[self._current]) / self._total)

    def finish(self) -> None:
        self._emit(1.0)

    def _emit(self, value: float) -> None:
        value = min(value, 1.0)
        if self._callback is not None and value > self._last:
            self._last = value
            self._callback(value)


@contextmanager
def ascii_temp_dir() -> Generator[Path]:
    """A fresh work directory whose path is pure ASCII, because CrispASR cannot open others.

    A Windows user name with Chinese characters puts the default temp folder out of reach,
    so the drive root is used then.
    """
    base = Path(tempfile.gettempdir())
    if not str(base).isascii():
        base = Path(base.anchor) / _FALLBACK_TEMP
        base.mkdir(exist_ok=True)
    work = Path(tempfile.mkdtemp(prefix="vst-asr-", dir=base))
    try:
        yield work
    finally:
        shutil.rmtree(work, ignore_errors=True)


def read_json(path: Path) -> dict[str, Any]:
    try:
        raw: object = json.loads(path.read_bytes().decode("utf-8"))
    except OSError as exc:
        raise EngineOutputError(f"engine output {path} was not written: {exc}") from exc
    except UnicodeDecodeError as exc:
        raise EngineOutputError(
            f"engine output {path.name} is not valid UTF-8 at byte {exc.start}"
        ) from exc
    except json.JSONDecodeError as exc:
        raise EngineOutputError(f"engine output {path.name} is not valid JSON: {exc}") from exc
    if not isinstance(raw, dict):
        raise EngineOutputError(f"engine output {path.name} is not a JSON object")
    return cast("dict[str, Any]", raw)


def strip_annotations(words: Sequence[Word]) -> list[Word]:
    kept: list[Word] = []
    index = 0
    while index < len(words):
        text = words[index].text
        if text.startswith("<|") and text.endswith("|>"):
            index += 1
            continue
        if text.startswith("["):
            stop = min(index + _MAX_ANNOTATION_WORDS, len(words))
            close = next((j for j in range(index, stop) if "]" in words[j].text), None)
            if close is not None:
                index = close + 1
                continue
        kept.append(words[index])
        index += 1
    return kept


def segment_of(words: Sequence[Word], start_ms: int, end_ms: int) -> Segment:
    return Segment(
        " ".join(w.text for w in words),
        min(start_ms, words[0].start_ms),
        max(end_ms, *(w.end_ms for w in words)),
        tuple(words),
    )


class SubprocessEngine(ABC):
    id: str
    supports_word_timestamps = True
    ascii_paths_only = False

    def __init__(
        self,
        binary: Path,
        model: Path,
        *,
        device: Device = Device.CUDA,
        timeout_s: float | None = None,
    ) -> None:
        self.binary = binary
        self.model = model
        self.device = device
        self.timeout_s = timeout_s

    def required_files(self) -> dict[str, Path]:
        return {"binary": self.binary, "model": self.model}

    @abstractmethod
    def command(
        self, inputs: Sequence[Path], output_bases: Sequence[Path], language: str
    ) -> list[str]: ...

    @abstractmethod
    def output_path(self, base: Path) -> Path: ...

    @abstractmethod
    def parse(self, output: Path, language: str = "en") -> list[Segment]: ...

    @abstractmethod
    def on_stderr_line(self, line: str, progress: MonotonicProgress) -> None: ...

    def problem(self) -> str | None:
        for label, path in self.required_files().items():
            if not path.is_file():
                return f"{self.id}: {label} not found: {path}"
            if self.ascii_paths_only and not str(path).isascii():
                return f"{self.id} cannot open a path with non-ASCII characters: {path}"
        return None

    def is_available(self) -> bool:
        return self.problem() is None

    def transcribe(
        self,
        wav_path: Path,
        language: str = "en",
        progress_cb: ProgressCb | None = None,
        cancel: threading.Event | None = None,
    ) -> list[Segment]:
        return self.transcribe_many([wav_path], language, progress_cb, cancel)[0]

    def transcribe_many(
        self,
        wav_paths: Sequence[Path],
        language: str = "en",
        progress_cb: ProgressCb | None = None,
        cancel: threading.Event | None = None,
    ) -> list[list[Segment]]:
        issue = self.problem()
        if issue is not None:
            raise EngineUnavailableError(issue)
        durations = [wav_duration_ms(wav) / 1000 for wav in wav_paths]
        progress = MonotonicProgress(durations, progress_cb)
        results: list[list[Segment]] = []
        with ascii_temp_dir() as work:
            inputs = self._stage(wav_paths, work)
            for start, stop in self.command_batches(inputs, work):
                outputs = [work / f"o{i:05d}" for i in range(start, stop)]
                command = self.command(inputs[start:stop], outputs, language)
                timeout = self.timeout_s
                if timeout is None:
                    timeout = DEFAULT_TIMEOUT_BASE_S + DEFAULT_TIMEOUT_PER_AUDIO_S * sum(
                        durations[start:stop]
                    )
                self._run(command, progress, cancel, timeout)
                results += [self.parse(self.output_path(base), language) for base in outputs]
        progress.finish()
        return results

    def _stage(self, wav_paths: Sequence[Path], work: Path) -> list[Path]:
        if not self.ascii_paths_only:
            return list(wav_paths)
        staged: list[Path] = []
        for index, wav in enumerate(wav_paths):
            if str(wav).isascii():
                staged.append(wav)
                continue
            target = work / f"i{index:05d}.wav"
            shutil.copyfile(wav, target)
            staged.append(target)
        return staged

    @staticmethod
    def command_batches(inputs: Sequence[Path], work: Path) -> Iterator[tuple[int, int]]:
        """Index ranges that each fit one Windows command line."""
        start, size = 0, 0
        for index, path in enumerate(inputs):
            cost = len(str(path)) + len(str(work)) + 24
            if index > start and size + cost > _MAX_COMMAND_CHARS:
                yield start, index
                start, size = index, 0
            size += cost
        if inputs:
            yield start, len(inputs)

    def _run(
        self,
        command: list[str],
        progress: MonotonicProgress,
        cancel: threading.Event | None,
        timeout_s: float,
    ) -> None:
        vc_runtime.require(EngineUnavailableError)
        flags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
        try:
            proc = subprocess.Popen(
                command,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
                creationflags=flags,
            )
        except OSError as exc:
            raise EngineUnavailableError(f"{self.id}: cannot start {self.binary}: {exc}") from exc
        process_guard.adopt(proc)
        lines: queue.Queue[bytes | None] = queue.Queue()
        reader = threading.Thread(target=_pump, args=(proc, lines), daemon=True)
        reader.start()
        tail: deque[str] = deque(maxlen=_STDERR_TAIL_LINES)
        deadline = time.monotonic() + timeout_s
        try:
            while True:
                if cancel is not None and cancel.is_set():
                    raise EngineCancelled(f"{self.id} was cancelled")
                if time.monotonic() > deadline:
                    raise EngineTimeoutError(f"{self.id} did not finish in {timeout_s:g} s")
                try:
                    raw = lines.get(timeout=_POLL_S)
                except queue.Empty:
                    continue
                if raw is None:
                    break
                line = raw.decode("utf-8", errors="backslashreplace").rstrip()
                if line:
                    tail.append(line)
                    self.on_stderr_line(line, progress)
        except BaseException:
            proc.kill()
            raise
        finally:
            try:
                proc.wait(timeout=_KILL_WAIT_S)
            except subprocess.TimeoutExpired:
                log.warning(
                    "%s: %s is still running %g s after it was killed",
                    self.id,
                    proc.pid,
                    _KILL_WAIT_S,
                )
            reader.join(timeout=_KILL_WAIT_S)
        if proc.returncode != 0:
            detail = " | ".join(tail) or "no output"
            raise EngineFailedError(f"{self.id} exited with code {proc.returncode}: {detail}")


def _pump(proc: subprocess.Popen[bytes], lines: queue.Queue[bytes | None]) -> None:
    assert proc.stderr is not None
    for raw in iter(proc.stderr.readline, b""):
        lines.put(raw)
    lines.put(None)


_PERCENT = re.compile(r"progress\s*=\s*(\d+)\s*%")


def percent_in(line: str) -> float | None:
    match = _PERCENT.search(line)
    return int(match.group(1)) / 100 if match else None
