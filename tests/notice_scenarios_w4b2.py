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
import socket
import sys
import time
import urllib.error
from email.message import Message
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

import pytest
from download_support import serve
from manage_support import Rig
from notice_scenarios import _slashes
from notice_scenarios_w4b import Entry, _entry, _replaced
from test_api import open_client
from test_queue import QueueRig, make_app

from backend.core import queue_runner
from backend.core.notices import notices_of
from backend.manager import llm_check, maintain, secrets
from backend.manager.download import JobState
from backend.manager.profiles import WHISPER_RUNTIME, WHISPER_TURBO
from backend.manager.secrets import SecretError
from backend.manager.settings import LlmSettings, LlmSource, SettingsStore


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


# Group 8: managing models and runtimes.

QWEN3_ASR = "qwen3-asr-1.7b-q8_0"
SILERO_GGML = "silero-vad-ggml-v6.2.0"
ADD_ON = "cudart-llama-b12068-win-cuda12.4"


def _repaired(reply: Any) -> Entry:
    body = cast("dict[str, Any]", reply.json())
    return _entry(body["reason"], body.get("reason_notices"))


def _blocker(reply: Any, index: int) -> Entry:
    detail = cast("dict[str, Any]", reply.json()["detail"])
    return _entry(detail["blockers"][index], detail.get("blockers_notices"))


def _managing(found: dict[str, Entry], rig: Rig) -> None:
    client = rig.client
    rig.jobs.running = True
    for code, call in {
        "repair": lambda: client.post(f"/api/inventory/{WHISPER_TURBO}/repair"),
        "redownload": lambda: client.post(f"/api/inventory/{WHISPER_TURBO}/redownload"),
        "update": lambda: client.post(f"/api/inventory/{WHISPER_TURBO}/update"),
        "move": lambda: client.post("/api/storage/move", json={"target": str(rig.tmp / "m")}),
        "deleteModel": lambda: client.delete(f"/api/models/{WHISPER_TURBO}"),
        "deleteRuntime": lambda: client.delete(f"/api/runtimes/{WHISPER_RUNTIME}"),
        "selftest": lambda: client.post("/api/runtimes/selftest"),
    }.items():
        found[f"manage.busy.{code}"] = _reply(call())
    rig.jobs.running = False

    def downloading(_asset: str) -> object:
        return SimpleNamespace(id="j", state=JobState.DOWNLOADING)

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(rig.ctx.runner, "active_job", downloading)
        found["manage.beingDownloaded"] = _reply(client.delete(f"/api/models/{WHISPER_TURBO}"))
        installing = _reply(client.delete(f"/api/runtimes/{WHISPER_RUNTIME}"))
        found["manage.beingInstalled"] = _replaced(installing, WHISPER_RUNTIME, "<runtime>")
    found["manage.notInstalled"] = _reply(client.post(f"/api/inventory/{WHISPER_TURBO}/verify"))
    found["manage.repair.fileMissing"] = _repaired(
        client.post(f"/api/inventory/{WHISPER_TURBO}/repair")
    )
    rig.wait_jobs()
    found["manage.repair.incomplete"] = _repaired(
        client.post(f"/api/inventory/{WHISPER_RUNTIME}/repair")
    )
    rig.wait_jobs()
    found["manage.repair.shaMatches"] = _repaired(
        client.post(f"/api/inventory/{WHISPER_TURBO}/repair")
    )
    found["manage.repair.runtimeChecked"] = _repaired(
        client.post(f"/api/inventory/{WHISPER_RUNTIME}/repair")
    )
    found["manage.addOn"] = _reply(client.post(f"/api/inventory/{ADD_ON}/repair"))
    needed = client.delete(f"/api/models/{WHISPER_TURBO}")
    found["manage.stillNeeded"] = _reply(needed)
    found["manage.activeProfileNeeds"] = _blocker(needed, 0)
    found["manage.forceNeedsReason"] = _reply(
        client.delete(f"/api/models/{WHISPER_TURBO}?force=true&reason=no")
    )
    model = Path(rig.asset(WHISPER_TURBO)["path"])
    model.write_bytes(bytes(model.stat().st_size))
    found["manage.repair.shaDiffers"] = _repaired(
        client.post(f"/api/inventory/{WHISPER_TURBO}/repair")
    )
    rig.wait_jobs()
    rig.set_profile("cpu")
    rig.install("models", QWEN3_ASR)
    found["manage.dependentNeeds"] = _blocker(client.delete(f"/api/models/{SILERO_GGML}"), 0)

    def locked(*_args: object) -> None:
        raise PermissionError(13, "denied", "C:/m/a.bin")

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(maintain, "delete_model", locked)
        found["manage.cannotDelete"] = _reply(client.delete(f"/api/models/{QWEN3_ASR}"))
    rig.set_profile("gpu-24gb")
    found["manage.stillNeeded.two"] = _reply(client.delete(f"/api/models/{SILERO_GGML}"))


