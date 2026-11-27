"""The W4b sentences: what each real site sends now, against what it sent at 96dc7b3."""

from __future__ import annotations

import json
from functools import partial
from pathlib import Path
from typing import Any

from manage_support import Rig
from notice_scenarios_w4b import collect

from backend.core import notices
from backend.core.notices import noticed, to_json
from backend.manager.updates import UpdateError

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "app/src/i18n/notices.w4b.fixture.json"

REWORDED: dict[str, str] = {}
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
