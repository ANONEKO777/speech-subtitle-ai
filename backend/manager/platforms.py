"""Which machine the backend runs on, as data the registry and the profiles can name.

Two platforms are supported: Windows on x64 (`win-x64`) and a Mac with Apple silicon
(`macos-arm64`). Everything else, an Intel Mac or Linux for example, gets one plain sentence
from `UnsupportedPlatform` and no stack trace."""

from __future__ import annotations

import platform as _platform
import sys

WIN_X64 = "win-x64"
MACOS_ARM64 = "macos-arm64"
SUPPORTED = (WIN_X64, MACOS_ARM64)

UNSUPPORTED_MESSAGE = (
    "這個程式只支援 Windows（64 位元）和搭載 Apple 晶片的 Mac（M1 以後），"
    "偵測到的是 {system} {machine}，Intel 版 Mac 和 Linux 目前不支援。"
)


class UnsupportedPlatform(RuntimeError):
    """The machine is neither Windows nor an Apple-silicon Mac. The text is shown as it is."""


def detect_platform(system: str | None = None, machine: str | None = None) -> str:
    """`win-x64` on any Windows, `macos-arm64` on an Apple-silicon Mac. `system` is a value of
    `sys.platform` and `machine` one of `platform.machine()`; both default to this machine."""
    system = sys.platform if system is None else system
    machine = _platform.machine() if machine is None else machine
    if system == "win32":
        return WIN_X64
    if system == "darwin" and machine.lower() == "arm64":
        return MACOS_ARM64
    name = {"darwin": "macOS", "linux": "Linux"}.get(system, system)
    raise UnsupportedPlatform(UNSUPPORTED_MESSAGE.format(system=name, machine=machine or "?"))


def check_platform() -> str | None:
    """None on a supported machine, else the sentence to print before exiting."""
    try:
        detect_platform()
    except UnsupportedPlatform as exc:
        return str(exc)
    return None
