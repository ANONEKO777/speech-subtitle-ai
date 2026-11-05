from __future__ import annotations

from pathlib import Path
from typing import Annotated, Any

from fastapi import APIRouter, HTTPException, Query, Request, Response
from pydantic import BaseModel, ConfigDict, Field

from backend.core.jobs import JobBook
from backend.core.model import Cue
from backend.core.projects import (
    MEDIA_TYPES,
    BadCues,
    NotReady,
    ProjectInfo,
    ProjectStore,
    SubFormat,
    UnknownProject,
)
from backend.core.subtitle_io import RenderLang
from backend.core.summarize import Lang

router = APIRouter(prefix="/api/projects", tags=["projects"])


class NewProject(BaseModel):
    model_config = ConfigDict(extra="forbid")
    video_path: str = Field(min_length=1)


class CueBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: int = Field(ge=0)
    start_ms: int = Field(ge=0)
    end_ms: int = Field(ge=0)
    en: str
    zh: str


class CuesBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    cues: list[CueBody]


def store_of(request: Request) -> ProjectStore:
    return request.app.state.projects


def jobs_of(request: Request) -> JobBook:
    return request.app.state.jobs


def project_json(info: ProjectInfo, jobs: JobBook) -> dict[str, Any]:
    active = jobs.active(info.id)
    return {
        "id": info.id,
        "video_path": info.project.video_path,
        "folder": str(info.folder),
        "steps": {
            step.value: {
                "status": state.status.value,
                "updated_at_ms": state.updated_at_ms,
                "error": state.error,
            }
            for step, state in info.project.steps.items()
        },
        "files": {name: str(path) for name, path in info.files.items()},
        "active_job": active.id if active else None,
    }


def _known(store: ProjectStore, pid: str) -> ProjectInfo:
    try:
        return store.info(pid)
    except UnknownProject as exc:
        raise HTTPException(404, f"unknown project {pid!r}") from exc


@router.post("")
def create_project(body: NewProject, request: Request, response: Response) -> dict[str, Any]:
    video = Path(body.video_path)
    if not video.is_absolute() or not video.is_file():
        raise HTTPException(
            422, f"video_path must be the absolute path of an existing file: {video}"
        )
    info, created = store_of(request).create(video)
    response.status_code = 201 if created else 200
    return project_json(info, jobs_of(request))


@router.get("/{pid}")
def get_project(pid: str, request: Request) -> dict[str, Any]:
    return project_json(_known(store_of(request), pid), jobs_of(request))


@router.get("/{pid}/subtitles")
def get_subtitles(
    pid: str,
    request: Request,
    lang: Annotated[RenderLang, Query()] = "bilingual",
    format: Annotated[SubFormat, Query()] = "srt",
) -> Response:
    store = store_of(request)
    _known(store, pid)
    try:
        text = store.subtitles(pid, lang, format)
    except NotReady as exc:
        raise HTTPException(409, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    return Response(text.encode("utf-8"), media_type=f"{MEDIA_TYPES[format]}; charset=utf-8")


@router.put("/{pid}/subtitles")
def put_subtitles(pid: str, body: CuesBody, request: Request) -> dict[str, Any]:
    store, jobs = store_of(request), jobs_of(request)
    _known(store, pid)
    try:
        cues = [Cue(c.id, c.start_ms, c.end_ms, c.en, c.zh) for c in body.cues]
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    with jobs.exclusive(pid) as busy:
        if busy:
            raise HTTPException(409, f"job {busy} is using this project")
        try:
            store.save_cues(pid, cues)
        except NotReady as exc:
            raise HTTPException(409, str(exc)) from exc
        except BadCues as exc:
            raise HTTPException(422, str(exc)) from exc
    return project_json(store.info(pid), jobs)


@router.get("/{pid}/summary")
def get_summary(pid: str, request: Request, lang: Annotated[Lang, Query()] = "zh-TW") -> Response:
    store = store_of(request)
    _known(store, pid)
    try:
        content = store.summary(pid, lang)
    except NotReady as exc:
        raise HTTPException(409, str(exc)) from exc
    return Response(content, media_type="text/markdown; charset=utf-8")
