from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException

from backend.api.deps import Context, job_json, unknown
from backend.manager.context import ManagerContext
from backend.manager.download import InstallState, JobState
from backend.manager.models import delete_model, model_plan
from backend.manager.registry import Model

router = APIRouter(prefix="/api/models", tags=["models"])


def model_entry(ctx: ManagerContext, model: Model) -> dict[str, Any]:
    plan = model_plan(model.id, ctx.registry, ctx.storage)
    active = ctx.runner.active_job(model.id)
    return {
        "id": model.id,
        "kind": model.kind,
        "engine": model.engine,
        "version": model.version,
        "size_bytes": model.size_bytes,
        "license": model.license,
        "needs": list(model.needs),
        "state": InstallState.INSTALLING if active else plan.state(),
        "path": str(ctx.storage.model_file(model)),
        "job_id": active.id if active else None,
    }


@router.get("")
def list_models(ctx: Context) -> list[dict[str, Any]]:
    return [model_entry(ctx, model) for model in ctx.registry.models.values()]


@router.post("/{model_id}/download")
def download_model(model_id: str, ctx: Context) -> dict[str, Any]:
    if model_id not in ctx.registry.models:
        raise unknown("model", model_id)
    return job_json(ctx.runner.submit(model_plan(model_id, ctx.registry, ctx.storage)))


@router.delete("/{model_id}", status_code=204)
def remove_model(model_id: str, ctx: Context) -> None:
    if model_id not in ctx.registry.models:
        raise unknown("model", model_id)
    active = ctx.runner.active_job(model_id)
    if active and active.state is not JobState.QUEUED:
        raise HTTPException(409, f"{model_id} is being downloaded; cancel the download first")
    if active:
        ctx.runner.cancel(active.id)
    delete_model(model_id, ctx.registry, ctx.storage)
