"""What the machine does when the queue is done: sleep or shut down after a countdown.

The countdown is a thread that waits on a cancel event, so a user can stop it any time during the
grace period. The call that really sleeps or shuts down is `system_power`, and `Countdown` takes
it as an argument so a test passes a fake and never touches the machine.
"""

from __future__ import annotations

import logging
import subprocess
import sys
import threading
import time
from collections.abc import Callable, Mapping
from enum import StrEnum
from types import MappingProxyType

log = logging.getLogger(__name__)

COUNTDOWN_S = 60.0


class PowerAction(StrEnum):
    SLEEP = "sleep"
    SHUTDOWN = "shutdown"


PowerExecutor = Callable[[PowerAction], None]
StillDue = Callable[[PowerAction], bool]
Emit = Callable[[str, Mapping[str, object]], None]


COMMANDS: Mapping[str, Mapping[PowerAction, tuple[str, ...]]] = MappingProxyType(
    {
        "win32": MappingProxyType(
            {
                PowerAction.SLEEP: ("rundll32.exe", "powrprof.dll,SetSuspendState", "0,1,0"),
                PowerAction.SHUTDOWN: ("shutdown", "/s", "/t", "0"),
            }
        ),
        # `pmset sleepnow` needs no password. Shutting down without one goes through System
        # Events, which asks the person once to let this app control it (an Automation prompt).
        "darwin": MappingProxyType(
            {
                PowerAction.SLEEP: ("pmset", "sleepnow"),
                PowerAction.SHUTDOWN: (
                    "osascript",
                    "-e",
                    'tell application "System Events" to shut down',
                ),
            }
        ),
    }
)

Runner = Callable[[tuple[str, ...]], int]


def _run(command: tuple[str, ...]) -> int:
    return subprocess.run(command, check=False).returncode


def system_power(action: PowerAction, system: str | None = None, run: Runner = _run) -> None:
    """Put this machine to sleep, or shut it down at once. `system` is a `sys.platform` value and
    `run` starts the command, so a test can see what would have run."""
    commands = COMMANDS.get(sys.platform if system is None else system)
    if commands is None:
        log.warning("no %s command for this platform", action.value)
        return
    command = commands[action]
    if run(command) != 0:
        log.warning("%s did not succeed: %s", action.value, " ".join(command))


class Countdown:
    """At most one countdown at a time. `emit(name, data)` reports `countdown`,
    `countdown_cancelled` and `power`. `still_due(action)` is asked once more under the lock that
    `cancel` takes, and a False cancels the countdown. Passing that check sets `firing` in the
    same locked step, so from then on `cancel` returns False and the executor runs. The executor
    is never called with the lock held. A change that completed before the check is seen by it;
    one that lands after it cannot stop the action."""

    def __init__(
        self, executor: PowerExecutor | None, emit: Emit, seconds: float, still_due: StillDue
    ) -> None:
        self._executor = executor
        self._emit = emit
        self._seconds = seconds
        self._still_due = still_due
        self._firing = False
        self._cancel = threading.Event()
        self._thread: threading.Thread | None = None
        self._lock = threading.Lock()

    @property
    def active(self) -> bool:
        with self._lock:
            return self._thread is not None and self._thread.is_alive()

    def start(self, action: PowerAction) -> None:
        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                return
            self._cancel = threading.Event()
            self._firing = False
            self._thread = threading.Thread(
                target=self._run, args=(action, self._cancel), name="vst-power", daemon=True
            )
            deadline_ms = time.time_ns() // 1_000_000 + int(self._seconds * 1000)
            self._emit(
                "countdown",
                {"action": action.value, "seconds": self._seconds, "deadline_ms": deadline_ms},
            )
            self._thread.start()

    def cancel(self) -> bool:
        """Stop the countdown. False when none was running or the action is already firing."""
        with self._lock:
            if (
                self._thread is None
                or not self._thread.is_alive()
                or self._cancel.is_set()
                or self._firing
            ):
                return False
            self._cancel.set()
            return True

    def join(self) -> None:
        thread = self._thread
        if thread is not None:
            thread.join()

    def _run(self, action: PowerAction, cancel: threading.Event) -> None:
        if cancel.wait(self._seconds):
            self._emit("countdown_cancelled", {"action": action.value})
            return
        with self._lock:
            fire = not cancel.is_set() and self._still_due(action)
            if fire:
                self._firing = True
            else:
                cancel.set()
        if not fire:
            self._emit("countdown_cancelled", {"action": action.value})
            return
        if self._executor is None:
            self._emit("power", {"action": action.value, "executed": False})
            return
        self._emit("power", {"action": action.value, "executed": True})
        self._executor(action)
