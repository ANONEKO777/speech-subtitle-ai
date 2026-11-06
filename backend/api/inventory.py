from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, ConfigDict

from backend.api.deps import Context, job_json, refusal, refuse_while_busy, unknown
from backend.manager.active import resolve_active
from backend.manager.inventory import Entry
from backend.manager.licenses import license_entries
from backend.manager.maintain import (
    Refused,
    list_entries,
    redownload,
    repair,
)
from backend.manager.profiles import VAD_MODEL
from backend.manager.registry import Model
from backend.manager.storage_move import MoveError
from backend.manager.updates import UpdateError, UpdateStatus, check_updates

router = APIRouter(prefix="/api", tags=["inventory"])


class MoveBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    target: str
    source: str | None = None
    """Where the models are now. Defaults to the current models folder."""


def _entry_json(entry: Entry) -> dict[str, Any]:
    return asdict(entry)


def _known(ctx: Context, asset_id: str) -> None:
    if asset_id not in ctx.registry.models and asset_id not in ctx.registry.runtimes:
        raise unknown("asset", asset_id)


def _one(ctx: Context, asset_id: str) -> dict[str, Any]:
    entry = next(e for e in list_entries(ctx) if e.id == asset_id)
    return _entry_json(entry)


@router.get("/inventory")
def inventory(ctx: Context) -> dict[str, Any]:
    active = resolve_active(ctx.settings.current, ctx.detect_hardware(), ctx.registry)
    found = list_entries(ctx)
    vad = ctx.storage.model_file(ctx.registry.models[VAD_MODEL])
    return {
        "active_profile": active.selection.profile.id.value,
        "models_dir": str(ctx.storage.models_root),
        "runtimes_dir": str(ctx.storage.runtimes_root),
        "vad_model_path": str(vad),
        "installed_bytes": sum(e.size_on_disk or 0 for e in found),
        "assets": [_entry_json(e) for e in found],
    }


@router.get("/inventory/{asset_id}")
def inventory_item(asset_id: str, ctx: Context) -> dict[str, Any]:
    _known(ctx, asset_id)
    return _one(ctx, asset_id)


@router.post("/inventory/{asset_id}/verify")
def verify(asset_id: str, ctx: Context) -> dict[str, Any]:
    """Hash a model file now and compare it with the registry digest."""
    _known(ctx, asset_id)
    found = ctx.registry.models.get(asset_id)
    if not isinstance(found, Model):
        raise HTTPException(
            400, f"{asset_id} is a runtime; its archive was checked when it was downloaded"
        )
    if not ctx.storage.model_file(found).is_file():
        raise HTTPException(409, f"{asset_id} is not installed")
    ctx.inventory.verify_model(found)
    return _one(ctx, asset_id)


@router.post("/inventory/{asset_id}/repair")
def repair_asset(asset_id: str, request: Request, ctx: Context) -> dict[str, Any]:
    """Check the asset, and fetch it again if it is missing, partial or its SHA256 is wrong."""
    _known(ctx, asset_id)
    refuse_while_busy(request, "repair an asset")
    try:
        result = repair(ctx, asset_id)
    except Refused as exc:
        raise refusal(exc) from exc
    return {
        "action": result.action,
        "reason": result.reason,
        "job": job_json(result.job) if result.job else None,
        "asset": _one(ctx, asset_id),
    }


@router.post("/inventory/{asset_id}/redownload")
def redownload_asset(asset_id: str, request: Request, ctx: Context) -> dict[str, Any]:
    _known(ctx, asset_id)
    refuse_while_busy(request, "download an asset again")
    try:
        return job_json(redownload(ctx, asset_id))
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.post("/updates/check")
def updates(ctx: Context) -> dict[str, Any]:
    try:
        report = check_updates(ctx.inventory, ctx.settings.current.registry_url, ctx.fetch_remote)
    except UpdateError as exc:
        raise HTTPException(502, {"message": str(exc), "url": exc.url}) from exc
    return asdict(report)


@router.post("/inventory/{asset_id}/update")
def update_asset(asset_id: str, request: Request, ctx: Context) -> dict[str, Any]:
    """Fetch the registry version again, only when the installed one differs from it."""
    _known(ctx, asset_id)
    refuse_while_busy(request, "update an asset")
    try:
        report = check_updates(ctx.inventory, ctx.settings.current.registry_url, ctx.fetch_remote)
    except UpdateError as exc:
        raise HTTPException(502, {"message": str(exc), "url": exc.url}) from exc
    item = next(i for i in report.items if i.id == asset_id)
    if item.status is not UpdateStatus.UPDATE_AVAILABLE or not item.installable:
        raise HTTPException(409, f"nothing to update for {asset_id}: {item.message}")
    return job_json(redownload(ctx, asset_id))


@router.get("/licenses")
def licenses(ctx: Context) -> dict[str, Any]:
    return {"licenses": [asdict(e) for e in license_entries(ctx.registry)]}


@router.get("/storage/move")
def move_status(ctx: Context) -> dict[str, Any]:
    return asdict(ctx.mover.status())


@router.post("/storage/move", status_code=202)
def move_models(body: MoveBody, request: Request, ctx: Context) -> dict[str, Any]:
    """Move the installed models. This is the only call that moves model files."""
    refuse_while_busy(request, "move the models")
    source = Path(body.source) if body.source else ctx.storage.models_root
    try:
        return asdict(ctx.mover.start(source, Path(body.target)))
    except MoveError as exc:
        raise HTTPException(409, str(exc)) from exc
