from __future__ import annotations

import socket
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

import pytest

from backend.llm.local_server import HOST, LlamaServer, ServerError

FAKE = Path(__file__).parent / "fixtures" / "fake_llama_server.py"

pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="llama-server is Windows only here")


def make_exe(tmp_path: Path, extra: str = "") -> Path:
    exe = tmp_path / "llama-server.cmd"
    exe.write_text(f'@"{sys.executable}" "{FAKE}" {extra} %*\r\n', encoding="ascii")
    return exe


def make_gguf(tmp_path: Path) -> Path:
    path = tmp_path / "model.gguf"
    path.write_bytes(b"gguf")
    return path


def reachable(port: int) -> bool:
    with socket.socket() as probe:
        probe.settimeout(0.5)
        return probe.connect_ex((HOST, port)) == 0


def test_the_server_listens_on_loopback_only_and_stops_with_the_block(tmp_path: Path) -> None:
    server = LlamaServer(make_exe(tmp_path), make_gguf(tmp_path), log_path=tmp_path / "s.log")
    with server as running:
        assert running.base_url == f"http://127.0.0.1:{running.port}/v1"
        with urllib.request.urlopen(f"http://127.0.0.1:{running.port}/health", timeout=5) as reply:
            assert reply.status == 200
        assert reachable(running.port)
    deadline = time.monotonic() + 10
    while reachable(server.port) and time.monotonic() < deadline:
        time.sleep(0.1)
    assert not reachable(server.port)


def test_the_server_stops_when_the_block_raises(tmp_path: Path) -> None:
    server = LlamaServer(make_exe(tmp_path), make_gguf(tmp_path), log_path=tmp_path / "s.log")
    with pytest.raises(KeyError), server:
        raise KeyError("boom")
    deadline = time.monotonic() + 10
    while reachable(server.port) and time.monotonic() < deadline:
        time.sleep(0.1)
    assert not reachable(server.port)


def test_a_server_that_exits_at_once_is_reported_with_its_log(tmp_path: Path) -> None:
    server = LlamaServer(
        make_exe(tmp_path, "--die"), make_gguf(tmp_path), log_path=tmp_path / "s.log"
    )
    with pytest.raises(ServerError, match="exited with code 3"):
        server.__enter__()


def test_a_missing_program_or_model_names_the_path(tmp_path: Path) -> None:
    with pytest.raises(ServerError, match="llama-server not found"):
        LlamaServer(
            tmp_path / "nope.exe", make_gguf(tmp_path), log_path=tmp_path / "s.log"
        ).__enter__()
    with pytest.raises(ServerError, match="LLM model not found"):
        LlamaServer(
            make_exe(tmp_path), tmp_path / "nope.gguf", log_path=tmp_path / "s.log"
        ).__enter__()


def test_the_server_never_binds_beyond_loopback(tmp_path: Path) -> None:
    with LlamaServer(make_exe(tmp_path), make_gguf(tmp_path), log_path=tmp_path / "s.log") as s:
        outside = socket.gethostbyname(socket.gethostname())
        if outside.startswith("127."):
            pytest.skip("no non-loopback address on this machine")
        with pytest.raises((urllib.error.URLError, OSError)):
            urllib.request.urlopen(f"http://{outside}:{s.port}/health", timeout=2)


def test_the_server_stops_when_the_job_object_step_is_interrupted(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from backend.llm import local_server

    def interrupt(self: object, proc: object) -> None:
        raise KeyboardInterrupt

    monkeypatch.setattr(local_server._KillOnClose, "adopt", interrupt)  # pyright: ignore[reportPrivateUsage]
    server = LlamaServer(make_exe(tmp_path), make_gguf(tmp_path), log_path=tmp_path / "s.log")
    with pytest.raises(KeyboardInterrupt):
        server.__enter__()
    assert server._proc is None  # pyright: ignore[reportPrivateUsage]
