from __future__ import annotations

import subprocess
import sys

import pytest

pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="error modes are Windows only")

CREATE_DEFAULT_ERROR_MODE = 0x04000000
QUIET = 0x0001 | 0x8000

PROBE = """
import ctypes, sys
sys.path.insert(0, sys.argv[1])
before = ctypes.WinDLL("kernel32").GetErrorMode()
import backend.engines.base
print(before, ctypes.WinDLL("kernel32").GetErrorMode())
"""


def test_importing_the_backend_silences_the_system_error_dialog() -> None:
    root = __file__.rsplit("tests", 1)[0]
    out = subprocess.run(
        [sys.executable, "-c", PROBE, root],
        capture_output=True,
        text=True,
        check=True,
        creationflags=CREATE_DEFAULT_ERROR_MODE,
    ).stdout.split()
    before, after = int(out[0]), int(out[1])
    assert before & QUIET == 0
    assert after & QUIET == QUIET
