from __future__ import annotations

import json
import logging
import os
import shutil
import struct
import subprocess
import sys
import threading
import time
import wave
from dataclasses import dataclass
from pathlib import Path

from backend.core.subtitle_io import read_text_file, write_text_file

SAMPLE_RATE = 16_000
TOOL_DIR_ENV = "VST_FFMPEG_DIR"
DEFAULT_EXTRACT_TIMEOUT_S = 1800.0

_STAMP_VERSION = 1
_STDERR_TAIL_CHARS = 1500
_POLL_S = 0.1
_PROBE_TIMEOUT_S = 60.0

log = logging.getLogger(__name__)


class AudioError(Exception):
    pass


class NoAudioStreamError(AudioError):
    pass


class ExtractCancelled(AudioError):
    pass


@dataclass(frozen=True, slots=True)
class ExtractResult:
    wav: Path
    duration_ms: int
    skipped: bool


def find_tool(name: str, tool_dir: Path | None = None) -> Path:
    """Look in `tool_dir`, then in `$VST_FFMPEG_DIR`, then on PATH."""
    env_dir = os.environ.get(TOOL_DIR_ENV)
    search = [str(d) for d in (tool_dir, env_dir and Path(env_dir)) if d]
    for directory in search:
        found = shutil.which(name, path=directory)
        if found:
            return Path(found)
    found = shutil.which(name)
    if found is None:
        raise AudioError(
            f"{name} was not found. Install ffmpeg, add it to PATH, or set {TOOL_DIR_ENV}."
        )
    return Path(found)


def _run(
    command: list[str],
    what: str,
    *,
    timeout_s: float | None = None,
    cancel: threading.Event | None = None,
) -> subprocess.CompletedProcess[str]:
    flags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
    deadline = None if timeout_s is None else time.monotonic() + timeout_s
    with subprocess.Popen(
        command,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
        creationflags=flags,
    ) as proc:
        try:
            while True:
                if cancel is not None and cancel.is_set():
                    raise ExtractCancelled(f"{what} was cancelled")
                wait = _POLL_S
                if deadline is not None:
                    wait = min(wait, deadline - time.monotonic())
                    if wait <= 0:
                        raise AudioError(f"{what} did not finish in {timeout_s:g} s; stopped it")
                try:
                    out, err = proc.communicate(timeout=wait)
                except subprocess.TimeoutExpired:
                    continue
                return subprocess.CompletedProcess(command, proc.returncode, out, err)
        except BaseException:
            proc.kill()
            raise


def _stamp_path(wav: Path) -> Path:
    return wav.with_name(wav.name + ".src.json")


def _source_stamp(video: Path) -> dict[str, int]:
    stat = video.stat()
    return {"version": _STAMP_VERSION, "size": stat.st_size, "mtime_ns": stat.st_mtime_ns}


def _wav_layout(wav: Path) -> tuple[int, int]:
    """Frame count and the file size the header promises, for a 16 kHz mono 16-bit wav."""
    try:
        with wave.open(str(wav), "rb") as reader:
            if (reader.getframerate(), reader.getnchannels(), reader.getsampwidth()) != (
                SAMPLE_RATE,
                1,
                2,
            ):
                raise AudioError(f"{wav} is not 16 kHz mono 16-bit PCM")
            frames = reader.getnframes()
        with wav.open("rb") as handle:
            handle.seek(12)
            while len(header := handle.read(8)) == 8:
                chunk_id, size = struct.unpack("<4sI", header)
                if chunk_id == b"data":
                    return frames, handle.tell() + size
                handle.seek(size + (size & 1), os.SEEK_CUR)
    except (wave.Error, EOFError, struct.error) as exc:
        raise AudioError(f"{wav} is not a readable wav file: {exc}") from exc
    raise AudioError(f"{wav} is not a readable wav file: no data chunk")


def wav_duration_ms(wav: Path) -> int:
    """Length of a 16 kHz mono 16-bit wav. Raises AudioError for any other or a cut-short file."""
    frames, promised = _wav_layout(wav)
    actual = wav.stat().st_size
    if actual < promised:
        raise AudioError(f"{wav} is cut short: {actual} bytes, its header promises {promised}")
    return frames * 1000 // SAMPLE_RATE


