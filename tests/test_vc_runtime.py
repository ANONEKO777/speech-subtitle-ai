"""A PC without the Visual C++ runtime gets a plain message before a downloaded program starts."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from backend.core import vc_runtime
from backend.engines.base import EngineUnavailableError
from backend.llm.local_server import LlamaServer, ServerError
from backend.manager.selftest import ProbeFailed, _run  # pyright: ignore[reportPrivateUsage]


def refuse_to_start(monkeypatch: pytest.MonkeyPatch) -> None:
    def popen(*_a: object, **_k: object) -> None:
        raise AssertionError("a program was started on a PC without the runtime")

    monkeypatch.setattr(subprocess, "Popen", popen)


def test_missing_lists_what_system32_lacks(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    system32 = tmp_path / "System32"
    system32.mkdir()
    (system32 / "vcruntime140.dll").write_bytes(b"")
    monkeypatch.setattr(vc_runtime.sys, "platform", "win32")
    monkeypatch.setenv("SystemRoot", str(tmp_path))
    assert vc_runtime.missing() == ("vcruntime140_1.dll", "msvcp140.dll")


def test_nothing_is_missing_when_all_three_are_there(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    system32 = tmp_path / "System32"
    system32.mkdir()
    for name in vc_runtime.LIBRARIES:
        (system32 / name).write_bytes(b"")
    monkeypatch.setattr(vc_runtime.sys, "platform", "win32")
    monkeypatch.setenv("SystemRoot", str(tmp_path))
    assert vc_runtime.missing() == ()


def test_the_message_names_the_download_and_no_dll_code():
    assert vc_runtime.NOTICE.code == "runtime.vcMissing"
    assert vc_runtime.INFO_URL in vc_runtime.NOTICE.message
    assert "vc_redist.x64.exe" in vc_runtime.NOTICE.message
    assert "0xC0000135" not in vc_runtime.NOTICE.message


def test_the_self_test_stops_before_starting_anything(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("VST_SIMULATE_NO_VCRUNTIME", "1")
    refuse_to_start(monkeypatch)
    with pytest.raises(ProbeFailed, match="Visual C"):
        _run(["whisper-cli.exe"], 1.0)


def test_the_llm_server_stops_before_starting_anything(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    exe, gguf = tmp_path / "llama-server.exe", tmp_path / "m.gguf"
    exe.write_bytes(b"")
    gguf.write_bytes(b"")
    monkeypatch.setenv("VST_SIMULATE_NO_VCRUNTIME", "1")
    refuse_to_start(monkeypatch)
    with (
        pytest.raises(ServerError, match="Visual C"),
        LlamaServer(exe, gguf, log_path=tmp_path / "log"),
    ):
        pass


@pytest.mark.parametrize("error", [EngineUnavailableError, ServerError, ProbeFailed])
def test_the_error_types_are_what_each_caller_already_handles(
    monkeypatch: pytest.MonkeyPatch, error: type[Exception]
):
    monkeypatch.setenv("VST_SIMULATE_NO_VCRUNTIME", "1")
    with pytest.raises(error, match="Visual C"):
        vc_runtime.require(error)
