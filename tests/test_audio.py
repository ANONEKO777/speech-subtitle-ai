import logging
import os
import shutil
import subprocess
import sys
import threading
import time
import wave
from pathlib import Path
from typing import Any

import numpy as np
import pytest

from backend.core import audio
from backend.core.audio import (
    SAMPLE_RATE,
    TOOL_DIR_ENV,
    AudioError,
    ExtractCancelled,
    NoAudioStreamError,
    extract,
    find_tool,
    wav_duration_ms,
)

CLIP_SECONDS = 3


def _ffmpeg(*args: str) -> None:
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-nostdin", *args], check=True)


@pytest.fixture(scope="module")
def video(ffmpeg_tools: None, tmp_path_factory: pytest.TempPathFactory) -> Path:
    path = tmp_path_factory.mktemp("media") / "talk.mp4"
    _ffmpeg(
        *("-f", "lavfi", "-i", f"sine=frequency=440:duration={CLIP_SECONDS}:sample_rate=44100"),
        *("-f", "lavfi", "-i", f"color=c=black:s=64x64:r=10:d={CLIP_SECONDS}"),
        *("-ac", "2", "-c:v", "mpeg4", "-c:a", "aac", "-shortest", str(path)),
    )
    return path


@pytest.fixture(scope="module")
def silent_video(ffmpeg_tools: None, tmp_path_factory: pytest.TempPathFactory) -> Path:
    path = tmp_path_factory.mktemp("media") / "no-audio.mp4"
    _ffmpeg(
        *("-f", "lavfi", "-i", f"color=c=black:s=64x64:r=10:d={CLIP_SECONDS}"),
        *("-c:v", "mpeg4", "-an", str(path)),
    )
    return path


def _assert_16k_mono(wav: Path) -> None:
    with wave.open(str(wav), "rb") as reader:
        assert (reader.getframerate(), reader.getnchannels(), reader.getsampwidth()) == (
            SAMPLE_RATE,
            1,
            2,
        )
    assert abs(wav_duration_ms(wav) - CLIP_SECONDS * 1000) < 100


def test_extract_writes_16k_mono_wav_matching_the_video_length(video: Path, tmp_path: Path) -> None:
    result = extract(video, tmp_path / "audio.wav")
    assert result.skipped is False
    assert result.duration_ms == wav_duration_ms(result.wav)
    _assert_16k_mono(result.wav)
    assert sorted(p.name for p in tmp_path.iterdir()) == ["audio.wav", "audio.wav.src.json"]


