"""What a player offers around the cues: the library of finished projects, where each one was left
off, thumbnails, stills, and the export of a video with the subtitle burned in."""

from __future__ import annotations

import base64
import time
from pathlib import Path
from typing import Any, Literal

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel, ConfigDict, Field

from backend.api.projects import store_of
from backend.core import render
from backend.core.audio import AudioError, probe_duration_s
from backend.core.languages import UnknownLanguage, get
from backend.core.playback import MAX_OFFSET_MS, Playback, with_changes
from backend.core.projects import NotReady, ProjectStore, UnknownProject
from backend.core.render import BurnBook, BurnBusy, SubtitleLook

router = APIRouter(prefix="/api", tags=["player"])
THUMB = "thumb.jpg"
PICKED_FOLDERS = "output-folders.txt"


class PlaybackBody(BaseModel):
    """Only the fields sent change."""

    model_config = ConfigDict(extra="forbid")
    position_s: float | None = Field(default=None, ge=0, le=1e7)
    duration_s: float | None = Field(default=None, ge=0, le=1e7)
    offset_ms: int | None = Field(default=None, ge=-MAX_OFFSET_MS, le=MAX_OFFSET_MS)
    opened: bool = False


class Look(BaseModel):
    model_config = ConfigDict(extra="forbid")
    mode: Literal["en", "zh", "both"] = "both"
    zh_first: bool = True
    size_ratio: float = Field(default=0.045, ge=0.01, le=0.2)
    color: str = Field(default="#ffffff", pattern=r"^#[0-9a-fA-F]{6}$")

    def look(self) -> SubtitleLook:
        return SubtitleLook(self.mode, self.zh_first, self.size_ratio, self.color)


class StillBody(Look):
    time_s: float = Field(ge=0, le=1e7)
    lang: str | None = None
    burn: bool = False
    dir: str | None = None


class BurnBody(Look):
    lang: str | None = None
    start_s: float = Field(default=0, ge=0, le=1e7)
    duration_s: float | None = Field(default=None, gt=0, le=1e7)
    dir: str | None = None


def _burns(request: Request) -> BurnBook:
    return request.app.state.burns


def _known(request: Request, pid: str) -> tuple[ProjectStore, Path]:
    store = store_of(request)
    try:
        return store, Path(store.info(pid).project.video_path)
    except UnknownProject as exc:
        raise HTTPException(404, f"unknown project {pid!r}") from exc


def _playback_json(state: Playback) -> dict[str, Any]:
    return {
        "position_s": state.position_s,
        "duration_s": state.duration_s,
        "offset_ms": state.offset_ms,
        "opened_at_ms": state.opened_at_ms,
    }


def picked_folders(user_data: Path) -> list[Path]:
    """The folders the person chose in the native dialog, which only the desktop shell writes."""
    try:
        lines = (user_data / PICKED_FOLDERS).read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    return [Path(line) for line in lines if line.strip()]


def _inside(path: Path, root: Path) -> bool:
    return path == root or root in path.parents


def _out_dir(request: Request, given: str | None, leaf: str) -> Path:
    """The folder the person chose in the native dialog, else a folder under the app data, made
    when missing. A request cannot name any other folder."""
    user_data: Path = request.app.state.user_data
    if not given:
        folder = user_data / leaf
        try:
            folder.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            raise HTTPException(422, f"cannot use the folder {folder}: {exc}") from exc
        return folder
    folder = Path(given)
    if not folder.is_absolute():
        raise HTTPException(422, f"dir must be an absolute path: {given}")
    try:
        real = folder.resolve(strict=True)
        allowed = [
            (user_data / "screenshots").resolve(),
            (user_data / "exports").resolve(),
            *(p.resolve() for p in picked_folders(user_data)),
        ]
    except OSError as exc:
        raise HTTPException(422, f"cannot use the folder {folder}: {exc}") from exc
    if not real.is_dir() or not any(_inside(real, root) for root in allowed):
        raise HTTPException(422, f"{folder} is not a folder picked in the app; pick it again")
    return real


def _free(folder: Path, stem: str, suffix: str) -> Path:
    path = folder / f"{stem}{suffix}"
    n = 2
    while path.exists():
        path = folder / f"{stem}-{n}{suffix}"
        n += 1
    return path


def _video(path: Path) -> Path:
    if not path.is_file():
        raise HTTPException(409, f"the video is not at {path} any more")
    return path


def _cues(store: ProjectStore, pid: str, lang: str | None) -> tuple[str, list[Any]]:
    try:
        code = get(lang or store.active_lang(pid)).code
        return code, store.cues(pid, code)
    except (NotReady, UnknownLanguage) as exc:
        raise HTTPException(409, str(exc)) from exc


