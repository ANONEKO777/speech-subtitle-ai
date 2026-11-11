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

LIBRARIES = ("vcruntime140.dll", "vcruntime140_1.dll", "msvcp140.dll")
INFO_URL = "https://learn.microsoft.com/cpp/windows/latest-supported-vc-redist"
MESSAGE = (
    "這台電腦缺少 Microsoft Visual C++ 可轉散發套件（x64），語音辨識和翻譯程式無法啟動。"
    f"請到 {INFO_URL} 下載並安裝「vc_redist.x64.exe」，裝好後再試一次。"
)


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
        raise error(MESSAGE)
