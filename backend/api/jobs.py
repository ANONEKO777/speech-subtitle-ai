from __future__ import annotations

import json
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Annotated, Any

from fastapi import APIRouter, Header, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict, Field

from backend.api.projects import jobs_of, store_of
from backend.core.jobs import Job, JobEvent, JobOptions, OptionsError, ProjectBusy, Resolver
from backend.core.projects import UnknownProject
from backend.core.translate import BATCH_SIZE, GlossaryEntry
from backend.manager.profiles import QWEN3_8B

router = APIRouter(prefix="/api", tags=["jobs"])


class GlossaryBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    term: str = Field(min_length=1)
    zh: str = ""


class JobBody(BaseModel):
    """What a client may choose. The pipeline's steps always all run, and the ones whose inputs
    did not change are skipped, so there is no list of steps to pick."""

    model_config = ConfigDict(extra="forbid")
    engine: str = "whispercpp"
    llm: str = QWEN3_8B
    llm_model: str | None = None
    cpu: bool = False
    glossary: list[GlossaryBody] = []
    summary_en: bool = False
    batch_size: int = Field(default=BATCH_SIZE, ge=1, le=4 * BATCH_SIZE)

    def options(self) -> JobOptions:
        return JobOptions(
            self.engine,
            self.llm,
            self.llm_model,
            self.cpu,
            tuple(GlossaryEntry(g.term.strip(), g.zh.strip()) for g in self.glossary),
            self.summary_en,
            self.batch_size,
        )


def resolver_of(request: Request) -> Resolver:
    return request.app.state.resolver


def _job(request: Request, job_id: str) -> Job:
    job = jobs_of(request).get(job_id)
    if job is None:
        raise HTTPException(404, f"unknown job {job_id!r}")
    return job


@router.post("/projects/{pid}/jobs", status_code=202)
def create_job(pid: str, body: JobBody, request: Request) -> dict[str, Any]:
    store, jobs = store_of(request), jobs_of(request)
    try:
        info = store.info(pid)
    except UnknownProject as exc:
        raise HTTPException(404, f"unknown project {pid!r}") from exc
    video = Path(info.project.video_path)
    if not video.is_file():
        raise HTTPException(422, f"the video is gone: {video}")
    busy = jobs.active(pid)
    if busy is not None:
        raise HTTPException(409, f"job {busy.id} is already running on this project")
    try:
        settings, ports = resolver_of(request)(body.options(), info.folder)
    except OptionsError as exc:
        raise HTTPException(422, str(exc)) from exc
    try:
        job = jobs.submit(pid, video, info.folder, settings, ports)
    except ProjectBusy as exc:
        raise HTTPException(409, str(exc)) from exc
    return job.describe()


@router.get("/jobs/{job_id}")
def get_job(job_id: str, request: Request) -> dict[str, Any]:
    return _job(request, job_id).describe()


@router.post("/jobs/{job_id}/cancel")
def cancel_job(job_id: str, request: Request) -> dict[str, Any]:
    job = _job(request, job_id)
    job.request_cancel()
    return job.describe()


def _frame(event: JobEvent) -> str:
    data = json.dumps({"seq": event.seq, **event.data}, ensure_ascii=False)
    return f"id: {event.seq}\nevent: {event.kind.value}\ndata: {data}\n\n"


@router.get("/jobs/{job_id}/events")
async def job_events(
    job_id: str,
    request: Request,
    last_event_id: Annotated[int | None, Header()] = None,
) -> StreamingResponse:
    """Server-sent events: `status`, then `progress` events, then one of `done`, `failed` or
    `cancelled`, after which the stream ends. A client that reconnects with `Last-Event-ID`
    gets the events after that one."""
    job = _job(request, job_id)

    async def frames() -> AsyncIterator[str]:
        async for event in job.log.follow(-1 if last_event_id is None else last_event_id):
            yield ": keepalive\n\n" if event is None else _frame(event)

    return StreamingResponse(
        frames(),
        media_type="text/event-stream",
        headers={"cache-control": "no-store", "x-accel-buffering": "no"},
    )
