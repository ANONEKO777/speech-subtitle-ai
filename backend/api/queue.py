"""The persistent work queue: add many videos, follow, reorder, pause, retry, clean up.

The per-job routes in `backend.api.jobs` keep working. A queue item runs as an ordinary job and
reports its id in `job_id` while it runs.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import replace
from pathlib import Path
from typing import Annotated, Any

from fastapi import APIRouter, Header, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from backend.api.deps import refused
from backend.api.jobs import JobBody, event_stream
from backend.core.jobs import JobOptions
from backend.core.languages import get as get_language
from backend.core.notices import (
    BATCH_NOT_A_FOLDER,
    BATCH_NOTHING_GIVEN,
    BATCH_REMOVE_FINISHED_ONLY,
    Notice,
    notices_of,
    to_json,
)
from backend.core.queue_runner import QueueRunner, scan_folder
from backend.core.queue_store import OnDone, QueueError, QueueSettings
from backend.core.source_langs import get_source

router = APIRouter(prefix="/api/queue", tags=["queue"])


def _known_languages(codes: list[str] | None) -> list[str] | None:
    """The codes, each a known target language and none twice."""
    if codes is None:
        return None
    known = [get_language(code).code for code in codes]
    if not known or len(set(known)) != len(known):
        raise ValueError("target_langs must list at least one language, each once")
    return known


class QueuePath(BaseModel):
    """`target_lang` is one target. `target_langs` is several, queued one after the other in this
    order for the same video, so the speech steps run once. At most one of the two."""

    model_config = ConfigDict(extra="forbid")
    path: str = Field(min_length=1)
    target_lang: str | None = None
    target_langs: list[str] | None = None
    source_lang: str | None = None

    @field_validator("target_lang")
    @classmethod
    def _known_language(cls, code: str | None) -> str | None:
        return None if code is None else get_language(code).code

    @field_validator("target_langs")
    @classmethod
    def _known_codes(cls, codes: list[str] | None) -> list[str] | None:
        return _known_languages(codes)

    @model_validator(mode="after")
    def _one_kind_of_target(self) -> QueuePath:
        if self.target_lang is not None and self.target_langs is not None:
            raise ValueError("give target_lang or target_langs, not both")
        return self

    @field_validator("source_lang")
    @classmethod
    def _known_source(cls, code: str | None) -> str | None:
        return None if code is None else get_source(code).code


class QueueFolder(QueuePath):
    recursive: bool = False


class AddBody(BaseModel):
    """Videos to queue. `options` is shared by all of them, and a `target_lang`, `target_langs` or
    `source_lang` on an item or a folder overrides the one in `options`. `target_langs` here is the
    targets of every video that names none of its own. Each video gets one queue item per target,
    the targets of a video next to each other in the order given."""

    model_config = ConfigDict(extra="forbid")
    items: list[QueuePath] = []
    folders: list[QueueFolder] = []
    options: JobBody = JobBody()
    target_langs: list[str] | None = None

    @field_validator("target_langs")
    @classmethod
    def _known_codes(cls, codes: list[str] | None) -> list[str] | None:
        return _known_languages(codes)


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
        raise refused(422, BATCH_NOTHING_GIVEN())
    base: JobOptions = body.options.options()
    entries: list[tuple[Path, JobOptions]] = []
    skipped: list[dict[str, Any]] = []
    for entry in body.items:
        entries.extend((Path(entry.path), options) for options in _with_langs(base, entry, body))
    for folder in body.folders:
        try:
            found = scan_folder(Path(folder.path), folder.recursive)
        except NotADirectoryError:
            skipped.append(_skipped(folder.path, *_said(BATCH_NOT_A_FOLDER())))
            continue
        except (OSError, QueueError) as exc:
            skipped.append(_skipped(folder.path, str(exc), notices_of(exc)))
            continue
        per_target = _with_langs(base, folder, body)
        entries.extend((video, options) for video in found for options in per_target)
    queue = queue_of(request)
    added = queue.add(entries)
    skipped.extend(_skipped(*one) for one in added.skipped)
    return {
        "added": queue.describe_items([i.id for i in added.items]),
        "skipped": skipped,
    }


def _said(notice: Notice) -> tuple[str, tuple[Notice, ...]]:
    return notice.message, (notice,)


def _skipped(path: str, reason: str, notices: Sequence[Notice]) -> dict[str, Any]:
    return {"path": path, "reason": reason, "reason_notices": to_json(notices)}


def _with_langs(options: JobOptions, entry: QueuePath, body: AddBody) -> list[JobOptions]:
    """The options of each target of `entry`, in order: its own, else the request's, else the one
    in `options`. A pair the source does not support refuses the whole request."""
    if entry.source_lang is not None:
        options = replace(options, source_lang=entry.source_lang)
    if entry.target_langs is not None:
        targets = entry.target_langs
    elif entry.target_lang is not None:
        targets = [entry.target_lang]
    else:
        targets = body.target_langs or [options.target_lang]
    source = get_source(options.source_lang)
    for target in targets:
        if not source.supports(get_language(target)):
            raise HTTPException(
                422,
                f"{source.name} speech can be translated into {source.allowed_targets()}, "
                f"not {target}: {entry.path}",
            )
    return [replace(options, target_lang=target) for target in targets]


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
        raise refused(409, BATCH_REMOVE_FINISHED_ONLY())
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
