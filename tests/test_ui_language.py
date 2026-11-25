from __future__ import annotations

import json
from pathlib import Path

import pytest
from manage_support import Rig

from backend.manager.settings import (
    AppSettings,
    SettingsError,
    SettingsStore,
    UiLanguage,
    parse_settings,
    settings_json,
)


def test_the_window_language_follows_the_system_until_a_person_picks_one(rig: Rig) -> None:
    assert rig.client.get("/api/settings").json()["ui_language"] == "auto"
    assert rig.ctx.settings.current.ui_language is UiLanguage.AUTO


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


def test_changing_the_window_language_keeps_the_other_saved_settings(rig: Rig) -> None:
    url = "https://example.test/registry.json"
    rig.client.put("/api/settings", json={"registry_url": url})

    rig.client.put("/api/settings", json={"ui_language": "zh-CN"})

    body = rig.client.get("/api/settings").json()
    assert body["registry_url"] == url and body["ui_language"] == "zh-CN"


def test_a_settings_file_from_before_the_window_language_loads_as_auto(tmp_path: Path) -> None:
    old = {"schema_version": 1, "profile": None, "llm": {"source": "builtin"}, "registry_url": None}
    (tmp_path / "settings.json").write_text(json.dumps(old), encoding="utf-8")

    store = SettingsStore(tmp_path)

    assert store.problem is None and store.current.ui_language is UiLanguage.AUTO


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
