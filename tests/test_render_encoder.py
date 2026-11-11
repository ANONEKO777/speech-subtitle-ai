"""Burn-in picks libx264 only where the ffmpeg lists it; the LGPL build has no x264."""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

import pytest

from backend.core import render


def fake_encoders(monkeypatch: pytest.MonkeyPatch, listing: str) -> None:
    def run(*_args: Any, **_kwargs: Any) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess([], 0, stdout=listing)

    render._video_encoder.cache_clear()  # pyright: ignore[reportPrivateUsage]
    monkeypatch.setattr(render.subprocess, "run", run)


def test_x264_is_used_when_the_ffmpeg_has_it(monkeypatch: pytest.MonkeyPatch):
    fake_encoders(monkeypatch, " V....D libx264              libx264 H.264\n")
    args = render._video_encoder("ffmpeg-gpl")  # pyright: ignore[reportPrivateUsage]
    assert args[:2] == ("-c:v", "libx264")
    assert "-crf" in args


def test_the_windows_encoder_is_used_when_it_has_not(monkeypatch: pytest.MonkeyPatch):
    fake_encoders(
        monkeypatch,
        " V....D libopenh264         OpenH264\n V....D h264_mf  H264 via MediaFoundation\n",
    )
    args = render._video_encoder("ffmpeg-lgpl")  # pyright: ignore[reportPrivateUsage]
    assert args[:2] == ("-c:v", "h264_mf")
    assert "libx264" not in args


def fake_run(monkeypatch: pytest.MonkeyPatch, *, probe_code: int = 0, probe_hangs: bool = False):
    calls: list[list[str]] = []

    def run(command: list[str], **kwargs: Any) -> subprocess.CompletedProcess[Any]:
        calls.append(command)
        if "-encoders" in command:
            return subprocess.CompletedProcess(command, 0, stdout=" V....D h264_mf  H264 via MF\n")
        if probe_hangs:
            raise subprocess.TimeoutExpired(command, kwargs["timeout"])
        return subprocess.CompletedProcess(command, probe_code, stdout=b"", stderr=b"boom")

    render._video_encoder.cache_clear()  # pyright: ignore[reportPrivateUsage]
    monkeypatch.setattr(render.subprocess, "run", run)
    return calls


def test_the_windows_encoder_is_tried_once_on_one_frame_before_it_is_trusted(
    monkeypatch: pytest.MonkeyPatch,
):
    calls = fake_run(monkeypatch)
    render._video_encoder("ffmpeg-lgpl")  # pyright: ignore[reportPrivateUsage]
    render._video_encoder("ffmpeg-lgpl")  # pyright: ignore[reportPrivateUsage]
    probes = [c for c in calls if "-encoders" not in c]
    assert len(probes) == 1
    assert "-frames:v" in probes[0]
    assert probes[0][-3:-1] == ["-f", "null"]


@pytest.mark.parametrize("hang", [False, True])
def test_a_missing_or_hung_encoder_gives_a_plain_message(
    monkeypatch: pytest.MonkeyPatch, hang: bool
):
    fake_run(monkeypatch, probe_code=0 if hang else 1, probe_hangs=hang)
    with pytest.raises(render.EncoderMissing) as caught:
        render._video_encoder("ffmpeg-lgpl")  # pyright: ignore[reportPrivateUsage]
    assert str(caught.value) == render.NO_ENCODER_MESSAGE
    assert "ffmpeg" not in str(caught.value).lower()
    assert "媒體功能套件" in str(caught.value)


def test_the_simulation_seam_acts_like_a_missing_encoder(monkeypatch: pytest.MonkeyPatch):
    fake_run(monkeypatch)
    monkeypatch.setenv("VST_SIMULATE_NO_H264", "1")
    with pytest.raises(render.EncoderMissing):
        render._video_encoder("ffmpeg-lgpl")  # pyright: ignore[reportPrivateUsage]


def test_a_failed_preflight_is_not_remembered(monkeypatch: pytest.MonkeyPatch):
    fake_run(monkeypatch, probe_code=1)
    with pytest.raises(render.EncoderMissing):
        render._video_encoder("ffmpeg-lgpl")  # pyright: ignore[reportPrivateUsage]
    fake_run(monkeypatch, probe_code=0)
    assert render._video_encoder("ffmpeg-lgpl")[:2] == ("-c:v", "h264_mf")  # pyright: ignore[reportPrivateUsage]


def test_a_burn_on_such_a_pc_fails_with_the_plain_message(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    fake_run(monkeypatch, probe_code=1)

    def find_tool(_name: str) -> Path:
        return Path("ffmpeg-lgpl")

    def audio_codec(_video: Path) -> str:
        return "aac"

    monkeypatch.setattr(render, "find_tool", find_tool)
    monkeypatch.setattr(render, "_audio_codec", audio_codec)
    job = render.BurnJob.__new__(render.BurnJob)
    with pytest.raises(render.EncoderMissing, match="H.264"):
        render.BurnBook()._encode(  # pyright: ignore[reportPrivateUsage]
            job, tmp_path / "v.mp4", tmp_path, tmp_path / "o.mp4", 0.0, 1.0
        )
