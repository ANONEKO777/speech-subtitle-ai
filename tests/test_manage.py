from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import pytest
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient
from manage_support import (
    GPU_4090,
    NO_GPU,
    FakeServer,
    Rig,
    always_ok,
    cuda_broken,
)

from backend.api import inventory, profile, runtimes, settings
from backend.api.auth import GuardConfig
from backend.core.jobs import JobOptions
from backend.core.pipeline import Ports, Settings
from backend.main import AppConfig, create_app
from backend.manager import registry
from backend.manager.active import runs_on_cpu
from backend.manager.profiles import (
    LLAMA_CPU_RUNTIME,
    LLAMA_RUNTIME,
    QWEN3_8B,
    VAD_MODEL,
    WHISPER_CPU_RUNTIME,
    WHISPER_RUNTIME,
    WHISPER_TURBO,
)
from backend.manager.registry import Registry
from backend.manager.secrets import DpapiSecretStore
from backend.manager.selftest import FAULT_ENV, ProbeFailed, real_probe
from backend.manager.settings import AppSettings, SettingsStore, parse_settings
from backend.manager.updates import UpdateError

QWEN3_ASR = "qwen3-asr-1.7b-q8_0"
SILERO_GGML = "silero-vad-ggml-v6.2.0"


def inventory_of(rig: Rig) -> dict[str, dict[str, Any]]:
    listing = rig.client.get("/api/inventory").json()
    return {a["id"]: a for a in listing["assets"]}


def test_inventory_lists_every_registry_asset_and_says_what_is_installed(rig: Rig) -> None:
    before = inventory_of(rig)
    rig.install("models", WHISPER_TURBO)
    after = inventory_of(rig)
    turbo = after[WHISPER_TURBO]

    assert set(before) == {*rig.registry.models, *rig.registry.runtimes}
    assert not any(a["installed"] for a in before.values())
    assert turbo["installed"] and turbo["state"] == "installed"
    assert turbo["size_on_disk"] == turbo["size_bytes"]
    assert Path(turbo["path"]).is_file()
    assert (turbo["sha256_state"], turbo["sha256_scope"]) == ("verified", "file")
    assert turbo["installed_version"] == turbo["version"]
    assert set(turbo["used_by_profiles"]) == {"gpu-24gb", "gpu-8gb", "cpu"}
    assert turbo["in_active_profile"] is True
    assert after[QWEN3_ASR]["used_by_profiles"] == ["gpu-24gb"]


def test_inventory_names_dependents_and_runtime_sizes(rig: Rig) -> None:
    rig.install("models", QWEN3_ASR)
    rig.install("runtimes", LLAMA_RUNTIME)
    found = inventory_of(rig)

    assert found[SILERO_GGML]["dependents"] == [{"id": QWEN3_ASR, "installed": True}]
    llama = found[LLAMA_RUNTIME]
    assert llama["size_on_disk"] > 0 and llama["sha256_scope"] == "archive_at_install"
    assert llama["sha256_state"] == "verified"
    addon = found["cudart-llama-b12068-win-cuda12.4"]
    assert addon["installed"] is True and addon["size_on_disk"] is None


def test_deleting_what_the_active_profile_needs_is_refused_until_forced_with_a_reason(
    rig: Rig,
) -> None:
    rig.install("models", WHISPER_TURBO)
    path = Path(rig.asset(WHISPER_TURBO)["path"])

    refused = rig.client.delete(f"/api/models/{WHISPER_TURBO}")
    no_reason = rig.client.delete(f"/api/models/{WHISPER_TURBO}?force=true")
    short = rig.client.delete(f"/api/models/{WHISPER_TURBO}?force=true&reason=no")

    assert refused.status_code == 409
    assert refused.json()["detail"]["blockers"] == ["the active profile needs it"]
    assert refused.json()["detail"]["can_force"] is True
    assert (no_reason.status_code, short.status_code) == (422, 422)
    assert path.is_file()

    forced = rig.client.delete(
        f"/api/models/{WHISPER_TURBO}?force=true&reason=replacing it with a copy"
    )
    assert forced.status_code == 204 and not path.exists()


