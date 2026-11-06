from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from download_support import FAST, Origin, blob, make_zip, serve, sha, wait_until
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.api import downloads, models, runtimes
from backend.manager import registry
from backend.manager.context import build_context
from backend.manager.hardware import Hardware

ORIGIN = "https://origin.test/"
MODEL = blob(2 * 1024 * 1024, seed=5)
AUX = blob(300_000, seed=6)
BIG = blob(8 * 1024 * 1024, seed=7)


def raw_registry(rt_zip: bytes, addon_zip: bytes) -> dict[str, Any]:
    def model(mid: str, data: bytes, needs: list[str]) -> dict[str, Any]:
        return {
            "id": mid, "kind": "asr", "engine": "e", "version": "1", "url": f"{ORIGIN}{mid}.bin",
            "file": f"{mid}.bin", "sha256": sha(data), "size_bytes": len(data), "license": "MIT",
            "license_url": "https://l.test/x", "vram_mib": None, "params_b": None, "needs": needs,
        }  # fmt: skip

    def runtime(rid: str, data: bytes, exe: str | None, needs: list[str]) -> dict[str, Any]:
        return {
            "id": rid, "engine": "e", "version": "1", "platform": "win-x64", "backend": "cpu",
            "url": f"{ORIGIN}{rid}.zip", "file": f"{rid}.zip", "sha256": sha(data),
            "size_bytes": len(data), "license": "MIT", "license_url": "https://l.test/x",
            "executable": exe, "min_driver": None,
            "ascii_paths_only": False, "needs": needs,
        }  # fmt: skip

    return {
        "schema_version": 1,
        "models": [model("main", MODEL, ["aux"]), model("aux", AUX, []), model("big", BIG, [])],
        "runtimes": [
            runtime("rt", rt_zip, "bin/run.exe", ["addon"]),
            runtime("addon", addon_zip, None, []),
        ],
    }


class Rig:
    def __init__(self, tmp_path: Path, origin: Origin) -> None:
        self.data = tmp_path / "data"
        rt = make_zip(tmp_path / "rt.zip", {"bin/run.exe": b"MZ"})
        addon = make_zip(tmp_path / "addon.zip", {"cuda.dll": b"dll"})
        origin.files.update(
            {
                "/main.bin": MODEL,
                "/aux.bin": AUX,
                "/big.bin": BIG,
                "/rt.zip": rt,
                "/addon.zip": addon,
            }
        )
        self.raw = raw_registry(rt, addon)
        self.origin = origin
        self.start()
        self.client.put("/api/storage", json={"mirrors": {ORIGIN: origin.url("/")}})

    def start(self, hardware: Hardware | None = None, shipped: bool = False) -> None:
        none = Hardware(None, None, None, None, None)
        ctx = build_context(
            self.data,
            registry.load() if shipped else registry.parse(self.raw),
            policy=FAST,
            detect_hardware=lambda: hardware or none,
        )
        app = FastAPI()
        app.state.manager = ctx
        for module in (downloads, models, runtimes):
            app.include_router(module.router)
        self.client: Any = TestClient(app)

    def entry(self, kind: str, asset_id: str) -> dict[str, Any]:
        listing: dict[str, Any] = self.client.get("/api/registry").json()
        return next(e for e in listing[kind] if e["id"] == asset_id)

    def finish(self, job: dict[str, Any]) -> dict[str, Any]:
        def done() -> bool:
            return self.client.get(f"/api/downloads/{job['id']}").json()["state"] in (
                "done",
                "failed",
                "cancelled",
            )

        wait_until(done, 20)
        return self.client.get(f"/api/downloads/{job['id']}").json()


@pytest.fixture
def rig(tmp_path: Path):
    with serve() as origin:
        yield Rig(tmp_path, origin)


def test_nothing_is_installed_at_first(rig: Rig) -> None:
    listing = rig.client.get("/api/registry").json()

    assert {m["state"] for m in listing["models"]} == {"not_installed"}
    assert {r["state"] for r in listing["runtimes"]} == {"not_installed", None}


def test_download_then_delete_a_model_through_the_api(rig: Rig) -> None:
    job = rig.client.post("/api/models/main/download").json()
    final = rig.finish(job)
    entry = rig.entry("models", "main")

    assert (final["state"], final["outcome"]) == ("done", "installed")
    assert entry["state"] == "installed"
    assert Path(entry["path"]).read_bytes() == MODEL
    assert (rig.data / "models" / "aux" / "aux.bin").read_bytes() == AUX

    assert rig.client.delete("/api/models/main").status_code == 204
    assert rig.entry("models", "main")["state"] == "not_installed"
    assert not Path(entry["path"]).exists()


def test_a_second_download_of_the_same_model_reports_it_already_exists(rig: Rig) -> None:
    rig.finish(rig.client.post("/api/models/aux/download").json())
    before = len(rig.origin.requests)

    again = rig.client.post("/api/models/aux/download").json()

    assert (again["state"], again["outcome"]) == ("done", "already_present")
    assert len(rig.origin.requests) == before


