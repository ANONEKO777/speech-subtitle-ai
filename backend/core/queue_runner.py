"""Runs the queue: one item at a time through the job book, and every command on it.

The runner is one thread. It takes the first queued item, resolves its settings, hands it to the
`JobBook` (whose single worker is the one GPU lane, so a job started by hand through the per-job
routes waits its turn like a queue item) and waits for it. Whatever happens to that item, the
next one starts. The queue file is the durable state: an item a dead backend left running is
queued again at start and resumes through the pipeline cache. Live progress is not saved.
"""

from __future__ import annotations

import logging
import os
import stat
import threading
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import asdict, dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any

from backend.core import audio
from backend.core.jobs import (
    EventLog,
    Job,
    JobBook,
    JobOptions,
    JobStatus,
    ProjectBusy,
    Resolver,
)
from backend.core.media import is_media
from backend.core.model import Step
from backend.core.notices import (
    BATCH_CANNOT_CANCEL,
    BATCH_CANNOT_PAUSE,
    BATCH_CANNOT_RESUME,
    BATCH_CANNOT_RETRY,
    BATCH_CRASHED,
    BATCH_FOLDER_SLOW,
    BATCH_NOT_A_FILE,
    BATCH_NOT_MEDIA,
    VIDEO_GONE,
    Notice,
    Template,
    from_json,
    noticed,
    notices_of,
    to_json,
)
from backend.core.pipeline import Ports, Settings
from backend.core.power import COUNTDOWN_S, Countdown, PowerAction, PowerExecutor
from backend.core.projects import ProjectStore
from backend.core.queue_eta import Live, etas, live_from_overall, step_rates
from backend.core.queue_store import (
    ItemState,
    OnDone,
    QueueError,
    QueueItem,
    QueueSettings,
    QueueStore,
    StepTiming,
)

log = logging.getLogger(__name__)

POLL_S = 0.5
SCAN_TIMEOUT_S = 10.0
PROBE_BUDGET_S = 5.0
Probe = Callable[[Path], float | None]


class QueueEventKind(StrEnum):
    ITEM = "item"
    REMOVED = "removed"
    ORDER = "order"
    QUEUE = "queue"
    DONE = "done"
    COUNTDOWN = "countdown"
    COUNTDOWN_CANCELLED = "countdown_cancelled"
    POWER = "power"


class Stop(StrEnum):
    """Why a running item is being stopped, which decides the state it ends in."""

    CANCEL = "cancel"
    PAUSE = "pause"
    REQUEUE = "requeue"


@dataclass(frozen=True, slots=True)
class Added:
    items: list[QueueItem]
    skipped: list[tuple[str, str, tuple[Notice, ...]]]
    """Each path that was not added, why, and the notices inside the why."""


def _is_link(entry: os.DirEntry[str]) -> bool:
    """A symlink or, on Windows, any reparse point such as a junction."""
    if entry.is_symlink():
        return True
    attributes = getattr(entry.stat(follow_symlinks=False), "st_file_attributes", 0)
    return bool(attributes & stat.FILE_ATTRIBUTE_REPARSE_POINT)


def _walk(folder: Path, recursive: bool) -> list[Path]:
    if not folder.is_dir():
        raise NotADirectoryError(str(folder))
    found: list[Path] = []
    pending = [folder]
    while pending:
        with os.scandir(pending.pop()) as entries:
            for entry in entries:
                if entry.is_dir(follow_symlinks=False):
                    if recursive and not _is_link(entry):
                        pending.append(Path(entry.path))
                elif entry.is_file(follow_symlinks=False) and is_media(entry.name):
                    found.append(Path(entry.path))
    return sorted(found)


