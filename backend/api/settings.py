from __future__ import annotations

from dataclasses import asdict
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, field_validator

from backend.api.deps import Context
from backend.api.downloads import get_storage
from backend.core import notices
from backend.core.notices import noticed
from backend.llm.client import sendable
from backend.manager.llm_check import test_connection
from backend.manager.secrets import LLM_KEY, SecretError
from backend.manager.settings import (
    CLOUD_CONSENT_TEXT,
    DEFAULT_OLLAMA_URL,
    AppSettings,
    LlmSettings,
    LlmSource,
    SettingsError,
    UiLanguage,
)

router = APIRouter(prefix="/api", tags=["settings"])


class LlmBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    source: LlmSource
    ollama_url: str = DEFAULT_OLLAMA_URL
    ollama_model: str = ""
    cloud_url: str = ""
    cloud_model: str = ""
    cloud_consent: bool = False
    """Must be true to save a cloud source: the content of your videos leaves this machine."""
    api_key: str | None = None
    """Write only. Omit to keep the saved key, send an empty string to delete it. Spaces and line
    breaks around it are dropped, as a pasted key often carries them and none can be sent."""

    @field_validator("api_key")
    @classmethod
    def _trimmed(cls, key: str | None) -> str | None:
        return key.strip() if key is not None else None

    def sendable_key(self) -> str | None:
        """`api_key`, refused now when no header can carry it, not at the first run."""
        if self.api_key and not sendable(self.api_key):
            raise noticed(SettingsError, notices.LLM_KEY_UNSENDABLE())
        return self.api_key

    def settings(self, *, consent: bool | None = None) -> LlmSettings:
        return LlmSettings(
            source=self.source,
            ollama_url=self.ollama_url,
            ollama_model=self.ollama_model,
            cloud_url=self.cloud_url,
            cloud_model=self.cloud_model,
            cloud_consent=self.cloud_consent if consent is None else consent,
        )


class SettingsBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    llm: LlmBody | None = None
    registry_url: str | None = None
    ui_language: UiLanguage | None = None
    """Omit to keep the saved language of the window."""


def _llm_json(ctx: Context, llm: LlmSettings) -> dict[str, Any]:
    return {**asdict(llm), "source": llm.source.value, "api_key_set": _key_saved(ctx)}


def _key_saved(ctx: Context) -> bool:
    try:
        return bool(ctx.secrets.get(LLM_KEY))
    except SecretError:
        return False


def view(ctx: Context) -> dict[str, Any]:
    current = ctx.settings.current
    return {
        "llm": _llm_json(ctx, current.llm),
        "registry_url": current.registry_url,
        "ui_language": current.ui_language.value,
        "cloud_consent_text": CLOUD_CONSENT_TEXT,
        "problem": ctx.settings.problem,
        "storage": get_storage(ctx),
    }


def _unprocessable(exc: Exception) -> HTTPException:
    return HTTPException(422, str(exc))


@router.get("/settings")
def get_settings(ctx: Context) -> dict[str, Any]:
    return view(ctx)


@router.put("/settings")
def put_settings(body: SettingsBody, ctx: Context) -> dict[str, Any]:
    current = ctx.settings.current
    sent = body.model_fields_set
    try:
        llm = body.llm.settings() if body.llm else current.llm
        registry_url = body.registry_url if "registry_url" in sent else current.registry_url
        ui_language = body.ui_language or current.ui_language
        updated = AppSettings(current.profile, llm, registry_url or None, ui_language)
        key = body.llm.sendable_key() if body.llm else None
        if llm.source is LlmSource.CLOUD and not (key or (key is None and _key_saved(ctx))):
            raise SettingsError("an API key is required for a cloud LLM")
        if _url_changed(current.llm, llm) and key is None:
            raise SettingsError(
                "the cloud address changed, so the saved API key is not sent to it; "
                "enter the API key for the new address"
            )
        if key is not None:
            if key:
                ctx.secrets.set(LLM_KEY, key)
            else:
                ctx.secrets.clear(LLM_KEY)
    except (SettingsError, SecretError) as exc:
        raise _unprocessable(exc) from exc
    ctx.settings.save(updated)
    return view(ctx)


def _url_changed(saved: LlmSettings, new: LlmSettings) -> bool:
    """A saved key belongs to the address it was entered for, so a cloud save that moves to
    another address needs its own key. Asking is safer than deleting the old key behind the
    user's back, and the old key and address stay as they were when the save is refused."""
    return new.source is LlmSource.CLOUD and new.cloud_url != saved.cloud_url


def _saved_key_for(ctx: Context, llm: LlmSettings) -> str | None:
    """The saved key goes only to the cloud address the user saved and consented to. A typo or
    another address gets no key unless the request carries its own."""
    saved = ctx.settings.current.llm
    if llm.source is not LlmSource.CLOUD or not (saved.cloud_consent and saved.cloud_url):
        return None
    if llm.cloud_url != saved.cloud_url:
        return None
    try:
        return ctx.secrets.get(LLM_KEY)
    except SecretError:
        return None


class TestBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    llm: LlmBody


@router.post("/llm/test")
def test_llm(body: TestBody, ctx: Context) -> dict[str, Any]:
    """Check that the source answers. Failure is a normal answer with `ok: false` and the URL."""
    try:
        llm = body.llm.settings(consent=True)
        sent = body.llm.sendable_key()
    except SettingsError as exc:
        raise _unprocessable(exc) from exc
    key = sent if sent is not None else _saved_key_for(ctx, llm)
    result = test_connection(llm, key, ctx.registry, ctx.storage)
    return {**asdict(result), "source": result.source.value, "models": list(result.models)}