def _cached_duration_ms(wav: Path, stamp: dict[str, int]) -> int | None:
    try:
        if json.loads(read_text_file(_stamp_path(wav))) != stamp:
            return None
        frames, promised = _wav_layout(wav)
        return frames * 1000 // SAMPLE_RATE if wav.stat().st_size == promised else None
    except (OSError, ValueError, AudioError):
        return None


def _stderr_tail(proc: subprocess.CompletedProcess[str]) -> str:
    return proc.stderr.strip()[-_STDERR_TAIL_CHARS:]


def _require_audio_stream(video: Path, ffprobe: Path, cancel: threading.Event | None) -> None:
    proc = _run(
        [
            str(ffprobe),
            "-v",
            "error",
            "-select_streams",
            "a:0",
            "-show_entries",
            "stream=codec_type",
            "-of",
            "csv=p=0",
            str(video.absolute()),
        ],
        f"ffprobe on {video.name}",
        timeout_s=_PROBE_TIMEOUT_S,
        cancel=cancel,
    )
    if proc.returncode != 0:
        raise AudioError(f"ffprobe could not read {video.name}: {_stderr_tail(proc)}")
    if not proc.stdout.strip():
        raise NoAudioStreamError(f"{video.name} has no audio track")


def _ffmpeg_failure(video: Path, proc: subprocess.CompletedProcess[str]) -> AudioError:
    detail = _stderr_tail(proc) or "no error output, so it was probably killed or ran out of memory"
    return AudioError(f"ffmpeg stopped on {video.name} (exit code {proc.returncode}): {detail}")


def _flush_to_disk(path: Path) -> None:
    with path.open("rb+") as handle:
        os.fsync(handle.fileno())


def extract(
    video: Path,
    wav: Path,
    *,
    tool_dir: Path | None = None,
    timeout_s: float | None = DEFAULT_EXTRACT_TIMEOUT_S,
    cancel: threading.Event | None = None,
) -> ExtractResult:
    """Write `video`'s first audio track to `wav` as 16 kHz mono 16-bit PCM.

    A sidecar `<wav>.src.json` records the video's size and mtime as they were before
    ffmpeg started. The call returns early when the wav is intact and the stamp still
    matches. The wav appears only when complete. ffmpeg is killed and the partial file
    removed when `timeout_s` passes (AudioError) or `cancel` is set (ExtractCancelled).
    """
    if not video.is_file():
        raise FileNotFoundError(f"video not found: {video}")
    stamp = _source_stamp(video)
    cached = _cached_duration_ms(wav, stamp)
    if cached is not None:
        log.info("skip extract: %s is up to date for %s", wav.name, video.name)
        return ExtractResult(wav, cached, skipped=True)

    ffmpeg = find_tool("ffmpeg", tool_dir)
    ffprobe = find_tool("ffprobe", tool_dir)
    _require_audio_stream(video, ffprobe, cancel)
    wav.parent.mkdir(parents=True, exist_ok=True)
    partial = wav.with_name(f".{wav.name}.partial")
    started = time.perf_counter()
    try:
        proc = _run(
            [
                str(ffmpeg),
                "-y",
                "-nostdin",
                "-v",
                "error",
                "-i",
                str(video.absolute()),
                "-map",
                "0:a:0",
                "-vn",
                "-ac",
                "1",
                "-ar",
                str(SAMPLE_RATE),
                "-c:a",
                "pcm_s16le",
                "-f",
                "wav",
                str(partial.absolute()),
            ],
            f"ffmpeg on {video.name}",
            timeout_s=timeout_s,
            cancel=cancel,
        )
        if proc.returncode != 0:
            raise _ffmpeg_failure(video, proc)
        duration_ms = wav_duration_ms(partial)
        _flush_to_disk(partial)
        os.replace(partial, wav)
    finally:
        partial.unlink(missing_ok=True)
    write_text_file(_stamp_path(wav), json.dumps(stamp))
    log.info("extracted %s in %.1fs", wav.name, time.perf_counter() - started)
    return ExtractResult(wav, duration_ms, skipped=False)
