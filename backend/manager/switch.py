"""Switching the active profile: what it needs, what is missing, and fetching the missing parts."""

from __future__ import annotations

from dataclasses import dataclass

from backend.manager.active import Active, resolve_active
from backend.manager.context import ManagerContext
from backend.manager.download import JobStatus
from backend.manager.inventory import active_assets, asset
from backend.manager.maintain import plan_of
from backend.manager.profiles import Profile, ProfileId, fits, selection_for
from backend.manager.registry import Runtime


@dataclass(frozen=True, slots=True)
class MissingAsset:
    id: str
    type: str
    size_bytes: int
    local_build: bool = False
    """The program is built on this machine by a script, not downloaded."""


@dataclass(frozen=True, slots=True)
class Requirements:
    missing: tuple[MissingAsset, ...]
    download_bytes: int


def requirements(ctx: ManagerContext, profile_id: ProfileId) -> Requirements:
    selection = selection_for(profile_id, ctx.detect_hardware(), ctx.registry)
    missing: list[MissingAsset] = []
    for asset_id in sorted(active_assets(selection, ctx.registry)):
        found = asset(ctx.registry, asset_id)
        assert found is not None
        if not ctx.inventory.is_installed(asset_id):
            kind = "runtime" if isinstance(found, Runtime) else "model"
            local_build = isinstance(found, Runtime) and found.is_local_build
            missing.append(MissingAsset(asset_id, kind, found.size_bytes, local_build))
    return Requirements(tuple(missing), sum(m.size_bytes for m in missing))


def warnings_for(ctx: ManagerContext, profile: Profile) -> list[str]:
    hardware = ctx.detect_hardware()
    found: list[str] = []
    if not fits(profile, hardware) and profile.min_unified_mib is not None:
        have = f"{hardware.ram_mib} MiB" if hardware.ram_mib else "unknown memory"
        found.append(
            f"This machine has {have} of memory; {profile.id.value} needs "
            f"{profile.min_unified_mib} MiB. The self-test will fall back to the CPU if the "
            "GPU cannot run it."
        )
    elif not fits(profile, hardware):
        have = f"{hardware.vram_mib} MiB" if hardware.vram_mib else "no NVIDIA GPU"
        found.append(
            f"This machine has {have}; {profile.id.value} needs {profile.min_vram_mib} MiB of "
            "VRAM. The self-test will fall back to the CPU if the GPU cannot run it."
        )
    return found


def download_missing(ctx: ManagerContext, profile_id: ProfileId) -> list[JobStatus]:
    """Start a download for each missing asset. A runtime's add-ons come with it."""
    jobs: list[JobStatus] = []
    for item in requirements(ctx, profile_id).missing:
        found = ctx.registry.runtimes.get(item.id)
        if found is not None and (found.executable is None or found.is_local_build):
            continue
        jobs.append(ctx.runner.submit(plan_of(ctx, item.id)))
    return jobs


def current(ctx: ManagerContext) -> Active:
    return resolve_active(ctx.settings.current, ctx.detect_hardware(), ctx.registry)
