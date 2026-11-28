from __future__ import annotations

import json
import os
import subprocess
import threading
import time
from collections.abc import Callable, Generator, Sequence
from pathlib import Path
from typing import Any

import pytest
from fastapi import FastAPI
from test_api import GUARD, Client, Rig, open_client
from test_pipeline import SETTINGS

from backend.core import queue_runner
from backend.core.jobs import JobOptions, OptionsError
from backend.core.media import MEDIA_EXTENSIONS
from backend.core.model import Step, Word
from backend.core.pipeline import Ports, Settings
from backend.core.power import Countdown, PowerAction
from backend.core.queue_eta import Live, etas, live_from_overall, step_rates
from backend.core.queue_runner import QueueRunner, scan_folder
from backend.core.queue_store import (
    ItemState,
    OnDone,
    QueueError,
    QueueSettings,
    QueueStore,
    StepTiming,
)
from backend.core.vad import Chunk
from backend.main import AppConfig, create_app

AUDIO_S = 60.0


class QueueRig(Rig):
    """A file named bad* fails in ASR, and a run waits in ASR until `release` is set."""

    def __init__(self) -> None:
        super().__init__()
        self.order: list[str] = []
        self.release = threading.Event()
        self.release.set()
        self.started = threading.Event()

    def transcribe(
        self,
        wav: Path,
        chunks: Sequence[Chunk],
        progress: Callable[[float], None],
        cancel: threading.Event,
    ) -> list[Word]:
        name = Path(json.loads((wav.parent / "project.json").read_text("utf-8"))["video_path"]).stem
        self.order.append(name)
        self.started.set()
        if name.startswith("bad"):
            raise RuntimeError("cannot decode this file")
        while not self.release.is_set() and not cancel.is_set():
            progress(0.5)
            time.sleep(0.005)
        return super().transcribe(wav, chunks, progress, cancel)

    def resolve(self, options: JobOptions, folder: Path) -> tuple[Settings, Ports]:
        if options.engine == "nope":
            raise OptionsError("unknown engine 'nope'")
        return SETTINGS, self.ports()


class Power:
    def __init__(self) -> None:
        self.calls: list[PowerAction] = []

    def __call__(self, action: PowerAction) -> None:
        self.calls.append(action)


@pytest.fixture
def rig() -> QueueRig:  # pyright: ignore[reportIncompatibleVariableOverride]
    return QueueRig()


@pytest.fixture
def power() -> Power:
    return Power()


def make_app(tmp_path: Path, rig: QueueRig, power: Power | None, countdown_s: float = 0.05):
    return create_app(
        AppConfig(
            tmp_path / "data",
            GUARD,
            rig.resolve,
            power=power,
            countdown_s=countdown_s,
            probe=lambda _p: AUDIO_S,
        )
    )


@pytest.fixture
def client(tmp_path: Path, rig: QueueRig, power: Power) -> Generator[Client]:
    with open_client(make_app(tmp_path, rig, power)) as c:
        yield c


def options_for(lang: str) -> JobOptions:
    return JobOptions("whispercpp", "q", None, False, (), False, 8, lang)


def video(tmp_path: Path, name: str, ext: str = ".mp4") -> Path:
    path = tmp_path / "videos" / f"{name}{ext}"
    path.parent.mkdir(exist_ok=True)
    path.write_bytes(name.encode())
    return path


def add(client: Client, *paths: Path, **body: Any) -> dict[str, Any]:
    response = client.post(
        "/api/queue/items", json={"items": [{"path": str(p)} for p in paths], **body}
    )
    assert response.status_code == 201, response.text
    return response.json()


def states(client: Client) -> dict[str, str]:
    items = client.get("/api/queue").json()["items"]
    return {Path(i["video_path"]).stem: i["state"] for i in items}


def wait_for(client: Client, want: dict[str, str]) -> None:
    deadline = time.monotonic() + 15
    seen: dict[str, str] = {}
    while time.monotonic() < deadline:
        seen = states(client)
        if all(seen.get(k) == v for k, v in want.items()):
            return
        time.sleep(0.02)
    raise AssertionError(f"wanted {want}, got {seen}")


def kinds(app: FastAPI) -> list[str]:
    return [e.kind for e in app.state.queue.events.snapshot()]


def wait_kind(app: FastAPI, kind: str) -> None:
    deadline = time.monotonic() + 10
    while kind not in kinds(app) and time.monotonic() < deadline:
        time.sleep(0.02)
    assert kind in kinds(app)


