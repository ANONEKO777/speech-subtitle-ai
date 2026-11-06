"""Background runs of the pipeline, and the events a client follows them by.

`JobBook` owns every job. Jobs run one at a time on one worker thread, because there is one GPU,
and a project has at most one job that is not finished. A job's story is its `EventLog`, an
append-only list that late subscribers replay from the start. Nothing here knows about HTTP.
"""

from __future__ import annotations

import asyncio
import logging
import threading
import time
import uuid
from collections.abc import AsyncIterator, Callable, Generator, Mapping
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from backend.core.languages import DEFAULT_CODE
from backend.core.model import Step
from backend.core.pipeline import (
    Cancelled,
    PipelineError,
    Ports,
    Progress,
    RunReport,
    Settings,
    run,
)
from backend.core.translate import GlossaryEntry

log = logging.getLogger(__name__)

KEEPALIVE_S = 15.0
"""Overall share of each step, from the step times of a 38-minute talk (translation dominates)."""
STEP_WEIGHTS: Mapping[Step, float] = {
    Step.AUDIO: 0.01,
    Step.VAD: 0.03,
    Step.ASR: 0.12,
    Step.SEGMENT: 0.01,
    Step.TRANSLATE: 0.74,
    Step.EXPORT: 0.01,
    Step.SUMMARIZE: 0.08,
}
BEFORE: Mapping[Step, float] = {
    step: sum(w for s, w in STEP_WEIGHTS.items() if list(Step).index(s) < index)
    for index, step in enumerate(Step)
}


class JobStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"
    CANCELLED = "cancelled"

    @property
    def finished(self) -> bool:
        return self in (JobStatus.DONE, JobStatus.FAILED, JobStatus.CANCELLED)


class EventKind(StrEnum):
    STATUS = "status"
    PROGRESS = "progress"
    DONE = "done"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass(frozen=True, slots=True)
class JobEvent:
    seq: int
    kind: str
    data: Mapping[str, object]
    last: bool = False


class EventLog:
    """Events in order. `append` is called from the worker thread, `follow` from the event loop."""

    def __init__(self) -> None:
        self._events: list[JobEvent] = []
        self._lock = threading.Lock()
        self._waiters: list[tuple[asyncio.AbstractEventLoop, asyncio.Event]] = []

    def append(self, kind: StrEnum, data: Mapping[str, object], *, last: bool = False) -> None:
        """`last` ends the stream of every follower after this event."""
        with self._lock:
            self._events.append(JobEvent(len(self._events), kind, data, last))
            waiters = list(self._waiters)
        for loop, wake in waiters:
            loop.call_soon_threadsafe(wake.set)

    def snapshot(self) -> list[JobEvent]:
        with self._lock:
            return list(self._events)

    async def follow(self, after: int = -1) -> AsyncIterator[JobEvent | None]:
        """Every event with `seq > after`, then new ones, ending after the last event.
        Yields None every `KEEPALIVE_S` seconds of silence."""
        wake = asyncio.Event()
        entry = (asyncio.get_running_loop(), wake)
        with self._lock:
            self._waiters.append(entry)
        try:
            while True:
                wake.clear()
                with self._lock:
                    pending = self._events[after + 1 :]
                for event in pending:
                    yield event
                    after = event.seq
                    if event.last:
                        return
                if pending:
                    continue
                try:
                    await asyncio.wait_for(wake.wait(), KEEPALIVE_S)
                except TimeoutError:
                    yield None
        finally:
            with self._lock:
                self._waiters.remove(entry)


@dataclass(frozen=True, slots=True)
class JobOptions:
    """What a client may choose. Paths to programs are not here, so a request cannot run one."""

    engine: str
    llm: str
    llm_model: str | None
    cpu: bool
    glossary: tuple[GlossaryEntry, ...]
    summary_en: bool
    batch_size: int
    target_lang: str = DEFAULT_CODE


class OptionsError(ValueError):
    """The options name a model, engine or file that cannot be used."""


class ProjectBusy(Exception):
    """The project already has a job that is not finished."""

    def __init__(self, job_id: str) -> None:
        super().__init__(f"the project already has an unfinished job {job_id}")
        self.job_id = job_id


Resolver = Callable[[JobOptions, Path], tuple[Settings, Ports]]


def _now_ms() -> int:
    return time.time_ns() // 1_000_000


def _report_json(report: RunReport) -> dict[str, object]:
    return {
        "total_s": round(report.total_s, 3),
        "edits_kept": report.edits_kept,
        "edits_unmatched": report.edits_unmatched,
        "summary_degraded": report.summary_degraded,
        "steps": [
            {"step": r.step.value, "ran": r.ran, "seconds": round(r.seconds, 3)}
            for r in report.steps
        ],
    }


