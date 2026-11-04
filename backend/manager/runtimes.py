from __future__ import annotations

import shutil
from pathlib import Path

from backend.manager.download import Item, Plan, part_of, staging_of
from backend.manager.registry import Registry, Runtime
from backend.manager.storage import Storage


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


def runtime_executable(runtime_id: str, registry: Registry, storage: Storage) -> Path | None:
    runtime = registry.runtimes[runtime_id]
    if runtime.executable is None:
        return None
    path = storage.runtime_dir(runtime) / runtime.executable
    return path if path.is_file() else None


def delete_runtime(runtime_id: str, registry: Registry, storage: Storage) -> None:
    plan = runtime_plan(runtime_id, registry, storage)
    if plan.unpack_to is not None:
        shutil.rmtree(plan.unpack_to, ignore_errors=True)
        shutil.rmtree(staging_of(plan.unpack_to), ignore_errors=True)
    for item in plan.items:
        item.dest.unlink(missing_ok=True)
        part_of(item.dest).unlink(missing_ok=True)
