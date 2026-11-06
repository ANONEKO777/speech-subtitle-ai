"""Live check of the settings, inventory, profile and self-test routes against a real backend.

Usage: uv run python scripts/live_manage.py --user-data <COPY of a populated user data folder>

Run it on a copy. It deletes and re-downloads one small model there, switches profiles, downloads
the two CPU runtimes, and starts the backend twice (once with the CUDA fault switch). It checks
`tasklist` for stray ASR or LLM processes before and after and stops every process it starts."""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

SILERO_GGML = "silero-vad-ggml-v6.2.0"
WHISPER_TURBO = "whisper-large-v3-turbo"
GPU_PROCESSES = re.compile(r"whisper-cli|crispasr|llama-server", re.IGNORECASE)


class Backend:
    def __init__(self, user_data: Path, env: dict[str, str] | None = None) -> None:
        self.proc = subprocess.Popen(
            [sys.executable, "-m", "backend.main", "--user-data", str(user_data)],
            stdout=subprocess.PIPE,
            text=True,
            env={**os.environ, **(env or {})},
        )
        assert self.proc.stdout is not None
        line = self.proc.stdout.readline()
        match = re.search(r"port=(\d+) token=(\S+)", line)
        assert match, f"no READY line: {line!r}"
        self.base = f"http://127.0.0.1:{match.group(1)}"
        self.token = match.group(2)

    def call(self, method: str, path: str, body: Any = None, token: bool = True) -> tuple[int, Any]:
        data = json.dumps(body).encode() if body is not None else None
        headers = {"Content-Type": "application/json"}
        if token:
            headers["Authorization"] = f"Bearer {self.token}"
        request = urllib.request.Request(self.base + path, data, headers, method=method)
        try:
            with urllib.request.urlopen(request, timeout=300) as reply:
                raw = reply.read()
                return reply.status, json.loads(raw) if raw else None
        except urllib.error.HTTPError as exc:
            raw = exc.read()
            return exc.code, json.loads(raw) if raw else None

    def stop(self) -> None:
        self.proc.terminate()
        try:
            self.proc.wait(10)
        except subprocess.TimeoutExpired:
            self.proc.kill()


def gpu_processes() -> list[str]:
    out = subprocess.run(["tasklist"], capture_output=True, text=True, check=False).stdout
    return [line for line in out.splitlines() if GPU_PROCESSES.search(line)]


def check(name: str, ok: bool, detail: object = "") -> None:
    print(f"{'PASS' if ok else 'FAIL'} {name} {detail}", flush=True)
    if not ok:
        raise SystemExit(f"failed: {name}")