def test_a_batch_runs_in_order_one_at_a_time_and_each_item_ends_done(
    client: Client, rig: QueueRig, tmp_path: Path
) -> None:
    rig.release.clear()
    names = ["slow1", "b", "c"]
    # paused while adding: otherwise the runner may start the first item before the reply is built
    client.post("/api/queue/pause")
    added = add(client, *(video(tmp_path, n) for n in names))["added"]
    assert [i["state"] for i in added] == ["queued"] * 3
    client.post("/api/queue/resume")
    rig.started.wait(5)
    running = [i for i in client.get("/api/queue").json()["items"] if i["state"] == "running"]
    assert [Path(i["video_path"]).stem for i in running] == ["slow1"]
    deadline = time.monotonic() + 5
    while not client.get("/api/queue").json()["items"][0]["job_id"] and time.monotonic() < deadline:
        time.sleep(0.02)
    job_id = client.get("/api/queue").json()["items"][0]["job_id"]
    assert client.get(f"/api/jobs/{job_id}").status_code == 200
    rig.release.set()
    wait_for(client, {n: "done" for n in names})
    assert rig.order == names
    body = client.get("/api/queue").json()
    assert body["counts"]["done"] == 3
    assert all(i["progress"] == 1.0 and i["attempts"] == 1 for i in body["items"])


def test_each_item_has_its_own_target_language_and_a_folder_is_scanned(
    client: Client, tmp_path: Path
) -> None:
    folder = tmp_path / "talks"
    folder.mkdir()
    (folder / "one.MP4").write_bytes(b"x")
    (folder / "two.mkv").write_bytes(b"x")
    (folder / "notes.txt").write_bytes(b"x")
    body = add(
        client,
        video(tmp_path, "solo"),
        folders=[{"path": str(folder), "target_lang": "ja"}],
        options={"target_lang": "zh-CN"},
    )
    langs = {Path(i["video_path"]).stem: i["target_lang"] for i in body["added"]}
    assert langs == {"solo": "zh-CN", "one": "ja", "two": "ja"}
    assert [p.name for p in scan_folder(folder, False)] == ["one.MP4", "two.mkv"]


def test_each_item_carries_its_own_source_language(client: Client, tmp_path: Path) -> None:
    body = add(
        client,
        video(tmp_path, "english"),
        options={"source_lang": "en"},
    )
    clip = video(tmp_path, "japanese")
    response = client.post(
        "/api/queue/items",
        json={"items": [{"path": str(clip), "source_lang": "ja"}]},
    )
    assert response.status_code == 201, response.text
    langs = {
        Path(i["video_path"]).stem: i["source_lang"]
        for i in client.get("/api/queue").json()["items"]
    }
    assert langs == {"english": "en", "japanese": "ja"}
    assert body["added"][0]["options"]["source_lang"] == "en"
    refused = client.post(
        "/api/queue/items",
        json={"items": [{"path": str(clip), "source_lang": "ja", "target_lang": "es"}]},
    )
    assert refused.status_code == 422 and "zh-TW, zh-CN, en, ko, not es" in refused.text
    unknown = client.post(
        "/api/queue/items", json={"items": [{"path": str(clip), "source_lang": "xx"}]}
    )
    assert unknown.status_code == 422


def test_a_queue_saved_before_source_languages_still_loads() -> None:
    from backend.core.queue_store import options_from_json

    old = (
        '{"engine": "whispercpp", "llm": "q", "llm_model": null, "cpu": false, "glossary": [], '
        '"summary_en": false, "batch_size": 8, "target_lang": "zh-TW"}'
    )
    assert options_from_json(old).source_lang == "en"


def test_a_missing_file_a_duplicate_and_an_unknown_language_are_reported(
    client: Client, tmp_path: Path, rig: QueueRig
) -> None:
    rig.release.clear()
    clip = video(tmp_path, "slow")
    add(client, clip)
    again = add(client, clip, tmp_path / "nope.mp4")
    assert again["added"] == []
    reasons = {Path(s["path"]).name: s["reason"] for s in again["skipped"]}
    assert "already in the batch" in reasons["slow.mp4"]
    assert "existing file" in reasons["nope.mp4"]
    bad_lang = client.post(
        "/api/queue/items", json={"items": [{"path": str(clip), "target_lang": "xx"}]}
    )
    assert bad_lang.status_code == 422
    assert client.post("/api/queue/items", json={}).status_code == 422
    rig.release.set()


