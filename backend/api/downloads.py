from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from backend.api.deps import Context, job_json, pipeline_busy
from backend.api.models import model_entry
from backend.api.runtimes import runtime_entry
from backend.manager import profiles
from backend.manager.context import ManagerContext
from backend.manager.download import TERMINAL
from backend.manager.storage import StorageError, parse_config
from backend.manager.storage_move import MoveState, installed_models

router = APIRouter(prefix="/api", tags=["downloads"])


class StorageBody(BaseModel):
    models_dir: str | None = None
    mirrors: dict[str, str] | None = None


@router.get("/registry")
def registry(ctx: Context) -> dict[str, Any]:
    return {
        "models": [model_entry(ctx, m) for m in ctx.registry.models.values()],
        "runtimes": [runtime_entry(ctx, r) for r in ctx.registry.runtimes.values()],
    }


@router.get("/work")
def work(request: Request, ctx: Context) -> dict[str, list[str]]:
    """What the backend is doing now that an app update would cut off, because installing stops
    the backend. The window holds the install while this list is not empty."""
    burns = getattr(request.app.state, "burns", None)
    doing = {
        "job": pipeline_busy(request),
        "export": burns is not None and burns.running() is not None,
        "download": any(j.state not in TERMINAL for j in ctx.runner.jobs()),
        "move": ctx.mover.status().state is MoveState.RUNNING,
        "selftest": ctx.selftest.running,
    }
    return {"work": [kind for kind, now in doing.items() if now]}


@router.get("/downloads")
def list_downloads(ctx: Context) -> list[dict[str, Any]]:
    return [job_json(status) for status in ctx.runner.jobs()]


@router.get("/downloads/{job_id}")
def get_download(job_id: str, ctx: Context) -> dict[str, Any]:
    status = ctx.runner.status(job_id)
    if status is None:
        raise HTTPException(404, f"unknown download {job_id!r}")
    return job_json(status)


@router.post("/downloads/{job_id}/cancel")
def cancel_download(job_id: str, ctx: Context) -> dict[str, Any]:
    status = ctx.runner.cancel(job_id)
    if status is None:
        raise HTTPException(404, f"unknown download {job_id!r}")
    return job_json(status)


@router.get("/storage")
def get_storage(ctx: Context) -> dict[str, Any]:
    config = ctx.storage.config
    return {
        "user_data": str(ctx.storage.user_data),
        "models_dir": str(ctx.storage.models_root),
        "custom_models_dir": str(config.models_dir) if config.models_dir else None,
        "mirrors": dict(config.mirrors),
    }


@router.put("/storage")
def put_storage(body: StorageBody, ctx: Context) -> dict[str, Any]:
    current = ctx.storage.config
    sent = body.model_fields_set
    try:
        config = parse_config(
            {
                "models_dir": body.models_dir
                if "models_dir" in sent
                else _text(current.models_dir),
                "mirrors": body.mirrors if body.mirrors is not None else dict(current.mirrors),
            }
        )
        if config.models_dir:
            config.models_dir.mkdir(parents=True, exist_ok=True)
    except (StorageError, OSError) as exc:
        raise HTTPException(422, str(exc)) from exc
    old_root = ctx.storage.models_root
    ctx.storage.update(config)
    result = get_storage(ctx)
    result["warnings"] = _unmoved_warning(ctx, old_root)
    return result


def _unmoved_warning(ctx: ManagerContext, old_root: Path) -> list[str]:
    if old_root == ctx.storage.models_root:
        return []
    left = installed_models(ctx.registry, old_root)
    if not left:
        return []
    size = sum(s for _m, _p, s in left)
    return [
        f"{len(left)} installed model(s), {size / (1 << 30):.1f} GiB, stay in {old_root} and are "
        f"not moved. The app now looks for models in {ctx.storage.models_root}, so they show as "
        "not installed there. Use POST /api/storage/move to move them, or set the folder back."
    ]


def _text(path: Path | None) -> str | None:
    return str(path) if path else None


@router.get("/assets/required")
def required_assets(ctx: Context) -> dict[str, Any]:
    selection = profiles.select(ctx.detect_hardware(), ctx.registry)
    assets = profiles.required_assets(selection)
    return {
        "profile": selection.profile.id,
        "models": list(assets.models),
        "runtimes": list(assets.runtimes),
    }
