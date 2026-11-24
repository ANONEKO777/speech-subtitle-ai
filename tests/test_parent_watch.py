# pyright: reportUnknownLambdaType=false, reportUnknownArgumentType=false
"""The backend ends itself when the desktop shell that started it is gone (a Mac has no
kill-on-parent-exit). The platform is faked for the pid rules; a real process pair covers the
check itself where the system has POSIX signals."""

from __future__ import annotations

import subprocess
import sys
import textwrap
import threading
import time
from pathlib import Path

import pytest

from backend.core.parent_watch import PARENT_PID_ENV, is_alive, parent_pid, watch

ROOT = Path(__file__).resolve().parents[1]


def test_a_pid_in_the_environment_is_watched() -> None:
    assert parent_pid({PARENT_PID_ENV: "4242"}, "darwin") == 4242


@pytest.mark.parametrize("value", ["", "abc", "0", "1", "-5", "12.5", " "])
def test_nothing_is_watched_without_a_usable_pid(value: str) -> None:
    assert parent_pid({PARENT_PID_ENV: value}, "darwin") is None


def test_nothing_is_watched_when_the_variable_is_missing() -> None:
    assert parent_pid({}, "darwin") is None


def test_windows_is_never_watched_because_os_kill_would_end_the_process_there() -> None:
    assert parent_pid({PARENT_PID_ENV: "4242"}, "win32") is None


def test_the_callback_runs_once_when_the_parent_is_gone() -> None:
    gone = threading.Event()
    calls: list[int] = []
    answers = iter([True, True, False])

    def alive(pid: int) -> bool:
        calls.append(pid)
        return next(answers, False)

    def on_gone() -> None:
        calls.append(-1)
        gone.set()

    thread = watch(7, on_gone, alive=alive, every_s=0.01)
    assert gone.wait(2)
    thread.join(2)
    assert calls == [7, 7, 7, -1]


def test_a_parent_that_stays_alive_never_triggers_the_callback() -> None:
    stop = threading.Event()
    calls: list[int] = []
    thread = watch(7, lambda: calls.append(1), alive=lambda _pid: True, every_s=0.01, stop=stop)
    time.sleep(0.15)
    stop.set()
    thread.join(2)
    assert calls == []
    assert not thread.is_alive()


def test_this_process_is_alive_to_the_check() -> None:
    import os

    assert is_alive(os.getpid())


@pytest.mark.skipif(sys.platform == "win32", reason="needs POSIX signals")
def test_a_backend_whose_shell_was_killed_ends_by_itself(tmp_path: Path) -> None:
    child = textwrap.dedent(
        f"""
        import os, sys, time
        sys.path.insert(0, {str(ROOT)!r})
        from backend.core import parent_watch
        pid = parent_watch.parent_pid(os.environ)
        done = []
        parent_watch.watch(pid, lambda: done.append(1), every_s=0.05)
        while not done:
            time.sleep(0.05)
        open({str(tmp_path / "ended")!r}, "w").write("ok")
        """
    )
    shell = textwrap.dedent(
        f"""
        import os, subprocess, sys
        env = dict(os.environ, {PARENT_PID_ENV}=str(os.getpid()))
        proc = subprocess.Popen([sys.executable, "-c", {child!r}], env=env)
        print(proc.pid, flush=True)
        os._exit(0)
        """
    )
    pid_file = tmp_path / "pid"
    with pid_file.open("w") as sink:
        subprocess.run([sys.executable, "-c", shell], stdout=sink, timeout=30, check=True)
    assert int(pid_file.read_text().strip()) > 1
    deadline = time.monotonic() + 10
    while not (tmp_path / "ended").exists() and time.monotonic() < deadline:
        time.sleep(0.05)
    assert (tmp_path / "ended").read_text() == "ok"


class _FakeServer:
    instances: list[_FakeServer] = []  # noqa: RUF012

    def __init__(self, _config: object) -> None:
        self.should_exit = False
        self.ran = False
        _FakeServer.instances.append(self)

    def run(self, sockets: object = None) -> None:
        self.ran = True


def _serve_with_fakes(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> list[tuple[int, object]]:
    from backend import main

    watched: list[tuple[int, object]] = []
    _FakeServer.instances.clear()
    monkeypatch.setattr(main, "create_app", lambda _config: object())
    monkeypatch.setattr(main.uvicorn, "Server", _FakeServer)
    monkeypatch.setattr(main.uvicorn, "Config", lambda *_a, **_k: None)
    monkeypatch.setattr(
        main.parent_watch, "watch", lambda pid, on_gone, **_k: watched.append((pid, on_gone))
    )
    main.serve(tmp_path, None, [])
    return watched


def test_serve_watches_the_shell_it_was_told_about_and_stops_the_server_when_it_is_gone(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr("sys.platform", "darwin")
    monkeypatch.setenv(PARENT_PID_ENV, "4242")

    watched = _serve_with_fakes(monkeypatch, tmp_path)

    (server,) = _FakeServer.instances
    assert [pid for pid, _ in watched] == [4242]
    assert server.ran
    assert not server.should_exit
    callback = watched[0][1]
    assert callable(callback)
    callback()
    assert server.should_exit


def test_serve_watches_nothing_when_no_shell_started_it(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr("sys.platform", "darwin")
    monkeypatch.delenv(PARENT_PID_ENV, raising=False)

    assert _serve_with_fakes(monkeypatch, tmp_path) == []
