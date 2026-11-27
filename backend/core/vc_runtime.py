"""The Microsoft Visual C++ runtime the downloaded whisper.cpp and llama.cpp programs import.

A clean Windows machine may not have it, and then those programs die at start with a missing-DLL
code and no explanation. The installer does not carry it (the programs are downloaded later, into a
folder the backend's own copies are not on the DLL path of), so the app checks for it before the
first start and says what to install.

`VST_SIMULATE_NO_VCRUNTIME=1` makes the check fail, to test the message."""

from __future__ import annotations

import os
import sys
from pathlib import Path

from backend.core.notices import VC_RUNTIME_MISSING, noticed

LIBRARIES = ("vcruntime140.dll", "vcruntime140_1.dll", "msvcp140.dll")
INFO_URL = "https://learn.microsoft.com/cpp/windows/latest-supported-vc-redist"
NOTICE = VC_RUNTIME_MISSING(url=INFO_URL)


def missing() -> tuple[str, ...]:
    """The runtime libraries absent from System32; always empty off Windows."""
    if os.environ.get("VST_SIMULATE_NO_VCRUNTIME"):
        return LIBRARIES
    if sys.platform != "win32":
        return ()
    system32 = Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32"
    return tuple(name for name in LIBRARIES if not (system32 / name).is_file())


def require(error: type[Exception]) -> None:
    """Raises `error` with the plain message when the runtime is missing."""
    if missing():
        raise noticed(error, NOTICE)
