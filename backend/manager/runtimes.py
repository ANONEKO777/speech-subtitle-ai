from __future__ import annotations

import os
import shutil
import uuid
from pathlib import Path

from backend.core.audio import HOMEBREW_DIRS
from backend.manager.download import Item, Plan, old_of, part_of, recover_swap, staging_of
from backend.manager.registry import Registry, Runtime
from backend.manager.storage import Storage

TRASH_MARK = ".trash-"
LOCAL_BUILD_MESSAGE = (
    "{engine} 在這個平台沒有現成的程式可以下載，要在這台電腦上自己編譯一次："
    "請在專案資料夾執行 {script}（步驟見 docs/MACOS.md）。"
    "編譯好的 {program} 會放在 {folder}，放在 PATH 上也找得到。"
)


FOUND_ELSEWHERE_MESSAGE = (
    "{program} 是在 {where} 找到的，不在 App 的執行檔資料夾（{folder}）裡，"
    "所以 App 沒有刪它。要移除請自己處理（用 Homebrew 裝的就用 brew uninstall）。"
)


class NotInstallable(ValueError):
    pass


def local_build_message(runtime: Runtime, storage: Storage) -> str:
    """What to tell a person whose runtime is built on the machine and is not there yet."""
    assert runtime.build is not None and runtime.executable is not None
    return LOCAL_BUILD_MESSAGE.format(
        engine=runtime.engine,
        script=runtime.build.script,
        program=Path(runtime.executable).name,
        folder=storage.runtime_dir(runtime),
    )


def _find_local_build(runtime: Runtime, storage: Storage) -> Path | None:
    """The program of a runtime built on the machine: in its runtimes folder first, then on
    PATH, then in the Homebrew folders."""
    assert runtime.executable is not None
    own = storage.runtime_dir(runtime) / runtime.executable
    if own.is_file():
        return own
    name = Path(runtime.executable).name
    found = shutil.which(name) or shutil.which(name, path=os.pathsep.join(HOMEBREW_DIRS))
    return Path(found) if found else None


def found_outside_runtimes(runtime: Runtime, storage: Storage) -> Path | None:
    """Where a built-on-the-machine program was found when that is not its own runtimes folder
    (PATH or Homebrew). The app does not own that file and never deletes it."""
    if not runtime.is_local_build:
        return None
    found = _find_local_build(runtime, storage)
    if found is None or found.is_relative_to(storage.runtime_dir(runtime)):
        return None
    return found


def program_of(runtime: Runtime, storage: Storage) -> Path:
    """Where the runtime's program is, or where it would be: nothing is checked for a download,
    so a runtime that is not installed yet reports its own missing path."""
    if runtime.is_local_build:
        found = _find_local_build(runtime, storage)
        if found is not None:
            return found
    return storage.runtime_dir(runtime) / (runtime.executable or "")


def runtime_bundle(runtime_id: str, registry: Registry, storage: Storage) -> tuple[Runtime, ...]:
    runtime = registry.runtimes[runtime_id]
    if runtime.is_local_build:
        raise NotInstallable(local_build_message(runtime, storage))
    if runtime.executable is None:
        raise NotInstallable(
            f"{runtime_id} is an add-on and installs with the runtime that needs it"
        )
    return (runtime, *(registry.runtimes[need] for need in runtime.needs))


def runtime_plan(runtime_id: str, registry: Registry, storage: Storage) -> Plan:
    runtime, *addons = runtime_bundle(runtime_id, registry, storage)
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
    if runtime.is_local_build:
        return _find_local_build(runtime, storage)
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
    if registry.runtimes[runtime_id].is_local_build:
        folder = storage.runtime_dir(registry.runtimes[runtime_id])
        for trash in _rename_to_trash([folder] if folder.exists() else []):
            shutil.rmtree(trash, ignore_errors=True)
        return
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
