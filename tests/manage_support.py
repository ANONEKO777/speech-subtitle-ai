"""A rig for the settings, inventory, profile and self-test routes.

It rewrites the shipped registry so every real id (the profiles name them) points at a few
kilobytes served by a local HTTP server, then drives the real routers through `TestClient`."""

from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from download_support import FAST, Origin, blob, make_zip, sha, wait_until
from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.exceptions import HTTPException as StarletteHTTPException

from backend.api import downloads, inventory, models, profile, runtimes, settings
from backend.api.deps import locked_path_response, noticed_http_error
from backend.core.notices import Notice
from backend.manager import registry
from backend.manager.context import ManagerContext, build_context
from backend.manager.hardware import Hardware
from backend.manager.registry import REGISTRY_PATH, Registry
from backend.manager.secrets import MemorySecretStore
from backend.manager.selftest import Probe, ProbeFailed

ORIGIN = "https://origin.test/"
GPU_4090 = Hardware("NVIDIA GeForce RTX 4090", 24564, "596.36", 65536, 500000)
NO_GPU = Hardware(None, None, None, 32768, 500000)


class FakeJobs:
    def __init__(self) -> None:
        self.running = False

    def busy(self) -> bool:
        return self.running


def tiny_registry(tmp_path: Path, origin: Origin) -> Registry:
    raw: dict[str, Any] = json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
    for index, model in enumerate(raw["models"]):
        data = blob(3000 + index, seed=index + 1)
        origin.files[f"/{model['id']}"] = data
        model.update(url=f"{ORIGIN}{model['id']}", sha256=sha(data), size_bytes=len(data))
    raw["runtimes"] = [r for r in raw["runtimes"] if r["platform"] == "win-x64"]
    for index, runtime in enumerate(raw["runtimes"]):
        exe = runtime["executable"] or "addon.dll"
        archive = make_zip(tmp_path / f"{runtime['id']}.zip", {exe: b"MZ" + bytes([index])})
        origin.files[f"/{runtime['id']}.zip"] = archive
        runtime.update(url=f"{ORIGIN}{runtime['id']}.zip", sha256=sha(archive))
        runtime["size_bytes"] = len(archive)
    return registry.parse(raw)


def always_ok(stage: str, program: Path, model: Path, device: Any, timeout_s: float) -> str:
    return f"{stage} ok on {device.value}"


def cuda_broken(stage: str, program: Path, model: Path, device: Any, timeout_s: float) -> str:
    if device.value == "cuda":
        raise ProbeFailed("CUDA error: no kernel image is available")
    return f"{stage} ok on cpu"


class Rig:
    def __init__(self, tmp_path: Path, origin: Origin) -> None:
        self.tmp = tmp_path
        self.data = tmp_path / "data"
        self.origin = origin
        self.registry = tiny_registry(tmp_path, origin)
        self.jobs = FakeJobs()
        self.secrets = MemorySecretStore()
        self.remote: Registry | None = None
        self.remote_error: Exception | None = None
        self.probe: Probe = always_ok
        self.start(GPU_4090)
        self.client.put("/api/storage", json={"mirrors": {ORIGIN: origin.url("/")}})

    def run_probe(
        self, stage: str, program: Path, model: Path, device: Any, timeout: float
    ) -> str | Notice:
        return self.probe(stage, program, model, device, timeout)

    def fetch_remote(self, url: str) -> Registry:
        if self.remote_error is not None:
            raise self.remote_error
        assert self.remote is not None, url
        return self.remote

    def start(self, hardware: Hardware = GPU_4090) -> None:
        self.ctx: ManagerContext = build_context(
            self.data,
            self.registry,
            policy=FAST,
            detect_hardware=lambda: hardware,
            secrets=self.secrets,
            probe=self.run_probe,
            fetch_remote=self.fetch_remote,
        )
        app = FastAPI()
        app.add_exception_handler(OSError, locked_path_response)
        app.add_exception_handler(StarletteHTTPException, noticed_http_error)
        app.state.manager = self.ctx
        app.state.jobs = self.jobs
        for module in (downloads, models, runtimes, inventory, profile, settings):
            app.include_router(module.router)
        self.client: Any = TestClient(app)

    def asset(self, asset_id: str) -> dict[str, Any]:
        return self.client.get(f"/api/inventory/{asset_id}").json()

    def wait_jobs(self) -> None:
        def idle() -> bool:
            jobs = self.client.get("/api/downloads").json()
            return all(j["state"] in ("done", "failed", "cancelled") for j in jobs)

        wait_until(idle, 20)

    def install(self, kind: str, asset_id: str) -> None:
        verb = "download" if kind == "models" else "install"
        assert self.client.post(f"/api/{kind}/{asset_id}/{verb}").status_code == 200
        self.wait_jobs()

    def set_profile(self, profile_id: str | None) -> dict[str, Any]:
        reply = self.client.put("/api/profile", json={"profile": profile_id})
        assert reply.status_code == 200, reply.text
        return reply.json()

    def install_profile(self, profile_id: str) -> None:
        self.set_profile(profile_id)
        assert self.client.post("/api/profile/download").status_code == 202
        self.wait_jobs()
        assert self.client.get("/api/profile").json()["active"]["id"] == profile_id


class FakeServer:
    """Stands in for Ollama and for an OpenAI-compatible cloud endpoint."""

    def __init__(self) -> None:
        self.auth: list[str | None] = []
        outer = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, format: str, *args: object) -> None:
                return

            def do_GET(self) -> None:
                outer.auth.append(self.headers.get("Authorization"))
                if self.path == "/api/tags":
                    body = {"models": [{"name": "qwen3:8b"}, {"name": "llama3:latest"}]}
                elif self.path == "/v1/models":
                    if self.headers.get("Authorization") != "Bearer good-key":
                        self.send_error(401)
                        return
                    body = {"data": [{"id": "gpt-x"}]}
                else:
                    self.send_error(404)
                    return
                payload = json.dumps(body).encode()
                self.send_response(200)
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.url = f"http://127.0.0.1:{self.server.server_address[1]}"
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def close(self) -> None:
        self.server.shutdown()
        self.server.server_close()
