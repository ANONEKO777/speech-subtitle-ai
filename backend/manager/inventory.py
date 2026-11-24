"""What is installed, what needs it, and what may be deleted, repaired or updated.

An asset is a registry model or runtime. A model file is hashed on request and the result is
remembered in the manifest. A runtime is a folder unpacked from a zip whose SHA-256 was checked at
download time, so it reports that, not a hash of the folder."""

from __future__ import annotations

import hashlib
import os
import time
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from backend.manager.download import CHUNK, InstallState, Item, Plan
from backend.manager.manifest import Manifest, Record
from backend.manager.platforms import detect_platform
from backend.manager.profiles import (
    ALL_PROFILES,
    ProfileId,
    Selection,
    profiles_for,
    required_assets,
)
from backend.manager.registry import Model, Registry, Runtime
from backend.manager.runtimes import program_of, runtime_executable
from backend.manager.storage import Storage


class AssetType(StrEnum):
    MODEL = "model"
    RUNTIME = "runtime"


class Sha(StrEnum):
    VERIFIED = "verified"
    UNCHECKED = "unchecked"
    CORRUPT = "corrupt"
    NOT_INSTALLED = "not_installed"


class Scope(StrEnum):
    FILE = "file"
    ARCHIVE_AT_INSTALL = "archive_at_install"


@dataclass(frozen=True, slots=True)
class Dependent:
    id: str
    installed: bool


@dataclass(frozen=True, slots=True)
class Entry:
    id: str
    type: AssetType
    kind: str
    """The model kind, or the runtime backend."""
    installed: bool
    state: InstallState
    version: str
    """What the registry ships."""
    installed_version: str | None
    size_bytes: int
    size_on_disk: int | None
    path: str | None
    sha256: str
    sha256_state: Sha
    sha256_scope: Scope
    verified_at_ms: int | None
    used_by_profiles: tuple[ProfileId, ...]
    in_active_profile: bool
    dependents: tuple[Dependent, ...]
    blockers: tuple[str, ...]
    """Why a plain delete is refused. Empty means it may go."""
    license: str
    license_url: str


def asset(registry: Registry, asset_id: str) -> Model | Runtime | None:
    return registry.models.get(asset_id) or registry.runtimes.get(asset_id)


def closure(ids: Iterable[str], registry: Registry) -> frozenset[str]:
    """The ids and everything they need, transitively."""
    seen: set[str] = set()
    todo = list(ids)
    while todo:
        current = todo.pop()
        if current in seen:
            continue
        seen.add(current)
        found = asset(registry, current)
        if found is not None:
            todo.extend(found.needs)
    return frozenset(seen)


def profile_assets(profile_id: ProfileId, registry: Registry) -> frozenset[str]:
    profile = ALL_PROFILES[profile_id]
    stages = [profile.asr, profile.llm]
    if profile.asr_fallback is not None:
        stages.append(profile.asr_fallback)
    return closure(
        [*(s.model for s in stages), *(s.runtime for s in stages), "silero-vad-onnx-v6.2.3"],
        registry,
    )


def active_assets(selection: Selection, registry: Registry) -> frozenset[str]:
    needed = required_assets(selection)
    return closure([*needed.models, *needed.runtimes], registry)


def dependents_of(asset_id: str, registry: Registry) -> tuple[str, ...]:
    pool = (*registry.models.values(), *registry.runtimes.values())
    return tuple(a.id for a in pool if asset_id in a.needs)


