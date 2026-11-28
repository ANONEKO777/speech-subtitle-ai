"""Pictures and video made from a project's media with ffmpeg: a thumbnail, a still with the
subtitle burned in, and a clip or whole video with it burned in.

The subtitle goes in through libass from a temporary `.ass` file that ffmpeg reads from its own
working folder, so no Windows path ever sits inside the filter string. The input is seeked before
it is read, which restarts ffmpeg's clock at zero, so the cues are shifted by the start time (and
the person's subtitle offset) before the file is written.
"""

from __future__ import annotations

import functools
import os
import subprocess
import sys
import tempfile
import threading
import time
import uuid
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from backend.core import process_guard
from backend.core.audio import AudioError, find_tool
from backend.core.languages import Wrap
from backend.core.model import Cue
from backend.core.notices import (
    NO_H264_MACOS,
    NO_H264_WINDOWS,
    PLAYER_BURN_BUSY,
    PLAYER_BURN_FAILED,
    PLAYER_STILL_FAILED,
    PLAYER_THUMBNAIL_FAILED,
    Notice,
    Template,
    noticed,
    notices_of,
)
from backend.core.playback import shift_cues
from backend.core.subtitle_io import BurnMode, render_burn_ass, write_text_file

CRF = 20
PRESET = "veryfast"
THUMB_WIDTH = 320
MIN_FPS = 5.0
MAX_FPS = 240.0
_MP4_AUDIO = frozenset({"aac", "mp3", "ac3", "eac3", "alac"})
_FLAGS = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
_MF_QUALITY = "75"
_VT_QUALITY = "65"
"""VideoToolbox `-q:v` (0 to 100). A first guess, not a measured value (P37d)."""


_PROBE_TIMEOUT_S = 20


class EncoderMissing(AudioError):
    """Burn-in cannot run because this PC has no usable H.264 encoder."""


def _h264_mf_works(ffmpeg: str) -> bool:
    """Encodes one frame to the null device. `-encoders` lists h264_mf even where Windows has no
    H.264 encoder, so only an encode shows whether it is there."""
    return _one_frame_encodes(
        ffmpeg, ("-c:v", "h264_mf", "-rate_control", "quality", "-quality", _MF_QUALITY)
    )


def _one_frame_encodes(ffmpeg: str, codec_args: tuple[str, ...]) -> bool:
    if os.environ.get("VST_SIMULATE_NO_H264"):
        return False
    try:
        probe = subprocess.run(  # noqa: S603
            [
                ffmpeg,
                "-hide_banner",
                "-v",
                "error",
                "-nostdin",
                "-f",
                "lavfi",
                "-i",
                "color=c=black:s=128x128:r=1",
                "-frames:v",
                "1",
                *codec_args,
                "-pix_fmt",
                "yuv420p",
                "-f",
                "null",
                os.devnull,
            ],  # fmt: skip
            stdin=subprocess.DEVNULL,
            capture_output=True,
            timeout=_PROBE_TIMEOUT_S,
            creationflags=_FLAGS,
        )
    except (subprocess.TimeoutExpired, OSError):
        return False
    return probe.returncode == 0


@functools.cache
def _video_encoder(ffmpeg: str, system: str | None = None) -> tuple[str, ...]:
    """libx264 where this ffmpeg has it. The LGPL ffmpeg the installer ships has no x264 (it is
    GPL), so it uses the H.264 encoder that comes with Windows, tried once before the first burn.
    On a Mac it is VideoToolbox, tried the same way. `system` is a `sys.platform` value.
    Raises EncoderMissing, which is not cached, so a fix on the PC works without a restart."""
    try:
        listed = subprocess.run(  # noqa: S603
            [ffmpeg, "-hide_banner", "-encoders"],
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            timeout=_PROBE_TIMEOUT_S,
            creationflags=_FLAGS,
        ).stdout
    except subprocess.TimeoutExpired:
        listed = ""
    if " libx264 " in listed:
        return ("-c:v", "libx264", "-preset", PRESET, "-crf", str(CRF))
    if (sys.platform if system is None else system) == "darwin":
        videotoolbox = ("-c:v", "h264_videotoolbox", "-q:v", _VT_QUALITY)
        if " h264_videotoolbox " in listed and _one_frame_encodes(ffmpeg, videotoolbox):
            return videotoolbox
        raise noticed(EncoderMissing, NO_H264_MACOS())
    if not _h264_mf_works(ffmpeg):
        raise noticed(EncoderMissing, NO_H264_WINDOWS())
    return ("-c:v", "h264_mf", "-rate_control", "quality", "-quality", _MF_QUALITY)


