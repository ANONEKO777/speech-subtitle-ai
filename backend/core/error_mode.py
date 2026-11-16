from __future__ import annotations

import ctypes
import sys

SEM_FAILCRITICALERRORS = 0x0001
SEM_NOOPENFILEERRORBOX = 0x8000
QUIET = SEM_FAILCRITICALERRORS | SEM_NOOPENFILEERRORBOX


def silence_system_dialogs() -> None:
    """Make a failed process start return an error instead of a modal Windows dialog.

    With the default error mode, starting a file that is not a valid program (a corrupt or
    half-downloaded engine binary) pops "unsupported 16-bit application" on the desktop and
    blocks until someone clicks OK. The caller gets the OSError either way. Child processes
    inherit the mode.
    """
    if sys.platform != "win32":
        return
    kernel32 = ctypes.WinDLL("kernel32")
    kernel32.SetErrorMode(kernel32.GetErrorMode() | QUIET)
