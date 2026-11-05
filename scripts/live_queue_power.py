"""Drive the real service's batch queue against a fake power executor, never the machine's.

    uv run python scripts/live_queue_power.py --user-data DIR --out OUT --wav A.wav --wav2 B.wav

The service runs here with `power` replaced by a function that only appends a timestamp to
`OUT/<run>/power.log`, so no scenario can sleep or shut the host down. Scenarios: one queue item
from an audio-only file end to end, a job started by hand during a countdown, and a stress run
that revokes the countdown around its deadline. Without --wav and --wav2 only the stress run
executes, and it needs no GPU. Exit 0 when every check holds.
"""

from __future__ import annotations

import argparse
import json
import random
import re
import socket
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from collections.abc import Callable
from pathlib import Path
from typing import Any

ROOT = Path(__file__).parent.parent
STRESS_RUNS = 30
STRESS_COUNTDOWN_S = 1.0
GPU_COUNTDOWN_S = 12.0


def serve(user_data: Path, out: Path, countdown_s: float) -> None:
    import uvicorn

    sys.path.insert(0, str(ROOT))
    from backend.core.power import PowerAction
    from backend.main import (
        APP_ORIGINS,
        AppConfig,
        GuardConfig,
        create_app,
        default_resolver,
        local_hosts,
        new_token,
    )

    def fake_power(action: PowerAction) -> None:
        with (out / "power.log").open("a") as log:
            log.write(f"{time.time_ns()} {action.value}\n")

    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    listener.listen(128)
    port: int = listener.getsockname()[1]
    token = new_token()
    guard = GuardConfig(token, local_hosts(port), APP_ORIGINS)

    def ready() -> None:
        print(f"READY port={port} token={token}", flush=True)

    app = create_app(
        AppConfig(
            user_data,
            guard,
            default_resolver(user_data),
            ready,
            projects_dir=out / "projects",
            power=fake_power,
            countdown_s=countdown_s,
        )
    )
    uvicorn.Server(uvicorn.Config(app, log_level="warning")).run(sockets=[listener])


class Api:
    def __init__(self, base: str, token: str) -> None:
        self.base, self.token = base, token
        self.events: list[tuple[str, dict[str, Any]]] = []
        threading.Thread(target=self._listen, daemon=True).start()

    def call(self, method: str, path: str, body: object = None) -> tuple[int, Any]:
        data = None if body is None else json.dumps(body).encode()
        headers = {"Authorization": f"Bearer {self.token}", "Content-Type": "application/json"}
        request = urllib.request.Request(self.base + path, data, headers, method=method)
        try:
            with urllib.request.urlopen(request) as response:
                return response.status, json.loads(response.read() or b"null")
        except urllib.error.HTTPError as exc:
            return exc.code, exc.read().decode()

    def _listen(self) -> None:
        request = urllib.request.Request(
            self.base + "/api/queue/events", headers={"Authorization": f"Bearer {self.token}"}
        )
        kind = ""
        with urllib.request.urlopen(request) as stream:
            for raw in stream:
                text = raw.decode("utf-8").rstrip("\n")
                if text.startswith("event: "):
                    kind = text.removeprefix("event: ")
                elif text.startswith("data: "):
                    self.events.append((kind, json.loads(text.removeprefix("data: "))))

    def count(self, kind: str) -> int:
        return sum(1 for k, _ in self.events if k == kind)

    def wait(self, ok: Callable[[], bool], timeout_s: float, step_s: float = 0.02) -> bool:
        end = time.monotonic() + timeout_s
        while time.monotonic() < end:
            if ok():
                return True
            time.sleep(step_s)
        return ok()

    def items(self) -> list[dict[str, Any]]:
        return self.call("GET", "/api/queue")[1]["items"]

    def job_status(self, job_id: str) -> str:
        return self.call("GET", f"/api/jobs/{job_id}")[1]["status"]


def fired(out: Path) -> list[int]:
    log = out / "power.log"
    return [int(line.split()[0]) for line in log.read_text().splitlines()] if log.exists() else []


def wav_end_to_end(api: Api, wav: Path) -> dict[str, Any]:
    status, body = api.call("POST", "/api/queue/items", {"items": [{"path": str(wav)}]})
    item = body["added"][0]["id"]
    api.wait(
        lambda: any(i["id"] == item and i["state"] in ("done", "failed") for i in api.items()),
        900,
        0.5,
    )
    state = next(i for i in api.items() if i["id"] == item)
    return {
        "add_status": status,
        "state": state["state"],
        "error": state.get("error"),
        "ok": status == 201 and state["state"] == "done",
    }


