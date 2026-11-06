"""Which profile is active, and what runs where.

The active profile is the user's choice (`settings.profile`) or, when there is none, the
recommendation for the detected hardware. A failed GPU self-test makes the pipeline run on the CPU
runtimes of that profile until the self-test passes again or the profile changes."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from backend.manager import registry as registry_module
from backend.manager.hardware import Hardware, detect
from backend.manager.profiles import Device, Selection, select, selection_for
from backend.manager.registry import Registry
from backend.manager.selftest_store import SelfTestStore
from backend.manager.settings import AppSettings, load_settings


class Source(StrEnum):
    USER = "user"
    RECOMMENDED = "recommended"


@dataclass(frozen=True, slots=True)
class Active:
    selection: Selection
    source: Source
    hardware: Hardware
    recommended: Selection


def resolve_active(settings: AppSettings, hardware: Hardware, registry: Registry) -> Active:
    recommended = select(hardware, registry)
    if settings.profile is None:
        return Active(recommended, Source.RECOMMENDED, hardware, recommended)
    chosen = selection_for(settings.profile, hardware, registry)
    return Active(chosen, Source.USER, hardware, recommended)


def runs_on_cpu(
    user_data: Path,
    detect_hardware: Callable[[], Hardware] = detect,
    registry: Registry | None = None,
) -> bool:
    """Whether a job started now uses the CPU runtimes. Read fresh from disk on every call."""
    settings = load_settings(user_data)
    registry = registry or registry_module.load()
    if settings.profile is None:
        profile = select(detect_hardware(), registry).profile
    else:
        profile = selection_for(settings.profile, detect_hardware(), registry).profile
    if profile.asr.device is Device.CPU:
        return True
    record = SelfTestStore(user_data).load()
    return record is not None and record.fallback is not None and record.profile == profile.id
