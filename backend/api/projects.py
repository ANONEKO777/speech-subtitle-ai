from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Annotated, Any

from fastapi import APIRouter, HTTPException, Query, Request, Response
from pydantic import BaseModel, ConfigDict, Field

from backend.core import cue_failures
from backend.core.cue_edits import CueProblem
from backend.core.jobs import JobBook
from backend.core.languages import UnknownLanguage
from backend.core.languages import get as get_language
from backend.core.media import accepted_extensions, is_media
from backend.core.model import Cue, Step, StepState
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


def _steps_json(steps: Mapping[Step, StepState]) -> dict[str, Any]:
    return {
        step.value: {
            "status": state.status.value,
            "updated_at_ms": state.updated_at_ms,
            "error": state.error,
            "degraded": state.degraded,
        }
        for step, state in steps.items()
    }


def _failed_cues_json(info: ProjectInfo) -> dict[str, Any]:
    """The cues each language's translation could not do, for the languages that have any:
    `failed` ids, and `english` for the ones that show their English."""
    found = {
        code: cue_failures.read(info.folder, get_language(code))
        for code in info.project.languages()
    }
    return {
        code: {"failed": list(f.failed), "english": list(f.english)}
        for code, f in found.items()
        if f
    }


def project_json(info: ProjectInfo, jobs: JobBook) -> dict[str, Any]:
    """`steps` is every step as it stands for `active_lang`, the language last worked on.
    `languages` has the translate, export and summarize steps of every language the project
    has been given, and `failed_cues` the cues of a translation that has none."""
    active = jobs.active(info.id)
    return {
        "id": info.id,
        "video_path": info.project.video_path,
        "folder": str(info.folder),
        "active_lang": info.project.active_lang,
        "source_lang": info.project.source_lang,
        "steps": _steps_json(info.project.steps),
        "languages": {
            lang: _steps_json(states) for lang, states in info.project.languages().items()
        },
        "files": {name: str(path) for name, path in info.files.items()},
        "active_job": active.id if active else None,
        "failed_cues": _failed_cues_json(info),
    }


def _known(store: ProjectStore, pid: str) -> ProjectInfo:
    try:
        return store.info(pid)
    except UnknownProject as exc:
        raise HTTPException(404, f"unknown project {pid!r}") from exc


def _bad_cues(message: str, problems: Sequence[CueProblem]) -> HTTPException:
    """422 whose detail names each cue at fault, so the editor can show the error on it."""
    found = [{"id": p.id, "code": p.code, "message": p.message, "other": p.other} for p in problems]
    return HTTPException(422, {"message": message, "problems": found})


@router.post("")
def create_project(body: NewProject, request: Request, response: Response) -> dict[str, Any]:
    video = Path(body.video_path)
    if not video.is_absolute() or not video.is_file():
        raise HTTPException(
            422, f"video_path must be the absolute path of an existing file: {video}"
        )
    if not is_media(video):
        raise HTTPException(
            422,
            f"not a media file extension: {video.suffix or video.name}; "
            f"accepted: {accepted_extensions()}",
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
    target_lang: Annotated[str | None, Query()] = None,
) -> Response:
    """`lang` picks the texts to show and `target_lang` the translation they come from, by
    default the language the project was last worked on."""
    store = store_of(request)
    _known(store, pid)
    try:
        text = store.subtitles(pid, lang, format, target_lang)
    except NotReady as exc:
        raise HTTPException(409, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    return Response(text.encode("utf-8"), media_type=f"{MEDIA_TYPES[format]}; charset=utf-8")


@router.put("/{pid}/subtitles")
def put_subtitles(
    pid: str,
    body: CuesBody,
    request: Request,
    target_lang: Annotated[str | None, Query()] = None,
) -> dict[str, Any]:
    store, jobs = store_of(request), jobs_of(request)
    _known(store, pid)
    cues: list[Cue] = []
    problems: list[CueProblem] = []
    for c in body.cues:
        try:
            cues.append(Cue(c.id, c.start_ms, c.end_ms, c.en, c.zh))
        except ValueError as exc:
            code = "end_before_start" if c.end_ms < c.start_ms else "bad_text"
            problems.append(CueProblem(c.id, code, str(exc)))
    if problems:
        raise _bad_cues("some cues are not valid", problems)
    with jobs.exclusive(pid) as busy:
        if busy:
            raise HTTPException(409, f"job {busy} is using this project")
        try:
            store.save_cues(pid, cues, target_lang)
        except NotReady as exc:
            raise HTTPException(409, str(exc)) from exc
        except BadCues as exc:
            raise _bad_cues(str(exc), exc.problems) from exc
        except UnknownLanguage as exc:
            raise HTTPException(422, str(exc)) from exc
    return project_json(store.info(pid), jobs)


@router.get("/{pid}/edits")
def get_edits(
    pid: str, request: Request, target_lang: Annotated[str | None, Query()] = None
) -> dict[str, Any]:
    """The ids of the cues a person corrected. A rerun of translate keeps them."""
    store = store_of(request)
    _known(store, pid)
    try:
        return {"ids": store.edited_ids(pid, target_lang)}
    except UnknownLanguage as exc:
        raise HTTPException(422, str(exc)) from exc


@router.get("/{pid}/summary")
def get_summary(
    pid: str, request: Request, lang: Annotated[Lang | None, Query()] = None
) -> Response:
    """`lang` is a language code or `en`. The default is the language last worked on."""
    store = store_of(request)
    _known(store, pid)
    try:
        content = store.summary(pid, lang)
    except NotReady as exc:
        raise HTTPException(409, str(exc)) from exc
    except UnknownLanguage as exc:
        raise HTTPException(422, str(exc)) from exc
    return Response(content, media_type="text/markdown; charset=utf-8")
