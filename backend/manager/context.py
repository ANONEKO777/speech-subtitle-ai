from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from backend.manager import registry as registry_module
from backend.manager.download import TERMINAL, JobRunner, Opener, RetryPolicy
from backend.manager.hardware import Hardware, detect
from backend.manager.inventory import Inventory
from backend.manager.manifest import Manifest
from backend.manager.registry import Registry
from backend.manager.secrets import DpapiSecretStore, SecretStore
from backend.manager.selftest import Probe, real_probe
from backend.manager.selftest_store import SelfTestStore
from backend.manager.settings import SettingsStore
from backend.manager.storage import Storage
from backend.manager.storage_move import MoveRunner
from backend.manager.updates import fetch_registry


@dataclass(frozen=True, slots=True)
class ManagerContext:
    registry: Registry
    storage: Storage
    runner: JobRunner
    detect_hardware: Callable[[], Hardware]
    settings: SettingsStore
    secrets: SecretStore
    manifest: Manifest
    inventory: Inventory
    selftest: SelfTestStore
    mover: MoveRunner
    probe: Probe
    fetch_remote: Callable[[str], Registry]


def build_context(
    user_data: Path,
    registry: Registry | None = None,
    policy: RetryPolicy | None = None,
    opener: Opener | None = None,
    detect_hardware: Callable[[], Hardware] = detect,
    secrets: SecretStore | None = None,
    probe: Probe = real_probe,
    fetch_remote: Callable[[str], Registry] = fetch_registry,
) -> ManagerContext:
    registry = registry or registry_module.load()
    storage = Storage(user_data)
    manifest = Manifest(user_data)
    inventory = Inventory(registry, storage, manifest)
    runner = JobRunner(storage.resolve_url, policy, opener, inventory.record_install)
    return ManagerContext(
        registry=registry,
        storage=storage,
        runner=runner,
        detect_hardware=detect_hardware,
        settings=SettingsStore(user_data),
        secrets=secrets or DpapiSecretStore(user_data),
        manifest=manifest,
        inventory=inventory,
        selftest=SelfTestStore(user_data),
        mover=MoveRunner(
            storage, registry, lambda: any(j.state not in TERMINAL for j in runner.jobs())
        ),
        probe=probe,
        fetch_remote=fetch_remote,
    )
