"""What was installed and checked, kept in `installed.json` next to the settings.

A downloaded model is verified against its SHA-256 while it is written. This file remembers that,
with the size and modification time of the file at that moment, so the inventory can say
"verified" without hashing gigabytes on every request. If the file changes, the record no longer
matches and the state falls back to "unchecked"."""

from __future__ import annotations

import json
import logging
import threading
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import cast

from backend.manager.settings import write_json_atomic

log = logging.getLogger(__name__)

MANIFEST_FILE = "installed.json"
SCHEMA_VERSION = 1


@dataclass(frozen=True, slots=True)
class Record:
    version: str
    sha256: str
    """The digest that was computed or downloaded against, not the registry's current one."""
    size_bytes: int | None
    mtime_ns: int | None
    """Size and modification time of the file when it was checked. None for a runtime folder."""
    verified_at_ms: int
    ok: bool


def _record(raw: object) -> Record | None:
    if not isinstance(raw, dict):
        return None
    d = cast("dict[str, object]", raw)
    try:
        size, mtime = d["size_bytes"], d["mtime_ns"]
        if not (
            isinstance(d["version"], str)
            and isinstance(d["sha256"], str)
            and isinstance(d["verified_at_ms"], int)
            and type(d["ok"]) is bool
            and (size is None or isinstance(size, int))
            and (mtime is None or isinstance(mtime, int))
        ):
            return None
        return Record(d["version"], d["sha256"], size, mtime, d["verified_at_ms"], d["ok"])
    except KeyError:
        return None


class Manifest:
    def __init__(self, user_data: Path) -> None:
        self._path = user_data / MANIFEST_FILE
        self._lock = threading.Lock()
        self._records = self._load()

    def get(self, asset_id: str) -> Record | None:
        with self._lock:
            return self._records.get(asset_id)

    def put(self, asset_id: str, record: Record) -> None:
        with self._lock:
            self._records[asset_id] = record
            self._write()

    def forget(self, asset_id: str) -> None:
        with self._lock:
            if self._records.pop(asset_id, None) is not None:
                self._write()

    def _write(self) -> None:
        write_json_atomic(
            self._path,
            {
                "schema_version": SCHEMA_VERSION,
                "assets": {k: asdict(v) for k, v in self._records.items()},
            },
        )

    def _load(self) -> dict[str, Record]:
        try:
            raw = cast("object", json.loads(self._path.read_text(encoding="utf-8")))
        except FileNotFoundError:
            return {}
        except (OSError, ValueError) as exc:
            log.warning("%s was not used: %s", self._path, exc)
            return {}
        if not isinstance(raw, dict):
            return {}
        assets = cast("dict[str, object]", raw).get("assets")
        if not isinstance(assets, dict):
            return {}
        parsed = {k: _record(v) for k, v in cast("dict[str, object]", assets).items()}
        return {k: v for k, v in parsed.items() if v is not None}