def test_deleting_a_model_another_installed_asset_needs_is_refused(rig: Rig) -> None:
    rig.set_profile("cpu")
    rig.install("models", QWEN3_ASR)

    refused = rig.client.delete(f"/api/models/{SILERO_GGML}")
    assert refused.status_code == 409
    assert f"{QWEN3_ASR} is installed and needs it" in refused.json()["detail"]["blockers"]

    assert rig.client.delete(f"/api/models/{QWEN3_ASR}").status_code == 204
    assert rig.client.delete(f"/api/models/{SILERO_GGML}").status_code == 204


def test_an_unused_asset_deletes_and_leaves_no_record_or_files(rig: Rig) -> None:
    rig.install("runtimes", WHISPER_RUNTIME)
    rig.set_profile("cpu")
    folder = Path(rig.asset(WHISPER_RUNTIME)["path"])
    assert folder.is_dir()

    assert rig.client.delete(f"/api/runtimes/{WHISPER_RUNTIME}").status_code == 204
    assert not folder.exists()
    assert rig.ctx.manifest.get(WHISPER_RUNTIME) is None
    assert rig.asset(WHISPER_RUNTIME)["state"] == "not_installed"


def test_nothing_changes_while_a_job_runs(rig: Rig) -> None:
    rig.install("models", SILERO_GGML)
    rig.jobs.running = True

    assert rig.client.delete(f"/api/models/{SILERO_GGML}").status_code == 409
    assert rig.client.post(f"/api/inventory/{SILERO_GGML}/repair").status_code == 409
    assert rig.client.post(f"/api/inventory/{SILERO_GGML}/redownload").status_code == 409
    assert rig.client.post("/api/runtimes/selftest").status_code == 409
    assert rig.asset(SILERO_GGML)["installed"] is True


def test_verify_finds_a_changed_file_and_repair_fetches_it_again(rig: Rig) -> None:
    rig.install("models", SILERO_GGML)
    path = Path(rig.asset(SILERO_GGML)["path"])
    good = path.read_bytes()
    path.write_bytes(b"x" + good[1:])

    assert rig.asset(SILERO_GGML)["sha256_state"] == "unchecked"
    bad = rig.client.post(f"/api/inventory/{SILERO_GGML}/verify").json()
    assert bad["sha256_state"] == "corrupt"

    fixed = rig.client.post(f"/api/inventory/{SILERO_GGML}/repair").json()
    rig.wait_jobs()

    assert fixed["action"] == "refetch" and "SHA256" in fixed["reason"]
    assert path.read_bytes() == good
    assert rig.asset(SILERO_GGML)["sha256_state"] == "verified"


def test_repair_of_a_healthy_model_does_nothing_and_a_missing_one_is_fetched(rig: Rig) -> None:
    rig.install("models", SILERO_GGML)
    path = Path(rig.asset(SILERO_GGML)["path"])
    before = len(rig.origin.requests)

    healthy = rig.client.post(f"/api/inventory/{SILERO_GGML}/repair").json()
    assert healthy["action"] == "none" and len(rig.origin.requests) == before
    assert healthy["asset"]["sha256_state"] == "verified"

    path.unlink()
    missing = rig.client.post(f"/api/inventory/{SILERO_GGML}/repair").json()
    rig.wait_jobs()
    assert missing["action"] == "refetch" and path.is_file()


def test_a_file_that_was_already_there_is_unchecked_until_verified(rig: Rig) -> None:
    path = rig.ctx.storage.model_file(rig.registry.models[SILERO_GGML])
    path.parent.mkdir(parents=True)
    path.write_bytes(rig.origin.files[f"/{SILERO_GGML}"])

    assert rig.asset(SILERO_GGML)["sha256_state"] == "unchecked"
    assert rig.asset(SILERO_GGML)["installed_version"] is None
    verified = rig.client.post(f"/api/inventory/{SILERO_GGML}/verify").json()
    assert verified["sha256_state"] == "verified"
    assert verified["installed_version"] == verified["version"]


def test_redownload_replaces_a_runtime_folder(rig: Rig) -> None:
    rig.install("runtimes", WHISPER_CPU_RUNTIME)
    stray = Path(rig.asset(WHISPER_CPU_RUNTIME)["path"]) / "stray.txt"
    stray.write_text("left over")

    assert rig.client.post(f"/api/inventory/{WHISPER_CPU_RUNTIME}/redownload").status_code == 200
    rig.wait_jobs()

    assert not stray.exists() and rig.asset(WHISPER_CPU_RUNTIME)["installed"]