def test_a_bad_file_fails_alone_and_a_retry_puts_it_at_the_end(
    client: Client, tmp_path: Path
) -> None:
    add(client, video(tmp_path, "a"), video(tmp_path, "bad"), video(tmp_path, "c"))
    wait_for(client, {"a": "done", "bad": "failed", "c": "done"})
    items = {Path(i["video_path"]).stem: i for i in client.get("/api/queue").json()["items"]}
    assert "cannot decode" in items["bad"]["last_error"]
    assert items["bad"]["attempts"] == 1
    assert client.post(f"/api/queue/items/{items['bad']['id']}/retry").status_code == 200
    wait_for(client, {"bad": "failed"})
    assert client.get("/api/queue").json()["items"][-1]["attempts"] == 2
    assert client.post(f"/api/queue/items/{items['a']['id']}/retry").status_code == 409


def test_a_bad_options_error_fails_only_its_item(client: Client, tmp_path: Path) -> None:
    add(client, video(tmp_path, "x"), options={"engine": "nope"})
    wait_for(client, {"x": "failed"})
    assert "unknown engine" in client.get("/api/queue").json()["items"][0]["last_error"]
    add(client, video(tmp_path, "y"))
    wait_for(client, {"x": "failed", "y": "done"})


def test_reorder_changes_the_order_the_items_run_in(
    client: Client, tmp_path: Path, rig: QueueRig
) -> None:
    client.post("/api/queue/pause")
    items = add(client, *(video(tmp_path, n) for n in ("a", "b", "c")))["added"]
    ids = [i["id"] for i in items]
    response = client.put("/api/queue/order", json={"ids": [ids[2], ids[0]]})
    assert [Path(i["video_path"]).stem for i in response.json()["items"]] == ["c", "a", "b"]
    assert client.put("/api/queue/order", json={"ids": ["nope"]}).status_code == 422
    client.post("/api/queue/resume")
    wait_for(client, {"a": "done", "b": "done", "c": "done"})
    assert rig.order == ["c", "a", "b"]


def test_pausing_the_queue_starts_nothing_new_and_resume_continues(
    client: Client, tmp_path: Path
) -> None:
    client.post("/api/queue/pause")
    add(client, video(tmp_path, "a"))
    time.sleep(0.3)
    assert states(client) == {"a": "queued"}
    assert client.get("/api/queue").json()["paused"] is True
    client.post("/api/queue/resume")
    wait_for(client, {"a": "done"})


def test_a_paused_item_is_skipped_until_resumed(client: Client, tmp_path: Path) -> None:
    client.post("/api/queue/pause")
    items = add(client, video(tmp_path, "a"), video(tmp_path, "b"))["added"]
    assert client.post(f"/api/queue/items/{items[0]['id']}/pause").json()["state"] == "paused"
    client.post("/api/queue/resume")
    wait_for(client, {"a": "paused", "b": "done"})
    client.post(f"/api/queue/items/{items[0]['id']}/resume")
    wait_for(client, {"a": "done"})


def test_cancel_a_queued_item_and_a_running_one(
    client: Client, tmp_path: Path, rig: QueueRig
) -> None:
    rig.release.clear()
    items = add(client, video(tmp_path, "slow"), video(tmp_path, "b"))["added"]
    rig.started.wait(5)
    assert client.post(f"/api/queue/items/{items[1]['id']}/cancel").json()["state"] == "cancelled"
    client.post(f"/api/queue/items/{items[0]['id']}/cancel")
    wait_for(client, {"slow": "cancelled", "b": "cancelled"})
    assert client.post(f"/api/queue/items/{items[0]['id']}/cancel").status_code == 409
    assert client.post("/api/queue/items/nope/cancel").status_code == 404


def test_pausing_a_running_item_stops_it_and_resume_finishes_it(
    client: Client, tmp_path: Path, rig: QueueRig
) -> None:
    rig.release.clear()
    item = add(client, video(tmp_path, "slow"))["added"][0]
    rig.started.wait(5)
    client.post(f"/api/queue/items/{item['id']}/pause")
    wait_for(client, {"slow": "paused"})
    rig.release.set()
    client.post(f"/api/queue/items/{item['id']}/resume")
    wait_for(client, {"slow": "done"})
    assert client.get("/api/queue").json()["items"][0]["attempts"] == 2


