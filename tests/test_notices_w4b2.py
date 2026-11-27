"""The W4b part 2 sentences: what each real site sends now, against what it sent at 372aad7."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from notice_scenarios_w4b2 import collect

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "app/src/i18n/notices.w4b2.fixture.json"

REWORDED = {
    "batch.alreadyIn": 'said "queue" where the window says "batch"',
    "storage.unmoved": "named an API route a person cannot use, where the window has a button",
    "move.otherContent": 'began with "MoveError: ", a name from the code',
    "move.wrongSize": 'began with "OSError: ", a name from the code',
    "switch.unknownMemory": 'said "This machine has unknown memory of memory"',
}
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