def test_updates_say_no_remote_is_configured_and_never_invent_one(rig: Rig) -> None:
    rig.install("models", SILERO_GGML)
    report = rig.client.post("/api/updates/check").json()
    item = next(i for i in report["items"] if i["id"] == SILERO_GGML)
    gone = next(i for i in report["items"] if i["id"] == QWEN3_8B)

    version = rig.registry.models[SILERO_GGML].version
    assert item["status"] == "current"
    assert item["message"] == f"registry version {version} installed, no remote configured"
    assert report["remote_url"] is None and gone["status"] == "not_installed"


def test_an_older_install_is_an_update_and_update_fetches_the_registry_version(
    rig: Rig,
) -> None:
    rig.install("models", SILERO_GGML)
    record = rig.ctx.manifest.get(SILERO_GGML)
    assert record is not None
    rig.ctx.manifest.put(SILERO_GGML, type(record)("old", "0" * 64, None, None, 1, True))

    report = rig.client.post("/api/updates/check").json()
    item = next(i for i in report["items"] if i["id"] == SILERO_GGML)
    assert item["status"] == "update_available" and item["installable"] is True

    assert rig.client.post(f"/api/inventory/{SILERO_GGML}/update").status_code == 200
    rig.wait_jobs()
    again = rig.client.post(f"/api/inventory/{SILERO_GGML}/update")
    assert again.status_code == 409
    assert rig.asset(SILERO_GGML)["installed_version"] == rig.registry.models[SILERO_GGML].version


def test_a_remote_registry_newer_than_the_bundled_one_asks_for_an_app_update(rig: Rig) -> None:
    rig.install("models", SILERO_GGML)
    raw = _raw(rig.registry)
    next(m for m in raw["models"] if m["id"] == SILERO_GGML).update(version="v9", sha256="a" * 64)
    rig.remote = registry.parse(raw)
    rig.client.put("/api/settings", json={"registry_url": "https://example.test/registry.json"})

    report = rig.client.post("/api/updates/check").json()
    item = next(i for i in report["items"] if i["id"] == SILERO_GGML)

    assert item["status"] == "update_available" and item["installable"] is False
    assert item["remote_version"] == "v9" and "update the app" in item["message"]
    assert rig.client.post(f"/api/inventory/{SILERO_GGML}/update").status_code == 409


def test_a_remote_registry_that_cannot_be_read_is_a_502_naming_the_url(rig: Rig) -> None:
    url = "https://example.test/registry.json"
    rig.client.put("/api/settings", json={"registry_url": url})
    rig.remote_error = UpdateError(url, "cannot connect (timed out)")

    reply = rig.client.post("/api/updates/check")

    assert reply.status_code == 502 and reply.json()["detail"]["url"] == url


def _raw(reg: Registry) -> dict[str, Any]:
    from dataclasses import asdict

    return {
        "schema_version": 1,
        "models": [
            {**asdict(m), "kind": m.kind.value, "needs": list(m.needs)} for m in reg.models.values()
        ],
        "runtimes": [{**asdict(r), "needs": list(r.needs)} for r in reg.runtimes.values()],
    }


def test_changing_the_models_folder_warns_and_moves_nothing(rig: Rig, tmp_path: Path) -> None:
    rig.install("models", SILERO_GGML)
    old = rig.ctx.storage.models_root
    new = tmp_path / "elsewhere"

    reply = rig.client.put("/api/storage", json={"models_dir": str(new)}).json()

    assert "not moved" in reply["warnings"][0] and str(old) in reply["warnings"][0]
    assert (old / SILERO_GGML).is_dir() and not new.exists() or not any(new.iterdir())
    assert rig.asset(SILERO_GGML)["installed"] is False