def scan_folder(folder: Path, recursive: bool, timeout_s: float | None = None) -> list[Path]:
    """The media files in `folder`, by name. A recursive scan does not enter symlinks or
    junctions, and a folder that does not answer in time (`SCAN_TIMEOUT_S`, an unreachable network
    share) is a `QueueError`. A path that is not a folder is a `NotADirectoryError`."""
    timeout_s = SCAN_TIMEOUT_S if timeout_s is None else timeout_s
    outcome: list[list[Path] | Exception] = []

    def work() -> None:
        try:
            outcome.append(_walk(folder, recursive))
        except Exception as exc:
            outcome.append(exc)

    thread = threading.Thread(target=work, name="vst-scan", daemon=True)
    thread.start()
    thread.join(timeout_s)
    if not outcome:
        raise noticed(QueueError, BATCH_FOLDER_SLOW(seconds=f"{timeout_s:g}"))
    result = outcome[0]
    if isinstance(result, Exception):
        raise result
    return result


def _said(notice: Notice) -> tuple[str, tuple[Notice, ...]]:
    return notice.message, (notice,)


def _now_ms() -> int:
    return time.time_ns() // 1_000_000


def _settings_json(settings: QueueSettings) -> dict[str, Any]:
    return {"on_done": settings.on_done.value, "allow_power": settings.allow_power}