def wait_downloads(api: Backend, timeout: float = 600) -> None:
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        _, jobs = api.call("GET", "/api/downloads")
        if all(j["state"] in ("done", "failed", "cancelled") for j in jobs):
            failed = [j for j in jobs if j["state"] == "failed"]
            check("downloads finished without failure", not failed, failed)
            return
        time.sleep(0.5)
    raise SystemExit("downloads did not finish")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--user-data", type=Path, required=True)
    args = parser.parse_args()
    user_data: Path = args.user_data
    check("no GPU process before", not gpu_processes(), gpu_processes())

    api = Backend(user_data)
    try:
        status, listing = api.call("GET", "/api/inventory", token=False)
        check("inventory needs the token", status == 401, status)
        _, listing = api.call("GET", "/api/inventory")
        assets = {a["id"]: a for a in listing["assets"]}
        for a in assets.values():
            print(
                "  ",
                a["id"],
                a["type"],
                "installed" if a["installed"] else "-",
                a["version"][:12],
                a["size_on_disk"],
                a["sha256_state"],
                a["used_by_profiles"],
                "dependents",
                [d["id"] for d in a["dependents"]],
                "blockers",
                a["blockers"],
            )
        installed = {i for i, a in assets.items() if a["installed"]}
        check("inventory sees the copied assets", WHISPER_TURBO in installed, sorted(installed))
        check(
            "vad path",
            listing["vad_model_path"].endswith("silero_vad.onnx"),
            listing["vad_model_path"],
        )

        status, body = api.call("DELETE", f"/api/models/{WHISPER_TURBO}")
        check("delete of an in-use model is refused", status == 409, body)
        status, body = api.call("DELETE", f"/api/models/{WHISPER_TURBO}?force=true")
        check("force without a reason is refused", status == 422, body)
        _, after = api.call("GET", f"/api/inventory/{WHISPER_TURBO}")
        check("the in-use model is still there", after["installed"], after["path"])

        _, view = api.call("PUT", "/api/profile", {"profile": "cpu"})
        cpu = next(p for p in view["profiles"] if p["id"] == "cpu")
        print("   cpu profile missing:", [m["id"] for m in cpu["missing"]], cpu["download_bytes"])
        check("cpu profile lists the missing runtimes", len(cpu["missing"]) == 2, cpu["missing"])
        status, _ = api.call("POST", "/api/profile/download")
        wait_downloads(api)
        _, view = api.call("GET", "/api/profile")
        check(
            "cpu profile complete after download",
            next(p for p in view["profiles"] if p["id"] == "cpu")["missing"] == [],
        )

        api.call("PUT", "/api/profile", {"profile": "gpu-8gb"})
        api.call("POST", f"/api/models/{SILERO_GGML}/download")
        wait_downloads(api)
        _, one = api.call("GET", f"/api/inventory/{SILERO_GGML}")
        check("small model installed and verified", one["sha256_state"] == "verified", one)
        status, _ = api.call("DELETE", f"/api/models/{SILERO_GGML}")
        _, one = api.call("GET", f"/api/inventory/{SILERO_GGML}")
        check("unused model deleted", status == 204 and not one["installed"], status)
        api.call("POST", f"/api/models/{SILERO_GGML}/download")
        wait_downloads(api)
        path = Path(one["path"])
        data = bytearray(path.read_bytes())
        data[100] ^= 0xFF
        path.write_bytes(bytes(data))
        _, bad = api.call("POST", f"/api/inventory/{SILERO_GGML}/verify")
        check("corruption is detected", bad["sha256_state"] == "corrupt", bad["sha256_state"])
        _, fixed = api.call("POST", f"/api/inventory/{SILERO_GGML}/repair")
        wait_downloads(api)
        _, one = api.call("GET", f"/api/inventory/{SILERO_GGML}")
        check(
            "repair refetched it",
            fixed["action"] == "refetch" and one["sha256_state"] == "verified",
            fixed["reason"],
        )

        api.call("PUT", "/api/profile", {"profile": "gpu-24gb"})
        check("no GPU process before the self-test", not gpu_processes())
        status, report = api.call("POST", "/api/runtimes/selftest")
        print("   selftest:", json.dumps(report, indent=1))
        check(
            "self-test passes on the GPU",
            status == 200 and report["ok"] and report["device"] == "cuda",
            report["message"],
        )
        check("self-test is fast", report["seconds"] < 20, report["seconds"])
        check("no GPU process after the self-test", not gpu_processes(), gpu_processes())

        status, body = api.call(
            "PUT",
            "/api/settings",
            {
                "llm": {
                    "source": "cloud",
                    "cloud_url": "https://api.example.com/v1",
                    "cloud_model": "m",
                    "api_key": "sk-live-check",
                }
            },
        )
        check("cloud save without consent is 422", status == 422, body)
        status, body = api.call(
            "POST",
            "/api/llm/test",
            {"llm": {"source": "ollama", "ollama_url": "http://127.0.0.1:9", "ollama_model": "m"}},
        )
        check(
            "wrong Ollama URL fails and shows the URL",
            body["ok"] is False and "127.0.0.1:9" in body["detail"],
            body,
        )
        _, lic = api.call("GET", "/api/licenses")
        ids = {e["id"] for e in lic["licenses"]}
        check("licenses cover the registry", ids == set(assets), len(ids))
        _, cfg = api.call("GET", "/api/settings")
        check("no key in settings", "sk-live-check" not in json.dumps(cfg))
        stored = (
            (user_data / "settings.json").read_text(encoding="utf-8")
            if (user_data / "settings.json").exists()
            else ""
        )
        check("no key in settings.json", "sk-live-check" not in stored)
    finally:
        api.stop()

    faulty = Backend(user_data, {"VST_SIMULATE_CUDA_FAILURE": "1"})
    try:
        check("no GPU process before the faulted self-test", not gpu_processes())
        status, report = faulty.call("POST", "/api/runtimes/selftest")
        print("   faulted selftest:", json.dumps(report, indent=1))
        check(
            "injected CUDA fault falls back to CPU with a reason",
            report["ok"] and report["device"] == "cpu" and report["fallback"] is not None,
            report["fallback"]["reason"] if report["fallback"] else report,
        )
        _, view = faulty.call("GET", "/api/profile")
        check(
            "fallback is exposed on the profile",
            view["fallback"] is not None and view["active"]["device"] == "cpu",
        )
    finally:
        faulty.stop()

    healthy = Backend(user_data)
    try:
        _, view = healthy.call("GET", "/api/profile")
        check("fallback survives a restart", view["fallback"] is not None)
        _, report = healthy.call("POST", "/api/runtimes/selftest")
        check(
            "self-test back on the GPU clears it",
            report["device"] == "cuda" and report["fallback"] is None,
            report["message"],
        )
    finally:
        healthy.stop()
    check("no GPU process after", not gpu_processes(), gpu_processes())


if __name__ == "__main__":
    main()