def test_finished_items_can_be_removed_and_unfinished_ones_cannot(
    client: Client, tmp_path: Path, rig: QueueRig
) -> None:
    rig.release.clear()
    first = add(client, video(tmp_path, "slow"))["added"][0]
    rig.started.wait(5)
    assert client.delete(f"/api/queue/items/{first['id']}").status_code == 409
    rig.release.set()
    add(client, video(tmp_path, "bad"))
    wait_for(client, {"slow": "done", "bad": "failed"})
    assert client.delete(f"/api/queue/items/{first['id']}").json() == {"removed": [first["id"]]}
    assert len(client.delete("/api/queue/finished").json()["removed"]) == 1
    assert client.get("/api/queue").json()["items"] == []


def test_an_item_left_running_by_a_dead_backend_is_queued_again_and_finishes(
    tmp_path: Path, rig: QueueRig, power: Power
) -> None:
    clip = video(tmp_path, "a")
    store = QueueStore(tmp_path / "data" / "queue.db")
    store.add(str(clip), "0" * 16, options_for("zh-TW"), AUDIO_S, 1)
    assert store.claim_next(2) is not None
    store.close()
    with open_client(make_app(tmp_path, rig, power)) as client:
        wait_for(client, {"a": "done"})
        assert client.get("/api/queue").json()["items"][0]["attempts"] == 2


def test_the_queue_file_keeps_items_order_settings_and_pause_across_a_restart(
    tmp_path: Path,
) -> None:
    path = tmp_path / "queue.db"
    store = QueueStore(path)
    first = store.add("a.mp4", "1" * 16, options_for("ja"), 3.0, 1)
    second = store.add("b.mp4", "2" * 16, options_for("ko"), None, 2)
    store.reorder([second.id])
    store.set_paused(True)
    store.set_settings(QueueSettings(OnDone.SLEEP, True))
    store.close()
    again = QueueStore(path)
    assert [i.id for i in again.items()] == [second.id, first.id]
    assert again.items()[1].options == options_for("ja")
    assert again.paused
    assert again.settings() == QueueSettings(OnDone.SLEEP, True)
    with pytest.raises(QueueError, match="already in the batch"):
        again.add("a.mp4", "1" * 16, options_for("ja"), 3.0, 3)
    again.add("a.mp4", "1" * 16, options_for("zh-TW"), 3.0, 3)


def test_sleep_and_shutdown_need_an_explicit_opt_in(client: Client) -> None:
    assert client.get("/api/queue/settings").json()["settings"] == {
        "on_done": "notify",
        "allow_power": False,
    }
    assert client.put("/api/queue/settings", json={"on_done": "shutdown"}).status_code == 422
    assert client.put("/api/queue/settings", json={"on_done": "x"}).status_code == 422
    ok = client.put("/api/queue/settings", json={"on_done": "sleep", "allow_power": True})
    assert ok.json()["settings"] == {"on_done": "sleep", "allow_power": True}


def test_the_default_on_done_only_notifies(tmp_path: Path, rig: QueueRig, power: Power) -> None:
    app = make_app(tmp_path, rig, power)
    with open_client(app) as client:
        add(client, video(tmp_path, "a"))
        wait_kind(app, "done")
        time.sleep(0.3)
        assert "countdown" not in kinds(app)
    assert power.calls == []


def test_sleep_runs_after_the_countdown(tmp_path: Path, rig: QueueRig, power: Power) -> None:
    app = make_app(tmp_path, rig, power, countdown_s=0.1)
    with open_client(app) as client:
        client.put("/api/queue/settings", json={"on_done": "sleep", "allow_power": True})
        add(client, video(tmp_path, "a"))
        wait_kind(app, "power")
    assert power.calls == [PowerAction.SLEEP]
    assert kinds(app).index("countdown") < kinds(app).index("power")


def test_a_cancelled_countdown_never_shuts_down(
    tmp_path: Path, rig: QueueRig, power: Power
) -> None:
    app = make_app(tmp_path, rig, power, countdown_s=30)
    with open_client(app) as client:
        client.put("/api/queue/settings", json={"on_done": "shutdown", "allow_power": True})
        add(client, video(tmp_path, "a"))
        wait_kind(app, "countdown")
        assert client.get("/api/queue").json()["countdown"] is True
        assert client.post("/api/queue/power/cancel").json() == {"cancelled": True}
        wait_kind(app, "countdown_cancelled")
        assert client.post("/api/queue/power/cancel").json() == {"cancelled": False}
    assert power.calls == []


