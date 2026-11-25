from __future__ import annotations

import json
import re
from pathlib import Path

import pytest
from manage_support import Rig

from backend.manager.settings import (
    DEFAULT_UI_LANGUAGE,
    AppSettings,
    SettingsError,
    SettingsStore,
    UiLanguage,
    parse_settings,
    settings_json,
)

ROOT = Path(__file__).resolve().parent.parent


def test_the_window_is_traditional_chinese_until_a_person_picks_a_language(rig: Rig) -> None:
    assert rig.client.get("/api/settings").json()["ui_language"] == "zh-TW"
    assert rig.ctx.settings.current.ui_language is UiLanguage.ZH_TW


def test_the_frontend_and_the_backend_start_from_the_same_window_language() -> None:
    source = (ROOT / "app" / "src" / "i18n" / "locale.ts").read_text(encoding="utf-8")
    declared = re.search(r'export const DEFAULT_UI_LANGUAGE: UiLanguage = "([^"]+)";', source)

    assert declared is not None
    assert declared.group(1) == DEFAULT_UI_LANGUAGE.value


@pytest.mark.parametrize("language", ["en", "zh-TW", "zh-CN", "ja", "auto"])
def test_a_saved_window_language_comes_back_and_survives_a_restart(rig: Rig, language: str) -> None:
    reply = rig.client.put("/api/settings", json={"ui_language": language})

    assert reply.status_code == 200 and reply.json()["ui_language"] == language
    rig.start()
    assert rig.client.get("/api/settings").json()["ui_language"] == language


@pytest.mark.parametrize("bad", ["fr", "zh-Hant", "EN", "", 3])
def test_a_window_language_that_is_not_offered_is_refused_and_nothing_changes(
    rig: Rig, bad: object
) -> None:
    rig.client.put("/api/settings", json={"ui_language": "ja"})

    reply = rig.client.put("/api/settings", json={"ui_language": bad})

    assert reply.status_code == 422
    assert rig.client.get("/api/settings").json()["ui_language"] == "ja"


def test_saving_another_part_of_the_settings_keeps_the_window_language(rig: Rig) -> None:
    rig.client.put("/api/settings", json={"ui_language": "en"})

    rig.client.put("/api/settings", json={"registry_url": "https://example.test/registry.json"})
    rig.client.put("/api/settings", json={"llm": {"source": "builtin"}})

    assert rig.client.get("/api/settings").json()["ui_language"] == "en"


def test_switching_the_model_profile_keeps_the_window_language(rig: Rig) -> None:
    rig.client.put("/api/settings", json={"ui_language": "ja"})

    reply = rig.client.put("/api/profile", json={"profile": "cpu"})

    assert reply.status_code == 200
    assert rig.client.get("/api/settings").json()["ui_language"] == "ja"
    rig.start()
    assert rig.client.get("/api/settings").json()["ui_language"] == "ja"


def test_changing_the_window_language_keeps_the_other_saved_settings(rig: Rig) -> None:
    url = "https://example.test/registry.json"
    rig.client.put("/api/settings", json={"registry_url": url})

    rig.client.put("/api/settings", json={"ui_language": "zh-CN"})

    body = rig.client.get("/api/settings").json()
    assert body["registry_url"] == url and body["ui_language"] == "zh-CN"


def test_a_settings_file_from_before_the_window_language_loads_as_the_default(
    tmp_path: Path,
) -> None:
    old = {"schema_version": 1, "profile": None, "llm": {"source": "builtin"}, "registry_url": None}
    (tmp_path / "settings.json").write_text(json.dumps(old), encoding="utf-8")

    store = SettingsStore(tmp_path)

    assert store.problem is None and store.current.ui_language is DEFAULT_UI_LANGUAGE


def test_a_settings_file_with_a_bad_window_language_is_not_used_and_says_why(
    tmp_path: Path,
) -> None:
    (tmp_path / "settings.json").write_text(json.dumps({"ui_language": "fr"}), encoding="utf-8")

    store = SettingsStore(tmp_path)

    assert store.current == AppSettings() and store.problem is not None
    assert "fr" in store.problem


def test_the_settings_model_writes_and_reads_the_window_language() -> None:
    saved = settings_json(AppSettings(ui_language=UiLanguage.JA))

    assert saved["ui_language"] == "ja"
    assert parse_settings(saved).ui_language is UiLanguage.JA
    with pytest.raises(SettingsError):
        parse_settings({"ui_language": "klingon"})