BurnState = Literal["running", "done", "failed", "cancelled"]


@dataclass(frozen=True, slots=True)
class SubtitleLook:
    """How burned subtitles look. `size_ratio` is the font height over the picture height."""

    mode: BurnMode
    zh_first: bool
    size_ratio: float
    color: str
    source_font: str = "Arial"
    target_font: str = "Microsoft JhengHei"


def _ass_file(
    folder: Path, cues: Sequence[Cue], wrap: Wrap, look: SubtitleLook, shift_ms: int
) -> None:
    text = render_burn_ass(
        shift_cues(cues, shift_ms),
        wrap,
        mode=look.mode,
        zh_first=look.zh_first,
        size_ratio=look.size_ratio,
        color=look.color,
        source_font=look.source_font,
        target_font=look.target_font,
    )
    write_text_file(folder / "sub.ass", text)


def _run(command: list[str], cwd: Path | None, failed: Template, video: Path) -> None:
    proc = subprocess.run(  # noqa: S603
        command,
        cwd=cwd,
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        creationflags=_FLAGS,
        timeout=120,
        check=False,
    )
    if proc.returncode != 0:
        said = failed(video=video.name, output=proc.stderr.strip()[-400:])
        raise noticed(AudioError, said)


def thumbnail(video: Path, at_s: float, out: Path) -> None:
    """A JPEG about `THUMB_WIDTH` wide of the frame at `at_s`."""
    partial = out.with_name(f".{out.stem}.{uuid.uuid4().hex}.tmp.jpg")
    try:
        _run(
            [
                str(find_tool("ffmpeg")),
                "-y",
                "-nostdin",
                "-v",
                "error",
                "-ss",
                f"{at_s:.3f}",
                "-i",
                str(video.absolute()),
                "-frames:v",
                "1",
                "-vf",
                f"scale={THUMB_WIDTH}:-2",
                "-q:v",
                "4",
                str(partial),
            ],
            None,
            PLAYER_THUMBNAIL_FAILED,
            video,
        )
        os.replace(partial, out)
    finally:
        partial.unlink(missing_ok=True)


def still(
    video: Path,
    at_s: float,
    out: Path,
    *,
    burn: tuple[Sequence[Cue], Wrap, SubtitleLook, int] | None,
) -> None:
    """The frame at `at_s` as a PNG at the video's own size. `burn` is the cues, their wrap, the
    look and the person's subtitle offset, when the subtitle goes into the picture."""
    command = [
        str(find_tool("ffmpeg")),
        "-y",
        "-nostdin",
        "-v",
        "error",
        "-ss",
        f"{at_s:.3f}",
        "-i",
        str(video.absolute()),
        "-frames:v",
        "1",
    ]
    with tempfile.TemporaryDirectory(prefix="vst-still-") as tmp:
        folder = Path(tmp)
        if burn is not None:
            cues, wrap, look, offset_ms = burn
            _ass_file(folder, cues, wrap, look, offset_ms - round(at_s * 1000))
            command += ["-vf", "ass=sub.ass"]
        partial = out.with_name(f".{out.stem}.{uuid.uuid4().hex}.tmp.png")
        try:
            _run([*command, str(partial)], folder, PLAYER_STILL_FAILED, video)
            os.replace(partial, out)
        finally:
            partial.unlink(missing_ok=True)