def test_adding_work_during_a_countdown_cancels_it(
    tmp_path: Path, rig: QueueRig, power: Power
) -> None:
    app = make_app(tmp_path, rig, power, countdown_s=30)
    with open_client(app) as client:
        client.put("/api/queue/settings", json={"on_done": "sleep", "allow_power": True})
        add(client, video(tmp_path, "a"))
        wait_kind(app, "countdown")
        add(client, video(tmp_path, "b"))
        wait_for(client, {"a": "done", "b": "done"})
        wait_kind(app, "countdown_cancelled")
    assert power.calls == []


def test_without_a_power_executor_shutdown_does_nothing(tmp_path: Path, rig: QueueRig) -> None:
    app = make_app(tmp_path, rig, None)
    with open_client(app) as client:
        client.put("/api/queue/settings", json={"on_done": "shutdown", "allow_power": True})
        add(client, video(tmp_path, "a"))
        wait_kind(app, "power")
    power_event = next(e for e in app.state.queue.events.snapshot() if e.kind == "power")
    assert power_event.data["executed"] is False


def test_the_queue_events_follow_every_change(tmp_path: Path, rig: QueueRig, power: Power) -> None:
    app = make_app(tmp_path, rig, power)
    with open_client(app) as client:
        item = add(client, video(tmp_path, "a"))["added"][0]
        wait_for(client, {"a": "done"})
        client.put("/api/queue/order", json={"ids": [item["id"]]})
        client.delete("/api/queue/finished")
    seen = kinds(app)
    assert seen.count("item") >= 3
    assert {"order", "removed"} <= set(seen)
    first = app.state.queue.events.snapshot()[0]
    assert first.kind == "item" and first.data["state"] == "queued"


def timing(step: Step, audio_s: float, seconds: float) -> StepTiming:
    return StepTiming(step.value, audio_s, seconds)


def test_rates_are_seconds_per_audio_second_over_the_recent_runs() -> None:
    rates = step_rates(
        [timing(Step.ASR, 60, 6), timing(Step.ASR, 120, 6), timing(Step.TRANSLATE, 60, 30)]
    )
    assert rates[Step.ASR] == pytest.approx(12 / 180)
    assert rates[Step.TRANSLATE] == pytest.approx(0.5)


def item_of(store: QueueStore, name: str, audio_s: float | None) -> str:
    return store.add(name, name[:1] * 16, options_for("ja"), audio_s, 1).id


def test_eta_counts_the_rest_of_the_running_item_then_each_queued_one(tmp_path: Path) -> None:
    store = QueueStore(tmp_path / "q.db")
    running = item_of(store, "a", 100)
    unknown = item_of(store, "b", None)
    queued = item_of(store, "c", 100)
    store.claim_next(1)
    rates = step_rates([timing(Step.TRANSLATE, 100, 100)])
    live = live_from_overall("j", Step.TRANSLATE, 0.01 + 0.03 + 0.12 + 0.01 + 0.74 / 2)
    out = etas(store.items(), live, rates)
    assert out[running] == pytest.approx(50, abs=1)
    assert out[unknown] == out[running]
    assert out[queued] == pytest.approx(150, abs=1)
    assert etas(store.items(), None, {}) == {running: None, unknown: None, queued: None}


def test_eta_skips_paused_and_finished_items(tmp_path: Path) -> None:
    store = QueueStore(tmp_path / "q.db")
    a = item_of(store, "a", 10)
    b = item_of(store, "b", 10)
    store.move(a, [ItemState.QUEUED], ItemState.PAUSED, 1)
    store.finish(b, ItemState.DONE, 2, None)
    assert etas(store.items(), Live("j", None, 0, 0), {Step.ASR: 1.0}) == {}


COUNTDOWN_S = 1.0
PAST_COUNTDOWN_S = 1.6


def arm_countdown(client: Client, app: FastAPI, rig: QueueRig, tmp_path: Path) -> str:
    """Finish the queue under a sleep opt-in so a countdown is pending. Returns the item id."""
    client.put("/api/queue/settings", json={"on_done": "sleep", "allow_power": True})
    rig.release.clear()
    item_id = add(client, video(tmp_path, "a"))["added"][0]["id"]
    rig.started.wait(5)
    client.post(f"/api/queue/items/{item_id}/cancel")
    wait_for(client, {"a": "cancelled"})
    wait_kind(app, "countdown")
    return item_id


