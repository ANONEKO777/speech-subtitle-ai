"""The persistent work queue: add many videos, follow, reorder, pause, retry, clean up.

The per-job routes in `backend.api.jobs` keep working. A queue item runs as an ordinary job and
reports its id in `job_id` while it runs.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from pathlib import Path
from typing import Annotated, Any

from fastapi import APIRouter, Header, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict, Field, field_validator

from backend.api.jobs import JobBody, event_stream
from backend.core.jobs import JobOptions
from backend.core.languages import get as get_language
from backend.core.queue_runner import QueueRunner, scan_folder
from backend.core.queue_store import OnDone, QueueError, QueueSettings

router = APIRouter(prefix="/api/queue", tags=["queue"])


class QueuePath(BaseModel):
    model_config = ConfigDict(extra="forbid")
    path: str = Field(min_length=1)
    target_lang: str | None = None

    @field_validator("target_lang")
    @classmethod
    def _known_language(cls, code: str | None) -> str | None:
        return None if code is None else get_language(code).code


class QueueFolder(QueuePath):
    recursive: bool = False


class AddBody(BaseModel):
    """Videos to queue. `options` is shared by all of them, and a `target_lang` on an item or a
    folder overrides the one in `options`."""

    model_config = ConfigDict(extra="forbid")
    items: list[QueuePath] = []
    folders: list[QueueFolder] = []
    options: JobBody = JobBody()


class OrderBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    ids: list[str]


class PauseBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    interrupt: bool = False


class SettingsBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    on_done: OnDone = OnDone.NOTIFY
    allow_power: bool = False


def queue_of(request: Request) -> QueueRunner:
    return request.app.state.queue


def _item_not_found(exc: KeyError) -> HTTPException:
    return HTTPException(404, f"unknown queue item {exc.args[0]!r}")


@router.get("")
def get_queue(request: Request) -> dict[str, Any]:
    return queue_of(request).describe()


@router.post("/items", status_code=201)
def add_items(body: AddBody, request: Request) -> dict[str, Any]:
    """Queue the files and the videos found in the folders. Every path that was not queued comes
    back under `skipped` with the reason, and the rest is queued."""
    if not body.items and not body.folders:
        raise HTTPException(422, "give at least one item or folder")
    base: JobOptions = body.options.options()
    entries: list[tuple[Path, JobOptions]] = []
    skipped: list[dict[str, str]] = []
    for entry in body.items:
        entries.append((Path(entry.path), _with_lang(base, entry.target_lang)))
    for folder in body.folders:
        try:
            found = scan_folder(Path(folder.path), folder.recursive)
        except NotADirectoryError:
            skipped.append({"path": folder.path, "reason": "not a folder"})
            continue
        except (OSError, QueueError) as exc:
            skipped.append({"path": folder.path, "reason": str(exc)})
            continue
        options = _with_lang(base, folder.target_lang)
        entries.extend((video, options) for video in found)
    queue = queue_of(request)
    added = queue.add(entries)
    skipped.extend({"path": p, "reason": r} for p, r in added.skipped)
    return {
        "added": queue.describe_items([i.id for i in added.items]),
        "skipped": skipped,
    }


def _with_lang(options: JobOptions, code: str | None) -> JobOptions:
    return options if code is None else replace(options, target_lang=code)


@router.put("/order")
def reorder(body: OrderBody, request: Request) -> dict[str, Any]:
    """Put the listed items first, in this order. Items not listed keep their order after them."""
    try:
        queue_of(request).reorder(body.ids)
    except QueueError as exc:
        raise HTTPException(422, str(exc)) from exc
    return queue_of(request).describe()


@router.post("/pause")
def pause(request: Request, body: PauseBody | None = None) -> dict[str, Any]:
    """Stop starting items. The running one finishes, or with `interrupt` stops and is queued
    again at its place."""
    queue_of(request).set_paused(True, body is not None and body.interrupt)
    return queue_of(request).describe()


@router.post("/resume")
def resume(request: Request) -> dict[str, Any]:
    queue_of(request).set_paused(False)
    return queue_of(request).describe()


@router.put("/settings")
def put_settings(body: SettingsBody, request: Request) -> dict[str, Any]:
    """`on_done` is `notify` (the default), `sleep` or `shutdown`. The last two need
    `allow_power` true, which is the user's explicit opt-in."""
    try:
        queue_of(request).set_settings(QueueSettings(body.on_done, body.allow_power))
    except QueueError as exc:
        raise HTTPException(422, str(exc)) from exc
    return queue_of(request).describe_queue()


@router.get("/settings")
def get_settings(request: Request) -> dict[str, Any]:
    return queue_of(request).describe_queue()


@router.post("/power/cancel")
def cancel_power(request: Request) -> dict[str, bool]:
    """Stop the sleep or shutdown countdown."""
    return {"cancelled": queue_of(request).cancel_power()}


@router.delete("/finished")
def remove_finished(request: Request) -> dict[str, Any]:
    return {"removed": queue_of(request).remove_finished()}


@router.delete("/items/{item_id}")
def remove_item(item_id: str, request: Request) -> dict[str, Any]:
    queue = queue_of(request)
    if not queue.has(item_id):
        raise HTTPException(404, f"unknown queue item {item_id!r}")
    removed = queue.remove([item_id])
    if not removed:
        raise HTTPException(409, "only a finished item can be removed; cancel it first")
    return {"removed": removed}


def _command(
    request: Request, item_id: str, action: Callable[[QueueRunner, str], None]
) -> dict[str, Any]:
    queue = queue_of(request)
    try:
        action(queue, item_id)
        return queue.describe_item(item_id)
    except KeyError as exc:
        raise _item_not_found(exc) from exc
    except QueueError as exc:
        raise HTTPException(409, str(exc)) from exc


@router.post("/items/{item_id}/pause")
def pause_item(item_id: str, request: Request) -> dict[str, Any]:
    return _command(request, item_id, QueueRunner.pause_item)


@router.post("/items/{item_id}/resume")
def resume_item(item_id: str, request: Request) -> dict[str, Any]:
    return _command(request, item_id, QueueRunner.resume_item)


@router.post("/items/{item_id}/cancel")
def cancel_item(item_id: str, request: Request) -> dict[str, Any]:
    return _command(request, item_id, QueueRunner.cancel_item)


@router.post("/items/{item_id}/retry")
def retry_item(item_id: str, request: Request) -> dict[str, Any]:
    return _command(request, item_id, QueueRunner.retry_item)


@router.get("/events")
async def queue_events(
    request: Request, last_event_id: Annotated[int | None, Header()] = None
) -> StreamingResponse:
    """Server-sent events for the whole queue, which never end. `item` carries one item as
    `GET /api/queue` shows it, `removed` and `order` carry ids, `queue` the pause flag and
    settings, `done` the item counts when the queue runs dry, and `countdown`,
    `countdown_cancelled` and `power` follow a sleep or shutdown. A client that reconnects with
    `Last-Event-ID` gets the events after that one."""
    return event_stream(queue_of(request).events, last_event_id)
