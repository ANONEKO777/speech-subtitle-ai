from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException

from backend.api.deps import Context, job_json, unknown
from backend.manager.context import ManagerContext
from backend.manager.download import InstallState, JobState
from backend.manager.registry import Runtime
from backend.manager.runtimes import (
    NotInstallable,
    delete_runtime,
    runtime_executable,
    runtime_plan,
)

router = APIRouter(prefix="/api/runtimes", tags=["runtimes"])


def runtime_entry(ctx: ManagerContext, runtime: Runtime) -> dict[str, Any]:
    installable = runtime.executable is not None
    active = ctx.runner.active_job(runtime.id)
    state = None
    if installable:
        plan = runtime_plan(runtime.id, ctx.registry, ctx.storage)
        state = InstallState.INSTALLING if active else plan.state()
    exe = runtime_executable(runtime.id, ctx.registry, ctx.storage)
    return {
        "id": runtime.id,
        "engine": runtime.engine,
        "version": runtime.version,
        "backend": runtime.backend,
        "size_bytes": runtime.size_bytes,
        "license": runtime.license,
        "min_driver": runtime.min_driver,
        "ascii_paths_only": runtime.ascii_paths_only,
        "needs": list(runtime.needs),
        "installable": installable,
        "state": state,
        "executable_path": str(exe) if exe else None,
        "job_id": active.id if active else None,
    }


@router.get("")
def list_runtimes(ctx: Context) -> list[dict[str, Any]]:
    return [runtime_entry(ctx, runtime) for runtime in ctx.registry.runtimes.values()]


@router.post("/{runtime_id}/install")
def install_runtime(runtime_id: str, ctx: Context) -> dict[str, Any]:
    if runtime_id not in ctx.registry.runtimes:
        raise unknown("runtime", runtime_id)
    try:
        plan = runtime_plan(runtime_id, ctx.registry, ctx.storage)
    except NotInstallable as exc:
        raise HTTPException(400, str(exc)) from exc
    return job_json(ctx.runner.submit(plan))


@router.delete("/{runtime_id}", status_code=204)
def remove_runtime(runtime_id: str, ctx: Context) -> None:
    if runtime_id not in ctx.registry.runtimes:
        raise unknown("runtime", runtime_id)
    active = ctx.runner.active_job(runtime_id)
    if active and active.state is not JobState.QUEUED:
        raise HTTPException(409, f"{runtime_id} is being installed; cancel the install first")
    if active:
        ctx.runner.cancel(active.id)
    try:
        delete_runtime(runtime_id, ctx.registry, ctx.storage)
    except NotInstallable as exc:
        raise HTTPException(400, str(exc)) from exc