def _audio_codec(video: Path) -> str:
    try:
        proc = subprocess.run(  # noqa: S603
            [
                str(find_tool("ffprobe")),
                "-v",
                "error",
                "-select_streams",
                "a:0",
                "-show_entries",
                "stream=codec_name",
                "-of",
                "csv=p=0",
                str(video.absolute()),
            ],
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            creationflags=_FLAGS,
            timeout=30,
            check=False,
        )
    except (AudioError, subprocess.TimeoutExpired):
        return ""
    return proc.stdout.strip()


def parse_rate(text: str) -> float | None:
    """A frame rate ffprobe prints as `30000/1001`, or None when it is `0/0` or not a number."""
    num, _, den = text.strip().partition("/")
    try:
        value = float(num) / float(den or 1)
    except (ValueError, ZeroDivisionError):
        return None
    return value if MIN_FPS <= value <= MAX_FPS else None


def frame_rate(video: Path) -> float | None:
    """The frames per second one step of the player should move by: the stream's base rate
    (`r_frame_rate`, the tick every timestamp is a multiple of, so a variable-rate stream steps by
    its shortest frame), else its average. None when ffprobe cannot tell."""
    try:
        proc = subprocess.run(  # noqa: S603
            [
                str(find_tool("ffprobe")),
                "-v",
                "error",
                "-select_streams",
                "v:0",
                "-show_entries",
                "stream=r_frame_rate,avg_frame_rate",
                "-of",
                "csv=p=0",
                str(video.absolute()),
            ],
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            creationflags=_FLAGS,
            timeout=30,
            check=False,
        )
    except (AudioError, subprocess.TimeoutExpired):
        return None
    for field_ in proc.stdout.strip().split(","):
        if (rate := parse_rate(field_)) is not None:
            return rate
    return None


@dataclass(slots=True)
class BurnJob:
    id: str
    output: Path
    state: BurnState = "running"
    percent: float = 0.0
    error: str | None = None
    error_notices: tuple[Notice, ...] = ()
    started: float = 0.0
    finished: float | None = None
    cancel: threading.Event = field(default_factory=threading.Event)


