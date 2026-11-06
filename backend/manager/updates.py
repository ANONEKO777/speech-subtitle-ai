"""Compare what is installed with the registry, bundled or remote.

The bundled registry ships with the app and is what the downloader installs from. A remote
registry URL is optional and set in the settings; it is only read, to say that a newer app or
registry exists. No remote is ever assumed."""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum
from typing import cast

from backend.manager.inventory import Inventory, asset
from backend.manager.registry import Registry, RegistryError
from backend.manager.registry import parse as parse_registry

FETCH_TIMEOUT_S = 10.0
_MAX_BYTES = 2 << 20


class UpdateError(Exception):
    def __init__(self, url: str, reason: str) -> None:
        super().__init__(f"could not read the registry at {url}: {reason}")
        self.url = url


class UpdateStatus(StrEnum):
    NOT_INSTALLED = "not_installed"
    CURRENT = "current"
    UPDATE_AVAILABLE = "update_available"
    UNKNOWN = "unknown"


@dataclass(frozen=True, slots=True)
class UpdateItem:
    id: str
    status: UpdateStatus
    installed_version: str | None
    registry_version: str
    remote_version: str | None
    installable: bool
    """The downloader can fetch the newer version with this app. False when only the remote
    registry knows it, which means the app itself needs updating."""
    message: str


@dataclass(frozen=True, slots=True)
class UpdateReport:
    remote_url: str | None
    checked_at_ms: int
    message: str
    items: tuple[UpdateItem, ...]
    new_in_remote: tuple[str, ...]


def fetch_registry(url: str) -> Registry:
    request = urllib.request.Request(url, headers={"Accept": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=FETCH_TIMEOUT_S) as response:
            raw = cast("object", json.loads(response.read(_MAX_BYTES).decode("utf-8")))
        return parse_registry(raw)
    except urllib.error.HTTPError as exc:
        raise UpdateError(url, f"HTTP {exc.code} {exc.reason}") from exc
    except urllib.error.URLError as exc:
        raise UpdateError(url, f"cannot connect ({exc.reason})") from exc
    except (RegistryError, ValueError) as exc:
        raise UpdateError(url, f"it is not a valid registry ({exc})") from exc
    except (TimeoutError, OSError) as exc:
        raise UpdateError(url, f"{type(exc).__name__}: {exc}") from exc


def _item(
    inv: Inventory, asset_id: str, remote: Registry | None, remote_url: str | None
) -> UpdateItem:
    bundled = asset(inv.registry, asset_id)
    assert bundled is not None
    other = asset(remote, asset_id) if remote is not None else None
    remote_version = other.version if other else None
    if not inv.is_installed(asset_id):
        return UpdateItem(
            asset_id,
            UpdateStatus.NOT_INSTALLED,
            None,
            bundled.version,
            remote_version,
            True,
            "not installed",
        )
    record = inv.manifest.get(asset_id)
    if record is None or not record.ok:
        why = "its last check failed" if record else "its version was not recorded"
        return UpdateItem(
            asset_id, UpdateStatus.UNKNOWN, None, bundled.version, remote_version, True,
            f"installed, but {why}; verify or re-download it to compare with "
            f"registry version {bundled.version}",
        )  # fmt: skip
    target = other or bundled
    if record.sha256 == target.sha256 and record.version == target.version:
        where = f"remote registry {remote_url} agrees" if remote else "no remote configured"
        return UpdateItem(
            asset_id, UpdateStatus.CURRENT, record.version, bundled.version, remote_version, True,
            f"registry version {record.version} installed, {where}",
        )  # fmt: skip
    newer_than_bundle = other is not None and (other.sha256 != bundled.sha256)
    note = (
        f"installed {record.version}, remote registry lists {other.version if other else ''}; "
        f"this app ships {bundled.version}, so update the app to get it"
        if newer_than_bundle
        else f"installed {record.version}, the registry has {target.version}"
    )
    return UpdateItem(
        asset_id, UpdateStatus.UPDATE_AVAILABLE, record.version, bundled.version, remote_version,
        not newer_than_bundle, note,
    )  # fmt: skip


def check_updates(
    inv: Inventory,
    remote_url: str | None,
    fetch: Callable[[str], Registry] = fetch_registry,
) -> UpdateReport:
    remote = fetch(remote_url) if remote_url else None
    ids = [*inv.registry.models, *inv.registry.runtimes]
    items = tuple(_item(inv, i, remote, remote_url) for i in ids)
    new = tuple(i for i in (*remote.models, *remote.runtimes) if i not in ids) if remote else ()
    available = [i.id for i in items if i.status is UpdateStatus.UPDATE_AVAILABLE]
    if available:
        message = f"Updates available for {', '.join(available)}."
    elif remote_url:
        message = f"Everything installed matches the remote registry at {remote_url}."
    else:
        message = (
            "No remote registry is configured; compared with the registry shipped with this app."
        )
    return UpdateReport(remote_url, time.time_ns() // 1_000_000, message, items, new)
