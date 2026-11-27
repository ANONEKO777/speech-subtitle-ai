"""The service's routes on a Mac, driven through `TestClient` with the platform faked.

The registry is the shipped one filtered to macOS; nothing is downloaded and no program starts."""

from __future__ import annotations

import dataclasses
import shutil
from pathlib import Path
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.api import inventory, profile, runtimes, settings
from backend.core.notices import CLOUD_KEY_UNAVAILABLE
from backend.manager import registry as registry_module
from backend.manager.context import build_context
from backend.manager.hardware import Hardware
from backend.manager.platforms import MACOS_ARM64
from backend.manager.profiles import ProfileId
from backend.manager.secrets import UnavailableSecretStore
from backend.manager.switch import download_missing, requirements

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
    assert reply.json()["detail"] == CLOUD_KEY_UNAVAILABLE().message
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


def test_the_profile_page_marks_the_missing_program_the_script_builds_and_only_that_one(
    client: Any,
) -> None:
    body = client.get("/api/profile").json()
    active = next(p for p in body["profiles"] if p["active"])
    flags = {m["id"]: (m["local_build"], m["size_bytes"]) for m in active["missing"]}

    assert flags[WHISPER] == (True, 0)
    assert all(not built for asset, (built, _) in flags.items() if asset != WHISPER)
    assert all(size > 0 for asset, (_, size) in flags.items() if asset != WHISPER)
    assert active["download_bytes"] == sum(size for _, size in flags.values())


def test_the_inventory_marks_the_program_the_script_builds_and_only_that_one(
    client: Any,
) -> None:
    rows = {e["id"]: e for e in client.get("/api/inventory").json()["assets"]}

    assert rows[WHISPER]["local_build"] is True
    assert (rows[WHISPER]["state"], rows[WHISPER]["size_bytes"]) == ("not_installed", 0)
    assert [i for i, e in rows.items() if e["local_build"]] == [WHISPER]
    assert rows["llama.cpp-b12068-macos-metal"]["size_bytes"] > 0


class RecordingRunner:
    def __init__(self) -> None:
        self.plans: list[Any] = []

    def submit(self, plan: Any) -> str:
        self.plans.append(plan)
        return plan.asset_id


def test_fetching_what_a_mac_profile_misses_skips_the_runtime_built_on_the_machine(
    client: Any,
) -> None:
    missing = {m.id for m in requirements(client.ctx, ProfileId.METAL_32GB).missing}
    assert WHISPER in missing
    runner = RecordingRunner()
    ctx: Any = dataclasses.replace(client.ctx, runner=runner)

    started = download_missing(ctx, ProfileId.METAL_32GB)

    submitted = {plan.asset_id for plan in runner.plans}
    assert started == [plan.asset_id for plan in runner.plans]
    assert WHISPER not in submitted
    assert "llama.cpp-b12068-macos-metal" in submitted
    assert submitted == missing - {WHISPER}


def fake_which(monkeypatch: pytest.MonkeyPatch, on_path: Path | str | None) -> None:
    """`shutil.which` finds `on_path` on PATH and nothing in the Homebrew folders."""

    def which(name: str, mode: int = 0, path: str | None = None) -> str | None:
        return str(on_path) if on_path is not None and path is None else None

    monkeypatch.setattr(shutil, "which", which)


def test_a_whisper_found_on_path_is_listed_with_where_and_the_delete_leaves_it_alone(
    client: Any, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    program = tmp_path / "homebrew" / "whisper-cli"
    program.parent.mkdir()
    program.write_bytes(b"x")
    fake_which(monkeypatch, program)

    row = {e["id"]: e for e in client.get("/api/inventory").json()["assets"]}[WHISPER]
    plain = client.delete(f"/api/runtimes/{WHISPER}")
    forced = client.delete(f"/api/runtimes/{WHISPER}", params={"force": True, "reason": "x" * 20})

    assert (row["state"], row["found_outside_runtimes"], row["path"]) == (
        "installed",
        True,
        str(program),
    )
    for reply in (plain, forced):
        assert reply.status_code == 400
        assert reply.json()["detail"]["can_force"] is False
        assert "The app didn't delete whisper-cli" in reply.json()["detail"]["message"]
        assert str(program.parent) in reply.json()["detail"]["message"]
    assert program.read_bytes() == b"x"


def test_a_whisper_in_the_runtimes_folder_is_not_marked_and_the_delete_removes_it(
    client: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    folder = client.ctx.storage.runtime_dir(MAC.runtimes[WHISPER])
    (folder).mkdir(parents=True)
    (folder / "whisper-cli").write_bytes(b"x")
    fake_which(monkeypatch, "/opt/homebrew/bin/whisper-cli")

    row = {e["id"]: e for e in client.get("/api/inventory").json()["assets"]}[WHISPER]
    reply = client.delete(f"/api/runtimes/{WHISPER}", params={"force": True, "reason": "x" * 20})

    assert (row["state"], row["found_outside_runtimes"]) == ("installed", False)
    assert reply.status_code == 204
    assert not folder.exists()


def test_a_missing_whisper_is_not_marked_as_found_elsewhere(
    client: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake_which(monkeypatch, None)

    row = {e["id"]: e for e in client.get("/api/inventory").json()["assets"]}[WHISPER]

    assert (row["state"], row["found_outside_runtimes"]) == ("not_installed", False)
