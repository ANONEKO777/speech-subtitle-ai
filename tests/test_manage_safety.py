"""Failure paths of the manager: nothing the user already has may be lost or leaked."""

from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path
from typing import Any

import pytest
from manage_support import FakeServer, Rig
from test_manage import (
    SILERO_GGML,
    VAD_MODEL,
    _wait_move,  # pyright: ignore[reportPrivateUsage]
)

from backend.manager import secrets
from backend.manager.profiles import WHISPER_CPU_RUNTIME
from backend.manager.secrets import LLM_KEY, DpapiSecretStore


def test_a_failed_redownload_of_a_model_keeps_the_working_file(rig: Rig) -> None:
    rig.install("models", SILERO_GGML)
    path = Path(rig.asset(SILERO_GGML)["path"])
    good = path.read_bytes()
    del rig.origin.files[f"/{SILERO_GGML}"]

    rig.client.post(f"/api/inventory/{SILERO_GGML}/redownload")
    rig.wait_jobs()

    assert path.read_bytes() == good
    asset = rig.asset(SILERO_GGML)
    assert asset["installed"] and asset["sha256_state"] == "verified"
    assert rig.client.get("/api/downloads").json()[-1]["state"] == "failed"


def test_a_redownload_that_fails_its_sha256_keeps_the_working_file(rig: Rig) -> None:
    rig.install("models", SILERO_GGML)
    path = Path(rig.asset(SILERO_GGML)["path"])
    good = path.read_bytes()
    rig.origin.files[f"/{SILERO_GGML}"] = bytes(len(good))

    rig.client.post(f"/api/inventory/{SILERO_GGML}/redownload")
    rig.wait_jobs()

    assert path.read_bytes() == good and rig.asset(SILERO_GGML)["installed"]
    assert rig.client.get("/api/downloads").json()[-1]["failure"]["kind"] == "hash_mismatch"
    assert not list(path.parent.glob("*.new*"))


def test_a_failed_redownload_of_a_runtime_keeps_the_working_folder(rig: Rig) -> None:
    rig.install("runtimes", WHISPER_CPU_RUNTIME)
    folder = Path(rig.asset(WHISPER_CPU_RUNTIME)["path"])
    marker = folder / "marker.txt"
    marker.write_text("working")
    del rig.origin.files[f"/{WHISPER_CPU_RUNTIME}.zip"]

    rig.client.post(f"/api/inventory/{WHISPER_CPU_RUNTIME}/redownload")
    rig.wait_jobs()

    assert marker.read_text() == "working"
    assert rig.asset(WHISPER_CPU_RUNTIME)["installed"]
    assert rig.client.get("/api/downloads").json()[-1]["state"] == "failed"


def _hold(rig: Rig, target: Path, model_id: str) -> Path:
    source = rig.ctx.storage.model_file(rig.registry.models[model_id])
    dest = target / model_id / source.name
    dest.parent.mkdir(parents=True, exist_ok=True)
    return dest


def test_a_move_resumes_after_a_crash_left_copies_in_the_target(rig: Rig, tmp_path: Path) -> None:
    rig.install("models", SILERO_GGML)
    rig.install("models", VAD_MODEL)
    old = rig.ctx.storage.models_root
    target = tmp_path / "target"
    whole = _hold(rig, target, SILERO_GGML)
    shutil.copyfile(rig.ctx.storage.model_file(rig.registry.models[SILERO_GGML]), whole)
    half = _hold(rig, target, VAD_MODEL)
    half.with_name(half.name + ".part").write_bytes(b"cut off")

    started = rig.client.post("/api/storage/move", json={"target": str(target)})
    _wait_move(rig)
    status = rig.client.get("/api/storage/move").json()

    assert started.status_code == 202 and status["state"] == "done", status
    assert rig.ctx.storage.models_root == target
    assert rig.asset(SILERO_GGML)["installed"] and rig.asset(VAD_MODEL)["installed"]
    assert not (old / SILERO_GGML).exists() and not list(target.rglob("*.part"))


def test_a_move_leaves_foreign_content_alone(rig: Rig, tmp_path: Path) -> None:
    rig.install("models", SILERO_GGML)
    old = rig.ctx.storage.models_root
    source = rig.ctx.storage.model_file(rig.registry.models[SILERO_GGML])
    target = tmp_path / "target"
    foreign = _hold(rig, target, SILERO_GGML)
    foreign.write_bytes(bytes(source.stat().st_size))

    rig.client.post("/api/storage/move", json={"target": str(target)})
    _wait_move(rig)
    status = rig.client.get("/api/storage/move").json()

    assert status["state"] == "failed" and "other content" in status["error"]
    assert foreign.read_bytes() == bytes(source.stat().st_size)
    assert source.is_file() and rig.ctx.storage.models_root == old


@pytest.mark.skipif(sys.platform != "win32", reason="the key store is Windows DPAPI")
def test_the_key_file_is_flushed_to_disk_before_it_replaces_the_old_one(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    events: list[str] = []
    fsync, replace = os.fsync, os.replace

    def flushed(fd: int) -> None:
        events.append("fsync")
        fsync(fd)

    def swapped(src: Any, dst: Any) -> None:
        events.append("replace")
        replace(src, dst)

    monkeypatch.setattr(secrets.os, "fsync", flushed)
    monkeypatch.setattr(secrets.os, "replace", swapped)
    store = DpapiSecretStore(tmp_path)

    store.set(LLM_KEY, "sk-test")

    assert events == ["fsync", "replace"] and store.get(LLM_KEY) == "sk-test"


def _save_cloud(rig: Rig, url: str) -> None:
    llm = {
        "source": "cloud",
        "cloud_url": url,
        "cloud_model": "gpt-x",
        "cloud_consent": True,
        "api_key": "good-key",
    }
    assert rig.client.put("/api/settings", json={"llm": llm}).status_code == 200


def _test_cloud(rig: Rig, url: str, key: str | None = None) -> dict[str, Any]:
    llm: dict[str, Any] = {"source": "cloud", "cloud_url": url, "cloud_model": "gpt-x"}
    if key is not None:
        llm["api_key"] = key
    return rig.client.post("/api/llm/test", json={"llm": llm}).json()


def test_the_saved_key_goes_only_to_the_saved_endpoint(
    rig: Rig,
    fake_server: FakeServer,
) -> None:
    saved = f"{fake_server.url}/v1"
    _save_cloud(rig, saved)
    fake_server.auth.clear()

    same = _test_cloud(rig, saved)
    assert same["ok"] is True and fake_server.auth == ["Bearer good-key"]

    fake_server.auth.clear()
    typo = _test_cloud(rig, f"{fake_server.url}/v2")
    assert typo["ok"] is False and "no API key to test with" in typo["detail"]
    assert fake_server.auth == []

    other = FakeServer()
    try:
        _test_cloud(rig, f"{other.url}/v1")
        assert other.auth == []
        carried = _test_cloud(rig, f"{other.url}/v1", key="good-key")
        assert carried["ok"] is True and other.auth == ["Bearer good-key"]
    finally:
        other.close()
