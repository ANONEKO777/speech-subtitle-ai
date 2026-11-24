from __future__ import annotations

from dataclasses import asdict, replace
from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel, ConfigDict

from backend.api.deps import Context, job_json
from backend.core import vc_runtime
from backend.manager import profiles
from backend.manager.profiles import ProfileId, profiles_for
from backend.manager.switch import current, download_missing, requirements, warnings_for

router = APIRouter(prefix="/api", tags=["profile"])


class ProfileBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    profile: ProfileId | None
    """A profile id, or null to follow the recommendation for the detected hardware."""


def _stage(stage: profiles.Stage, ctx: Context) -> dict[str, Any]:
    model = ctx.registry.models[stage.model]
    runtime = ctx.registry.runtimes[stage.runtime]
    return {
        "model": model.id,
        "runtime": runtime.id,
        "engine": runtime.engine,
        "device": stage.device.value,
    }


def _profile_json(
    ctx: Context, profile: profiles.Profile, active_id: ProfileId, rec_id: ProfileId
) -> dict[str, Any]:
    need = requirements(ctx, profile.id)
    return {
        "id": profile.id.value,
        "label": profile.label,
        "asr": _stage(profile.asr, ctx),
        "llm": _stage(profile.llm, ctx),
        "recommend_cloud": profile.recommend_cloud,
        "fits_hardware": profiles.fits(profile, ctx.detect_hardware()),
        "active": profile.id is active_id,
        "recommended": profile.id is rec_id,
        "missing": [asdict(m) for m in need.missing],
        "download_bytes": need.download_bytes,
    }


def view(ctx: Context) -> dict[str, Any]:
    active = current(ctx)
    hardware = active.hardware
    chosen, rec = active.selection.profile, active.recommended
    report = ctx.selftest.load()
    return {
        "hardware": asdict(hardware),
        "vc_runtime_missing": bool(vc_runtime.missing()),
        "recommended": {
            "id": rec.profile.id.value,
            "label": rec.profile.label,
            "why": profiles.describe(rec, ctx.registry),
        },
        "active": {
            "id": chosen.id.value,
            "label": chosen.label,
            "source": active.source.value,
            "asr": _stage(chosen.asr, ctx),
            "llm": _stage(chosen.llm, ctx),
            "device": "cpu"
            if report and report.fallback and report.profile is chosen.id
            else chosen.asr.device.value,
        },
        "profiles": [
            _profile_json(ctx, p, chosen.id, rec.profile.id)
            for p in profiles_for(hardware.platform)
        ],
        "fallback": asdict(report.fallback)
        if report and report.fallback and report.profile is chosen.id
        else None,
    }


@router.get("/hardware")
def hardware(ctx: Context) -> dict[str, Any]:
    """The detected hardware (flat, as before) plus the recommended profile."""
    detected = ctx.detect_hardware()
    rec = profiles.select(detected, ctx.registry)
    return {
        **asdict(detected),
        "recommended_profile": rec.profile.id.value,
        "recommendation": profiles.describe(rec, ctx.registry),
    }


@router.get("/profile")
def get_profile(ctx: Context) -> dict[str, Any]:
    return view(ctx)


@router.put("/profile")
def put_profile(body: ProfileBody, ctx: Context) -> dict[str, Any]:
    """Make a profile active at any time. Nothing is downloaded or deleted: the answer lists what
    the profile still needs, and POST /api/profile/download fetches it."""
    ctx.settings.save(replace(ctx.settings.current, profile=body.profile))
    ctx.selftest.clear()
    result = view(ctx)
    chosen = current(ctx).selection.profile
    result["warnings"] = warnings_for(ctx, chosen)
    result["download"] = "/api/profile/download" if result_missing(result) else None
    return result


def result_missing(result: dict[str, Any]) -> bool:
    active_id = result["active"]["id"]
    return any(p["missing"] for p in result["profiles"] if p["id"] == active_id)


@router.post("/profile/download", status_code=202)
def download_profile(ctx: Context) -> dict[str, Any]:
    chosen = current(ctx).selection.profile
    jobs = download_missing(ctx, chosen.id)
    return {"profile": chosen.id.value, "jobs": [job_json(j) for j in jobs]}