class QueueRunner:
    def __init__(
        self,
        store: QueueStore,
        projects: ProjectStore,
        book: JobBook,
        resolver: Resolver,
        *,
        executor: PowerExecutor | None = None,
        countdown_s: float = COUNTDOWN_S,
        probe: Probe = audio.probe_duration_s,
    ) -> None:
        self.events = EventLog()
        self._store = store
        self._projects = projects
        self._book = book
        self._resolver = resolver
        self._probe = probe
        self._power = Countdown(executor, self._emit, countdown_s, self._power_due)
        book.on_submit(self._work_arrived)
        self._lock = threading.RLock()
        self._wake = threading.Event()
        self._halt = threading.Event()
        self._thread: threading.Thread | None = None
        self._current: str | None = None
        self._job: Job | None = None
        self._live: Live | None = None
        self._intent: Stop | None = None
        self._worked = False

    def start(self) -> None:
        for item_id in self._store.recover():
            log.warning("queue item %s was running when the backend stopped; queued again", item_id)
        self._thread = threading.Thread(target=self._loop, name="vst-queue", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        """Stop the running item (it is queued again) and the thread, and cancel a countdown."""
        self._halt.set()
        with self._lock:
            if self._current is not None:
                self._stop_current(self._current, Stop.REQUEUE)
        self._wake.set()
        if self._thread is not None:
            self._thread.join()
        self._power.cancel()
        self._power.join()

    def _emit(self, kind: str, data: Mapping[str, object]) -> None:
        self.events.append(QueueEventKind(kind), data)

    def _emit_item(self, item_id: str) -> None:
        """Report one item. An item deleted since is skipped."""
        try:
            self._emit("item", self.describe_item(item_id))
        except KeyError:
            log.info("queue item %s is gone; no item event", item_id)

    def _stop_current(self, item_id: str, why: Stop) -> bool:
        with self._lock:
            if self._current != item_id:
                return False
            self._intent = why
            if self._job is not None:
                self._job.request_cancel()
            return True

    def _loop(self) -> None:
        while not self._halt.is_set():
            try:
                self._step()
            except Exception:
                log.exception("queue loop iteration failed; the queue goes on")
                self._abandon_current()
                self._halt.wait(1.0)

    def _step(self) -> None:
        self._wake.clear()
        item = self._claim()
        if item is None:
            self._check_done()
            self._wake.wait(1.0)
            return
        self._worked = True
        self._run_item(item)

    def _abandon_current(self) -> None:
        """After a crash outside the item's own run, fail the item that was left running."""
        with self._lock:
            item_id = self._current
            self._current = self._job = self._live = self._intent = None
            if item_id is None:
                return
            try:
                crashed = BATCH_CRASHED()
                self._store.finish(
                    item_id, ItemState.FAILED, _now_ms(), crashed.message, (crashed,)
                )
            except Exception:
                log.exception("queue item %s could not be marked failed", item_id)

    def _claim(self) -> QueueItem | None:
        with self._lock:
            if self._store.paused:
                return None
            item = self._store.claim_next(_now_ms())
            if item is not None:
                self._current, self._intent, self._job, self._live = item.id, None, None, None
        if item is not None:
            self._power.cancel()
            self._emit_item(item.id)
        return item

    def _idle(self) -> bool:
        return all(i.state.finished for i in self._store.items())

    def _power_due(self, action: PowerAction) -> bool:
        """Whether `action` may still run: no queue item is waiting or running, no job is active
        (a job started by hand counts), and the user still opted in to it."""
        settings = self._store.settings()
        return (
            self._idle()
            and not self._book.busy()
            and settings.allow_power
            and settings.on_done.value == action.value
        )

    def _work_arrived(self) -> None:
        """The queue stopped being idle. A pending power action must not outlive that."""
        self._power.cancel()
        self._wake.set()

    def _check_done(self) -> None:
        """The queue is done when nothing is waiting and no job, a hand-started one included, is
        still active. While a job runs this returns and the loop asks again, so the countdown
        starts when the last job finishes."""
        if not self._worked or not self._idle() or self._book.busy():
            return
        self._worked = False
        self._emit("done", {"counts": self._counts()})
        settings = self._store.settings()
        if settings.on_done is not OnDone.NOTIFY:
            self._power.start(PowerAction(settings.on_done.value))

    def _run_item(self, item: QueueItem) -> None:
        state, error, notices = ItemState.FAILED, None, ()
        try:
            state, error, notices = self._execute(item)
        except Exception as exc:
            log.exception("queue item %s crashed", item.id)
            error = f"{type(exc).__name__}: {exc}"
            notices = notices_of(exc, error)
        with self._lock:
            intent = self._intent
            self._current = self._job = self._live = self._intent = None
            if state is ItemState.CANCELLED:
                if intent is None:
                    intent = Stop.REQUEUE if self._halt.is_set() else Stop.CANCEL
                state = {
                    Stop.CANCEL: ItemState.CANCELLED,
                    Stop.PAUSE: ItemState.PAUSED,
                    Stop.REQUEUE: ItemState.QUEUED,
                }[intent]
            if state in (ItemState.QUEUED, ItemState.PAUSED):
                self._store.move(item.id, [ItemState.RUNNING], state, _now_ms())
            else:
                self._store.finish(item.id, state, _now_ms(), error, notices)
        self._emit_item(item.id)

    def _execute(self, item: QueueItem) -> tuple[ItemState, str | None, tuple[Notice, ...]]:
        video = Path(item.video_path)
        if not video.is_file():
            gone = VIDEO_GONE(video=str(video))
            return ItemState.FAILED, gone.message, (gone,)
        info, _ = self._projects.create(video)
        settings, ports = self._resolver(item.options, info.folder)
        job = self._submit(info.id, video, info.folder, settings, ports)
        if job is None:
            return ItemState.CANCELLED, None, ()
        with self._lock:
            self._job = job
            if self._intent is not None:
                job.request_cancel()
        while not job.done.wait(POLL_S):
            self._observe(item.id, job)
        self._observe(item.id, job)
        match job.status:
            case JobStatus.DONE:
                self._record_timings(item, info.folder, job)
                return ItemState.DONE, None, ()
            case JobStatus.FAILED:
                error = str(job.outcome.get("error"))
                return ItemState.FAILED, error, from_json(job.outcome.get("error_notices"))
            case _:
                return ItemState.CANCELLED, None, ()

    def _submit(
        self, pid: str, video: Path, folder: Path, settings: Settings, ports: Ports
    ) -> Job | None:
        """Submit the job. When a job started by hand holds the project, wait for it. None when
        the item was stopped or the backend is stopping while it waited."""
        while True:
            try:
                return self._book.submit(pid, video, folder, settings, ports)
            except ProjectBusy as busy:
                other = self._book.get(busy.job_id)
                while other is not None and not other.done.wait(POLL_S):
                    if self._halt.is_set() or self._intent is not None:
                        return None
                if self._halt.is_set() or self._intent is not None:
                    return None

    def _observe(self, item_id: str, job: Job) -> None:
        described = job.describe()
        step = Step(str(described["step"])) if described["step"] else None
        live = live_from_overall(job.id, step, float(str(described["overall"])))
        with self._lock:
            last = self._live
            if self._current != item_id or (
                last is not None
                and (last.step, round(last.overall, 2)) == (live.step, round(live.overall, 2))
            ):
                return
            self._live = live
        self._emit_item(item_id)

    def _record_timings(self, item: QueueItem, folder: Path, job: Job) -> None:
        audio_s = item.audio_s
        if audio_s is None:
            try:
                audio_s = audio.wav_duration_ms(folder / "audio.wav") / 1000
            except (OSError, ValueError):
                return
        report: Any = job.outcome.get("report") or {}
        self._store.record_timings(
            StepTiming(s["step"], audio_s, s["seconds"])
            for s in report.get("steps", [])
            if s["ran"] and s["seconds"] > 0
        )

    def _counts(self) -> dict[str, int]:
        counts = {state.value: 0 for state in ItemState}
        for item in self._store.items():
            counts[item.state.value] += 1
        return counts

    def describe_item(self, item_id: str) -> dict[str, Any]:
        items = self._store.items()
        item = next((i for i in items if i.id == item_id), None)
        if item is None:
            raise KeyError(item_id)
        return self._item_json(item, self._etas(items))

    def describe_items(self, ids: Sequence[str]) -> list[dict[str, Any]]:
        """The listed items as `GET /api/queue` shows them. A deleted item is left out."""
        items = self._store.items()
        eta = self._etas(items)
        wanted = set(ids)
        return [self._item_json(i, eta) for i in items if i.id in wanted]

    def _etas(self, items: Sequence[QueueItem]) -> dict[str, float | None]:
        with self._lock:
            live = self._live
        return etas(items, live, step_rates(self._store.recent_timings()))

    def _item_json(self, item: QueueItem, eta: Mapping[str, float | None]) -> dict[str, Any]:
        with self._lock:
            live = self._live if item.id == self._current else None
        waiting = item.state in (ItemState.RUNNING, ItemState.QUEUED)
        return {
            "id": item.id,
            "video_path": item.video_path,
            "project_id": item.project_id,
            "target_lang": item.target_lang,
            "source_lang": item.source_lang,
            "options": asdict(item.options),
            "state": item.state.value,
            "position": item.position,
            "step": live.step.value if live and live.step else None,
            "progress": 1.0 if item.state is ItemState.DONE else (live.overall if live else 0.0),
            "eta_s": eta.get(item.id) if waiting else None,
            "attempts": item.attempts,
            "last_error": item.last_error,
            "last_error_notices": to_json(item.last_error_notices),
            "created_at_ms": item.created_at_ms,
            "started_at_ms": item.started_at_ms,
            "finished_at_ms": item.finished_at_ms,
            "audio_s": item.audio_s,
            "job_id": live.job_id if live else None,
        }

    def describe(self) -> dict[str, Any]:
        items = self._store.items()
        eta = self._etas(items)
        known = [v for v in eta.values() if v is not None]
        return {
            **self.describe_queue(),
            "countdown": self._power.active,
            "running": self._current,
            "eta_s": max(known) if known else None,
            "counts": self._counts(),
            "items": [self._item_json(i, eta) for i in items],
        }

    def describe_queue(self) -> dict[str, Any]:
        return {
            "paused": self._store.paused,
            "settings": _settings_json(self._store.settings()),
        }

    def add(self, entries: Sequence[tuple[Path, JobOptions]]) -> Added:
        """Queue each media file with its options. A path that is not a file with a media extension,
        or is already queued for that language, is skipped with the reason. A file that is not
        really a video is queued, and fails alone when it runs. The length of each video is
        probed for the ETA until `PROBE_BUDGET_S` is used up. The rest are probed in the
        background, so a big folder does not hold the request."""
        added: list[QueueItem] = []
        skipped: list[tuple[str, str, tuple[Notice, ...]]] = []
        late: list[tuple[str, Path]] = []
        deadline = time.monotonic() + PROBE_BUDGET_S
        for path, options in entries:
            if not path.is_absolute() or not path.is_file():
                skipped.append((str(path), *_said(BATCH_NOT_A_FILE())))
                continue
            if not is_media(path):
                skipped.append((str(path), *_said(BATCH_NOT_MEDIA())))
                continue
            info, _ = self._projects.create(path)
            probe_now = time.monotonic() < deadline
            try:
                item = self._store.add(
                    str(path.absolute()),
                    info.id,
                    options,
                    self._probe(path) if probe_now else None,
                    _now_ms(),
                )
            except QueueError as exc:
                skipped.append((str(path), str(exc), notices_of(exc)))
                continue
            added.append(item)
            if not probe_now:
                late.append((item.id, path))
            self._emit_item(item.id)
        if late:
            threading.Thread(
                target=self._probe_late, args=(late,), name="vst-probe", daemon=True
            ).start()
        if added:
            self._work_arrived()
        return Added(added, skipped)

    def _probe_late(self, pending: Sequence[tuple[str, Path]]) -> None:
        for item_id, path in pending:
            if self._halt.is_set():
                return
            try:
                audio_s = self._probe(path)
                if audio_s is not None:
                    self._store.set_audio_s(item_id, audio_s)
                    self._emit_item(item_id)
            except Exception:
                log.exception("could not probe %s", path)

    def has(self, item_id: str) -> bool:
        return self._store.get(item_id) is not None

    def _known(self, item_id: str) -> QueueItem:
        item = self._store.get(item_id)
        if item is None:
            raise KeyError(item_id)
        return item

    def reorder(self, ids: Sequence[str]) -> None:
        self._store.reorder(ids)
        self._emit("order", {"ids": [i.id for i in self._store.items()]})

    def set_paused(self, paused: bool, interrupt: bool = False) -> None:
        """Pause or resume the queue. Pausing lets the running item finish, or with `interrupt`
        stops it and queues it again at its place."""
        with self._lock:
            self._store.set_paused(paused)
            if paused and interrupt and self._current is not None:
                self._stop_current(self._current, Stop.REQUEUE)
        self._emit("queue", self.describe_queue())
        if not paused:
            self._power.cancel()
        self._wake.set()

    def set_settings(self, settings: QueueSettings) -> None:
        """Any change withdraws the consent a pending countdown was started under, so it is
        cancelled, and the user opts in again for the new setting."""
        self._store.set_settings(settings)
        self._power.cancel()
        self._emit("queue", self.describe_queue())

    def cancel_power(self) -> bool:
        return self._power.cancel()

    def _change(
        self, item_id: str, frm: Sequence[ItemState], to: ItemState, refused: Template
    ) -> None:
        with self._lock:
            item = self._known(item_id)
            if not self._store.move(item_id, frm, to, _now_ms()):
                raise noticed(QueueError, refused(state=item.state.value))
        self._emit_item(item_id)
        if to is ItemState.QUEUED:
            self._work_arrived()
        else:
            self._wake.set()

    def pause_item(self, item_id: str) -> None:
        with self._lock:
            if self._known(item_id).state is ItemState.RUNNING:
                self._stop_current(item_id, Stop.PAUSE)
                return
        self._change(item_id, [ItemState.QUEUED], ItemState.PAUSED, BATCH_CANNOT_PAUSE)

    def resume_item(self, item_id: str) -> None:
        self._change(item_id, [ItemState.PAUSED], ItemState.QUEUED, BATCH_CANNOT_RESUME)

    def cancel_item(self, item_id: str) -> None:
        with self._lock:
            if self._known(item_id).state is ItemState.RUNNING:
                self._stop_current(item_id, Stop.CANCEL)
                return
        self._change(
            item_id, [ItemState.QUEUED, ItemState.PAUSED], ItemState.CANCELLED, BATCH_CANNOT_CANCEL
        )

    def retry_item(self, item_id: str) -> None:
        with self._lock:
            item = self._known(item_id)
            if item.state not in (ItemState.FAILED, ItemState.CANCELLED):
                raise noticed(QueueError, BATCH_CANNOT_RETRY(state=item.state.value))
            self._store.to_end(item_id)
        self._emit_item(item_id)
        self._work_arrived()

    def remove(self, ids: Sequence[str]) -> list[str]:
        """Delete finished items. A queued, paused or running item is left alone."""
        gone = self._store.remove(ids)
        if gone:
            self._emit("removed", {"ids": gone})
        return gone

    def remove_finished(self) -> list[str]:
        return self.remove([i.id for i in self._store.items() if i.state.finished])
