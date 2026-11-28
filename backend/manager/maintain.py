"""Delete, verify, repair, re-download. The rules live here so the routes stay thin."""

from __future__ import annotations

import logging
from collections.abc import Sequence
from dataclasses import dataclass, replace
from enum import StrEnum

from backend.core.notices import (
    CANNOT_DELETE,
    FORCE_NEEDS_REASON,
    FOUND_ELSEWHERE,
    REPAIR_FILE_MISSING,
    REPAIR_INCOMPLETE,
    REPAIR_RUNTIME_CHECKED,
    REPAIR_SHA_DIFFERS,
    REPAIR_SHA_MATCHES,
    STILL_NEEDED,
    Notice,
    noticed,
)
from backend.manager.active import resolve_active
from backend.manager.context import ManagerContext
from backend.manager.download import InstallState, JobStatus, Plan, os_error_said
from backend.manager.inventory import Entry, active_assets, asset
from backend.manager.manifest import Record
from backend.manager.models import delete_model, model_plan
from backend.manager.registry import Model, Runtime
from backend.manager.runtimes import (
    NotInstallable,
    delete_runtime,
    found_outside_runtimes,
    runtime_plan,
)

log = logging.getLogger(__name__)

MIN_REASON_CHARS = 8


class Refused(Exception):
    def __init__(self, message: str, blockers: tuple[Notice, ...] = (), status: int = 409) -> None:
        super().__init__(message)
        self.blockers_notices = blockers
        self.blockers = tuple(blocker.message for blocker in blockers)
        self.status = status


def _refused(
    notice: Notice,
    blockers: tuple[Notice, ...] = (),
    status: int = 409,
    inside: Sequence[Notice] = (),
) -> Refused:
    """A refusal whose notices are `notice` and then those quoted inside it (`inside`)."""
    made = noticed(lambda text: Refused(text, blockers, status), notice)
    for quoted in reversed(inside):
        cause = noticed(ValueError, quoted)
        cause.__cause__, made.__cause__ = made.__cause__, cause
    return made


class RepairAction(StrEnum):
    NONE = "none"
    REFETCH = "refetch"
    RESUME = "resume"


@dataclass(frozen=True, slots=True)
class RepairResult:
    action: RepairAction
    reason: Notice
    job: JobStatus | None
    record: Record | None


def plan_of(ctx: ManagerContext, asset_id: str) -> Plan:
    if asset_id in ctx.registry.models:
        return model_plan(asset_id, ctx.registry, ctx.storage)
    return runtime_plan(asset_id, ctx.registry, ctx.storage)


def active_ids(ctx: ManagerContext) -> frozenset[str]:
    active = resolve_active(ctx.settings.current, ctx.detect_hardware(), ctx.registry)
    return active_assets(active.selection, ctx.registry)


def delete_asset(ctx: ManagerContext, asset_id: str, force: bool, reason: str) -> None:
    """Delete one asset, refusing when something still needs it. `force` overrides the refusal and
    needs a reason, which is logged."""
    found = asset(ctx.registry, asset_id)
    if isinstance(found, Runtime):
        elsewhere = found_outside_runtimes(found, ctx.storage)
        if elsewhere is not None:
            notice = FOUND_ELSEWHERE(
                program=elsewhere.name,
                where=str(elsewhere.parent),
                folder=str(ctx.storage.runtime_dir(found)),
            )
            raise noticed(lambda text: Refused(text, status=400), notice)
    blockers = ctx.inventory.blockers(asset_id, active_ids(ctx))
    if blockers:
        if not force:
            needed = STILL_NEEDED(asset=asset_id, blockers=[b.message for b in blockers])
            raise _refused(needed, blockers, inside=blockers)
        if len(reason.strip()) < MIN_REASON_CHARS:
            short = FORCE_NEEDS_REASON(asset=asset_id, characters=str(MIN_REASON_CHARS))
            raise _refused(short, blockers, status=422)
        log.warning(
            "forced delete of %s over %s: %s",
            asset_id,
            [b.message for b in blockers],
            reason.strip(),
        )
    try:
        if isinstance(found, Model):
            delete_model(asset_id, ctx.registry, ctx.storage)
        elif isinstance(found, Runtime):
            delete_runtime(asset_id, ctx.registry, ctx.storage)
    except OSError as exc:
        error, inside = os_error_said(exc)
        raise _refused(CANNOT_DELETE(asset=asset_id, error=error), inside=inside)  # noqa: B904
    ctx.manifest.forget(asset_id)


def redownload(ctx: ManagerContext, asset_id: str) -> JobStatus:
    """Fetch the files again. The new files are downloaded and checked beside the old ones and
    swapped in only on success, so a failed download leaves the working install as it was. A
    running download is returned as it is."""
    running = ctx.runner.active_job(asset_id)
    if running is not None:
        return running
    plan = replace(plan_of(ctx, asset_id), replacing=True)
    if plan.unpack_to is not None:
        for item in plan.items:
            item.dest.unlink(missing_ok=True)
    return ctx.runner.submit(plan)


def repair(ctx: ManagerContext, asset_id: str) -> RepairResult:
    found = asset(ctx.registry, asset_id)
    if isinstance(found, Model):
        path = ctx.storage.model_file(found)
        if not path.is_file():
            plan = plan_of(ctx, asset_id)
            action = (
                RepairAction.RESUME
                if plan.state() is InstallState.PARTIAL
                else RepairAction.REFETCH
            )
            return RepairResult(action, REPAIR_FILE_MISSING(), ctx.runner.submit(plan), None)
        record = ctx.inventory.verify_model(found)
        if record.ok:
            return RepairResult(RepairAction.NONE, REPAIR_SHA_MATCHES(), None, record)
        reason = REPAIR_SHA_DIFFERS(actual=record.sha256[:12], expected=found.sha256[:12])
        return RepairResult(RepairAction.REFETCH, reason, redownload(ctx, asset_id), record)
    try:
        plan = plan_of(ctx, asset_id)
    except NotInstallable as exc:
        raise Refused(str(exc)) from exc
    if plan.state() is InstallState.INSTALLED:
        return RepairResult(
            RepairAction.NONE,
            REPAIR_RUNTIME_CHECKED(),
            None,
            ctx.manifest.get(asset_id),
        )
    return RepairResult(RepairAction.RESUME, REPAIR_INCOMPLETE(), ctx.runner.submit(plan), None)


def asset_state(ctx: ManagerContext, asset_id: str) -> InstallState:
    if ctx.runner.active_job(asset_id) is not None:
        return InstallState.INSTALLING
    try:
        return plan_of(ctx, asset_id).state()
    except NotInstallable:
        installed = ctx.inventory.is_installed(asset_id)
        return InstallState.INSTALLED if installed else InstallState.NOT_INSTALLED


def list_entries(ctx: ManagerContext) -> list[Entry]:
    ids = active_ids(ctx)
    return [
        ctx.inventory.entry(asset_id, ids, asset_state(ctx, asset_id))
        for asset_id in (*ctx.registry.models, *ctx.registry.runtimes)
    ]
