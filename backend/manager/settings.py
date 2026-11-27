"""The one typed settings model: `settings.json` in the user data folder.

Bad values cannot be built (`__post_init__` refuses them), so a loaded file and an API body go
through the same checks. The cloud API key is not here (see `secrets`). The models folder and
download mirrors stay in `storage.json`, which `storage.Storage` owns."""

from __future__ import annotations

import json
import logging
import os
import threading
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import cast
from urllib.parse import urlsplit

from backend.manager.profiles import ProfileId

log = logging.getLogger(__name__)

SETTINGS_FILE = "settings.json"
SCHEMA_VERSION = 1
DEFAULT_OLLAMA_URL = "http://127.0.0.1:11434"
LOOPBACK = frozenset({"127.0.0.1", "localhost", "::1"})
CLOUD_CONSENT_TEXT = (
    "A cloud LLM receives your transcript text, glossary and the summary prompt over the "
    "internet. The content of your video leaves this machine and is handled under the "
    "provider's terms. Local models never send it anywhere."
)


class SettingsError(ValueError):
    pass


class LlmSource(StrEnum):
    BUILTIN = "builtin"
    OLLAMA = "ollama"
    CLOUD = "cloud"


class UiLanguage(StrEnum):
    """The language of the app window. AUTO follows the operating system, and the frontend picks."""

    AUTO = "auto"
    EN = "en"
    ZH_TW = "zh-TW"
    ZH_CN = "zh-CN"
    JA = "ja"


DEFAULT_UI_LANGUAGE = UiLanguage.AUTO
"""Follow the operating system, as a fresh install and a settings file with no language do."""


def clean_url(value: str, what: str, *, https_only: bool = False) -> str:
    parts = urlsplit(value.strip())
    schemes = ("https",) if https_only else ("http", "https")
    if parts.scheme not in schemes or not parts.hostname:
        raise SettingsError(f"{what} must be an {' or '.join(schemes)} URL with a host")
    if parts.username or parts.password or parts.query or parts.fragment:
        raise SettingsError(f"{what} must not hold a user name, password, query or fragment")
    return value.strip().rstrip("/")


@dataclass(frozen=True, slots=True)
class LlmSettings:
    source: LlmSource = LlmSource.BUILTIN
    ollama_url: str = DEFAULT_OLLAMA_URL
    ollama_model: str = ""
    cloud_url: str = ""
    cloud_model: str = ""
    cloud_consent: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(self, "ollama_url", clean_url(self.ollama_url, "ollama_url"))
        if self.cloud_url:
            url = clean_url(self.cloud_url, "cloud_url")
            if not url.startswith("https://") and urlsplit(url).hostname not in LOOPBACK:
                raise SettingsError("cloud_url must use https unless it points at this machine")
            object.__setattr__(self, "cloud_url", url)
        if self.source is LlmSource.OLLAMA and not self.ollama_model.strip():
            raise SettingsError("ollama_model is required when the source is ollama")
        if self.source is LlmSource.CLOUD:
            if not self.cloud_url or not self.cloud_model.strip():
                raise SettingsError("cloud_url and cloud_model are required for a cloud LLM")
            if not self.cloud_consent:
                raise SettingsError(
                    "cloud_consent must be true to use a cloud LLM. " + CLOUD_CONSENT_TEXT
                )


@dataclass(frozen=True, slots=True)
class AppSettings:
    profile: ProfileId | None = None
    """None follows the recommendation for the detected hardware."""
    llm: LlmSettings = field(default_factory=LlmSettings)
    registry_url: str | None = None
    """Where to look for a newer registry.json. None means no remote is configured."""
    ui_language: UiLanguage = DEFAULT_UI_LANGUAGE

    def __post_init__(self) -> None:
        if self.registry_url is not None:
            object.__setattr__(
                self, "registry_url", clean_url(self.registry_url, "registry_url", https_only=True)
            )


