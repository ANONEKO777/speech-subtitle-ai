from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from backend.manager import registry as registry_module
from backend.manager.download import JobRunner, Opener, RetryPolicy
from backend.manager.hardware import Hardware, detect
from backend.manager.registry import Registry
from backend.manager.storage import Storage


@dataclass(frozen=True, slots=True)
class ManagerContext:
    registry: Registry
    storage: Storage
    runner: JobRunner
    detect_hardware: Callable[[], Hardware]


def build_context(
    user_data: Path,
    registry: Registry | None = None,
    policy: RetryPolicy | None = None,
    opener: Opener | None = None,
    detect_hardware: Callable[[], Hardware] = detect,
) -> ManagerContext:
    storage = Storage(user_data)
    runner = JobRunner(storage.resolve_url, policy, opener)
    return ManagerContext(registry or registry_module.load(), storage, runner, detect_hardware)
