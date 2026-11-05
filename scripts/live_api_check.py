"""Run one video through the real service and write what a client sees.

    uv run python scripts/live_api_check.py VIDEO --user-data DIR --out OUT/api1

Starts `python -m backend.main`, times it to READY, creates a project, runs a job while reading
its event stream, and checks the stream (order, monotonic progress, ends with done) and the
subtitle and summary routes against the files in the project folder. Writes `sse.txt` and
`result.json` into OUT and stops the service. Compare the project folder with a CLI run by hand.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

ROOT = Path(__file__).parent.parent


def call(base: str, token: str, method: str, path: str, body: object = None) -> tuple[int, bytes]:
    data = None if body is None else json.dumps(body).encode()
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    request = urllib.request.Request(base + path, data, headers, method=method)
    try:
        with urllib.request.urlopen(request) as response:
            return response.status, response.read()
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("video", type=Path)
    parser.add_argument("--user-data", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    started = time.perf_counter()
    proc = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "backend.main",
            "--user-data",
            str(args.user_data),
            "--projects",
            str(args.out / "projects"),
        ],
        stdout=subprocess.PIPE,
        text=True,
        cwd=ROOT,
    )
    assert proc.stdout is not None
    try:
        line = proc.stdout.readline().strip()
        ready_s = time.perf_counter() - started
        match = re.fullmatch(r"READY port=(\d+) token=(\S+)", line)
        if not match:
            raise SystemExit(f"no READY line: {line!r}")
        base, token = f"http://127.0.0.1:{match[1]}", match[2]
        result = drive(base, token, args.video, args.out)
        result["ready_s"] = round(ready_s, 3)
        (args.out / "result.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
        print(json.dumps(result, indent=2))
        return 0 if result["ok"] else 1
    finally:
        proc.terminate()
        try:
            proc.wait(30)
        except subprocess.TimeoutExpired:
            proc.kill()


def drive(base: str, token: str, video: Path, out: Path) -> dict[str, Any]:
    raw = call(base, token, "POST", "/api/projects", {"video_path": str(video)})[1]
    project = json.loads(raw)
    started = time.perf_counter()
    raw = call(base, token, "POST", f"/api/projects/{project['id']}/jobs", {})[1]
    job = json.loads(raw)
    request = urllib.request.Request(
        f"{base}/api/jobs/{job['id']}/events", headers={"Authorization": f"Bearer {token}"}
    )
    lines: list[str] = []
    events: list[tuple[str, dict[str, Any]]] = []
    kind = ""
    with urllib.request.urlopen(request) as stream, (out / "sse.txt").open("w") as log:
        for raw_line in stream:
            text = raw_line.decode("utf-8").rstrip("\n")
            lines.append(text)
            log.write(text + "\n")
            if text.startswith("event: "):
                kind = text.removeprefix("event: ")
            elif text.startswith("data: "):
                events.append((kind, json.loads(text.removeprefix("data: "))))
    total_s = time.perf_counter() - started
    overall = [d["overall"] for k, d in events if k != "status"]
    steps = [d["step"] for k, d in events if k == "progress"]
    folder = Path(project["folder"])
    checks = {
        "ends_with_done": events[-1][0] == "done",
        "monotonic": overall == sorted(overall),
        "seq_in_order": [d["seq"] for _, d in events] == list(range(len(events))),
        "step_order": list(dict.fromkeys(steps))
        == ["audio", "vad", "asr", "segment", "translate", "export", "summarize"],
    }
    summary = call(base, token, "GET", f"/api/projects/{project['id']}/summary")[1]
    checks["summary_same"] = summary == (folder / "summary.md").read_bytes()
    for lang, name in (("en", "en.srt"), ("zh", "zh-TW.srt")):
        got = call(base, token, "GET", f"/api/projects/{project['id']}/subtitles?lang={lang}")[1]
        checks[f"{name}_same"] = got == (folder / name).read_bytes()
    report = events[-1][1].get("report", {})
    return {
        "ok": all(checks.values()),
        "checks": checks,
        "folder": str(folder),
        "events": len(events),
        "api_total_s": round(total_s, 2),
        "pipeline_total_s": report.get("total_s"),
        "steps": report.get("steps"),
    }


if __name__ == "__main__":
    sys.exit(main())
