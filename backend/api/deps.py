from __future__ import annotations

from dataclasses import asdict
from typing import Annotated, Any

from fastapi import Depends, HTTPException, Request

from backend.manager.context import ManagerContext
from backend.manager.download import JobStatus
from backend.manager.maintain import Refused


def get_context(request: Request) -> ManagerContext:
    return request.app.state.manager


Context = Annotated[ManagerContext, Depends(get_context)]


def job_json(status: JobStatus) -> dict[str, Any]:
    return asdict(status)


def unknown(kind: str, asset_id: str) -> HTTPException:
    return HTTPException(404, f"unknown {kind} {asset_id!r}")


def pipeline_busy(request: Request) -> bool:
    """Whether a pipeline job is running, so models and runtimes must not change under it."""
    jobs = getattr(request.app.state, "jobs", None)
    return jobs is not None and jobs.busy()


def refuse_while_busy(request: Request, action: str) -> None:
    if pipeline_busy(request):
        raise HTTPException(409, f"a job is running; wait for it before you {action}")


def refusal(exc: Refused) -> HTTPException:
    detail = {"message": str(exc), "blockers": list(exc.blockers), "can_force": exc.status == 409}
    return HTTPException(exc.status, detail)
