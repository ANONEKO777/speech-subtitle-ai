"""The service's routes on a Mac, driven through `TestClient` with the platform faked.

The registry is the shipped one filtered to macOS; nothing is downloaded and no program starts."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.api import inventory, profile, runtimes, settings
from backend.manager import registry as registry_module
from backend.manager.context import build_context
from backend.manager.hardware import Hardware
from backend.manager.platforms import MACOS_ARM64
from backend.manager.secrets import KEY_NOT_AVAILABLE_MESSAGE, UnavailableSecretStore

MAC = registry_module.load(platform=MACOS_ARM64)
WHISPER = "whispercpp-b5454-macos-metal"
MEMORY_36_GIB = 36 * 1024


class Idle:
    def busy(self) -> bool:
        return False


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Any:
    monkeypatch.setattr("sys.platform", "darwin")
    monkeypatch.setattr("platform.machine", lambda: "arm64")
    hardware = Hardware(None, None, None, MEMORY_36_GIB, 500_000, MACOS_ARM64, "Apple M3 Pro")
    ctx = build_context(
        tmp_path / "data",
        MAC,
        detect_hardware=lambda: hardware,
        secrets=UnavailableSecretStore(),
    )
    app = FastAPI()
    app.state.manager = ctx
    app.state.jobs = Idle()
    for module in (runtimes, inventory, profile, settings):
        app.include_router(module.router)
    found: Any = TestClient(app)
    found.ctx = ctx
    return found


def test_the_profile_page_lists_the_four_mac_profiles_and_recommends_the_conservative_one(
    client: Any,
) -> None:
    body = client.get("/api/profile").json()

    assert [p["id"] for p in body["profiles"]] == [
        "metal-32gb",
        "metal-32gb-parallel",
        "metal-16gb",
        "apple-cpu",
    ]
    assert body["recommended"]["id"] == body["active"]["id"] == "metal-32gb"
    assert body["active"]["device"] == "metal"
    assert body["hardware"]["chip"] == "Apple M3 Pro"
    assert body["hardware"]["gpu_name"] is None
    assert [p["fits_hardware"] for p in body["profiles"]] == [True, True, True, True]


def test_the_runtime_list_has_only_mac_runtimes_and_marks_the_built_one_not_installable(
    client: Any,
) -> None:
    rows = {r["id"]: r for r in client.get("/api/runtimes").json()}

    assert set(rows) == {
        WHISPER,
        "crispasr-v0.8.49-macos-metal",
        "llama.cpp-b12068-macos-metal",
    }
    assert rows[WHISPER]["installable"] is False
    assert rows[WHISPER]["state"] == "not_installed"
    assert rows["llama.cpp-b12068-macos-metal"]["installable"] is True
    assert rows["llama.cpp-b12068-macos-metal"]["backend"] == "metal"


def test_asking_to_install_the_built_runtime_is_a_400_that_names_the_script(client: Any) -> None:
    reply = client.post(f"/api/runtimes/{WHISPER}/install")

    assert reply.status_code == 400
    assert "scripts/mac/build_whisper_cli.sh" in reply.json()["detail"]


def test_the_runtime_shows_as_installed_once_the_program_is_in_its_folder(
    client: Any, tmp_path: Path
) -> None:
    folder = client.ctx.storage.runtime_dir(MAC.runtimes[WHISPER])
    folder.mkdir(parents=True)
    (folder / "whisper-cli").write_bytes(b"x")

    row = next(r for r in client.get("/api/runtimes").json() if r["id"] == WHISPER)

    assert row["state"] == "installed"
    assert row["executable_path"] == str(folder / "whisper-cli")


def test_saving_a_cloud_key_on_a_mac_is_a_422_with_the_plain_refusal(client: Any) -> None:
    reply = client.put(
        "/api/settings",
        json={
            "llm": {
                "source": "cloud",
                "cloud_url": "https://api.example.test/v1",
                "cloud_model": "m",
                "cloud_consent": True,
                "api_key": "sk-secret-123",
            }
        },
    )

    assert reply.status_code == 422
    assert reply.json()["detail"] == KEY_NOT_AVAILABLE_MESSAGE
    assert "sk-secret-123" not in reply.text


def test_the_settings_page_still_loads_on_a_mac_and_says_no_key_is_saved(client: Any) -> None:
    body = client.get("/api/settings").json()

    assert body["llm"]["api_key_set"] is False


def test_the_inventory_lists_every_mac_runtime_and_the_shared_models(client: Any) -> None:
    body = client.get("/api/inventory").json()
    ids = {e["id"] for e in body["assets"]}

    assert WHISPER in ids and "qwen3-8b-q4_k_m" in ids
    assert not any("-win-" in i for i in ids)
    assert body["active_profile"] == "metal-32gb"