@router.get("/projects")
def list_projects(request: Request) -> dict[str, Any]:
    """Every project with a finished translation, most recently opened first."""
    store = store_of(request)
    items: list[dict[str, Any]] = []
    for pid in store.ids():
        try:
            langs = store.translated_langs(pid)
            if not langs:
                continue
            state = store.playback(pid)
            video = Path(store.info(pid).project.video_path)
            items.append(
                {
                    "id": pid,
                    "video_path": str(video),
                    "title": video.stem,
                    "exists": video.is_file(),
                    "langs": langs,
                    "duration_s": store.length_s(pid),
                    "position_s": state.position_s,
                    "opened_at_ms": state.opened_at_ms,
                }
            )
        except (UnknownProject, OSError):
            continue
    items.sort(key=lambda i: (-i["opened_at_ms"], i["title"]))
    return {"projects": items}


@router.get("/projects/{pid}/playback")
def get_playback(pid: str, request: Request) -> dict[str, Any]:
    store, _ = _known(request, pid)
    return _playback_json(store.playback(pid))


@router.put("/projects/{pid}/playback")
def put_playback(pid: str, body: PlaybackBody, request: Request) -> dict[str, Any]:
    store, _ = _known(request, pid)
    changes: dict[str, float | int] = {
        k: v for k, v in body.model_dump(exclude={"opened"}).items() if v is not None
    }
    if body.opened:
        changes["opened_at_ms"] = time.time_ns() // 1_000_000
    state = with_changes(store.playback(pid), **changes)
    store.save_playback(pid, state)
    return _playback_json(state)


@router.get("/projects/{pid}/media")
def get_media(pid: str, request: Request) -> dict[str, Any]:
    """What the player needs to know about the picture: `frame_rate`, null when unknown."""
    _, video = _known(request, pid)
    return {"frame_rate": render.frame_rate(_video(video))}


@router.get("/projects/{pid}/thumbnail")
def get_thumbnail(pid: str, request: Request) -> Response:
    store, video = _known(request, pid)
    cached = store.folder(pid) / THUMB
    if not cached.is_file():
        at = min(max(store.length_s(pid) * 0.1, 1.0), 60.0)
        try:
            render.thumbnail(_video(video), at, cached)
        except AudioError as exc:
            raise HTTPException(500, str(exc)) from exc
    return Response(
        cached.read_bytes(), media_type="image/jpeg", headers={"cache-control": "max-age=86400"}
    )


@router.post("/projects/{pid}/screenshot")
def take_still(pid: str, body: StillBody, request: Request) -> dict[str, Any]:
    """Save the frame at `time_s` as a PNG, with the subtitle burned in when `burn` is set, and
    return it too so the app can put it on the clipboard."""
    store, video = _known(request, pid)
    burn = None
    if body.burn:
        code, cues = _cues(store, pid, body.lang)
        burn = (cues, get(code).wrap, body.look(), store.playback(pid).offset_ms)
    folder = _out_dir(request, body.dir, "screenshots")
    t = body.time_s
    stamp = f"{int(t // 3600):02d}-{int(t // 60 % 60):02d}-{t % 60:06.3f}"
    out = _free(folder, f"{video.stem}_{stamp}{'_sub' if burn else ''}", ".png")
    try:
        render.still(_video(video), t, out, burn=burn)
    except AudioError as exc:
        raise HTTPException(500, str(exc)) from exc
    return {"path": str(out), "png_base64": base64.b64encode(out.read_bytes()).decode("ascii")}


def _burn_json(job: render.BurnJob) -> dict[str, Any]:
    return {
        "id": job.id,
        "state": job.state,
        "percent": round(job.percent, 1),
        "output": str(job.output),
        "error": job.error,
    }


@router.post("/projects/{pid}/burn", status_code=202)
def start_burn(pid: str, body: BurnBody, request: Request) -> dict[str, Any]:
    store, video = _known(request, pid)
    code, cues = _cues(store, pid, body.lang)
    source = _video(video)
    total = probe_duration_s(source) or store.length_s(pid)
    duration = body.duration_s or (total - body.start_s)
    if duration <= 0 or (total and body.start_s >= total):
        raise HTTPException(422, "start_s is past the end of the video")
    folder = _out_dir(request, body.dir, "exports")
    clip = f".{int(body.start_s)}s-{int(duration)}s" if body.duration_s else ""
    out = _free(folder, f"{video.stem}{clip}.{code}.burned", ".mp4")
    try:
        job = _burns(request).start(
            source,
            out,
            cues=cues,
            wrap=get(code).wrap,
            look=body.look(),
            offset_ms=store.playback(pid).offset_ms,
            start_s=body.start_s,
            duration_s=duration,
        )
    except BurnBusy as exc:
        raise HTTPException(409, str(exc)) from exc
    return _burn_json(job)


@router.get("/burns/{job_id}")
def get_burn(job_id: str, request: Request) -> dict[str, Any]:
    job = _burns(request).get(job_id)
    if job is None:
        raise HTTPException(404, f"unknown export {job_id!r}")
    return _burn_json(job)


@router.post("/burns/{job_id}/cancel")
def cancel_burn(job_id: str, request: Request) -> dict[str, Any]:
    if not _burns(request).cancel(job_id):
        raise HTTPException(404, f"unknown export {job_id!r}")
    return {"ok": True}
