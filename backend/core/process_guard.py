"""Tie a child program to this process, so a stopped backend leaves no server or ASR run behind.

Windows has job objects: the system kills every process in the job when the handle closes, however
this process dies. macOS has no such thing, so `KillOnClose` there remembers its children and
stops them when it is closed, when this process exits normally, and when it is sent SIGTERM or
SIGHUP. A SIGKILL cannot be caught, so after one the children of a Mac backend are only reached by
a signal to the process group, which the desktop shell sends (the backend and its children share
one group)."""

from __future__ import annotations

import atexit
import ctypes
import logging
import os
import signal
import subprocess
import sys
import threading
import weakref
from types import FrameType

log = logging.getLogger(__name__)

_JOB_EXTENDED_LIMIT_INFORMATION = 9
_JOB_KILL_ON_CLOSE = 0x2000
_PROCESS_TERMINATE = 0x0001
_PROCESS_SET_QUOTA = 0x0100
_TERM_GRACE_S = 3.0
_STOP_SIGNALS = ("SIGTERM", "SIGHUP")


class KillOnClose:
    """A Windows job object that kills its processes when the handle closes, which Windows does
    when this Python process dies for any reason, so a killed backend cannot leave a server or an
    ASR run holding the GPU."""

    def __init__(self) -> None:
        self._handle: int | None = None
        self._children: list[subprocess.Popen[bytes] | subprocess.Popen[str]] = []
        if sys.platform != "win32":
            _watch(self)
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
            log.warning(
                "no job object; a hard kill of the pipeline would leave its children running"
            )
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

    def adopt(self, proc: subprocess.Popen[bytes] | subprocess.Popen[str]) -> None:
        if sys.platform != "win32":
            self._children = [c for c in self._children if c.poll() is None]
            self._children.append(proc)
            return
        if self._handle is None:
            return
        process = self._kernel32.OpenProcess(
            _PROCESS_SET_QUOTA | _PROCESS_TERMINATE, False, proc.pid
        )
        if not process:
            log.warning("cannot open pid %d to add it to the job object", proc.pid)
            return
        try:
            if not self._kernel32.AssignProcessToJobObject(
                ctypes.c_void_p(self._handle), ctypes.c_void_p(process)
            ):
                log.warning("cannot add pid %d to the job object", proc.pid)
        finally:
            self._kernel32.CloseHandle(ctypes.c_void_p(process))

    def close(self) -> None:
        if sys.platform != "win32":
            children, self._children = self._children, []
            _stop_all(children)
            return
        if self._handle is not None:
            self._kernel32.CloseHandle(ctypes.c_void_p(self._handle))
            self._handle = None


_watched: weakref.WeakSet[KillOnClose] = weakref.WeakSet()
_hooked = False


def _stop(proc: subprocess.Popen[bytes] | subprocess.Popen[str], sig: int) -> None:
    """Send `sig` to the child, and to its whole group when it leads one (a program that starts
    helpers of its own). Never to this process's own group."""
    killpg = getattr(os, "killpg", None)
    getpgid = getattr(os, "getpgid", None)
    try:
        if killpg is not None and getpgid is not None and getpgid(proc.pid) == proc.pid:
            killpg(proc.pid, sig)
        else:
            proc.send_signal(sig)
    except OSError:
        pass


def _stop_all(children: list[subprocess.Popen[bytes] | subprocess.Popen[str]]) -> None:
    """Ask each live child to end, wait a few seconds for all of them together, then kill the
    ones still running."""
    live = [c for c in children if c.poll() is None]
    for child in live:
        _stop(child, signal.SIGTERM)
    deadline_s = _TERM_GRACE_S
    for child in live:
        try:
            child.wait(timeout=max(deadline_s, 0.0))
        except subprocess.TimeoutExpired:
            pass
        deadline_s = 0.0
    kill = getattr(signal, "SIGKILL", signal.SIGTERM)
    for child in live:
        if child.poll() is None:
            _stop(child, kill)


def _stop_every_watched() -> None:
    for guard in list(_watched):
        guard.close()


def _on_stop_signal(signum: int, frame: FrameType | None) -> None:
    _stop_every_watched()
    signal.signal(signum, signal.SIG_DFL)
    os.kill(os.getpid(), signum)


def _watch(guard: KillOnClose) -> None:
    """Make sure `guard`'s children are stopped when this process exits or is told to stop. The
    exit hook goes in once. A signal handler goes in only where nothing else has one (a server
    that handles SIGTERM itself ends through the exit hook) and only from the main thread."""
    global _hooked
    _watched.add(guard)
    if _hooked:
        return
    _hooked = True
    atexit.register(_stop_every_watched)
    for name in _STOP_SIGNALS:
        number = getattr(signal, name, None)
        if number is None:
            continue
        try:
            if signal.getsignal(number) is signal.SIG_DFL:
                signal.signal(number, _on_stop_signal)
        except ValueError:
            return


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


_guard: KillOnClose | None = None
_guard_lock = threading.Lock()


def adopt(proc: subprocess.Popen[bytes] | subprocess.Popen[str]) -> None:
    """Tie a child to this process: Windows kills it when this process dies, however it dies.

    One job object lives for the whole process, so every GPU child (llama-server, whisper-cli,
    crispasr) and ffmpeg share it."""
    global _guard
    with _guard_lock:
        if _guard is None:
            _guard = KillOnClose()
        _guard.adopt(proc)