def test_downloads_go_to_the_configured_mirror(rig: Rig) -> None:
    rig.client.put("/api/storage", json={"mirrors": {ORIGIN: rig.origin.url("/other/")}})
    missed = rig.finish(rig.client.post("/api/models/aux/download").json())
    rig.client.put("/api/storage", json={"mirrors": {ORIGIN: rig.origin.url("/")}})
    fixed = rig.finish(rig.client.post("/api/models/aux/download").json())

    assert missed["failure"]["kind"] == "http"
    assert fixed["state"] == "done"
    assert [p for p, _ in rig.origin.requests] == ["/other/aux.bin", "/aux.bin"]


def test_a_runtime_installs_with_its_add_on_into_one_folder(rig: Rig) -> None:
    final = rig.finish(rig.client.post("/api/runtimes/rt/install").json())
    entry = rig.entry("runtimes", "rt")

    assert final["state"] == "done"
    assert entry["state"] == "installed"
    exe = Path(entry["executable_path"])
    assert exe.read_bytes() == b"MZ"
    assert (exe.parent / ".." / "cuda.dll").resolve().read_bytes() == b"dll"
    assert not list((rig.data / "runtimes" / "_archives").iterdir())

    assert rig.client.delete("/api/runtimes/rt").status_code == 204
    assert rig.entry("runtimes", "rt")["state"] == "not_installed"


def test_an_add_on_cannot_be_installed_on_its_own(rig: Rig) -> None:
    assert rig.client.post("/api/runtimes/addon/install").status_code == 400
    assert rig.entry("runtimes", "addon")["installable"] is False


def test_unknown_ids_are_404(rig: Rig) -> None:
    assert rig.client.post("/api/models/nope/download").status_code == 404
    assert rig.client.delete("/api/models/nope").status_code == 404
    assert rig.client.post("/api/runtimes/nope/install").status_code == 404
    assert rig.client.get("/api/downloads/nope").status_code == 404
    assert rig.client.post("/api/downloads/nope/cancel").status_code == 404


def test_cancel_through_the_api_leaves_a_part_file_and_a_partial_state(rig: Rig) -> None:
    rig.origin.pause_per_piece = 0.02
    job = rig.client.post("/api/models/big/download").json()
    wait_until(lambda: rig.client.get(f"/api/downloads/{job['id']}").json()["bytes_done"] > 0)

    assert rig.client.delete("/api/models/big").status_code == 409
    rig.client.post(f"/api/downloads/{job['id']}/cancel")
    final = rig.finish(job)

    assert final["state"] == "cancelled"
    assert rig.entry("models", "big")["state"] == "partial"
    assert [p.name for p in (rig.data / "models" / "big").iterdir()] == ["big.bin.part"]


def test_a_wrong_registry_hash_is_refused_and_the_file_deleted(rig: Rig) -> None:
    rig.raw["models"][1]["sha256"] = sha(b"other")
    rig.start()

    final = rig.finish(rig.client.post("/api/models/aux/download").json())

    assert final["failure"]["kind"] == "hash_mismatch"
    assert rig.entry("models", "aux")["state"] == "not_installed"
    assert list((rig.data / "models").rglob("*")) == [rig.data / "models" / "aux"]


def test_a_custom_models_folder_survives_a_restart(rig: Rig, tmp_path: Path) -> None:
    elsewhere = tmp_path / "elsewhere" / "ai-models"
    stored = rig.client.put("/api/storage", json={"models_dir": str(elsewhere)})
    rig.finish(rig.client.post("/api/models/aux/download").json())

    rig.start()
    entry = rig.entry("models", "aux")

    assert stored.json()["models_dir"] == str(elsewhere)
    assert (elsewhere / "aux" / "aux.bin").read_bytes() == AUX
    assert entry["state"] == "installed"
    assert entry["path"] == str(elsewhere / "aux" / "aux.bin")
    assert not (rig.data / "models").exists()


@pytest.mark.parametrize(
    "body",
    [
        {"models_dir": "relative/path"},
        {"mirrors": {"http://plain.example/": "https://x/"}},
        {"mirrors": {ORIGIN: "ftp://x/"}},
    ],
)
def test_bad_storage_settings_are_refused_and_not_saved(rig: Rig, body: dict[str, Any]) -> None:
    before = rig.client.get("/api/storage").json()

    assert rig.client.put("/api/storage", json=body).status_code == 422
    assert rig.client.get("/api/storage").json() == before


def test_the_required_assets_follow_the_detected_profile_and_driver(rig: Rig) -> None:
    rig.start(Hardware("NVIDIA GeForce RTX 4090", 24564, "596.36", 65536, 500000), shipped=True)
    full = rig.client.get("/api/assets/required").json()
    rig.start(Hardware("NVIDIA GeForce RTX 4090", 24564, "560.94", 65536, 500000), shipped=True)
    old = rig.client.get("/api/assets/required").json()
    rig.start(shipped=True)
    cpu = rig.client.get("/api/assets/required").json()

    assert full["profile"] == "gpu-24gb"
    assert "qwen3-asr-1.7b-q8_0" in full["models"]
    assert "qwen3-asr-1.7b-q8_0" not in old["models"]
    assert cpu["profile"] == "cpu"
    assert cpu["runtimes"] == ["whispercpp-b5454-win-cpu", "llama.cpp-b12068-win-cpu"]