class Job:
    def __init__(self, project_id: str) -> None:
        self.id = uuid.uuid4().hex
        self.project_id = project_id
        self.created_at_ms = _now_ms()
        self.log = EventLog()
        self.cancel = threading.Event()
        self.done = threading.Event()
        self.outcome: Mapping[str, object] = {}
        self._status = JobStatus.QUEUED
        self._step: Step | None = None
        self._overall = 0.0
        self._error: str | None = None
        self._lock = threading.Lock()
        self.log.append(EventKind.STATUS, {"status": JobStatus.QUEUED.value})

    @property
    def status(self) -> JobStatus:
        with self._lock:
            return self._status

    def describe(self) -> dict[str, object]:
        with self._lock:
            return {
                "id": self.id,
                "project_id": self.project_id,
                "status": self._status.value,
                "cancel_requested": self.cancel.is_set(),
                "step": self._step.value if self._step else None,
                "overall": self._overall,
                "error": self._error,
                "created_at_ms": self.created_at_ms,
            }

    def start(self) -> bool:
        """Move from queued to running. False when the job was cancelled while it waited."""
        with self._lock:
            if self._status is not JobStatus.QUEUED:
                return False
            self._status = JobStatus.RUNNING
            self.log.append(EventKind.STATUS, {"status": JobStatus.RUNNING.value})
            return True

    def on_progress(self, progress: Progress) -> None:
        """Overall progress never goes back, even where a step restarts its own counter."""
        with self._lock:
            if self._status is not JobStatus.RUNNING:
                return
            share = BEFORE[progress.step] + STEP_WEIGHTS[progress.step] * progress.fraction
            self._overall = max(self._overall, round(share, 4))
            self._step = progress.step
            self.log.append(
                EventKind.PROGRESS,
                {
                    "step": progress.step.value,
                    "fraction": progress.fraction,
                    "overall": self._overall,
                    "message": progress.message,
                },
            )

    def request_cancel(self) -> None:
        """Ask the run to stop. A job that has not started finishes at once, a running one when
        its current step notices, which is after its child processes are stopped."""
        with self._lock:
            if self._status.finished:
                return
            self.cancel.set()
            if self._status is JobStatus.QUEUED:
                self._finish(JobStatus.CANCELLED, EventKind.CANCELLED, {})

    def finish(self, status: JobStatus, kind: EventKind, data: Mapping[str, object]) -> None:
        with self._lock:
            if not self._status.finished:
                self._finish(status, kind, data)

    def _finish(self, status: JobStatus, kind: EventKind, data: Mapping[str, object]) -> None:
        self._status = status
        if status is JobStatus.FAILED:
            self._error = str(data.get("error"))
        if status is JobStatus.DONE:
            self._overall = 1.0
        self.outcome = data
        self.log.append(kind, {**data, "overall": self._overall}, last=True)
        self.done.set()


class JobBook:
    def __init__(self) -> None:
        self._jobs: dict[str, Job] = {}
        self._lock = threading.Lock()
        self._pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="vst-job")
        self._submit_listeners: list[Callable[[], None]] = []

    def on_submit(self, listener: Callable[[], None]) -> None:
        """Call `listener` after each job is registered, by any caller. It runs outside the book
        lock."""
        self._submit_listeners.append(listener)

    def busy(self) -> bool:
        """Whether any job, of any project, has not finished."""
        with self._lock:
            return any(not job.status.finished for job in self._jobs.values())

    def get(self, job_id: str) -> Job | None:
        with self._lock:
            return self._jobs.get(job_id)

    def active(self, project_id: str) -> Job | None:
        with self._lock:
            return self._active(project_id)

    def _active(self, project_id: str) -> Job | None:
        return next(
            (
                job
                for job in self._jobs.values()
                if job.project_id == project_id and not job.status.finished
            ),
            None,
        )

    @contextmanager
    def exclusive(self, project_id: str) -> Generator[str | None]:
        """Hold off new jobs for the project while the caller works on its files. Yields the id
        of the unfinished job that already uses it, or None."""
        with self._lock:
            busy = self._active(project_id)
            yield busy.id if busy else None

    def submit(
        self, project_id: str, video: Path, folder: Path, settings: Settings, ports: Ports
    ) -> Job:
        with self._lock:
            busy = self._active(project_id)
            if busy is not None:
                raise ProjectBusy(busy.id)
            job = Job(project_id)
            self._jobs[job.id] = job
        self._pool.submit(_work, job, video, folder, settings, ports)
        for listener in self._submit_listeners:
            listener()
        return job

    def shutdown(self) -> None:
        """Cancel everything and wait for the running job to stop its child processes."""
        with self._lock:
            jobs = list(self._jobs.values())
        for job in jobs:
            job.request_cancel()
        self._pool.shutdown(wait=True, cancel_futures=True)
        for job in jobs:
            job.finish(JobStatus.CANCELLED, EventKind.CANCELLED, {})


def _work(job: Job, video: Path, folder: Path, settings: Settings, ports: Ports) -> None:
    if not job.start():
        return
    try:
        report = run(video, folder, settings, ports, progress=job.on_progress, cancel=job.cancel)
    except Cancelled:
        job.finish(JobStatus.CANCELLED, EventKind.CANCELLED, {})
    except PipelineError as exc:
        job.finish(JobStatus.FAILED, EventKind.FAILED, {"error": str(exc), "step": exc.step.value})
    except Exception as exc:
        log.exception("job %s crashed", job.id)
        job.finish(JobStatus.FAILED, EventKind.FAILED, {"error": f"{type(exc).__name__}: {exc}"})
    else:
        job.finish(JobStatus.DONE, EventKind.DONE, {"report": _report_json(report)})