def never_fires(app: FastAPI, power: Power) -> None:
    time.sleep(PAST_COUNTDOWN_S)
    assert power.calls == []
    assert "power" not in kinds(app)
    assert "countdown_cancelled" in kinds(app)


def test_retrying_an_item_during_a_countdown_cancels_it(
    tmp_path: Path, rig: QueueRig, power: Power
) -> None:
    app = make_app(tmp_path, rig, power, countdown_s=COUNTDOWN_S)
    with open_client(app) as client:
        item_id = arm_countdown(client, app, rig, tmp_path)
        assert client.post(f"/api/queue/items/{item_id}/retry").status_code == 200
        wait_for(client, {"a": "running"})
        never_fires(app, power)
        assert states(client) == {"a": "running"}


def test_changing_the_settings_during_a_countdown_cancels_it(
    tmp_path: Path, rig: QueueRig, power: Power
) -> None:
    app = make_app(tmp_path, rig, power, countdown_s=COUNTDOWN_S)
    with open_client(app) as client:
        arm_countdown(client, app, rig, tmp_path)
        body = {"on_done": "notify", "allow_power": False}
        assert client.put("/api/queue/settings", json=body).status_code == 200
        never_fires(app, power)


def test_switching_the_action_during_a_countdown_cancels_it_too(
    tmp_path: Path, rig: QueueRig, power: Power
) -> None:
    app = make_app(tmp_path, rig, power, countdown_s=COUNTDOWN_S)
    with open_client(app) as client:
        arm_countdown(client, app, rig, tmp_path)
        body = {"on_done": "shutdown", "allow_power": True}
        assert client.put("/api/queue/settings", json=body).status_code == 200
        never_fires(app, power)


def test_resuming_the_queue_during_a_countdown_cancels_it(
    tmp_path: Path, rig: QueueRig, power: Power
) -> None:
    app = make_app(tmp_path, rig, power, countdown_s=COUNTDOWN_S)
    with open_client(app) as client:
        arm_countdown(client, app, rig, tmp_path)
        client.post("/api/queue/pause")
        assert "countdown_cancelled" not in kinds(app)
        client.post("/api/queue/resume")
        never_fires(app, power)


def test_a_countdown_that_was_not_cancelled_still_checks_before_it_fires(
    tmp_path: Path, rig: QueueRig, power: Power
) -> None:
    app = make_app(tmp_path, rig, power, countdown_s=COUNTDOWN_S)
    with open_client(app) as client:
        item_id = arm_countdown(client, app, rig, tmp_path)
        store = app.state.queue._store  # pyright: ignore[reportPrivateUsage]
        store.set_paused(True)
        store.to_end(item_id)
        never_fires(app, power)
        assert states(client) == {"a": "queued"}


def test_a_countdown_whose_opt_in_vanished_does_not_fire(
    tmp_path: Path, rig: QueueRig, power: Power
) -> None:
    app = make_app(tmp_path, rig, power, countdown_s=COUNTDOWN_S)
    with open_client(app) as client:
        arm_countdown(client, app, rig, tmp_path)
        app.state.queue._store.set_settings(QueueSettings())  # pyright: ignore[reportPrivateUsage]
        never_fires(app, power)


def test_cancel_reports_false_once_the_action_is_firing() -> None:
    inside, leave = threading.Event(), threading.Event()
    events: list[str] = []

    def executor(_action: PowerAction) -> None:
        inside.set()
        leave.wait(5)

    countdown = Countdown(executor, lambda kind, _d: events.append(kind), 0.0, lambda _a: True)
    countdown.start(PowerAction.SLEEP)
    assert inside.wait(5)
    assert countdown.cancel() is False
    leave.set()
    countdown.join()
    assert events == ["countdown", "power"]


def test_an_exception_in_one_loop_iteration_does_not_end_the_queue(
    tmp_path: Path, rig: QueueRig, power: Power, monkeypatch: pytest.MonkeyPatch
) -> None:
    real = QueueRunner._check_done  # pyright: ignore[reportPrivateUsage]
    crashed: list[bool] = []

    def flaky(self: QueueRunner) -> None:
        if not crashed:
            crashed.append(True)
            raise RuntimeError("boom")
        real(self)

    monkeypatch.setattr(QueueRunner, "_check_done", flaky)
    with open_client(make_app(tmp_path, rig, power)) as client:
        deadline = time.monotonic() + 5
        while not crashed and time.monotonic() < deadline:
            time.sleep(0.02)
        add(client, video(tmp_path, "a"))
        wait_for(client, {"a": "done"})


