from __future__ import annotations

from dataclasses import asdict
from typing import Annotated, Any

from fastapi import Depends, HTTPException, Request

from backend.manager.context import ManagerContext
from backend.manager.download import JobStatus


def get_context(request: Request) -> ManagerContext:
    return request.app.state.manager


Context = Annotated[ManagerContext, Depends(get_context)]


def job_json(status: JobStatus) -> dict[str, Any]:
    return asdict(status)


def unknown(kind: str, asset_id: str) -> HTTPException:
    return HTTPException(404, f"unknown {kind} {asset_id!r}")