def test_extract_skips_when_the_output_is_current(
    video: Path, tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    wav = tmp_path / "audio.wav"
    first = extract(video, wav)
    before = wav.stat().st_mtime_ns
    with caplog.at_level(logging.INFO, logger="backend.core.audio"):
        started = time.perf_counter()
        second = extract(video, wav)
        elapsed = time.perf_counter() - started
    assert second.skipped is True and second.duration_ms == first.duration_ms
    assert wav.stat().st_mtime_ns == before
    assert elapsed < 1
    assert any("skip extract" in record.message for record in caplog.records)


def test_extract_runs_again_when_the_video_changes(video: Path, tmp_path: Path) -> None:
    copy = tmp_path / "copy.mp4"
    shutil.copy(video, copy)
    wav = tmp_path / "audio.wav"
    assert extract(copy, wav).skipped is False
    os.utime(copy, ns=(1_000_000_000, 1_000_000_000))
    assert extract(copy, wav).skipped is False
    assert extract(copy, wav).skipped is True


def test_extract_runs_again_when_the_wav_is_truncated(video: Path, tmp_path: Path) -> None:
    wav = tmp_path / "audio.wav"
    extract(video, wav)
    wav.write_bytes(wav.read_bytes()[:30])
    result = extract(video, wav)
    assert result.skipped is False
    _assert_16k_mono(wav)


def test_extract_runs_again_when_the_stamp_is_missing_or_garbled(
    video: Path, tmp_path: Path
) -> None:
    wav = tmp_path / "audio.wav"
    extract(video, wav)
    stamp = tmp_path / "audio.wav.src.json"
    stamp.write_text("{not json", encoding="utf-8")
    assert extract(video, wav).skipped is False
    stamp.unlink()
    assert extract(video, wav).skipped is False


def test_extract_reports_a_video_without_an_audio_track(silent_video: Path, tmp_path: Path) -> None:
    with pytest.raises(NoAudioStreamError, match=r"no-audio\.mp4 has no audio track"):
        extract(silent_video, tmp_path / "audio.wav")
    assert list(tmp_path.iterdir()) == []


def test_extract_handles_cjk_and_spaces_in_the_path(video: Path, tmp_path: Path) -> None:
    folder = tmp_path / "專案 資料夾"
    folder.mkdir()
    cjk_video = folder / "一個人指揮 50 多個 Agent.mp4"
    shutil.copy(video, cjk_video)
    result = extract(cjk_video, folder / "輸出 音訊.wav")
    _assert_16k_mono(result.wav)


def test_extract_recovers_from_a_leftover_partial_file(video: Path, tmp_path: Path) -> None:
    wav = tmp_path / "audio.wav"
    partial = tmp_path / ".audio.wav.partial"
    partial.write_bytes(b"RIFF half written")
    result = extract(video, wav)
    assert result.skipped is False
    _assert_16k_mono(wav)
    assert not partial.exists()


def test_extract_creates_the_output_folder(video: Path, tmp_path: Path) -> None:
    result = extract(video, tmp_path / "project" / "cache" / "audio.wav")
    _assert_16k_mono(result.wav)


def test_extract_rejects_a_file_that_is_not_media(ffmpeg_tools: None, tmp_path: Path) -> None:
    junk = tmp_path / "notes.mp4"
    junk.write_bytes(b"this is not a video")
    with pytest.raises(AudioError, match=r"ffprobe could not read notes\.mp4") as info:
        extract(junk, tmp_path / "audio.wav")
    assert not isinstance(info.value, NoAudioStreamError)
    assert [p.name for p in tmp_path.iterdir()] == ["notes.mp4"]


def test_extract_reports_a_missing_video(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError, match="gone.mp4"):
        extract(tmp_path / "gone.mp4", tmp_path / "audio.wav")


def _fake_tool(folder: Path, name: str = "ffmpeg") -> Path:
    folder.mkdir(exist_ok=True)
    path = folder / (name + (".exe" if sys.platform == "win32" else ""))
    path.write_bytes(b"")
    path.chmod(0o755)
    return path


def test_find_tool_prefers_the_given_folder_over_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    given = _fake_tool(tmp_path / "given")
    monkeypatch.setenv("PATH", str(_fake_tool(tmp_path / "on_path").parent))
    monkeypatch.delenv(TOOL_DIR_ENV, raising=False)
    assert find_tool("ffmpeg", given.parent) == given


def test_find_tool_reads_the_environment_folder(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from_env = _fake_tool(tmp_path / "env")
    monkeypatch.setenv("PATH", str(_fake_tool(tmp_path / "on_path").parent))
    monkeypatch.setenv(TOOL_DIR_ENV, str(from_env.parent))
    assert find_tool("ffmpeg") == from_env


def test_find_tool_prefers_the_given_folder_over_the_environment_folder(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    given = _fake_tool(tmp_path / "given")
    monkeypatch.setenv(TOOL_DIR_ENV, str(_fake_tool(tmp_path / "env").parent))
    assert find_tool("ffmpeg", given.parent) == given


def test_find_tool_names_the_fix_when_ffmpeg_is_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("PATH", str(tmp_path))
    monkeypatch.delenv(TOOL_DIR_ENV, raising=False)
    with pytest.raises(AudioError, match=rf"ffmpeg was not found.*{TOOL_DIR_ENV}"):
        find_tool("ffmpeg")


def test_wav_duration_rejects_the_wrong_format(tmp_path: Path) -> None:
    stereo = tmp_path / "stereo.wav"
    with wave.open(str(stereo), "wb") as writer:
        writer.setnchannels(2)
        writer.setsampwidth(2)
        writer.setframerate(SAMPLE_RATE)
        writer.writeframes(b"\0" * 400)
    with pytest.raises(AudioError, match="16 kHz mono"):
        wav_duration_ms(stereo)
    (tmp_path / "junk.wav").write_bytes(b"nope")
    with pytest.raises(AudioError, match="not a readable wav"):
        wav_duration_ms(tmp_path / "junk.wav")


def test_wav_duration_rejects_a_wav_cut_short_after_its_header(tmp_path: Path) -> None:
    wav = tmp_path / "cut.wav"
    with wave.open(str(wav), "wb") as writer:
        writer.setnchannels(1)
        writer.setsampwidth(2)
        writer.setframerate(SAMPLE_RATE)
        writer.writeframes(b"\0" * 32_000)
    assert wav_duration_ms(wav) == 1000
    wav.write_bytes(wav.read_bytes()[:-10])
    with pytest.raises(AudioError, match="cut short"):
        wav_duration_ms(wav)


def test_extract_runs_again_when_the_cached_wav_lost_its_tail(video: Path, tmp_path: Path) -> None:
    wav = tmp_path / "audio.wav"
    extract(video, wav)
    wav.write_bytes(wav.read_bytes()[:-10])
    assert extract(video, wav).skipped is False
    assert extract(video, wav).skipped is True


def test_extract_runs_again_when_the_video_changes_size_but_not_mtime(
    video: Path, tmp_path: Path
) -> None:
    copy = tmp_path / "copy.mp4"
    shutil.copy(video, copy)
    before = copy.stat().st_mtime_ns
    wav = tmp_path / "audio.wav"
    extract(copy, wav)
    with copy.open("ab") as handle:
        handle.write(b"\0" * 16)
    os.utime(copy, ns=(before, before))
    assert extract(copy, wav).skipped is False


def test_extract_accepts_relative_paths_that_start_with_a_dash(
    video: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    shutil.copy(video, tmp_path / "-dash.mp4")
    monkeypatch.chdir(tmp_path)
    result = extract(Path("-dash.mp4"), Path("-out.wav"))
    _assert_16k_mono(result.wav)


def test_extract_stamps_the_video_as_it_was_before_ffmpeg_ran(
    video: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    copy = tmp_path / "copy.mp4"
    shutil.copy(video, copy)
    wav = tmp_path / "audio.wav"
    module: Any = audio
    real_run = module._run

    def touch_while_ffmpeg_runs(command: list[str], what: str, **kwargs: Any) -> object:
        if what.startswith("ffmpeg"):
            os.utime(copy, ns=(5_000_000_000, 5_000_000_000))
        return real_run(command, what, **kwargs)

    monkeypatch.setattr(audio, "_run", touch_while_ffmpeg_runs)
    extract(copy, wav)
    monkeypatch.setattr(audio, "_run", real_run)
    assert extract(copy, wav).skipped is False


def test_extract_flushes_the_partial_file_to_disk_before_it_appears(
    video: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    events: list[str] = []
    real_fsync, real_replace = os.fsync, os.replace

    def fsync(fd: int) -> None:
        events.append("fsync")
        real_fsync(fd)

    def replace(src: Any, dst: Any) -> None:
        events.append(f"replace {Path(str(dst)).name}")
        real_replace(src, dst)

    monkeypatch.setattr(os, "fsync", fsync)
    monkeypatch.setattr(os, "replace", replace)
    extract(video, tmp_path / "audio.wav")
    assert events.index("fsync") < events.index("replace audio.wav")


def test_extract_stops_ffmpeg_when_the_timeout_passes(video: Path, tmp_path: Path) -> None:
    with pytest.raises(AudioError, match="did not finish in 0.01 s"):
        extract(video, tmp_path / "audio.wav", timeout_s=0.01)
    assert list(tmp_path.iterdir()) == []


def test_extract_can_be_cancelled(video: Path, tmp_path: Path) -> None:
    cancel = threading.Event()
    cancel.set()
    with pytest.raises(ExtractCancelled, match="cancelled"):
        extract(video, tmp_path / "audio.wav", cancel=cancel)
    assert list(tmp_path.iterdir()) == []


def _fake_ffmpeg(folder: Path, *, writes_partial: bool, exit_code: int, message: str) -> None:
    folder.mkdir()
    if sys.platform == "win32":
        lines = ["@echo off", 'for %%a in (%*) do set "last=%%~a"']
        if writes_partial:
            lines.append('echo half written> "%last%"')
        if message:
            lines.append(f"echo {message} 1>&2")
        lines.append(f"exit /b {exit_code}")
        (folder / "ffmpeg.cmd").write_text("\r\n".join(lines) + "\r\n", encoding="ascii")
        return
    lines = ["#!/bin/sh", "for last; do :; done"]
    if writes_partial:
        lines.append('echo half written > "$last"')
    if message:
        lines.append(f"echo {message} >&2")
    lines.append(f"exit {exit_code}")
    script = folder / "ffmpeg"
    script.write_text("\n".join(lines) + "\n", encoding="ascii")
    script.chmod(0o755)


def test_a_killed_ffmpeg_is_reported_with_its_exit_code_and_leaves_no_files(
    video: Path, tmp_path: Path
) -> None:
    tools = tmp_path / "tools"
    _fake_ffmpeg(tools, writes_partial=True, exit_code=137, message="")
    out = tmp_path / "out"
    out.mkdir()
    with pytest.raises(AudioError, match=r"ffmpeg stopped on talk\.mp4 \(exit code 137\).*killed"):
        extract(video, out / "audio.wav", tool_dir=tools)
    assert list(out.iterdir()) == []


def test_an_ffmpeg_error_message_is_passed_on(video: Path, tmp_path: Path) -> None:
    tools = tmp_path / "tools"
    _fake_ffmpeg(tools, writes_partial=False, exit_code=1, message="Invalid data found")
    with pytest.raises(AudioError, match="Invalid data found"):
        extract(video, tmp_path / "audio.wav", tool_dir=tools)


def test_extract_takes_the_first_audio_track(ffmpeg_tools: None, tmp_path: Path) -> None:
    media = tmp_path / "two-tracks.mkv"
    _ffmpeg(
        *("-f", "lavfi", "-i", f"sine=frequency=440:duration={CLIP_SECONDS}:sample_rate=44100"),
        *("-f", "lavfi", "-i", f"sine=frequency=1760:duration={CLIP_SECONDS}:sample_rate=44100"),
        *("-map", "0:a", "-map", "1:a", "-c:a", "aac", str(media)),
    )
    result = extract(media, tmp_path / "audio.wav")
    with wave.open(str(result.wav), "rb") as reader:
        samples = np.frombuffer(reader.readframes(reader.getnframes()), dtype="<i2")
    spectrum = np.abs(np.fft.rfft(samples.astype(np.float64)))
    assert abs(int(spectrum.argmax()) * SAMPLE_RATE / len(samples) - 440) < 20