def test_the_explicit_move_relocates_the_models_and_switches_the_folder(
    rig: Rig, tmp_path: Path
) -> None:
    rig.install("models", SILERO_GGML)
    rig.install("models", VAD_MODEL)
    old = rig.ctx.storage.models_root
    target = tmp_path / "bigger-disk" / "models"

    started = rig.client.post("/api/storage/move", json={"target": str(target)})
    _wait_move(rig)
    status = rig.client.get("/api/storage/move").json()

    assert started.status_code == 202 and status["state"] == "done", status
    assert status["files_done"] == 2 and status["error"] is None
    assert rig.ctx.storage.models_root == target
    assert rig.asset(SILERO_GGML)["installed"] and not (old / SILERO_GGML).exists()
    assert rig.client.get("/api/inventory").json()["vad_model_path"] == str(
        target / VAD_MODEL / "silero_vad.onnx"
    )
    assert (target / VAD_MODEL / "silero_vad.onnx").read_bytes() == rig.origin.files[
        f"/{VAD_MODEL}"
    ]


def _wait_move(rig: Rig) -> None:
    from download_support import wait_until

    wait_until(lambda: rig.client.get("/api/storage/move").json()["state"] != "running", 10)


def test_a_move_that_fails_midway_leaves_the_old_folder_as_it_was(
    rig: Rig, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from backend.manager import storage_move

    rig.install("models", SILERO_GGML)
    rig.install("models", VAD_MODEL)
    old = rig.ctx.storage.models_root
    target = tmp_path / "target"
    calls = {"n": 0}
    real = storage_move.MoveRunner._transfer  # pyright: ignore[reportPrivateUsage]

    def flaky(self: Any, src: Path, dest: Path) -> None:
        calls["n"] += 1
        if calls["n"] == 2:
            raise OSError("disk unplugged")
        real(self, src, dest)

    monkeypatch.setattr(storage_move.MoveRunner, "_transfer", flaky)
    rig.client.post("/api/storage/move", json={"target": str(target)})
    _wait_move(rig)
    status = rig.client.get("/api/storage/move").json()

    assert status["state"] == "failed" and "disk unplugged" in status["error"]
    assert rig.ctx.storage.models_root == old
    assert rig.asset(SILERO_GGML)["installed"] and rig.asset(VAD_MODEL)["installed"]
    assert not list(target.rglob("*.*"))


def test_a_move_refuses_to_overwrite_and_to_nest(rig: Rig, tmp_path: Path) -> None:
    rig.install("models", SILERO_GGML)
    old = rig.ctx.storage.models_root

    assert (
        rig.client.post("/api/storage/move", json={"target": str(old / "inner")}).status_code == 409
    )
    other = tmp_path / "other"
    (other / SILERO_GGML).mkdir(parents=True)
    (other / SILERO_GGML / "ggml-silero-v6.2.0.bin").write_bytes(b"x")
    clash = rig.client.post("/api/storage/move", json={"target": str(other)})
    assert clash.status_code == 409 and SILERO_GGML in clash.json()["detail"]
    assert (old / SILERO_GGML).is_dir()


def test_the_hardware_route_keeps_its_fields_and_adds_the_recommendation(rig: Rig) -> None:
    reply = rig.client.get("/api/hardware").json()

    assert reply["gpu_name"] == GPU_4090.gpu_name and reply["vram_mib"] == 24564
    assert reply["recommended_profile"] == "gpu-24gb"
    assert "Profile:" in reply["recommendation"]


def test_the_profile_view_recommends_and_lists_what_each_profile_needs(rig: Rig) -> None:
    view = rig.client.get("/api/profile").json()
    by_id = {p["id"]: p for p in view["profiles"]}

    assert (view["active"]["id"], view["active"]["source"]) == ("gpu-24gb", "recommended")
    assert view["recommended"]["id"] == "gpu-24gb"
    assert by_id["gpu-24gb"]["recommended"] and by_id["gpu-24gb"]["active"]
    assert by_id["cpu"]["recommend_cloud"] and not by_id["gpu-8gb"]["recommend_cloud"]
    cpu_missing = {m["id"] for m in by_id["cpu"]["missing"]}
    assert {WHISPER_CPU_RUNTIME, LLAMA_CPU_RUNTIME, WHISPER_TURBO, QWEN3_8B} <= cpu_missing
    assert LLAMA_RUNTIME not in cpu_missing


def test_switching_to_cpu_lists_the_missing_assets_and_offers_the_download(rig: Rig) -> None:
    rig.install("models", WHISPER_TURBO)

    reply = rig.set_profile("cpu")
    missing = {m["id"] for p in reply["profiles"] if p["id"] == "cpu" for m in p["missing"]}

    assert reply["active"]["id"] == "cpu" and reply["active"]["source"] == "user"
    assert WHISPER_TURBO not in missing and WHISPER_CPU_RUNTIME in missing
    assert reply["download"] == "/api/profile/download"
    assert any("VRAM" not in w for w in reply["warnings"]) or reply["warnings"] == []

    assert rig.client.post("/api/profile/download").status_code == 202
    rig.wait_jobs()
    after = rig.client.get("/api/profile").json()
    assert next(p for p in after["profiles"] if p["id"] == "cpu")["missing"] == []


def test_a_chosen_profile_survives_a_restart_and_null_returns_to_the_recommendation(
    rig: Rig,
) -> None:
    rig.set_profile("gpu-8gb")
    rig.start(GPU_4090)
    assert rig.client.get("/api/profile").json()["active"]["id"] == "gpu-8gb"
    assert json.loads((rig.data / "settings.json").read_text())["profile"] == "gpu-8gb"

    assert rig.set_profile(None)["active"]["source"] == "recommended"
    assert rig.client.put("/api/profile", json={"profile": "tpu"}).status_code == 422


def test_choosing_a_gpu_profile_without_enough_vram_is_allowed_with_a_warning(rig: Rig) -> None:
    rig.start(NO_GPU)

    reply = rig.set_profile("gpu-24gb")

    assert reply["active"]["id"] == "gpu-24gb" and reply["recommended"]["id"] == "cpu"
    assert "no NVIDIA GPU" in reply["warnings"][0]


def test_the_pipeline_follows_the_active_profile_and_a_fallback(rig: Rig) -> None:
    def cpu() -> bool:
        return runs_on_cpu(rig.data, lambda: GPU_4090, rig.registry)

    assert cpu() is False
    rig.set_profile("cpu")
    assert cpu() is True
    rig.set_profile("gpu-8gb")
    assert cpu() is False


def test_the_self_test_passes_on_the_gpu(rig: Rig) -> None:
    rig.install_profile("gpu-24gb")

    report = rig.client.post("/api/runtimes/selftest").json()

    assert (report["ok"], report["device"], report["fallback"]) == (True, "cuda", None)
    assert [s["stage"] for s in report["stages"]] == ["asr", "llm"]
    assert rig.client.get("/api/runtimes/selftest").json()["at_ms"] == report["at_ms"]
    assert runs_on_cpu(rig.data, lambda: GPU_4090, rig.registry) is False


def test_a_failed_gpu_self_test_falls_back_to_the_cpu_and_says_why(rig: Rig) -> None:
    rig.install_profile("cpu")
    rig.install_profile("gpu-24gb")
    rig.probe = cuda_broken

    report = rig.client.post("/api/runtimes/selftest").json()

    assert (report["ok"], report["device"]) == (True, "cpu")
    reason = report["fallback"]["reason"]
    assert "GPU backend failed" in reason and "no kernel image" in reason
    assert "CPU backend is used instead" in reason
    assert all(s["device"] == "cpu" for s in report["stages"])
    assert runs_on_cpu(rig.data, lambda: GPU_4090, rig.registry) is True
    assert rig.client.get("/api/profile").json()["fallback"]["reason"] == reason

    rig.start(GPU_4090)
    assert runs_on_cpu(rig.data, lambda: GPU_4090, rig.registry) is True

    rig.probe = always_ok
    assert rig.client.post("/api/runtimes/selftest").json()["fallback"] is None
    assert runs_on_cpu(rig.data, lambda: GPU_4090, rig.registry) is False


def test_switching_profile_clears_a_recorded_fallback(rig: Rig) -> None:
    rig.install_profile("cpu")
    rig.install_profile("gpu-24gb")
    rig.probe = cuda_broken
    rig.client.post("/api/runtimes/selftest")

    rig.set_profile("gpu-24gb")

    assert rig.client.get("/api/runtimes/selftest").json() is None
    assert runs_on_cpu(rig.data, lambda: GPU_4090, rig.registry) is False


def test_when_the_cpu_runtime_is_missing_the_fallback_reports_failure(rig: Rig) -> None:
    rig.install_profile("gpu-24gb")
    rig.probe = cuda_broken

    report = rig.client.post("/api/runtimes/selftest").json()

    assert report["ok"] is False and report["fallback"] is None and report["device"] == "cuda"
    assert "GPU failed and the CPU runtime is not installed" in report["message"]
    assert f"Download {WHISPER_CPU_RUNTIME}" in report["message"]
    assert runs_on_cpu(rig.data, lambda: GPU_4090, rig.registry) is False


def test_a_missing_runtime_is_reported_as_not_installed_and_is_not_a_gpu_failure(rig: Rig) -> None:
    report = rig.client.post("/api/runtimes/selftest").json()

    assert report["ok"] is False and report["fallback"] is None
    assert all(not s["installed"] for s in report["stages"])
    assert "not installed" in report["message"]


def test_the_cuda_fault_switch_makes_the_real_probe_fail_without_touching_a_file(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from backend.manager.profiles import Device

    monkeypatch.setenv(FAULT_ENV, "1")
    with pytest.raises(ProbeFailed, match="simulated"):
        real_probe("asr", tmp_path / "none.exe", tmp_path / "none.bin", Device.CUDA, 1)
    with pytest.raises(ProbeFailed, match="cannot start"):
        real_probe("llm", tmp_path / "none.exe", tmp_path / "none.bin", Device.CPU, 1)


def put_llm(rig: Rig, **fields: Any) -> Any:
    return rig.client.put("/api/settings", json={"llm": fields})


def test_a_cloud_source_without_consent_is_refused_with_the_consent_text(rig: Rig) -> None:
    reply = put_llm(
        rig,
        source="cloud",
        cloud_url="https://api.example.test/v1",
        cloud_model="m",
        api_key="sk-1",
    )

    assert reply.status_code == 422
    assert "leaves this machine" in reply.json()["detail"]
    assert rig.client.get("/api/settings").json()["llm"]["source"] == "builtin"
    assert rig.secrets.get("llm_api_key") is None


def test_a_cloud_source_with_consent_saves_and_the_key_never_comes_back(rig: Rig) -> None:
    reply = put_llm(
        rig,
        source="cloud",
        cloud_url="https://api.example.test/v1",
        cloud_model="m",
        cloud_consent=True,
        api_key="sk-secret-123",
    )

    assert reply.status_code == 200
    assert reply.json()["llm"]["api_key_set"] is True
    assert "sk-secret-123" not in reply.text
    assert "sk-secret-123" not in rig.client.get("/api/settings").text
    assert "sk-secret-123" not in (rig.data / "settings.json").read_text()
    assert rig.secrets.get("llm_api_key") == "sk-secret-123"
    assert "leaves this machine" in reply.json()["cloud_consent_text"]

    keep = put_llm(
        rig,
        source="cloud",
        cloud_url="https://api.example.test/v1",
        cloud_model="m2",
        cloud_consent=True,
    )
    assert keep.status_code == 200 and rig.secrets.get("llm_api_key") == "sk-secret-123"
    put_llm(rig, source="builtin", api_key="")
    assert rig.secrets.get("llm_api_key") is None


def test_a_new_cloud_address_needs_its_own_key_and_the_old_key_stays_with_the_old_one(
    rig: Rig,
) -> None:
    cloud = {"source": "cloud", "cloud_model": "m", "cloud_consent": True}
    first = put_llm(rig, cloud_url="https://a.example.test/v1", api_key="sk-a", **cloud)
    assert first.status_code == 200

    moved = put_llm(rig, cloud_url="https://b.example.test/v1", **cloud)

    assert moved.status_code == 422 and "API key" in moved.json()["detail"]
    saved = rig.client.get("/api/settings").json()["llm"]
    assert saved["cloud_url"] == "https://a.example.test/v1" and saved["api_key_set"] is True
    assert rig.secrets.get("llm_api_key") == "sk-a"

    again = put_llm(rig, cloud_url="https://b.example.test/v1", api_key="sk-b", **cloud)
    assert again.status_code == 200 and rig.secrets.get("llm_api_key") == "sk-b"
    same = put_llm(rig, cloud_url="https://b.example.test/v1", **cloud)
    assert same.status_code == 200 and rig.secrets.get("llm_api_key") == "sk-b"


@pytest.mark.parametrize(
    "fields",
    [
        {
            "source": "cloud",
            "cloud_url": "https://a.test/v1",
            "cloud_model": "m",
            "cloud_consent": True,
        },
        {
            "source": "cloud",
            "cloud_url": "http://a.test/v1",
            "cloud_model": "m",
            "cloud_consent": True,
            "api_key": "k",
        },
        {
            "source": "cloud",
            "cloud_url": "",
            "cloud_model": "m",
            "cloud_consent": True,
            "api_key": "k",
        },
        {"source": "ollama", "ollama_url": "http://127.0.0.1:11434", "ollama_model": " "},
        {"source": "ollama", "ollama_url": "ftp://x", "ollama_model": "m"},
        {
            "source": "cloud",
            "cloud_url": "https://u:p@a.test/v1",
            "cloud_model": "m",
            "cloud_consent": True,
            "api_key": "k",
        },
    ],
)
def test_bad_llm_settings_are_refused_at_the_boundary(rig: Rig, fields: dict[str, Any]) -> None:
    assert put_llm(rig, **fields).status_code == 422
    assert rig.client.get("/api/settings").json()["llm"]["source"] == "builtin"


def test_an_ollama_source_is_saved_and_survives_a_restart(rig: Rig) -> None:
    put_llm(rig, source="ollama", ollama_url="http://127.0.0.1:11434/", ollama_model="qwen3:8b")
    rig.start(GPU_4090)

    llm = rig.client.get("/api/settings").json()["llm"]
    assert (llm["source"], llm["ollama_url"], llm["ollama_model"]) == (
        "ollama",
        "http://127.0.0.1:11434",
        "qwen3:8b",
    )
    assert not list(rig.data.glob("*.tmp"))


def test_testing_a_wrong_ollama_url_fails_and_names_the_url(rig: Rig) -> None:
    url = "http://127.0.0.1:9"
    reply = rig.client.post(
        "/api/llm/test", json={"llm": {"source": "ollama", "ollama_url": url, "ollama_model": "m"}}
    ).json()

    assert reply["ok"] is False and reply["url"] == f"{url}/api/tags"
    assert f"{url}/api/tags" in reply["detail"]
    assert "connection refused" in reply["detail"]


def test_testing_ollama_lists_models_and_notices_a_missing_one(
    rig: Rig, fake_server: FakeServer
) -> None:
    def test(model: str) -> dict[str, Any]:
        body = {"llm": {"source": "ollama", "ollama_url": fake_server.url, "ollama_model": model}}
        return rig.client.post("/api/llm/test", json=body).json()

    good = test("llama3")
    missing = test("nope")

    assert good["ok"] is True and "qwen3:8b" in good["models"]
    assert missing["ok"] is False and "'nope' is not installed" in missing["detail"]
    assert missing["url"] == f"{fake_server.url}/api/tags"


def test_testing_a_cloud_endpoint_uses_the_key_and_a_bad_key_is_explained_without_it(
    rig: Rig, fake_server: FakeServer
) -> None:
    def test(key: str | None) -> dict[str, Any]:
        llm: dict[str, Any] = {
            "source": "cloud",
            "cloud_url": f"{fake_server.url}/v1",
            "cloud_model": "gpt-x",
        }
        if key is not None:
            llm["api_key"] = key
        return rig.client.post("/api/llm/test", json={"llm": llm}).json()

    assert test("good-key")["ok"] is True
    bad = test("bad-key")
    assert bad["ok"] is False and "rejected the API key" in bad["detail"]
    assert "bad-key" not in json.dumps(bad) and bad["url"] == f"{fake_server.url}/v1/models"
    assert "no API key to test with" in test(None)["detail"]


def test_the_licenses_list_covers_every_registry_entry_with_a_name_and_a_url(rig: Rig) -> None:
    shipped = registry.load()
    listing = rig.client.get("/api/licenses").json()["licenses"]
    by_id = {e["id"]: e for e in listing}

    assert set(by_id) == {*shipped.models, *shipped.runtimes}
    for asset_id, entry in by_id.items():
        found = shipped.models.get(asset_id) or shipped.runtimes[asset_id]
        assert entry["license"] == found.license and entry["license_url"] == found.license_url
        assert entry["license_url"].startswith("https://") and entry["parts"]
    cuda = by_id[WHISPER_RUNTIME]["parts"]
    assert {p["id"] for p in cuda} == {"MIT", "Zlib", "LicenseRef-NVIDIA-CUDA-EULA"}


def test_the_settings_model_refuses_what_it_cannot_represent_and_reads_a_bad_file_safely(
    tmp_path: Path,
) -> None:
    with pytest.raises(ValueError, match="unexpected keys"):
        parse_settings({"llm": {"source": "builtin", "key": "x"}})
    with pytest.raises(ValueError, match="cloud_consent"):
        parse_settings(
            {"llm": {"source": "cloud", "cloud_url": "https://a.test", "cloud_model": "m"}}
        )
    with pytest.raises(ValueError, match="https"):
        AppSettings(registry_url="http://a.test/registry.json")
    (tmp_path / "settings.json").write_text("{not json", encoding="utf-8")

    store = SettingsStore(tmp_path)

    assert store.current == AppSettings() and store.problem is not None
    store.save(AppSettings())
    assert store.problem is None and json.loads((tmp_path / "settings.json").read_text())


@pytest.mark.skipif(sys.platform != "win32", reason="DPAPI is Windows only")
def test_the_api_key_is_encrypted_on_disk_with_dpapi(tmp_path: Path) -> None:
    store = DpapiSecretStore(tmp_path)

    store.set("llm_api_key", "sk-plain-text-key")

    assert store.get("llm_api_key") == "sk-plain-text-key"
    stored = next((tmp_path / "secrets").iterdir()).read_bytes()
    assert b"sk-plain-text-key" not in stored
    store.clear("llm_api_key")
    assert store.get("llm_api_key") is None


@pytest.mark.skipif(sys.platform != "win32", reason="DPAPI is Windows only")
def test_a_job_uses_the_llm_source_from_the_settings_unless_it_names_its_own(
    tmp_path: Path,
) -> None:
    from backend.main import _configured_llm  # pyright: ignore[reportPrivateUsage]

    assert _configured_llm(tmp_path) == (QWEN3_8B, None, "")
    store = SettingsStore(tmp_path)
    from backend.manager.settings import LlmSettings, LlmSource

    store.save(AppSettings(llm=LlmSettings(LlmSource.OLLAMA, ollama_model="qwen3:8b")))
    assert _configured_llm(tmp_path) == ("http://127.0.0.1:11434/v1", "qwen3:8b", "")
    DpapiSecretStore(tmp_path).set("llm_api_key", "k-1")
    cloud = LlmSettings(
        LlmSource.CLOUD, cloud_url="https://a.test/v1", cloud_model="m", cloud_consent=True
    )
    store.save(AppSettings(llm=cloud))
    assert _configured_llm(tmp_path) == ("https://a.test/v1", "m", "k-1")


def _no_resolver(options: JobOptions, folder: Path) -> tuple[Settings, Ports]:
    raise AssertionError("no job is started here")


NEW_PREFIXES = (
    "/api/inventory",
    "/api/profile",
    "/api/settings",
    "/api/llm",
    "/api/licenses",
    "/api/updates",
    "/api/storage/move",
    "/api/runtimes/selftest",
    "/api/hardware",
)


def test_every_new_route_needs_the_token(tmp_path: Path) -> None:
    guard = GuardConfig("t" * 43, frozenset({"testserver"}))
    app = create_app(AppConfig(tmp_path / "data", guard, _no_resolver))
    routes = [
        r
        for module in (inventory, profile, settings, runtimes)
        for r in module.router.routes
        if isinstance(r, APIRoute) and r.path.startswith(NEW_PREFIXES)
    ]
    client: Any = TestClient(app)
    with client:
        for route in routes:
            for method in route.methods or ():
                path = route.path.replace("{asset_id}", "x")
                bare = client.request(method, path, headers={"Authorization": ""})
                assert bare.status_code == 401, (method, path)
    assert len(routes) >= 16


def test_the_vad_model_path_is_the_registry_install_location(rig: Rig) -> None:
    listing = rig.client.get("/api/inventory").json()

    expected = rig.data / "models" / VAD_MODEL / "silero_vad.onnx"
    assert Path(listing["vad_model_path"]) == expected
    assert Path(rig.asset(VAD_MODEL)["path"]) == expected
