"""`GET /api/work` lists what an app update would cut off, since installing stops the backend."""

from __future__ import annotations

import threading
from pathlib import Path
from typing import Any

from manage_support import Rig

from backend.manager.profiles import WHISPER_TURBO
from backend.manager.storage_move import MoveState, MoveStatus


def _work(rig: Rig) -> list[str]:
    reply = rig.client.get("/api/work")
    assert reply.status_code == 200, reply.text
    return reply.json()["work"]


def test_an_idle_backend_holds_nothing(rig: Rig) -> None:
    assert _work(rig) == []


def test_a_pipeline_job_holds_the_install(rig: Rig) -> None:
    rig.jobs.running = True
    assert _work(rig) == ["job"]


def test_a_model_download_holds_the_install_until_it_ends(rig: Rig) -> None:
    rig.origin.pause_per_piece = 0.3
    assert rig.client.post(f"/api/models/{WHISPER_TURBO}/download").status_code == 200

    assert _work(rig) == ["download"]
    rig.origin.pause_per_piece = 0.0
    rig.wait_jobs()
    assert _work(rig) == []


def test_a_running_self_test_holds_the_install_until_it_ends(rig: Rig) -> None:
    rig.install_profile("gpu-24gb")
    entered, release = threading.Event(), threading.Event()

    def slow(stage: str, program: Path, model: Path, device: Any, timeout_s: float) -> str:
        entered.set()
        release.wait(10)
        return f"{stage} ok"

    rig.probe = slow
    replies: list[int] = []
    runner = threading.Thread(
        target=lambda: replies.append(rig.client.post("/api/runtimes/selftest").status_code)
    )
    runner.start()
    assert entered.wait(10)

    assert _work(rig) == ["selftest"]
    release.set()
    runner.join(10)
    assert replies == [200]
    assert _work(rig) == []


def test_a_models_folder_move_holds_the_install(rig: Rig) -> None:
    rig.ctx.mover.status = lambda: MoveStatus(state=MoveState.RUNNING)  # type: ignore[method-assign]
    assert _work(rig) == ["move"]


def test_a_burn_in_export_holds_the_install(rig: Rig) -> None:
    class Burns:
        def running(self) -> object:
            return object()

    rig.client.app.state.burns = Burns()
    assert _work(rig) == ["export"]


def test_every_kind_is_listed_in_one_fixed_order(rig: Rig) -> None:
    rig.jobs.running = True
    rig.ctx.mover.status = lambda: MoveStatus(state=MoveState.RUNNING)  # type: ignore[method-assign]
    assert _work(rig) == ["job", "move"]