def _object(raw: object, what: str, keys: set[str]) -> dict[str, object]:
    if not isinstance(raw, dict):
        raise SettingsError(f"{what} must be an object")
    data = cast("dict[str, object]", raw)
    extra = sorted(set(data) - keys)
    if extra:
        raise SettingsError(f"{what}: unexpected keys {extra}")
    return data


def _text(data: dict[str, object], key: str, default: str) -> str:
    value = data.get(key, default)
    if not isinstance(value, str):
        raise SettingsError(f"{key} must be a string")
    return value


def parse_settings(raw: object) -> AppSettings:
    top = _object(
        raw, "settings", {"schema_version", "profile", "llm", "registry_url", "ui_language"}
    )
    if top.get("schema_version", SCHEMA_VERSION) != SCHEMA_VERSION:
        raise SettingsError(f"unsupported schema_version {top['schema_version']!r}")
    llm = _object(
        top.get("llm", {}),
        "llm",
        {"source", "ollama_url", "ollama_model", "cloud_url", "cloud_model", "cloud_consent"},
    )
    consent = llm.get("cloud_consent", False)
    if type(consent) is not bool:
        raise SettingsError("cloud_consent must be true or false")
    try:
        source = LlmSource(llm.get("source", LlmSource.BUILTIN))
        profile = None if top.get("profile") is None else ProfileId(str(top["profile"]))
        ui_language = UiLanguage(top.get("ui_language", DEFAULT_UI_LANGUAGE))
    except ValueError as exc:
        raise SettingsError(str(exc)) from exc
    registry_url = top.get("registry_url")
    if registry_url is not None and not isinstance(registry_url, str):
        raise SettingsError("registry_url must be a string or null")
    return AppSettings(
        profile=profile,
        llm=LlmSettings(
            source=source,
            ollama_url=_text(llm, "ollama_url", DEFAULT_OLLAMA_URL),
            ollama_model=_text(llm, "ollama_model", ""),
            cloud_url=_text(llm, "cloud_url", ""),
            cloud_model=_text(llm, "cloud_model", ""),
            cloud_consent=consent,
        ),
        registry_url=registry_url or None,
        ui_language=ui_language,
    )


def settings_json(settings: AppSettings) -> dict[str, object]:
    llm = settings.llm
    return {
        "schema_version": SCHEMA_VERSION,
        "profile": settings.profile.value if settings.profile else None,
        "llm": {
            "source": llm.source.value,
            "ollama_url": llm.ollama_url,
            "ollama_model": llm.ollama_model,
            "cloud_url": llm.cloud_url,
            "cloud_model": llm.cloud_model,
            "cloud_consent": llm.cloud_consent,
        },
        "registry_url": settings.registry_url,
        "ui_language": settings.ui_language.value,
    }


def write_json_atomic(target: Path, payload: object) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    temp = target.with_name(target.name + ".tmp")
    with temp.open("w", encoding="utf-8") as sink:
        json.dump(payload, sink, indent=2)
        sink.flush()
        os.fsync(sink.fileno())
    os.replace(temp, target)


class SettingsStore:
    def __init__(self, user_data: Path) -> None:
        self._path = user_data / SETTINGS_FILE
        self._lock = threading.Lock()
        self.problem: str | None = None
        """Why the file on disk was not used, so the page can say so. None when it was fine."""
        self._current = self._load()

    @property
    def current(self) -> AppSettings:
        return self._current

    def save(self, settings: AppSettings) -> None:
        with self._lock:
            write_json_atomic(self._path, settings_json(settings))
            self._current = settings
            self.problem = None

    def _load(self) -> AppSettings:
        try:
            raw: object = json.loads(self._path.read_text(encoding="utf-8"))
            return parse_settings(raw)
        except FileNotFoundError:
            return AppSettings()
        except (OSError, ValueError) as exc:
            self.problem = f"{self._path} was not used: {exc}"
            log.warning("%s", self.problem)
            return AppSettings()


def load_settings(user_data: Path) -> AppSettings:
    """A fresh read, for code that runs once per job and must see a change made since start."""
    return SettingsStore(user_data).current
