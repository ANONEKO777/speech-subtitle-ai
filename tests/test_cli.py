from __future__ import annotations

import sys
from pathlib import Path

import pytest
from test_pipeline import SETTINGS, Fakes

from backend import cli
from backend.core.pipeline import Ports, Settings
from backend.manager.resolve import Request


def fake_resolve(fakes: Fakes) -> object:
    def resolve(request: Request, folder: Path) -> tuple[Settings, Ports]:
        return SETTINGS, fakes.ports()

    return resolve


def test_a_missing_input_exits_non_zero_and_names_the_path(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    missing = tmp_path / "no such talk.mp4"
    assert cli.main([str(missing)]) == 2
    assert str(missing) in capsys.readouterr().err


def test_help_documents_every_option(capsys: pytest.CaptureFixture[str]) -> None:
    parser = cli.build_parser()
    with pytest.raises(SystemExit) as stop:
        cli.main(["--help"])
    assert stop.value.code == 0
    text = capsys.readouterr().out
    for action in parser._actions:  # pyright: ignore[reportPrivateUsage]
        assert action.help, f"{action.dest} has no help text"
        assert action.option_strings or action.dest == "input"
        for flag in action.option_strings:
            assert flag in text


def test_a_run_writes_the_project_folder_and_prints_the_timing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    video = tmp_path / "演講 talk.mp4"
    video.write_bytes(b"video")
    monkeypatch.setattr(cli, "resolve", fake_resolve(Fakes()))
    assert cli.main([str(video)]) == 0
    folder = tmp_path / "演講 talk.vst"
    for name in ("en.srt", "zh-TW.srt", "bilingual.ass", "summary.md", "project.json"):
        assert (folder / name).is_file(), name
    out = capsys.readouterr().out
    assert "overhead" in out and "total" in out


def test_a_second_command_skips_everything(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    video = tmp_path / "talk.mp4"
    video.write_bytes(b"video")
    monkeypatch.setattr(cli, "resolve", fake_resolve(Fakes()))
    assert cli.main([str(video)]) == 0
    capsys.readouterr()
    assert cli.main([str(video)]) == 0
    assert capsys.readouterr().out.count("cached") == 7


def test_ctrl_c_exits_130_and_the_rerun_finishes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    video = tmp_path / "talk.mp4"
    video.write_bytes(b"video")
    monkeypatch.setattr(cli, "resolve", fake_resolve(Fakes(transcribe_error=KeyboardInterrupt())))
    assert cli.main([str(video)]) == 130
    monkeypatch.setattr(cli, "resolve", fake_resolve(Fakes()))
    assert cli.main([str(video)]) == 0
    assert (tmp_path / "talk.vst" / "summary.md").is_file()


def test_a_step_failure_exits_1(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    video = tmp_path / "talk.mp4"
    video.write_bytes(b"video")
    monkeypatch.setattr(
        cli, "resolve", fake_resolve(Fakes(transcribe_error=RuntimeError("engine blew up")))
    )
    assert cli.main([str(video)]) == 1


def test_unknown_engine_and_missing_programs_are_usage_errors_that_name_the_problem(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    video = tmp_path / "talk.mp4"
    video.write_bytes(b"video")
    assert cli.main([str(video), "--engine", "nope", "--user-data", str(tmp_path)]) == 2
    assert "unknown ASR engine" in capsys.readouterr().err
    assert cli.main([str(video), "--user-data", str(tmp_path / "empty")]) == 2
    assert "not found" in capsys.readouterr().err


def test_a_url_llm_needs_a_model_name(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    video = tmp_path / "talk.mp4"
    video.write_bytes(b"video")
    fake = tmp_path / "fake.bin"
    fake.write_bytes(b"x")
    args = [
        str(video), "--llm", "http://127.0.0.1:11434/v1",
        "--asr-bin", str(fake), "--asr-model", str(fake), "--vad-model", str(fake),
    ]  # fmt: skip
    assert cli.main(args) == 2
    assert "--llm-model is required" in capsys.readouterr().err


def test_python_dash_m_prints_help() -> None:
    import subprocess

    done = subprocess.run(
        [sys.executable, "-m", "backend.cli", "--help"], capture_output=True, check=False
    )
    assert done.returncode == 0
    assert b"--llm" in done.stdout