@dataclass(frozen=True, slots=True)
class Inventory:
    registry: Registry
    storage: Storage
    manifest: Manifest

    def is_installed(self, asset_id: str) -> bool:
        found = asset(self.registry, asset_id)
        if isinstance(found, Model):
            return self.storage.model_file(found).is_file()
        if isinstance(found, Runtime):
            if found.executable is None:
                return any(self.is_installed(d.id) for d in self._runtime_dependents(found.id))
            return runtime_executable(found.id, self.registry, self.storage) is not None
        return False

    def _runtime_dependents(self, asset_id: str) -> list[Runtime]:
        return [r for r in self.registry.runtimes.values() if asset_id in r.needs]

    def blockers(self, asset_id: str, active: frozenset[str]) -> tuple[str, ...]:
        found: list[str] = []
        if asset_id in active:
            found.append("the active profile needs it")
        for dep in dependents_of(asset_id, self.registry):
            if self.is_installed(dep):
                found.append(f"{dep} is installed and needs it")
        return tuple(found)

    def entry(self, asset_id: str, active: frozenset[str], plan_state: InstallState) -> Entry:
        found = asset(self.registry, asset_id)
        assert found is not None
        is_model = isinstance(found, Model)
        installed = self.is_installed(asset_id)
        record = self.manifest.get(asset_id)
        sha_state, scope, verified_at = self._sha_state(found, installed, record)
        profiles = tuple(
            p.id
            for p in profiles_for(detect_platform())
            if asset_id in profile_assets(p.id, self.registry)
        )
        return Entry(
            id=asset_id,
            type=AssetType.MODEL if is_model else AssetType.RUNTIME,
            kind=found.kind.value if isinstance(found, Model) else found.backend,
            installed=installed,
            state=plan_state if not installed else InstallState.INSTALLED,
            version=found.version,
            installed_version=self._installed_version(installed, record),
            size_bytes=found.size_bytes,
            size_on_disk=self._size_on_disk(found) if installed else None,
            path=self._path(found, installed),
            sha256=found.sha256,
            sha256_state=sha_state,
            sha256_scope=scope,
            verified_at_ms=verified_at,
            used_by_profiles=profiles,
            in_active_profile=asset_id in active,
            dependents=tuple(
                Dependent(d, self.is_installed(d)) for d in dependents_of(asset_id, self.registry)
            ),
            blockers=self.blockers(asset_id, active),
            license=found.license,
            license_url=found.license_url,
        )

    def _path(self, found: Model | Runtime, installed: bool) -> str | None:
        if isinstance(found, Model):
            return str(self.storage.model_file(found))
        if found.executable is None:
            return str(self.storage.runtimes_root) if installed else None
        if found.is_local_build:
            return str(program_of(found, self.storage))
        return str(self.storage.runtime_dir(found))

    def _size_on_disk(self, found: Model | Runtime) -> int | None:
        if isinstance(found, Model):
            return self.storage.model_file(found).stat().st_size
        if found.executable is None:
            return None
        if found.is_local_build:
            return program_of(found, self.storage).stat().st_size
        return folder_size(self.storage.runtime_dir(found))

    def _installed_version(self, installed: bool, record: Record | None) -> str | None:
        return record.version if installed and record is not None and record.ok else None

    def _sha_state(
        self, found: Model | Runtime, installed: bool, record: Record | None
    ) -> tuple[Sha, Scope, int | None]:
        if isinstance(found, Model):
            scope = Scope.FILE
            if not installed:
                return Sha.NOT_INSTALLED, scope, None
            if record is None:
                return Sha.UNCHECKED, scope, None
            stat = self.storage.model_file(found).stat()
            if record.size_bytes != stat.st_size or record.mtime_ns != stat.st_mtime_ns:
                return Sha.UNCHECKED, scope, None
            return (Sha.VERIFIED if record.ok else Sha.CORRUPT), scope, record.verified_at_ms
        scope = Scope.ARCHIVE_AT_INSTALL
        if not installed:
            return Sha.NOT_INSTALLED, scope, None
        if record is not None and record.ok:
            return Sha.VERIFIED, scope, record.verified_at_ms
        return Sha.UNCHECKED, scope, None

    def verify_model(
        self,
        model: Model,
        should_stop: Callable[[], bool] = lambda: False,
    ) -> Record:
        """Hash the file now and remember the result. Raises FileNotFoundError if it is gone."""
        path = self.storage.model_file(model)
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            while block := handle.read(CHUNK):
                if should_stop():
                    raise InterruptedError("verification stopped")
                digest.update(block)
        stat = path.stat()
        actual = digest.hexdigest()
        record = Record(
            version=model.version if actual == model.sha256 else "unknown",
            sha256=actual,
            size_bytes=stat.st_size,
            mtime_ns=stat.st_mtime_ns,
            verified_at_ms=time.time_ns() // 1_000_000,
            ok=actual == model.sha256,
        )
        self.manifest.put(model.id, record)
        return record

    def record_install(self, plan: Plan, fresh: tuple[Item, ...]) -> None:
        """Called by the downloader for files it has just written and checked against the registry
        digest. A file that was already there is not recorded, because nobody hashed it."""
        now = time.time_ns() // 1_000_000
        by_dest = {item.dest: item for item in fresh}
        for model in self.registry.models.values():
            dest = self.storage.model_file(model)
            if dest in by_dest:
                stat = dest.stat()
                self.manifest.put(
                    model.id,
                    Record(model.version, model.sha256, stat.st_size, stat.st_mtime_ns, now, True),
                )
        for runtime in self.registry.runtimes.values():
            if self.storage.archive_file(runtime) in by_dest:
                self.manifest.put(
                    runtime.id, Record(runtime.version, runtime.sha256, None, None, now, True)
                )


def folder_size(folder: Path) -> int:
    total = 0
    for root, _dirs, files in os.walk(folder):
        for name in files:
            try:
                total += (Path(root) / name).stat().st_size
            except OSError:
                pass
    return total
