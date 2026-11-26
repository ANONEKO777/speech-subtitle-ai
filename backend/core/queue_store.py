"""The work queue on disk.

One SQLite file holds the items, the queue settings and the step timings the ETA is made from.
SQLite and not a JSON file because a reorder, a claim or a requeue touches several rows and must
land whole or not at all, and a crash in the middle of a write must leave the last good state.
Nothing here runs a pipeline or knows about HTTP. `QueueStore` is thread safe.
"""

from __future__ import annotations

import json
import logging
import sqlite3
import threading
import uuid
from collections.abc import Iterable, Sequence
from dataclasses import asdict, dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any

from backend.core.jobs import JobOptions
from backend.core.notices import Notice, from_json, to_json
from backend.core.translate import GlossaryEntry

log = logging.getLogger(__name__)

TIMING_WINDOW = 10
"""How many recent runs of a step the ETA averages over."""


class ItemState(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    PAUSED = "paused"
    DONE = "done"
    FAILED = "failed"
    CANCELLED = "cancelled"

    @property
    def finished(self) -> bool:
        return self in (ItemState.DONE, ItemState.FAILED, ItemState.CANCELLED)


class OnDone(StrEnum):
    NOTIFY = "notify"
    SLEEP = "sleep"
    SHUTDOWN = "shutdown"


class QueueError(ValueError):
    """A request the queue cannot honour because of the state it is in or what it names."""


@dataclass(frozen=True, slots=True)
class QueueSettings:
    """What to do when the queue runs out of work. Sleep and shutdown need `allow_power`."""

    on_done: OnDone = OnDone.NOTIFY
    allow_power: bool = False

    def __post_init__(self) -> None:
        if self.on_done is not OnDone.NOTIFY and not self.allow_power:
            raise QueueError(f"on_done {self.on_done.value!r} needs allow_power to be true")


@dataclass(frozen=True, slots=True)
class QueueItem:
    id: str
    position: int
    video_path: str
    project_id: str
    options: JobOptions
    state: ItemState
    created_at_ms: int
    started_at_ms: int | None = None
    finished_at_ms: int | None = None
    attempts: int = 0
    last_error: str | None = None
    audio_s: float | None = None
    last_error_notices: tuple[Notice, ...] = ()
    """The notices inside `last_error`, so the window can word it."""

    @property
    def target_lang(self) -> str:
        return self.options.target_lang

    @property
    def source_lang(self) -> str:
        return self.options.source_lang


@dataclass(frozen=True, slots=True)
class StepTiming:
    step: str
    audio_s: float
    seconds: float


_SCHEMA = """
CREATE TABLE IF NOT EXISTS items (
    id TEXT PRIMARY KEY,
    position INTEGER NOT NULL,
    video_path TEXT NOT NULL,
    project_id TEXT NOT NULL,
    options TEXT NOT NULL,
    state TEXT NOT NULL,
    created_at_ms INTEGER NOT NULL,
    started_at_ms INTEGER,
    finished_at_ms INTEGER,
    attempts INTEGER NOT NULL DEFAULT 0,
    last_error TEXT,
    audio_s REAL,
    last_error_notices TEXT
);
CREATE TABLE IF NOT EXISTS timings (
    seq INTEGER PRIMARY KEY AUTOINCREMENT,
    step TEXT NOT NULL,
    audio_s REAL NOT NULL,
    seconds REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
"""
_COLUMNS = (
    "id, position, video_path, project_id, options, state, created_at_ms, started_at_ms, "
    "finished_at_ms, attempts, last_error, audio_s, last_error_notices"
)
_ADDED_COLUMNS = {"last_error_notices": "TEXT"}
"""Columns that a `queue.db` of an earlier version lacks. Each is added when the file opens."""


def options_json(options: JobOptions) -> str:
    return json.dumps(asdict(options), ensure_ascii=False)


def options_from_json(text: str) -> JobOptions:
    raw: dict[str, Any] = json.loads(text)
    glossary = tuple(GlossaryEntry(g["term"], g["zh"]) for g in raw.pop("glossary"))
    return JobOptions(glossary=glossary, **raw)


def _stored_notices(text: str | None) -> tuple[Notice, ...]:
    try:
        return () if text is None else from_json(json.loads(text))
    except ValueError:
        return ()


def _item(row: Sequence[Any]) -> QueueItem:
    return QueueItem(
        id=row[0],
        position=row[1],
        video_path=row[2],
        project_id=row[3],
        options=options_from_json(row[4]),
        state=ItemState(row[5]),
        created_at_ms=row[6],
        started_at_ms=row[7],
        finished_at_ms=row[8],
        attempts=row[9],
        last_error=row[10],
        audio_s=row[11],
        last_error_notices=_stored_notices(row[12]),
    )


class QueueStore:
    def __init__(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._db = sqlite3.connect(path, check_same_thread=False, isolation_level=None)
        self._db.execute("PRAGMA journal_mode=WAL")
        self._db.execute("PRAGMA synchronous=FULL")
        self._db.executescript(_SCHEMA)
        self._add_columns()

    def _add_columns(self) -> None:
        have = {row[1] for row in self._db.execute("PRAGMA table_info(items)")}
        for name, kind in _ADDED_COLUMNS.items():
            if name not in have:
                self._db.execute(f"ALTER TABLE items ADD COLUMN {name} {kind}")

    def close(self) -> None:
        with self._lock:
            self._db.close()

    def _tx(self, statements: Iterable[tuple[str, Sequence[Any]]]) -> int:
        """Run the statements as one transaction. Returns the rows changed by the last one."""
        with self._lock:
            self._db.execute("BEGIN IMMEDIATE")
            try:
                changed = 0
                for sql, args in statements:
                    changed = self._db.execute(sql, args).rowcount
            except BaseException:
                self._db.execute("ROLLBACK")
                raise
            self._db.execute("COMMIT")
            return changed

    def _rows(self, sql: str, args: Sequence[Any] = ()) -> list[Any]:
        with self._lock:
            return self._db.execute(sql, args).fetchall()

    def recover(self) -> list[str]:
        """Put the items a dead backend left running back in the queue, ahead of nothing else
        (they keep their position). Returns their ids. Their step cache lets a rerun resume."""
        ids = [r[0] for r in self._rows("SELECT id FROM items WHERE state = 'running'")]
        self._tx([("UPDATE items SET state = 'queued' WHERE state = 'running'", ())])
        return ids

    def items(self) -> list[QueueItem]:
        return [_item(r) for r in self._rows(f"SELECT {_COLUMNS} FROM items ORDER BY position")]

    def get(self, item_id: str) -> QueueItem | None:
        rows = self._rows(f"SELECT {_COLUMNS} FROM items WHERE id = ?", (item_id,))
        return _item(rows[0]) if rows else None

    def add(
        self,
        video_path: str,
        project_id: str,
        options: JobOptions,
        audio_s: float | None,
        now_ms: int,
    ) -> QueueItem:
        """Append an item. The same video into the same language twice while the first is not
        finished is a `QueueError`, whatever language it is spoken in: a project holds one."""
        with self._lock:
            for item in self.items():
                if (
                    item.project_id == project_id
                    and item.target_lang == options.target_lang
                    and not item.state.finished
                ):
                    raise QueueError(f"already in the queue as {item.id} ({item.state.value})")
            row = self._rows("SELECT COALESCE(MAX(position), -1) + 1 FROM items")[0][0]
            item = QueueItem(
                uuid.uuid4().hex,
                row,
                video_path,
                project_id,
                options,
                ItemState.QUEUED,
                now_ms,
                audio_s=audio_s,
            )
            self._tx(
                [
                    (
                        f"INSERT INTO items ({_COLUMNS}) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                        (
                            item.id,
                            item.position,
                            video_path,
                            project_id,
                            options_json(options),
                            item.state.value,
                            now_ms,
                            None,
                            None,
                            0,
                            None,
                            audio_s,
                            None,
                        ),
                    )
                ]
            )
            return item

    def claim_next(self, now_ms: int) -> QueueItem | None:
        """Move the first queued item to running and count the attempt."""
        with self._lock:
            rows = self._rows(
                "SELECT id FROM items WHERE state = 'queued' ORDER BY position LIMIT 1"
            )
            if not rows:
                return None
            item_id = rows[0][0]
            self._tx(
                [
                    (
                        "UPDATE items SET state = 'running', started_at_ms = ?, "
                        "finished_at_ms = NULL, attempts = attempts + 1, last_error = NULL, "
                        "last_error_notices = NULL "
                        "WHERE id = ? AND state = 'queued'",
                        (now_ms, item_id),
                    )
                ]
            )
            return self.get(item_id)

    def move(self, item_id: str, frm: Sequence[ItemState], to: ItemState, now_ms: int) -> bool:
        """Change the state of an item that is in one of the states `frm`. False when it is not,
        so a caller that lost a race sees it. A finish time is set for a finished state."""
        marks = ",".join("?" * len(frm))
        finished = now_ms if to.finished else None
        return (
            self._tx(
                [
                    (
                        f"UPDATE items SET state = ?, finished_at_ms = ? "
                        f"WHERE id = ? AND state IN ({marks})",
                        (to.value, finished, item_id, *(s.value for s in frm)),
                    )
                ]
            )
            == 1
        )

    def finish(
        self,
        item_id: str,
        state: ItemState,
        now_ms: int,
        error: str | None,
        notices: Sequence[Notice] = (),
    ) -> None:
        stored = json.dumps(to_json(notices), ensure_ascii=False) if notices else None
        self._tx(
            [
                (
                    "UPDATE items SET state = ?, finished_at_ms = ?, last_error = ?, "
                    "last_error_notices = ? WHERE id = ?",
                    (state.value, now_ms, error, stored, item_id),
                )
            ]
        )

    def to_end(self, item_id: str) -> None:
        """Retry: queue a finished item again, behind every other item."""
        with self._lock:
            end = self._rows("SELECT COALESCE(MAX(position), -1) + 1 FROM items")[0][0]
            self._tx(
                [
                    (
                        "UPDATE items SET state = 'queued', position = ?, finished_at_ms = NULL "
                        "WHERE id = ? AND state IN ('failed', 'cancelled')",
                        (end, item_id),
                    )
                ]
            )

    def set_audio_s(self, item_id: str, audio_s: float) -> None:
        with self._lock:
            self._tx([("UPDATE items SET audio_s = ? WHERE id = ?", (audio_s, item_id))])

    def reorder(self, ids: Sequence[str]) -> None:
        """Put `ids` first, in that order. The other items follow in their current order."""
        with self._lock:
            known = [i.id for i in self.items()]
            if len(set(ids)) != len(ids) or not set(ids) <= set(known):
                raise QueueError("the order must list each known item once")
            order = [*ids, *(i for i in known if i not in set(ids))]
            self._tx(
                [
                    ("UPDATE items SET position = ? WHERE id = ?", (pos, i))
                    for pos, i in enumerate(order)
                ]
            )

    def remove(self, ids: Iterable[str]) -> list[str]:
        """Delete finished items among `ids`. Returns the ids deleted."""
        with self._lock:
            gone = [i.id for i in self.items() if i.id in set(ids) and i.state.finished]
            self._tx([("DELETE FROM items WHERE id = ?", (i,)) for i in gone])
            return gone

    def settings(self) -> QueueSettings:
        raw = self._meta("settings")
        if raw is None:
            return QueueSettings()
        try:
            data = json.loads(raw)
            return QueueSettings(OnDone(data["on_done"]), bool(data["allow_power"]))
        except (ValueError, KeyError, TypeError):
            log.warning("queue settings in the queue file are invalid; using the safe default")
            return QueueSettings()

    def set_settings(self, settings: QueueSettings) -> None:
        text = json.dumps({"on_done": settings.on_done.value, "allow_power": settings.allow_power})
        self._set_meta("settings", text)

    @property
    def paused(self) -> bool:
        return self._meta("paused") == "1"

    def set_paused(self, paused: bool) -> None:
        self._set_meta("paused", "1" if paused else "0")

    def _meta(self, key: str) -> str | None:
        rows = self._rows("SELECT value FROM meta WHERE key = ?", (key,))
        return rows[0][0] if rows else None

    def _set_meta(self, key: str, value: str) -> None:
        self._tx([("INSERT OR REPLACE INTO meta (key, value) VALUES (?, ?)", (key, value))])

    def record_timings(self, timings: Iterable[StepTiming]) -> None:
        self._tx(
            [
                (
                    "INSERT INTO timings (step, audio_s, seconds) VALUES (?, ?, ?)",
                    (t.step, t.audio_s, t.seconds),
                )
                for t in timings
            ]
        )

    def recent_timings(self) -> list[StepTiming]:
        """The last `TIMING_WINDOW` runs of each step."""
        rows = self._rows(
            "SELECT step, audio_s, seconds FROM timings t WHERE seq IN ("
            "SELECT seq FROM timings WHERE step = t.step ORDER BY seq DESC LIMIT ?)",
            (TIMING_WINDOW,),
        )
        return [StepTiming(*r) for r in rows]