def arm_with_garbage(api: Api, directory: Path, n: int) -> None:
    """Leave the queue idle after a failed item so a countdown starts. No GPU is used."""
    api.call("PUT", "/api/queue/settings", {"on_done": "sleep", "allow_power": True})
    path = directory / f"garbage{n}.wav"
    path.write_bytes(b"not audio")
    before = api.count("countdown")
    status, _ = api.call("POST", "/api/queue/items", {"items": [{"path": str(path)}]})
    assert status == 201, status
    assert api.wait(lambda: api.count("countdown") > before, 30), "no countdown started"


def manual_during_countdown(api: Api, out: Path, wav: Path) -> dict[str, Any]:
    fired_before = len(fired(out))
    arm_with_garbage(api, out, 0)
    cancelled_before = api.count("countdown_cancelled")
    _, project = api.call("POST", "/api/projects", {"video_path": str(wav)})
    status, job = api.call("POST", f"/api/projects/{project['id']}/jobs", {})
    cancelled = api.wait(lambda: api.count("countdown_cancelled") > cancelled_before, 5)
    api.wait(lambda: api.job_status(job["id"]) in ("done", "failed"), 900, 0.5)
    final = api.job_status(job["id"])
    time.sleep(GPU_COUNTDOWN_S + 3)
    count = len(fired(out)) - fired_before
    return {
        "job_status": status,
        "cancelled_on_start": cancelled,
        "job_final": final,
        "fired": count,
        "ok": status == 202 and cancelled and final == "done" and count == 0,
    }


def revoke_stress(api: Api, out: Path) -> dict[str, Any]:
    fired_runs = late = 0
    for n in range(1, STRESS_RUNS + 1):
        arm_with_garbage(api, out, n)
        deadline_ms = next(d["deadline_ms"] for k, d in reversed(api.events) if k == "countdown")
        aim = deadline_ms / 1000 + random.uniform(-0.04, 0.02)
        while time.time() < aim - 0.05:
            time.sleep(0.005)
        while time.time() < aim:
            pass
        known = len(fired(out))
        api.call("PUT", "/api/queue/settings", {"on_done": "sleep", "allow_power": True})
        returned_ns = time.time_ns()
        time.sleep(0.4)
        times = fired(out)
        if len(times) > known:
            fired_runs += 1
            late += sum(1 for t in times[known:] if t > returned_ns)
        api.wait(lambda: not api.call("GET", "/api/queue")[1]["countdown"], 5)
    return {
        "runs": STRESS_RUNS,
        "fired": fired_runs,
        "fired_after_put_returned": late,
        "ok": late == 0,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--user-data", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--wav", type=Path)
    parser.add_argument("--wav2", type=Path)
    parser.add_argument("--serve-countdown", type=float, help=argparse.SUPPRESS)
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    if args.serve_countdown is not None:
        serve(args.user_data, args.out, args.serve_countdown)
        return 0
    results: dict[str, Any] = {}
    runs = [("stress", STRESS_COUNTDOWN_S)]
    if args.wav and args.wav2:
        runs.insert(0, ("gpu", GPU_COUNTDOWN_S))
    for name, countdown_s in runs:
        sub = args.out / name
        sub.mkdir(exist_ok=True)
        command = [sys.executable, __file__, "--user-data", str(args.user_data), "--out", str(sub)]
        proc = subprocess.Popen(
            [*command, "--serve-countdown", str(countdown_s)],
            stdout=subprocess.PIPE,
            text=True,
            cwd=ROOT,
        )
        assert proc.stdout is not None
        try:
            match = re.fullmatch(r"READY port=(\d+) token=(\S+)", proc.stdout.readline().strip())
            if not match:
                raise SystemExit("no READY line")
            api = Api(f"http://127.0.0.1:{match[1]}", match[2])
            if name == "gpu":
                assert args.wav and args.wav2
                results["wav_end_to_end"] = wav_end_to_end(api, args.wav)
                results["manual_during_countdown"] = manual_during_countdown(api, sub, args.wav2)
            else:
                results["revoke_stress"] = revoke_stress(api, sub)
        finally:
            proc.terminate()
            try:
                proc.wait(30)
            except subprocess.TimeoutExpired:
                proc.kill()
    results["ok"] = all(r["ok"] for r in results.values())
    print(json.dumps(results, indent=2))
    return 0 if results["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
