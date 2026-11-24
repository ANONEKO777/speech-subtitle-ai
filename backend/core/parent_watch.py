"""End the backend when the desktop shell that started it is gone.

Windows kills the backend through a job object and a Mac has no such thing, so a shell that was
killed hard (not closed) would leave the backend and its children running. The shell passes its own
pid in `VST_PARENT_PID`; a thread here checks that the pid is still alive and asks the server to
stop when it is not. A backend started from a terminal gets no such variable and watches nothing."""

from __future__ import annotations

import os
import sys
import threading
from collections.abc import Callable, Mapping

PARENT_PID_ENV = "VST_PARENT_PID"
CHECK_EVERY_S = 2.0


def parent_pid(env: Mapping[str, str], system: str | None = None) -> int | None:
    """The pid to watch, or None. Windows is left alone: there `os.kill` would end the process
    instead of testing it, and the job object already covers that case. A pid below 2 would be
    the system or every process of this group."""
    if (sys.platform if system is None else system) == "win32":
        return None
    try:
        pid = int(env.get(PARENT_PID_ENV, ""))
    except ValueError:
        return None
    return pid if pid > 1 else None


def is_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def watch(
    pid: int,
    on_gone: Callable[[], None],
    *,
    alive: Callable[[int], bool] = is_alive,
    every_s: float = CHECK_EVERY_S,
    stop: threading.Event | None = None,
) -> threading.Thread:
    """Call `on_gone` once, from a daemon thread, when `alive(pid)` turns false. Setting `stop`
    ends the watch without calling it."""
    done = stop or threading.Event()

    def run() -> None:
        while not done.wait(every_s):
            if not alive(pid):
                on_gone()
                return

    thread = threading.Thread(target=run, name="parent-watch", daemon=True)
    thread.start()
    return thread
