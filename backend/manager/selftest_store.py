"""The last self-test result, in `selftest.json`, so a GPU-to-CPU fallback survives a restart."""

from __future__ import annotations

import json
import logging
import threading
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, cast

from backend.core.notices import Notice, from_json
from backend.manager.profiles import Device, ProfileId
from backend.manager.settings import write_json_atomic

log = logging.getLogger(__name__)

SELFTEST_FILE = "selftest.json"


@dataclass(frozen=True, slots=True)
class StageResult:
    stage: str
    """`asr` or `llm`."""
    runtime_id: str
    device: Device
    installed: bool
    """False when the runtime or model file is missing; that is not a GPU failure."""
    ok: bool
    seconds: float
    detail: str
    detail_notices: tuple[Notice, ...] = ()
    """The notices inside `detail`. This and the two fields like it are empty in a file saved
    before them, and the window then shows the text as it was stored."""


@dataclass(frozen=True, slots=True)
class Fallback:
    reason: str
    """A sentence a person can read, naming the GPU stage that failed and why."""
    failed: tuple[StageResult, ...]
    reason_notices: tuple[Notice, ...] = ()


@dataclass(frozen=True, slots=True)
class SelfTestReport:
    at_ms: int
    profile: ProfileId
    ok: bool
    """Some device can run the active profile's ASR and LLM."""
    device: Device
    """What the pipeline will use: cuda, or cpu after a fallback or on the CPU profile."""
    stages: tuple[StageResult, ...]
    """The checks that decided `ok` and `device`, in the order they ran."""
    fallback: Fallback | None
    seconds: float
    message: str
    message_notices: tuple[Notice, ...] = ()


def _stage(raw: dict[str, Any]) -> StageResult:
    return StageResult(
        raw["stage"],
        raw["runtime_id"],
        Device(raw["device"]),
        bool(raw["installed"]),
        bool(raw["ok"]),
        float(raw["seconds"]),
        raw["detail"],
        from_json(raw.get("detail_notices")),
    )


def report_from_json(raw: dict[str, Any]) -> SelfTestReport:
    fb = raw["fallback"]
    return SelfTestReport(
        at_ms=int(raw["at_ms"]),
        profile=ProfileId(raw["profile"]),
        ok=bool(raw["ok"]),
        device=Device(raw["device"]),
        stages=tuple(_stage(s) for s in raw["stages"]),
        fallback=None
        if fb is None
        else Fallback(
            fb["reason"],
            tuple(_stage(s) for s in fb["failed"]),
            from_json(fb.get("reason_notices")),
        ),
        seconds=float(raw["seconds"]),
        message=raw["message"],
        message_notices=from_json(raw.get("message_notices")),
    )


class SelfTestStore:
    def __init__(self, user_data: Path) -> None:
        self._path = user_data / SELFTEST_FILE
        self._lock = threading.Lock()

    def load(self) -> SelfTestReport | None:
        try:
            raw = cast("dict[str, Any]", json.loads(self._path.read_text(encoding="utf-8")))
            return report_from_json(raw)
        except FileNotFoundError:
            return None
        except (OSError, ValueError, KeyError, TypeError) as exc:
            log.warning("%s was not used: %s", self._path, exc)
            return None

    def save(self, report: SelfTestReport) -> None:
        with self._lock:
            write_json_atomic(self._path, asdict(report))

    def clear(self) -> None:
        with self._lock:
            self._path.unlink(missing_ok=True)
