"""Check through the real service that a rerun of translate keeps the cues a person edited.

    uv run python scripts/check_edit_rerun.py PROJECTS_DIR --user-data DIR --out OUT

`PROJECTS_DIR` holds one finished project. The script edits three cues through `PUT /subtitles`,
runs a job with a glossary the project has not seen, which makes translate run again for every
cue, and compares the subtitles before and after. It passes when the three edited cues are the
same, the other cues were translated again, and the done event counts the edits it kept. Uses the
GPU. Writes `result.json` into OUT and stops the service.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import time
import urllib.request
from pathlib import Path
from typing import Any

from live_api_check import ROOT, call


def get(base: str, token: str, path: str) -> Any:
    status, body = call(base, token, "GET", path)
    assert status == 200, (status, body[:300])
    return json.loads(body)


def job_events(base: str, token: str, job_id: str) -> list[tuple[str, dict[str, Any]]]:
    request = urllib.request.Request(
        f"{base}/api/jobs/{job_id}/events", headers={"Authorization": f"Bearer {token}"}
    )
    events: list[tuple[str, dict[str, Any]]] = []
    name = ""
    with urllib.request.urlopen(request) as response:
        for raw in response:
            line = raw.decode().rstrip("\n")
            if line.startswith("event: "):
                name = line.removeprefix("event: ")
            elif line.startswith("data: "):
                events.append((name, json.loads(line.removeprefix("data: "))))
    return events


def drive(base: str, token: str, pid: str) -> dict[str, Any]:
    url = f"/api/projects/{pid}/subtitles"
    cues = get(base, token, f"{url}?format=json")["cues"]
    chosen = [cues[4], cues[7], cues[len(cues) // 2]]
    edits = {c["id"]: f"人工校對 {c['id']}" for c in chosen}
    body = {"cues": [{**c, "zh": edits.get(c["id"], c["zh"])} for c in cues]}
    status, reply = call(base, token, "PUT", url, body)
    assert status == 200, (status, reply[:300])
    before = {c["id"]: c["zh"] for c in get(base, token, f"{url}?format=json")["cues"]}
    status, reply = call(
        base,
        token,
        "POST",
        f"/api/projects/{pid}/jobs",
        {"glossary": [{"term": "agent", "zh": "代理"}]},
    )
    assert status == 202, (status, reply[:300])
    started = time.perf_counter()
    events = job_events(base, token, json.loads(reply)["id"])
    seconds = time.perf_counter() - started
    final_kind, final = events[-1]
    after = {c["id"]: c["zh"] for c in get(base, token, f"{url}?format=json")["cues"]}
    marked = get(base, token, f"/api/projects/{pid}/edits")["ids"]
    others = [i for i in before if i not in edits]
    changed = sum(before[i] != after[i] for i in others)
    report = final.get("report", {})
    ran = [s["step"] for s in report.get("steps", []) if s["ran"]]
    ok = (
        final_kind == "done"
        and "translate" in ran
        and all(after[i] == text for i, text in edits.items())
        and changed > 0
        and report.get("edits_kept") == len(edits)
        and sorted(marked) == sorted(edits)
    )
    return {
        "ok": ok,
        "job_s": round(seconds, 1),
        "steps_ran": ran,
        "edited_ids": sorted(edits),
        "edits_kept": report.get("edits_kept"),
        "edits_unmatched": report.get("edits_unmatched"),
        "edited_cues_unchanged": all(after[i] == text for i, text in edits.items()),
        "other_cues": len(others),
        "other_cues_changed_by_retranslation": changed,
        "marked_after": marked,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("projects", type=Path)
    parser.add_argument("--user-data", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    pid = next(p.name for p in args.projects.iterdir() if p.is_dir())
    proc = subprocess.Popen(
        [sys.executable, "-m", "backend.main", "--user-data", str(args.user_data)]
        + ["--projects", str(args.projects)],
        stdout=subprocess.PIPE,
        text=True,
        cwd=ROOT,
    )
    assert proc.stdout is not None
    try:
        match = re.fullmatch(r"READY port=(\d+) token=(\S+)", proc.stdout.readline().strip())
        if not match:
            raise SystemExit("no READY line")
        result = drive(f"http://127.0.0.1:{match[1]}", match[2], pid)
        (args.out / "result.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
        print(json.dumps(result, indent=2))
        return 0 if result["ok"] else 1
    finally:
        proc.terminate()
        try:
            proc.wait(30)
        except subprocess.TimeoutExpired:
            proc.kill()


if __name__ == "__main__":
    sys.exit(main())
