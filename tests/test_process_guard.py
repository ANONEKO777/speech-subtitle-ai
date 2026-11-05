from __future__ import annotations

import subprocess
import sys
import textwrap
import time
from pathlib import Path

import pytest

pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="job objects are Windows only")

PARENT = textwrap.dedent(
    """
    import subprocess, sys, time
    from backend.core import process_guard

    child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(120)"])
    process_guard.adopt(child)
    print(child.pid, flush=True)
    time.sleep(120)
    """
)


def alive(pid: int) -> bool:
    out = subprocess.run(
        ["tasklist", "/FI", f"PID eq {pid}", "/NH"], capture_output=True, text=True, check=False
    ).stdout
    return str(pid) in out


def test_a_guarded_child_dies_when_its_parent_is_hard_killed(tmp_path: Path) -> None:
    root = Path(__file__).resolve().parent.parent
    script = tmp_path / "parent.py"
    script.write_text(PARENT, encoding="utf-8")
    parent = subprocess.Popen(
        [sys.executable, str(script)], stdout=subprocess.PIPE, text=True, cwd=root,
        env={**__import__("os").environ, "PYTHONPATH": str(root)},
    )  # fmt: skip
    assert parent.stdout is not None
    child_pid = int(parent.stdout.readline())
    try:
        assert alive(child_pid)
        parent.kill()
        parent.wait(timeout=10)
        deadline = time.monotonic() + 10
        while alive(child_pid) and time.monotonic() < deadline:
            time.sleep(0.2)
        assert not alive(child_pid)
    finally:
        parent.kill()
        if alive(child_pid):
            subprocess.run(["taskkill", "/F", "/PID", str(child_pid)], check=False)
