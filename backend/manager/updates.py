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
from functools import partial
from typing import cast

from backend.core import notices
from backend.core.notices import Notice, noticed
from backend.manager.inventory import Inventory, asset
from backend.manager.registry import Registry, RegistryError
from backend.manager.registry import parse as parse_registry

FETCH_TIMEOUT_S = 10.0
_MAX_BYTES = 2 << 20


class UpdateError(Exception):
    """A remote registry that could not be read."""

    def __init__(self, url: str, message: str) -> None:
        super().__init__(message)
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
    message_notices: tuple[Notice, ...]


@dataclass(frozen=True, slots=True)
class UpdateReport:
    remote_url: str | None
    checked_at_ms: int
    message: str
    items: tuple[UpdateItem, ...]
    new_in_remote: tuple[str, ...]
    message_notices: tuple[Notice, ...]


def fetch_registry(url: str) -> Registry:
    request = urllib.request.Request(url, headers={"Accept": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=FETCH_TIMEOUT_S) as response:
            raw = cast("object", json.loads(response.read(_MAX_BYTES).decode("utf-8")))
        return parse_registry(raw)
    except urllib.error.HTTPError as exc:
        why = notices.REGISTRY_HTTP(url=url, status=f"{exc.code} {exc.reason}")
        raise noticed(partial(UpdateError, url), why) from exc
    except urllib.error.URLError as exc:
        why = notices.REGISTRY_UNREACHABLE(url=url, reason=str(exc.reason))
        raise noticed(partial(UpdateError, url), why) from exc
    except (RegistryError, ValueError) as exc:
        why = notices.REGISTRY_INVALID(url=url, error=str(exc))
        raise noticed(partial(UpdateError, url), why) from exc
    except (TimeoutError, OSError) as exc:
        why = notices.REGISTRY_UNREADABLE(url=url, error=f"{type(exc).__name__}: {exc}")
        raise noticed(partial(UpdateError, url), why) from exc


def _item(
    inv: Inventory, asset_id: str, remote: Registry | None, remote_url: str | None
) -> UpdateItem:
    bundled = asset(inv.registry, asset_id)
    assert bundled is not None
    other = asset(remote, asset_id) if remote is not None else None
    remote_version = other.version if other else None

    def item(
        status: UpdateStatus, installed: str | None, installable: bool, said: Notice
    ) -> UpdateItem:
        return UpdateItem(
            asset_id,
            status,
            installed,
            bundled.version,
            remote_version,
            installable,
            said.message,
            (said,),
        )

    if not inv.is_installed(asset_id):
        return item(UpdateStatus.NOT_INSTALLED, None, True, notices.ITEM_NOT_INSTALLED())
    record = inv.manifest.get(asset_id)
    if record is None or not record.ok:
        why = notices.ITEM_CHECK_FAILED if record else notices.ITEM_UNRECORDED
        return item(UpdateStatus.UNKNOWN, None, True, why(version=bundled.version))
    target = other or bundled
    if record.sha256 == target.sha256 and record.version == target.version:
        agrees = (
            notices.ITEM_MATCHES_REMOTE(version=record.version, url=str(remote_url))
            if remote
            else notices.ITEM_MATCHES_BUNDLE(version=record.version)
        )
        return item(UpdateStatus.CURRENT, record.version, True, agrees)
    newer_than_bundle = other is not None and (other.sha256 != bundled.sha256)
    note = (
        notices.ITEM_NEEDS_APP(
            installed=record.version,
            remote=other.version if other else "",
            shipped=bundled.version,
        )
        if newer_than_bundle
        else notices.ITEM_OLDER(installed=record.version, available=target.version)
    )
    return item(UpdateStatus.UPDATE_AVAILABLE, record.version, not newer_than_bundle, note)


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
        summary = notices.UPDATES_AVAILABLE(assets=available)
    elif remote_url:
        summary = notices.UPDATES_ALL_MATCH(url=remote_url)
    else:
        summary = notices.UPDATES_NO_REMOTE()
    now = time.time_ns() // 1_000_000
    return UpdateReport(remote_url, now, summary.message, items, new, (summary,))
