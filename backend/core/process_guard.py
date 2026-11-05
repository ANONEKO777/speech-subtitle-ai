from __future__ import annotations

import ctypes
import logging
import subprocess
import sys
import threading

log = logging.getLogger(__name__)

_JOB_EXTENDED_LIMIT_INFORMATION = 9
_JOB_KILL_ON_CLOSE = 0x2000
_PROCESS_TERMINATE = 0x0001
_PROCESS_SET_QUOTA = 0x0100


class KillOnClose:
    """A Windows job object that kills its processes when the handle closes, which Windows does
    when this Python process dies for any reason, so a killed backend cannot leave a server or an
    ASR run holding the GPU."""

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
