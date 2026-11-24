from __future__ import annotations

import logging
import socket
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path
from types import TracebackType

from backend.core import vc_runtime
from backend.core.process_guard import KillOnClose

log = logging.getLogger(__name__)

HOST = "127.0.0.1"
ALL_LAYERS = 99
"""`-ngl` value that puts every layer on the GPU; 0 keeps the model on the CPU."""
NO_THINK = {"chat_template_kwargs": {"enable_thinking": False}}
_STOP_WAIT_S = 10.0


class ServerError(RuntimeError):
    """llama-server did not start, or stopped by itself."""


def free_port() -> int:
    with socket.socket() as probe:
        probe.bind((HOST, 0))
        return int(probe.getsockname()[1])


class LlamaServer:
    """A `llama-server` bound to 127.0.0.1 on a free port, for the length of a `with` block.

    It stops on exit, on an exception and on Ctrl+C, and a Windows job object stops it if this
    process is killed."""

    def __init__(
        self,
        exe: Path,
        gguf: Path,
        *,
        log_path: Path,
        ctx: int = 8192,
        gpu_layers: int = ALL_LAYERS,
        startup_timeout_s: float = 300.0,
        cancel: threading.Event | None = None,
    ) -> None:
        self.exe, self.gguf, self.log_path = exe, gguf, log_path
        self.ctx, self.gpu_layers = ctx, gpu_layers
        self.startup_timeout_s, self.cancel = startup_timeout_s, cancel
        self.port = 0
        self._proc: subprocess.Popen[bytes] | None = None
        self._job: KillOnClose | None = None

    @property
    def base_url(self) -> str:
        return f"http://{HOST}:{self.port}/v1"

    def __enter__(self) -> LlamaServer:
        for label, path in (("llama-server", self.exe), ("LLM model", self.gguf)):
            if not path.is_file():
                raise ServerError(f"{label} not found: {path}")
        vc_runtime.require(ServerError)
        self.port = free_port()
        command = [
            str(self.exe), "-m", str(self.gguf), "--host", HOST, "--port", str(self.port),
            "-ngl", str(self.gpu_layers), "-c", str(self.ctx), "-np", "1", "--no-webui",
        ]  # fmt: skip
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        flags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
        try:
            with self.log_path.open("wb") as sink:
                self._proc = subprocess.Popen(
                    command,
                    stdin=subprocess.DEVNULL,
                    stdout=sink,
                    stderr=subprocess.STDOUT,
                    creationflags=flags,
                )
        except OSError as exc:
            raise ServerError(f"cannot start {self.exe}: {exc}") from exc
        try:
            self._job = KillOnClose()
            self._job.adopt(self._proc)
            self._wait_healthy()
        except BaseException:
            self.stop()
            raise
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self.stop()

    def _wait_healthy(self) -> None:
        assert self._proc is not None
        deadline = time.monotonic() + self.startup_timeout_s
        url = f"http://{HOST}:{self.port}/health"
        while time.monotonic() < deadline:
            if self.cancel is not None and self.cancel.is_set():
                raise ServerError("cancelled while llama-server was starting")
            code = self._proc.poll()
            if code is not None:
                raise ServerError(f"llama-server exited with code {code}; see {self.log_path}")
            try:
                with urllib.request.urlopen(url, timeout=2) as response:
                    if response.status == 200:
                        return
            except (urllib.error.URLError, OSError):
                pass
            time.sleep(0.5)
        raise ServerError(
            f"llama-server was not ready after {self.startup_timeout_s:g} s; see {self.log_path}"
        )

    def stop(self) -> None:
        proc, self._proc = self._proc, None
        if proc is not None and proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=_STOP_WAIT_S)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=_STOP_WAIT_S)
        if self._job is not None:
            self._job.close()
            self._job = None
