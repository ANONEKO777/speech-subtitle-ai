from __future__ import annotations

from dataclasses import asdict
from typing import Any

from fastapi import APIRouter, HTTPException, Request

from backend.api.deps import Context, job_json, refusal, refuse_while_busy, refused, unknown
from backend.core.notices import BEING_INSTALLED, BUSY_DELETE_RUNTIME, BUSY_SELFTEST
from backend.manager.active import resolve_active
from backend.manager.context import ManagerContext
from backend.manager.download import InstallState, JobState
from backend.manager.maintain import Refused, delete_asset
from backend.manager.registry import Runtime
from backend.manager.runtimes import NotInstallable, runtime_executable, runtime_plan
from backend.manager.selftest import run_selftest

router = APIRouter(prefix="/api/runtimes", tags=["runtimes"])


def runtime_entry(ctx: ManagerContext, runtime: Runtime) -> dict[str, Any]:
    installable = runtime.executable is not None and not runtime.is_local_build
    active = ctx.runner.active_job(runtime.id)
    state = None
    if installable:
        plan = runtime_plan(runtime.id, ctx.registry, ctx.storage)
        state = InstallState.INSTALLING if active else plan.state()
    exe = runtime_executable(runtime.id, ctx.registry, ctx.storage)
    if runtime.is_local_build:
        state = InstallState.INSTALLED if exe else InstallState.NOT_INSTALLED
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


@router.get("/selftest")
def last_selftest(ctx: Context) -> dict[str, Any] | None:
    report = ctx.selftest.load()
    return asdict(report) if report else None


@router.post("/selftest")
def selftest(request: Request, ctx: Context) -> dict[str, Any]:
    """Run the active profile's ASR and LLM runtimes for a few seconds. When the GPU backend
    fails, the CPU backend is tried and the reason is saved for the pipeline and the page."""
    refuse_while_busy(request, BUSY_SELFTEST)
    active = resolve_active(ctx.settings.current, ctx.detect_hardware(), ctx.registry)
    report = run_selftest(
        active.selection.profile, ctx.registry, ctx.storage, ctx.selftest, ctx.probe
    )
    return asdict(report)


@router.delete("/{runtime_id}", status_code=204)
def remove_runtime(
    runtime_id: str, request: Request, ctx: Context, force: bool = False, reason: str = ""
) -> None:
    if runtime_id not in ctx.registry.runtimes:
        raise unknown("runtime", runtime_id)
    refuse_while_busy(request, BUSY_DELETE_RUNTIME)
    active = ctx.runner.active_job(runtime_id)
    if active and active.state is not JobState.QUEUED:
        raise refused(409, BEING_INSTALLED(asset=runtime_id))
    try:
        delete_asset(ctx, runtime_id, force, reason)
    except Refused as exc:
        raise refusal(exc) from exc
    except NotInstallable as exc:
        raise HTTPException(400, str(exc)) from exc
    if active:
        ctx.runner.cancel(active.id)
