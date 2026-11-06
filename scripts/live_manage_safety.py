"""Live check of the failure paths: re-download offline, move retry, key scoping, CUDA fallback.

Usage: uv run python scripts/live_manage_safety.py --user-data <COPY of a user data folder>

Run it on a copy. It points the mirrors at a closed port, moves the models folder inside the copy's
parent, deletes the CPU twin runtimes there, and stops every process it starts."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from live_manage import Backend, check, gpu_processes

SILERO = "silero-vad-onnx-v6.2.3"
WHISPER_TURBO = "whisper-large-v3-turbo"
CPU_RUNTIME = "whispercpp-b5454-win-cpu"
DEAD_MIRROR = "http://127.0.0.1:9/"
HUGGINGFACE = "https://huggingface.co/"
GITHUB = "https://github.com/"


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def asset(api: Backend, asset_id: str) -> dict[str, object]:
    _, listing = api.call("GET", "/api/inventory")
    return next(a for a in listing["assets"] if a["id"] == asset_id)


def offline_redownload(api: Backend) -> None:
    api.call("PUT", "/api/storage", {"mirrors": {HUGGINGFACE: DEAD_MIRROR, GITHUB: DEAD_MIRROR}})
    model = Path(str(asset(api, SILERO)["path"]))
    folder = Path(str(asset(api, CPU_RUNTIME)["path"]))
    before = digest(model)
    (folder / "marker.txt").write_text("working")
    for asset_id in (SILERO, CPU_RUNTIME):
        status, job = api.call("POST", f"/api/inventory/{asset_id}/redownload")
        check(f"redownload of {asset_id} starts", status == 200, job["state"])
        time.sleep(4)
        _, jobs = api.call("GET", "/api/downloads")
        mine = next(j for j in jobs if j["id"] == job["id"])
        check(f"{asset_id} is still downloading, retrying", mine["state"] == "downloading", mine)
        check(f"{asset_id} stays installed mid-retry", bool(asset(api, asset_id)["installed"]))
        api.call("POST", f"/api/downloads/{job['id']}/cancel")
    for _ in range(60):
        _, jobs = api.call("GET", "/api/downloads")
        if all(j["state"] in ("done", "failed", "cancelled") for j in jobs):
            break
        time.sleep(0.5)
    check("model bytes unchanged", digest(model) == before)
    check("runtime folder unchanged", (folder / "marker.txt").read_text() == "working")
    check("inventory still says installed", all(asset(api, a)["installed"] for a in (SILERO,)))
    api.call("PUT", "/api/storage", {"mirrors": {}})


def move_retry(api: Backend, user_data: Path) -> None:
    target = user_data.parent / (f"{user_data.name}-move-{int(time.time())}")
    shutil.rmtree(target, ignore_errors=True)
    source = Path(str(asset(api, SILERO)["path"]))
    whole = target / SILERO / source.name
    whole.parent.mkdir(parents=True)
    shutil.copyfile(source, whole)
    half = target / WHISPER_TURBO / "ggml-large-v3-turbo.bin.part"
    half.parent.mkdir(parents=True)
    half.write_bytes(b"cut off by a crash")
    status, body = api.call("POST", "/api/storage/move", {"target": str(target)})
    check("retry over leftovers is accepted", status == 202, body)
    state: dict[str, object] = {}
    for _ in range(600):
        _, state = api.call("GET", "/api/storage/move")
        if state["state"] != "running":
            break
        time.sleep(0.5)
    check("retry finished", state["state"] == "done", state)
    check("models are in the target", (target / SILERO / source.name).is_file())
    check("no .part left", not list(target.rglob("*.part")))
    check("inventory sees the models", bool(asset(api, SILERO)["installed"]))


class KeyLog:
    def __init__(self) -> None:
        self.auth: list[str | None] = []
        outer = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, format: str, *args: object) -> None:
                return

            def do_GET(self) -> None:
                outer.auth.append(self.headers.get("Authorization"))
                payload = json.dumps({"data": [{"id": "gpt-x"}]}).encode()
                self.send_response(200)
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.url = f"http://127.0.0.1:{self.server.server_address[1]}"
        threading.Thread(target=self.server.serve_forever, daemon=True).start()


def key_scope(api: Backend) -> None:
    saved, other = KeyLog(), KeyLog()
    llm = {
        "source": "cloud",
        "cloud_url": f"{saved.url}/v1",
        "cloud_model": "gpt-x",
        "cloud_consent": True,
        "api_key": "sk-live-check",
    }
    status, body = api.call("PUT", "/api/settings", {"llm": llm})
    check("cloud settings saved", status == 200, body)
    probe = {k: v for k, v in llm.items() if k != "api_key"}
    api.call("POST", "/api/llm/test", {"llm": probe})
    check(
        "saved endpoint receives the saved key", saved.auth == ["Bearer sk-live-check"], saved.auth
    )
    api.call("POST", "/api/llm/test", {"llm": {**probe, "cloud_url": f"{other.url}/v1"}})
    check("another URL receives no request, so no key", other.auth == [], other.auth)
    _, reply = api.call("POST", "/api/llm/test", {"llm": {**probe, "cloud_url": f"{other.url}/v1"}})
    check("and says why", "no API key to test with" in reply["detail"] or reply["ok"], reply)
    for server in (saved, other):
        server.server.shutdown()


def cuda_without_twin(user_data: Path, env: dict[str, str]) -> None:
    api = Backend(user_data, env)
    try:
        for runtime in ("whispercpp-b5454-win-cpu", "llama.cpp-b12068-win-cpu"):
            status, body = api.call("DELETE", f"/api/runtimes/{runtime}")
            check(f"CPU twin {runtime} removed", status == 204, body)
        status, report = api.call("POST", "/api/runtimes/selftest")
        check("self-test ran", status == 200, report)
        print("  message:", report["message"])
        check("no fallback recorded", report["fallback"] is None and report["ok"] is False)
        check(
            "message names the problem and the asset",
            "GPU failed and the CPU runtime is not installed" in report["message"]
            and "whispercpp-b5454-win-cpu" in report["message"],
        )
        _, profile = api.call("GET", "/api/profile")
        check("pipeline stays on the profile device", profile["active"]["device"] == "cuda")
    finally:
        api.stop()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--user-data", type=Path, required=True)
    user_data: Path = parser.parse_args().user_data
    check("no GPU process before", not gpu_processes(), gpu_processes())
    api = Backend(user_data)
    try:
        offline_redownload(api)
        move_retry(api, user_data)
        key_scope(api)
    finally:
        api.stop()
    cuda_without_twin(user_data, {"VST_SIMULATE_CUDA_FAILURE": "1"})
    check("no GPU process after", not gpu_processes(), gpu_processes())


if __name__ == "__main__":
    sys.exit(main())
