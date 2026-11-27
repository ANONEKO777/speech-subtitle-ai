"""The W4b part 2 sentences, each raised at the site the app raises it from.

`app/src/i18n/notices.w4b2.fixture.json` holds, for each scenario, the text and notices this module
produces now (`tests/test_notices_w4b2.py` keeps them equal), `before`: the text the same call gave
at commit 372aad7, and `zh`: what a window in Traditional Chinese shows. `before` was written by
running this module on a clean export of that commit, so it only calls what both versions have.
The English must equal `before` except where `REWORDED` in the test says why.

A refusal is read from the HTTP reply the window gets. Paths are relative or replaced, so the
fixture is the same on every system and in every temporary folder.
"""

# pyright: reportPrivateUsage=false, reportUnknownLambdaType=false

from __future__ import annotations

import os
import sys
import time
from pathlib import Path
from typing import Any, cast

import pytest
from notice_scenarios import _slashes
from notice_scenarios_w4b import Entry, _entry, _replaced
from test_api import open_client
from test_queue import QueueRig, make_app

from backend.core import queue_runner


def _reply(response: Any) -> Entry:
    """What a refused request says: `detail` (or its `message`) and the notices beside it."""
    body = cast("dict[str, Any]", response.json())
    detail: object = body.get("detail")
    text = cast("dict[str, Any]", detail).get("message") if isinstance(detail, dict) else detail
    return _entry(str(text), body.get("notices"))


def _reason(skipped: dict[str, Any]) -> Entry:
    return _entry(skipped["reason"], skipped.get("reason_notices"))


# Group 7: the batch.


def _slow_walk(*_args: object) -> list[Path]:
    time.sleep(0.5)
    return []


def _batch_refusals(found: dict[str, Entry], tmp: Path) -> None:
    folder = tmp / "batch"
    folder.mkdir()
    video = folder / "talk.mp4"
    video.write_bytes(b"talk")
    text = folder / "notes.txt"
    text.write_text("notes", encoding="utf-8")
    with open_client(make_app(folder, QueueRig(), None)) as client:
        assert client.post("/api/queue/pause").status_code == 200

        def skipped(**body: Any) -> Entry:
            reply = client.post("/api/queue/items", json={"items": [], "folders": [], **body})
            return _reason(reply.json()["skipped"][0])

        found["batch.notAFolder"] = skipped(folders=[{"path": str(video)}])
        found["batch.notAFile"] = skipped(items=[{"path": "talk.mp4"}])
        found["batch.notMedia"] = skipped(items=[{"path": str(text)}])
        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(queue_runner, "SCAN_TIMEOUT_S", 0.05)
            mp.setattr(queue_runner, "_walk", _slow_walk)
            found["batch.folderSlow"] = skipped(folders=[{"path": str(folder)}])
        added = client.post("/api/queue/items", json={"items": [{"path": str(video)}]}).json()
        item = added["added"][0]["id"]
        again = skipped(items=[{"path": str(video)}])
        found["batch.alreadyIn"] = _replaced(again, item, "<item>")
        found["batch.nothingGiven"] = _reply(client.post("/api/queue/items", json={"items": []}))
        found["batch.badOrder"] = _reply(client.put("/api/queue/order", json={"ids": ["x", "x"]}))
        command = f"/api/queue/items/{item}"
        found["batch.cannotResume"] = _reply(client.post(f"{command}/resume"))
        found["batch.cannotRetry"] = _reply(client.post(f"{command}/retry"))
        found["batch.removeFinishedOnly"] = _reply(client.delete(command))
        client.post(f"{command}/pause")
        found["batch.cannotPause"] = _reply(client.post(f"{command}/pause"))
        client.post(f"{command}/cancel")
        found["batch.cannotCancel"] = _reply(client.post(f"{command}/cancel"))


def collect(tmp: Path) -> dict[str, Entry]:
    found: dict[str, Entry] = {}
    _batch_refusals(found, tmp)
    return {name: _slashes(entry) for name, entry in found.items()}


if __name__ == "__main__":
    import json
    import tempfile

    with tempfile.TemporaryDirectory(dir=os.environ.get("VST_SCRATCH")) as folder:
        made = json.dumps(collect(Path(folder)), ensure_ascii=False, indent=2)
        sys.stdout.buffer.write(made.encode("utf-8"))
