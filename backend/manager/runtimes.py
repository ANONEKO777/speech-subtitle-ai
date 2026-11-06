from __future__ import annotations

import os
import shutil
import uuid
from pathlib import Path

from backend.manager.download import Item, Plan, old_of, part_of, recover_swap, staging_of
from backend.manager.registry import Registry, Runtime
from backend.manager.storage import Storage

TRASH_MARK = ".trash-"


class NotInstallable(ValueError):
    pass


def runtime_bundle(runtime_id: str, registry: Registry) -> tuple[Runtime, ...]:
    runtime = registry.runtimes[runtime_id]
    if runtime.executable is None:
        raise NotInstallable(
            f"{runtime_id} is an add-on and installs with the runtime that needs it"
        )
    return (runtime, *(registry.runtimes[need] for need in runtime.needs))


def runtime_plan(runtime_id: str, registry: Registry, storage: Storage) -> Plan:
    runtime, *addons = runtime_bundle(runtime_id, registry)
    items = tuple(
        Item(r.url, storage.archive_file(r), r.sha256, r.size_bytes) for r in (runtime, *addons)
    )
    return Plan(
        runtime_id, items, unpack_to=storage.runtime_dir(runtime), entry_point=runtime.executable
    )


def recover_runtime(runtime: Runtime, storage: Storage) -> None:
    """Finish a swap that a kill stopped halfway (see `recover_swap`)."""
    recover_swap(storage.runtime_dir(runtime), runtime.executable)


def recover_runtimes(registry: Registry, storage: Storage) -> None:
    """Settle half-done swaps and finish deletes that stopped after the folder was renamed."""
    root = storage.runtimes_root
    if root.is_dir():
        for leftover in root.glob(f"*{TRASH_MARK}*"):
            shutil.rmtree(leftover, ignore_errors=True)
    for runtime in registry.runtimes.values():
        if runtime.executable is not None:
            recover_runtime(runtime, storage)


def runtime_executable(runtime_id: str, registry: Registry, storage: Storage) -> Path | None:
    runtime = registry.runtimes[runtime_id]
    if runtime.executable is None:
        return None
    recover_runtime(runtime, storage)
    path = storage.runtime_dir(runtime) / runtime.executable
    return path if path.is_file() else None


def _rename_to_trash(folders: list[Path]) -> list[Path]:
    """Rename each folder to a trash name beside it. A rename fails while any file inside is
    locked, so a failure puts back what was renamed and leaves every folder as it was."""
    moved: list[tuple[Path, Path]] = []
    try:
        for folder in folders:
            trash = folder.with_name(f"{folder.name}{TRASH_MARK}{uuid.uuid4().hex[:8]}")
            os.replace(folder, trash)
            moved.append((folder, trash))
    except BaseException:
        for folder, trash in reversed(moved):
            os.replace(trash, folder)
        raise
    return [trash for _, trash in moved]


def delete_runtime(runtime_id: str, registry: Registry, storage: Storage) -> None:
    """All or nothing for the user: the runtime folder is renamed away first, which fails (and
    changes nothing) while a program holds any file in it. The renamed folder is then deleted;
    what a locked file leaves behind is swept at the next start by `recover_runtimes`."""
    plan = runtime_plan(runtime_id, registry, storage)
    if plan.unpack_to is not None:
        folders = [
            folder
            for folder in (plan.unpack_to, old_of(plan.unpack_to), staging_of(plan.unpack_to))
            if folder.exists()
        ]
        for trash in _rename_to_trash(folders):
            shutil.rmtree(trash, ignore_errors=True)
    for item in plan.items:
        item.dest.unlink(missing_ok=True)
        part_of(item.dest).unlink(missing_ok=True)