class BurnBook:
    """The burn-in exports of this run of the service, one at a time. A job's ffmpeg is a child
    of the service, so shutting down cancels it."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._jobs: dict[str, BurnJob] = {}
        self._threads: list[threading.Thread] = []

    def get(self, job_id: str) -> BurnJob | None:
        with self._lock:
            return self._jobs.get(job_id)

    def running(self) -> BurnJob | None:
        with self._lock:
            return next((j for j in self._jobs.values() if j.state == "running"), None)

    def start(
        self,
        video: Path,
        out: Path,
        *,
        cues: Sequence[Cue],
        wrap: Wrap,
        look: SubtitleLook,
        offset_ms: int,
        start_s: float,
        duration_s: float,
        on_done: Callable[[BurnJob], None] | None = None,
    ) -> BurnJob:
        """Begin burning `duration_s` seconds from `start_s` into `out`. Refuses while another burn
        runs. The caller has chosen a free `out` name."""
        with self._lock:
            if any(j.state == "running" for j in self._jobs.values()):
                raise noticed(BurnBusy, PLAYER_BURN_BUSY())
            job = BurnJob(uuid.uuid4().hex[:12], out, started=time.monotonic())
            self._jobs[job.id] = job
            for old in [j for j in self._jobs.values() if j.state != "running"][:-20]:
                del self._jobs[old.id]
            thread = threading.Thread(
                target=self._run,
                args=(job, video, cues, wrap, look, offset_ms, start_s, duration_s, on_done),
                daemon=True,
            )
            self._threads.append(thread)
        thread.start()
        return job

    def cancel(self, job_id: str) -> bool:
        job = self.get(job_id)
        if job is None:
            return False
        job.cancel.set()
        return True

    def shutdown(self) -> None:
        with self._lock:
            jobs, threads = list(self._jobs.values()), list(self._threads)
        for job in jobs:
            job.cancel.set()
        for thread in threads:
            thread.join(timeout=10)

    def _finish(
        self,
        job: BurnJob,
        state: BurnState,
        error: str | None = None,
        notices: tuple[Notice, ...] = (),
    ) -> None:
        with self._lock:
            job.state, job.error, job.finished = state, error, time.monotonic()
            job.error_notices = notices
            if state == "done":
                job.percent = 100.0

    def _run(
        self,
        job: BurnJob,
        video: Path,
        cues: Sequence[Cue],
        wrap: Wrap,
        look: SubtitleLook,
        offset_ms: int,
        start_s: float,
        duration_s: float,
        on_done: Callable[[BurnJob], None] | None,
    ) -> None:
        partial = job.output.with_name(f".{job.output.stem}.{job.id}.part.mp4")
        try:
            with tempfile.TemporaryDirectory(prefix="vst-burn-") as tmp:
                folder = Path(tmp)
                _ass_file(folder, cues, wrap, look, offset_ms - round(start_s * 1000))
                self._encode(job, video, folder, partial, start_s, duration_s)
            if job.cancel.is_set():
                self._finish(job, "cancelled")
                return
            os.replace(partial, job.output)
            self._finish(job, "done")
            if on_done:
                on_done(job)
        except Exception as exc:  # noqa: BLE001
            self._finish(job, "failed", str(exc), notices_of(exc))
        finally:
            partial.unlink(missing_ok=True)

    def _encode(
        self,
        job: BurnJob,
        video: Path,
        folder: Path,
        partial: Path,
        start_s: float,
        duration_s: float,
    ) -> None:
        audio = (
            ["-c:a", "copy"]
            if _audio_codec(video) in _MP4_AUDIO
            else ["-c:a", "aac", "-b:a", "192k"]
        )
        ffmpeg = str(find_tool("ffmpeg"))
        command = [
            ffmpeg,
            "-y",
            "-nostdin",
            "-v",
            "error",
            "-progress",
            "pipe:1",
            "-nostats",
            "-ss",
            f"{start_s:.3f}",
            "-i",
            str(video.absolute()),
            "-t",
            f"{duration_s:.3f}",
            "-map",
            "0:v:0",
            "-map",
            "0:a:0?",
            "-vf",
            "ass=sub.ass",
            *_video_encoder(ffmpeg),
            "-pix_fmt",
            "yuv420p",
            *audio,
            "-movflags",
            "+faststart",
            str(partial.absolute()),
        ]
        with (
            tempfile.TemporaryFile("w+", encoding="utf-8", errors="replace") as errors,
            subprocess.Popen(  # noqa: S603
                command,
                cwd=folder,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=errors,
                text=True,
                encoding="utf-8",
                errors="replace",
                creationflags=_FLAGS,
            ) as proc,
        ):
            process_guard.adopt(proc)
            stop = threading.Thread(target=self._kill_on_cancel, args=(job, proc), daemon=True)
            stop.start()
            assert proc.stdout is not None
            for line in proc.stdout:
                key, _, value = line.strip().partition("=")
                if key == "out_time_us" and value.isdigit() and duration_s > 0:
                    job.percent = min(99.0, int(value) / 1e6 / duration_s * 100)
            code = proc.wait()
            if job.cancel.is_set():
                return
            if code != 0:
                errors.seek(0)
                said = PLAYER_BURN_FAILED(output=errors.read().strip()[-400:])
                raise noticed(AudioError, said)

    @staticmethod
    def _kill_on_cancel(job: BurnJob, proc: subprocess.Popen[str]) -> None:
        while proc.poll() is None:
            if job.cancel.wait(0.2):
                proc.kill()
                return


class BurnBusy(Exception):
    """A burn-in export is already running."""
