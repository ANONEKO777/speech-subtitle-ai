from __future__ import annotations

from dataclasses import asdict
from typing import Annotated, Any

from fastapi import Depends, HTTPException, Request
from fastapi.responses import JSONResponse

from backend.manager.context import ManagerContext
from backend.manager.download import JobStatus, is_locked, readable_os_error
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


def locked_path_response(_: Request, exc: Exception) -> JSONResponse:
    """The one mapping for a file another program holds: a readable 409 naming the path. Any
    route that touches files gets it. Other OS errors stay a server error."""
    if not (isinstance(exc, OSError) and is_locked(exc)):
        raise exc
    return JSONResponse({"detail": {"message": readable_os_error(exc)}}, status_code=409)
