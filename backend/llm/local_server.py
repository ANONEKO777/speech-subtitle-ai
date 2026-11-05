from __future__ import annotations

import ctypes
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

log = logging.getLogger(__name__)

HOST = "127.0.0.1"
NO_THINK = {"chat_template_kwargs": {"enable_thinking": False}}
_STOP_WAIT_S = 10.0
_JOB_EXTENDED_LIMIT_INFORMATION = 9
_JOB_KILL_ON_CLOSE = 0x2000
_PROCESS_TERMINATE = 0x0001
_PROCESS_SET_QUOTA = 0x0100


class ServerError(RuntimeError):
    """llama-server did not start, or stopped by itself."""


def free_port() -> int:
    with socket.socket() as probe:
        probe.bind((HOST, 0))
        return int(probe.getsockname()[1])


class _KillOnClose:
    """A Windows job object that kills its processes when the handle closes, which Windows does
    when this Python process dies for any reason, so a killed pipeline cannot leave a server
    holding the GPU."""

    def __init__(self) -> None:
        self._handle: int | None = None
        if sys.platform != "win32":
            return
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)  # pyright: ignore[reportAttributeAccessIssue]
        kernel32.CreateJobObjectW.restype = ctypes.c_void_p
        kernel32.OpenProcess.restype = ctypes.c_void_p
        kernel32.CloseHandle.argtypes = [ctypes.c_void_p]
        kernel32.AssignProcessToJobObject.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
        kernel32.SetInformationJobObject.argtypes = [
            ctypes.c_void_p,
            ctypes.c_int,
            ctypes.c_void_p,
            ctypes.c_uint32,
        ]
        job = kernel32.CreateJobObjectW(None, None)
        if not job:
            log.warning("no job object; a hard kill of the pipeline would leave llama-server up")
            return
        info = _limit_information()
        ok = kernel32.SetInformationJobObject(
            job, _JOB_EXTENDED_LIMIT_INFORMATION, ctypes.byref(info), ctypes.sizeof(info)
        )
        if not ok:
            kernel32.CloseHandle(ctypes.c_void_p(job))
            log.warning("cannot set the kill-on-close limit on the job object")
            return
        self._handle = int(job)
        self._kernel32 = kernel32

    def adopt(self, proc: subprocess.Popen[bytes]) -> None:
        if self._handle is None:
            return
        process = self._kernel32.OpenProcess(
            _PROCESS_SET_QUOTA | _PROCESS_TERMINATE, False, proc.pid
        )
        if not process:
            log.warning("cannot open llama-server to add it to the job object")
            return
        try:
            if not self._kernel32.AssignProcessToJobObject(
                ctypes.c_void_p(self._handle), ctypes.c_void_p(process)
            ):
                log.warning("cannot add llama-server to the job object")
        finally:
            self._kernel32.CloseHandle(ctypes.c_void_p(process))

    def close(self) -> None:
        if self._handle is not None:
            self._kernel32.CloseHandle(ctypes.c_void_p(self._handle))
            self._handle = None


def _limit_information() -> ctypes.Structure:
    class Basic(ctypes.Structure):
        _fields_ = [  # noqa: RUF012
            ("PerProcessUserTimeLimit", ctypes.c_int64),
            ("PerJobUserTimeLimit", ctypes.c_int64),
            ("LimitFlags", ctypes.c_uint32),
            ("MinimumWorkingSetSize", ctypes.c_size_t),
            ("MaximumWorkingSetSize", ctypes.c_size_t),
            ("ActiveProcessLimit", ctypes.c_uint32),
            ("Affinity", ctypes.c_size_t),
            ("PriorityClass", ctypes.c_uint32),
            ("SchedulingClass", ctypes.c_uint32),
        ]

    class Io(ctypes.Structure):
        _fields_ = [(name, ctypes.c_uint64) for name in ("r", "w", "o", "rb", "wb", "ob")]  # noqa: RUF012

    class Extended(ctypes.Structure):
        _fields_ = [  # noqa: RUF012
            ("Basic", Basic),
            ("Io", Io),
            ("ProcessMemoryLimit", ctypes.c_size_t),
            ("JobMemoryLimit", ctypes.c_size_t),
            ("PeakProcessMemoryUsed", ctypes.c_size_t),
            ("PeakJobMemoryUsed", ctypes.c_size_t),
        ]

    info = Extended()
    info.Basic.LimitFlags = _JOB_KILL_ON_CLOSE
    return info


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
        gpu_layers: int = 99,
        startup_timeout_s: float = 300.0,
        cancel: threading.Event | None = None,
    ) -> None:
        self.exe, self.gguf, self.log_path = exe, gguf, log_path
        self.ctx, self.gpu_layers = ctx, gpu_layers
        self.startup_timeout_s, self.cancel = startup_timeout_s, cancel
        self.port = 0
        self._proc: subprocess.Popen[bytes] | None = None
        self._job: _KillOnClose | None = None

    @property
    def base_url(self) -> str:
        return f"http://{HOST}:{self.port}/v1"

    def __enter__(self) -> LlamaServer:
        for label, path in (("llama-server", self.exe), ("LLM model", self.gguf)):
            if not path.is_file():
                raise ServerError(f"{label} not found: {path}")
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
            self._job = _KillOnClose()
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