def test_an_item_deleted_under_a_command_is_not_found_not_a_crash(
    client: Client, tmp_path: Path
) -> None:
    add(client, video(tmp_path, "a"))
    wait_for(client, {"a": "done"})
    item_id = client.get("/api/queue").json()["items"][0]["id"]
    client.delete("/api/queue/finished")
    assert client.post(f"/api/queue/items/{item_id}/retry").status_code == 404


def test_invalid_settings_in_the_queue_file_fall_back_to_notify(tmp_path: Path) -> None:
    store = QueueStore(tmp_path / "queue.db")
    store._set_meta(  # pyright: ignore[reportPrivateUsage]
        "settings", '{"on_done": "shutdown", "allow_power": false}'
    )
    assert store.settings() == QueueSettings()
    store._set_meta("settings", "not json")  # pyright: ignore[reportPrivateUsage]
    assert store.settings() == QueueSettings()


def test_a_file_without_a_media_extension_is_not_queued(client: Client, tmp_path: Path) -> None:
    text = tmp_path / "videos" / "passwords.txt"
    text.parent.mkdir()
    text.write_text("x")
    body = add(client, text, video(tmp_path, "ok"))
    assert [Path(i["video_path"]).name for i in body["added"]] == ["ok.mp4"]
    [skipped] = body["skipped"]
    assert (skipped["path"], skipped["reason"]) == (str(text), "not a media file extension")
    assert [n["code"] for n in skipped["reason_notices"]] == ["batch.notMedia"]


def make_link(link: Path, target: Path) -> None:
    if os.name == "nt":
        done = subprocess.run(["cmd", "/c", "mklink", "/J", str(link), str(target)], check=False)
        if done.returncode != 0:
            pytest.skip("cannot make a junction")
    else:
        link.symlink_to(target, target_is_directory=True)


def test_a_recursive_scan_does_not_follow_a_junction_or_symlink(tmp_path: Path) -> None:
    root, outside = tmp_path / "root", tmp_path / "outside"
    (root / "sub").mkdir(parents=True)
    outside.mkdir()
    (root / "a.mp4").write_bytes(b"x")
    (root / "sub" / "b.mkv").write_bytes(b"x")
    (outside / "hidden.mp4").write_bytes(b"x")
    make_link(root / "link", outside)
    assert [p.name for p in scan_folder(root, True)] == ["a.mp4", "b.mkv"]