# Group 9: the LLM page.


def _tested(
    found: dict[str, Entry], name: str, rig: Rig, llm: LlmSettings, key: str | None
) -> None:
    result = llm_check.test_connection(llm, key, rig.registry, rig.ctx.storage)
    found[name] = _entry(result.detail, getattr(result, "detail_notices", ()))


def _llm_page(found: dict[str, Entry], rig: Rig) -> None:
    ollama = LlmSettings(LlmSource.OLLAMA, "http://127.0.0.1:9", "qwen3:8b")
    cloud = LlmSettings(
        LlmSource.CLOUD,
        cloud_url="https://api.example.test/v1",
        cloud_model="m",
        cloud_consent=True,
    )
    moved = Message()
    moved["Location"] = "https://elsewhere.test/"
    answers: dict[str, object] = {
        "llmTest.refused": urllib.error.URLError(ConnectionRefusedError()),
        "llmTest.timedOut": urllib.error.URLError(TimeoutError()),
        "llmTest.hostNotFound": urllib.error.URLError(socket.gaierror()),
        "llmTest.cannotConnect": urllib.error.URLError(OSError("network is down")),
        "llmTest.redirected": urllib.error.HTTPError("u", 302, "Found", moved, None),
        "llmTest.keyRejected": urllib.error.HTTPError("u", 401, "Unauthorized", Message(), None),
        "llmTest.couldNotUse": urllib.error.HTTPError("u", 500, "Server Error", Message(), None),
        "llmTest.notJson": ValueError("not json"),
        "llmTest.modelMissing": {"models": [{"name": "other"}]},
        "llmTest.connected": {"models": [{"name": "qwen3:8b"}]},
    }
    for name, answer in answers.items():

        def get_json(_url: str, _key: str | None, _answer: object = answer) -> object:
            if isinstance(_answer, BaseException):
                raise _answer
            return _answer

        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(llm_check, "_get_json", get_json)
            _tested(found, name, rig, ollama, None)
    _tested(found, "llmTest.noKey", rig, cloud, None)
    _tested(found, "llmTest.notInstalled", rig, LlmSettings(), None)
    with pytest.MonkeyPatch.context() as mp:
        program = rig.tmp / "llama-server.exe"
        program.write_bytes(b"MZ")
        mp.setattr(llm_check, "runtime_executable", lambda *_args: program)  # pyright: ignore[reportUnknownArgumentType]
        gguf = rig.ctx.storage.model_file(rig.registry.models[llm_check.QWEN3_8B])
        gguf.parent.mkdir(parents=True, exist_ok=True)
        gguf.write_bytes(b"gguf")
        _tested(found, "llmTest.builtinReady", rig, LlmSettings(), None)
    reply = rig.client.put(
        "/api/settings", json={"registry_url": "https://example.test/r.json?token=1"}
    )
    found["settings.urlParts"] = _reply(reply)
    (rig.tmp / "user").mkdir()
    (rig.tmp / "user" / "settings.json").write_text("{", encoding="utf-8")
    store = SettingsStore(rig.tmp / "user")
    problem = store.problem or ""
    found["settings.fileNotUsed"] = _replaced(
        _entry(problem, getattr(store, "problem_notices", ())), str(rig.tmp / "user"), "<user>"
    )
    for name, failure in {"secrets.needDpapi": "needs", "secrets.dpapiFailed": "failed"}.items():
        found[name] = _secret_failure(failure)


def _secret_failure(failure: str) -> Entry:
    """What storing the API key says when Windows DPAPI is not there, or refuses."""
    refuse = SimpleNamespace(CryptProtectData=lambda *_args: 0)
    with pytest.MonkeyPatch.context() as mp:
        if failure == "needs":
            mp.setattr(secrets.sys, "platform", "linux")
        else:
            mp.setattr(secrets.ctypes, "windll", SimpleNamespace(crypt32=refuse), raising=False)
            mp.setattr(secrets.ctypes, "GetLastError", lambda: 13, raising=False)
        try:
            secrets._transform(b"k", protect=True)
        except SecretError as exc:
            return _entry(str(exc), notices_of(exc))
    raise AssertionError(failure)


def collect(tmp: Path) -> dict[str, Entry]:
    found: dict[str, Entry] = {}
    _batch_refusals(found, tmp)
    with serve() as origin:
        (tmp / "manage").mkdir()
        _managing(found, Rig(tmp / "manage", origin))
        (tmp / "llm").mkdir()
        _llm_page(found, Rig(tmp / "llm", origin))
    return {name: _slashes(entry) for name, entry in found.items()}


if __name__ == "__main__":
    import json
    import tempfile

    with tempfile.TemporaryDirectory(dir=os.environ.get("VST_SCRATCH")) as folder:
        made = json.dumps(collect(Path(folder)), ensure_ascii=False, indent=2)
        sys.stdout.buffer.write(made.encode("utf-8"))
