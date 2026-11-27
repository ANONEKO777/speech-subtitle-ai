"""The W4b sentences: what each real site sends now, against what it sent at 96dc7b3."""

from __future__ import annotations

import io
import json
import urllib.error
from email.message import Message
from functools import partial
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

import pytest
from manage_support import Rig
from notice_scenarios_w4b import collect

from backend.api.deps import locked_path_response
from backend.core import notices
from backend.core.notices import noticed, notices_of, to_json
from backend.core.source_langs import MIXED, SOURCES
from backend.llm import client
from backend.manager.updates import UpdateError

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "app/src/i18n/notices.w4b.fixture.json"

REWORDED = {"batch.crashed": 'said "queue" where the window says "batch"'}
"""Scenarios whose English changed on purpose, and why."""


def stored() -> dict[str, dict[str, Any]]:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def test_the_scenarios_still_send_what_the_window_fixture_holds(tmp_path: Path) -> None:
    now = collect(tmp_path)

    assert now == {k: {"text": v["text"], "notices": v["notices"]} for k, v in stored().items()}


def test_the_english_is_what_the_backend_sent_before() -> None:
    changed = {name for name, entry in stored().items() if entry["text"] != entry["before"]}

    assert changed == set(REWORDED)


def test_every_notice_a_scenario_sends_is_inside_its_text() -> None:
    for name, entry in stored().items():
        assert entry["notices"], name
        for notice in entry["notices"]:
            assert notice["message"] in entry["text"], (name, notice["code"])


# The channels this round added, as the window receives them.


def inside(text: str, notices: list[dict[str, Any]]) -> bool:
    return bool(notices) and all(notice["message"] in text for notice in notices)


def test_the_profile_route_sends_the_notices_of_each_line_of_why(rig: Rig) -> None:
    recommended = rig.client.get("/api/profile").json()["recommended"]
    lines = recommended["why"].split("\n")
    sent = [n["message"] for n in recommended["why_notices"]]

    assert inside(recommended["why"], recommended["why_notices"])
    assert [message for message in sent if message in lines] == lines


def test_the_update_check_sends_the_notices_of_its_summary_and_each_item(rig: Rig) -> None:
    report = rig.client.post("/api/updates/check").json()

    for entry in (report, *report["items"]):
        assert inside(entry["message"], entry["message_notices"]), entry


def test_a_registry_that_cannot_be_read_sends_the_notice_beside_the_refusal(rig: Rig) -> None:
    url = "https://example.test/registry.json"
    rig.client.put("/api/settings", json={"registry_url": url})
    why = notices.REGISTRY_UNREACHABLE(url=url, reason="timed out")
    rig.remote_error = noticed(partial(UpdateError, url), why)

    reply = rig.client.post("/api/updates/check")

    assert reply.status_code == 502 and reply.json()["notices"] == to_json([why])


def test_a_failed_download_sends_the_notices_of_its_failure(rig: Rig) -> None:
    model = next(iter(rig.registry.models.values()))
    rig.origin.files[f"/{model.id}"] = bytes(model.size_bytes)
    rig.client.post(f"/api/models/{model.id}/download")
    rig.wait_jobs()

    failure = next(j for j in rig.client.get("/api/downloads").json() if j["failure"])["failure"]

    assert [n["code"] for n in failure["message_notices"]] == ["download.hashMismatch"]
    assert inside(failure["message"], failure["message_notices"])


def test_a_locked_file_answers_a_409_with_the_notice_beside_it() -> None:
    reply = locked_path_response(cast("Any", None), PermissionError(13, "denied", "C:/m/a.bin"))
    body = json.loads(bytes(reply.body))

    assert reply.status_code == 409
    assert [n["code"] for n in body["notices"]] == ["download.locked"]
    assert inside(body["detail"]["message"], body["notices"])


def test_the_api_key_reaches_no_part_of_a_chat_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    key = "sk-secret-123"
    config = client.LlmConfig("https://api.example.test/v1", "m", key)
    echoed = f"bad key {key}".encode()
    moved = Message()
    moved["Location"] = f"https://api.example.test/?key={key}"
    answers: list[Exception] = [
        urllib.error.HTTPError(config.chat_url, 401, key, Message(), io.BytesIO(echoed)),
        urllib.error.HTTPError(config.chat_url, 302, "Found", moved, io.BytesIO()),
        urllib.error.URLError(f"proxy refused {key}"),
    ]
    for answer in answers:

        def refuse(*_args: object, _answer: Exception = answer, **_kwargs: object) -> None:
            raise _answer

        opener = SimpleNamespace(open=refuse)

        def opening(_config: object, _opener: object = opener) -> object:
            return _opener

        monkeypatch.setattr(client, "_opener", opening)
        with pytest.raises(client.LlmError) as caught:
            client.chat(config, [{"role": "user", "content": "hi"}])
        sent = to_json(notices_of(caught.value))

        assert sent and key not in json.dumps(sent) + str(caught.value)


def test_only_the_japanese_and_english_talk_names_its_own_speech_engine() -> None:
    """The two refusals about that engine say "Japanese and English" in the sentence itself. A
    second language with its own engine needs a language parameter instead."""
    own = [(code, source.name) for code, source in SOURCES.items() if source.asr_engine]

    assert own == [(MIXED, "Japanese and English")]