def test_a_folder_that_does_not_answer_is_skipped_quickly(
    client: Client, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    stuck = threading.Event()

    def hang(_folder: Path, _recursive: bool) -> list[Path]:
        stuck.wait(30)
        return []

    monkeypatch.setattr(queue_runner, "_walk", hang)
    monkeypatch.setattr(queue_runner, "SCAN_TIMEOUT_S", 0.2)
    started = time.monotonic()
    body = add(client, folders=[{"path": str(tmp_path)}])
    stuck.set()
    assert time.monotonic() - started < 5
    assert body["added"] == []
    assert "did not answer" in body["skipped"][0]["reason"]


def test_a_big_folder_is_probed_in_the_background_after_the_budget(
    client: Client, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(queue_runner, "PROBE_BUDGET_S", 0.0)
    body = add(client, video(tmp_path, "a"), video(tmp_path, "b"))
    assert len(body["added"]) == 2
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        items = client.get("/api/queue").json()["items"]
        if all(i["audio_s"] == AUDIO_S for i in items):
            return
        time.sleep(0.02)
    raise AssertionError("the durations were never probed")


def start_manual_job(client: Client, tmp_path: Path) -> str:
    path = video(tmp_path, "manual")
    pid = client.post("/api/projects", json={"video_path": str(path)}).json()["id"]
    response = client.post(f"/api/projects/{pid}/jobs", json={})
    assert response.status_code == 202, response.text
    return response.json()["id"]


def test_starting_a_job_by_hand_during_a_countdown_cancels_it(
    tmp_path: Path, rig: QueueRig, power: Power
) -> None:
    app = make_app(tmp_path, rig, power, countdown_s=COUNTDOWN_S)
    with open_client(app) as client:
        arm_countdown(client, app, rig, tmp_path)
        job_id = start_manual_job(client, tmp_path)
        wait_kind(app, "countdown_cancelled")
        never_fires(app, power)
        assert client.get(f"/api/jobs/{job_id}").json()["status"] == "running"
        rig.release.set()


def test_no_countdown_starts_while_a_job_started_by_hand_runs_and_it_starts_after(
    tmp_path: Path, rig: QueueRig, power: Power
) -> None:
    app = make_app(tmp_path, rig, power, countdown_s=0.05)
    with open_client(app) as client:
        client.put("/api/queue/settings", json={"on_done": "sleep", "allow_power": True})
        rig.release.clear()
        item_id = add(client, video(tmp_path, "a"))["added"][0]["id"]
        rig.started.wait(5)
        job_id = start_manual_job(client, tmp_path)
        client.post(f"/api/queue/items/{item_id}/cancel")
        wait_for(client, {"a": "cancelled"})
        time.sleep(1.5)
        assert client.get(f"/api/jobs/{job_id}").json()["status"] == "running"
        assert "countdown" not in kinds(app) and "done" not in kinds(app)
        rig.release.set()
        wait_kind(app, "power")
    assert power.calls == [PowerAction.SLEEP]
    assert client.get(f"/api/jobs/{job_id}").json()["status"] == "done"
    assert kinds(app).index("countdown") < kinds(app).index("power")


def test_the_final_power_check_counts_a_job_started_by_hand(
    tmp_path: Path, rig: QueueRig, power: Power
) -> None:
    app = make_app(tmp_path, rig, power, countdown_s=COUNTDOWN_S)
    with open_client(app) as client:
        arm_countdown(client, app, rig, tmp_path)
        app.state.jobs._submit_listeners.clear()  # pyright: ignore[reportPrivateUsage]
        start_manual_job(client, tmp_path)
        never_fires(app, power)
        rig.release.set()


def test_a_revoke_cannot_land_between_the_final_check_and_the_fire_decision() -> None:
    checking, proceed = threading.Event(), threading.Event()
    fired = threading.Event()

    def still_due(_action: PowerAction) -> bool:
        checking.set()
        proceed.wait(5)
        return True

    countdown = Countdown(lambda _a: fired.set(), lambda _k, _d: None, 0.0, still_due)
    countdown.start(PowerAction.SLEEP)
    assert checking.wait(5)
    revoked: list[bool] = []
    revoker = threading.Thread(target=lambda: revoked.append(countdown.cancel()))
    revoker.start()
    revoker.join(0.3)
    assert revoker.is_alive()
    proceed.set()
    revoker.join(5)
    countdown.join()
    assert revoked == [False]
    assert fired.is_set()


def test_a_revoke_that_wins_the_lock_stops_the_action() -> None:
    entered = threading.Event()
    calls: list[PowerAction] = []

    def still_due(_action: PowerAction) -> bool:
        entered.set()
        return True

    countdown = Countdown(calls.append, lambda _k, _d: None, 30.0, still_due)
    countdown.start(PowerAction.SLEEP)
    assert countdown.cancel() is True
    countdown.join()
    assert calls == [] and not entered.is_set()


def test_every_media_extension_is_queued_and_scanned(client: Client, tmp_path: Path) -> None:
    exts = sorted(MEDIA_EXTENSIONS)
    paths = [video(tmp_path, f"f{n}", ext) for n, ext in enumerate(exts)]
    assert {".wav", ".mp3", ".m4a", ".flac", ".ogg", ".aac", ".opus", ".mp4"} <= set(exts)
    body = add(client, *paths)
    assert len(body["added"]) == len(exts)
    assert body["skipped"] == []
    assert {p.suffix for p in scan_folder(paths[0].parent, False)} == set(exts)


def test_a_wav_item_runs_to_done(client: Client, tmp_path: Path) -> None:
    add(client, video(tmp_path, "talk", ".wav"))
    wait_for(client, {"talk": "done"})


def test_an_item_deleted_between_the_action_and_the_reply_is_not_found(
    client: Client, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    add(client, video(tmp_path, "bad"))
    wait_for(client, {"bad": "failed"})
    item_id = client.get("/api/queue").json()["items"][0]["id"]

    def gone(self: QueueRunner, item: str) -> dict[str, Any]:
        raise KeyError(item)

    monkeypatch.setattr(QueueRunner, "describe_item", gone)
    assert client.post(f"/api/queue/items/{item_id}/retry").status_code == 404
