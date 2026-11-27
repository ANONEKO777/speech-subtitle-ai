from __future__ import annotations

import json
import os
import sys
import threading
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from types import MappingProxyType
from typing import cast

from backend.core import notices
from backend.core.notices import noticed
from backend.manager.registry import Model, Runtime

USER_DATA_ENV = "VST_USER_DATA"
CONFIG_FILE = "storage.json"
APP_DIR = "video-subtitle-translator"
_SCHEMES = ("https://", "http://")


class StorageError(ValueError):
    pass


def default_user_data(
    env: Mapping[str, str] | None = None, system: str | None = None, home: Path | None = None
) -> Path:
    """`$VST_USER_DATA`, else the folder the platform keeps application data in: `%LOCALAPPDATA%`
    on Windows, `~/Library/Application Support` on a Mac. The desktop shell computes the same
    path, so a change here needs the same change in `app/src-tauri/src/folders.rs`."""
    env = os.environ if env is None else env
    if env.get(USER_DATA_ENV):
        return Path(env[USER_DATA_ENV])
    system = sys.platform if system is None else system
    home = Path.home() if home is None else home
    if system == "darwin":
        return home / "Library" / "Application Support" / APP_DIR
    base = env.get("LOCALAPPDATA") or str(home / ".local" / "share")
    return Path(base) / APP_DIR


@dataclass(frozen=True, slots=True)
class StorageConfig:
    models_dir: Path | None = None
    mirrors: Mapping[str, str] = field(default_factory=lambda: MappingProxyType({}))


def parse_config(raw: object) -> StorageConfig:
    if not isinstance(raw, dict):
        raise StorageError("storage config must be an object with models_dir and mirrors")
    data = cast(dict[object, object], raw)
    if set(data) - {"models_dir", "mirrors"}:
        raise StorageError("storage config must be an object with models_dir and mirrors")
    models_dir = data.get("models_dir")
    if models_dir is not None:
        if not isinstance(models_dir, str) or not Path(models_dir).is_absolute():
            raise noticed(StorageError, notices.STORAGE_NOT_ABSOLUTE())
    mirrors = data.get("mirrors", {})
    if not isinstance(mirrors, dict):
        raise StorageError("mirrors must map an origin prefix to a replacement prefix")
    checked: dict[str, str] = {}
    for origin, target in cast(dict[object, object], mirrors).items():
        if not (
            isinstance(origin, str)
            and isinstance(target, str)
            and origin.startswith("https://")
            and target.startswith(_SCHEMES)
        ):
            raise StorageError(f"bad mirror {origin!r} -> {target!r}: need https:// -> http(s)://")
        checked[origin] = target
    return StorageConfig(Path(models_dir) if models_dir else None, MappingProxyType(checked))


class Storage:
    def __init__(self, user_data: Path) -> None:
        self.user_data = user_data
        self._lock = threading.Lock()
        self._config = self._load()

    @property
    def config(self) -> StorageConfig:
        return self._config

    @property
    def models_root(self) -> Path:
        return self._config.models_dir or self.user_data / "models"

    @property
    def runtimes_root(self) -> Path:
        return self.user_data / "runtimes"

    @property
    def archives_dir(self) -> Path:
        return self.runtimes_root / "_archives"

    def model_file(self, model: Model) -> Path:
        return self.models_root / model.id / model.file

    def runtime_dir(self, runtime: Runtime) -> Path:
        return self.runtimes_root / runtime.id

    def archive_file(self, runtime: Runtime) -> Path:
        return self.archives_dir / runtime.file

    def resolve_url(self, url: str) -> str:
        mirrors = self._config.mirrors
        for origin in sorted(mirrors, key=len, reverse=True):
            if url.startswith(origin):
                return mirrors[origin] + url[len(origin) :]
        return url

    def update(self, config: StorageConfig) -> None:
        with self._lock:
            target = self.user_data / CONFIG_FILE
            target.parent.mkdir(parents=True, exist_ok=True)
            temp = target.with_name(target.name + ".tmp")
            payload = {
                "models_dir": str(config.models_dir) if config.models_dir else None,
                "mirrors": dict(config.mirrors),
            }
            temp.write_text(json.dumps(payload, indent=2), encoding="utf-8")
            os.replace(temp, target)
            self._config = config

    def _load(self) -> StorageConfig:
        path = self.user_data / CONFIG_FILE
        if not path.is_file():
            return StorageConfig()
        try:
            return parse_config(json.loads(path.read_text(encoding="utf-8")))
        except (OSError, ValueError) as exc:
            raise StorageError(f"cannot read {path}: {exc}") from exc
