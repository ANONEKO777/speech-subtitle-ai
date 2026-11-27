"""The sentences the window words in its own language: the registry, the channels that carry them
to the window, the files that store them, and the guards that keep new Chinese out of the sender."""

from __future__ import annotations

import ast
import json
import re
import sqlite3
import string
import threading
import time
from collections.abc import Callable
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest
from notice_scenarios import FIXTURE, collect
from test_api import GUARD, Rig, make_project, open_client
from test_pipeline import SETTINGS

from backend.core import notices, render, vc_runtime
from backend.core.audio import AudioError
from backend.core.jobs import JobOptions, OptionsError
from backend.core.model import Cue, Step
from backend.core.notices import REGISTRY, Notice, noticed, notices_of, to_json
from backend.core.pipeline import Ports, Settings
from backend.core.queue_store import ItemState, QueueStore
from backend.core.render import BurnBook, EncoderMissing, SubtitleLook
from backend.core.subtitle_io import parse_project, render_project
from backend.llm.local_server import ServerError
from backend.main import AppConfig, create_app
from backend.manager.secrets import UnavailableSecretStore
from backend.manager.selftest_store import SelfTestStore

ROOT = Path(__file__).resolve().parents[1]

VC = vc_runtime.NOTICE
"""One real notice to send through the channels."""


def test_the_checked_in_json_is_the_registry() -> None:
    checked_in = (ROOT / "app/src/i18n/notices.backend.json").read_text(encoding="utf-8")

    assert checked_in == notices.registry_file(), "run `python scripts/export_notices.py`"


def test_every_template_uses_exactly_the_parameters_it_declares() -> None:
    for code, template in REGISTRY.items():
        used = {name for _, name, _, _ in string.Formatter().parse(template.english) if name}
        assert used == set(template.params), code


def test_a_notice_refuses_a_missing_or_extra_parameter() -> None:
    with pytest.raises(TypeError):
        notices.VC_RUNTIME_MISSING()
    with pytest.raises(TypeError):
        notices.CLOUD_KEY_UNAVAILABLE(extra="x")


def test_the_scenarios_still_send_what_the_window_fixture_holds(tmp_path: Path) -> None:
    stored: dict[str, dict[str, Any]] = json.loads(FIXTURE.read_text(encoding="utf-8"))
    now = collect(tmp_path)

    assert now == {k: {"text": v["text"], "notices": v["notices"]} for k, v in stored.items()}


def test_every_code_has_a_scenario_so_the_window_proves_its_chinese() -> None:
    stored: dict[str, dict[str, Any]] = json.loads(FIXTURE.read_text(encoding="utf-8"))
    sent = {n["code"] for entry in stored.values() for n in entry["notices"]}

    assert sent == set(REGISTRY)


def test_every_notice_a_scenario_sends_is_inside_its_text() -> None:
    stored: dict[str, dict[str, Any]] = json.loads(FIXTURE.read_text(encoding="utf-8"))
    for name, entry in stored.items():
        assert entry["notices"], name
        for notice in entry["notices"]:
            assert notice["message"] in entry["text"], name


# Chinese, Japanese, Korean, Thai and full-width characters, as `app/src/i18n/notEnglish.ts`.
_NOT_ENGLISH = re.compile("[฀-๿ᄀ-ᇿ　-〿぀-ヿ㄰-㆏㐀-鿿ꥠ-꥿가-퟿＀-￯]")
_TRANSLATION_DATA = frozenset(
    {
        "core/fillers.py",
        "core/ja_routes.py",
        "core/ja_terms.py",
        "core/kana.py",
        "core/language_prompts.py",
        "core/languages.py",
        "core/segmenter.py",
        "core/source_langs.py",
        "core/subtitle_io.py",
        "core/translate.py",
        "core/unspaced.py",
        "core/zh_tw.py",
        "engines/mixed.py",
    }
)
"""Files whose Chinese, Japanese, Korean or Thai is what translation reads and writes. A sentence
for a person does not go in them: it goes in `backend/core/notices.py`, in English."""


def _docstrings(tree: ast.Module) -> set[int]:
    found: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            first = node.body[0] if node.body else None
            if isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant):
                found.add(id(first.value))
    return found


def _foreign_strings(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    skip = _docstrings(tree)
    return [
        f"{path.name}:{node.lineno}: {node.value[:60]!r}"
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant)
        and isinstance(node.value, str)
        and id(node) not in skip
        and _NOT_ENGLISH.search(node.value)
    ]


def test_the_backend_writes_no_sentence_in_another_script() -> None:
    backend = ROOT / "backend"
    found = [
        line
        for path in sorted(backend.rglob("*.py"))
        if path.relative_to(backend).as_posix() not in _TRANSLATION_DATA
        for line in _foreign_strings(path)
    ]

    assert not found, "send an English notice from backend/core/notices.py: " + "; ".join(found)


def test_the_shell_writes_no_text_in_another_script() -> None:
    found = [
        f"{path.name}:{number}: {line.strip()[:60]}"
        for path in sorted((ROOT / "app/src-tauri/src").rglob("*.rs"))
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1)
        if _NOT_ENGLISH.search(line)
    ]

    assert not found, "send a shell notice from app/src-tauri/src/notice.rs: " + "; ".join(found)


def test_a_wrapped_error_keeps_the_notice_its_words_still_hold() -> None:
    try:
        try:
            try:
                raise noticed(ServerError, VC)
            except ServerError as exc:
                raise ValueError(str(exc)) from exc
        except ValueError as exc:
            raise OptionsError(str(exc)) from exc
    except OptionsError as exc:
        assert notices_of(exc) == (VC,)
        assert notices_of(exc, f"OptionsError: {exc}") == (VC,)
        assert notices_of(exc, "something else was said") == ()


def test_an_error_with_no_notice_has_none() -> None:
    assert notices_of(RuntimeError("boom")) == ()


@pytest.mark.parametrize("stored", [None, "x", 3, [1], [{"code": 1, "message": "m"}], [{}]])
def test_damaged_stored_notices_are_left_out(stored: object) -> None:
    assert notices.from_json(stored) == ()


# What an earlier version stored: the Chinese sentence as a plain string.
OLD = "EngineUnavailableError: 這台電腦缺少 Microsoft Visual C++ 可轉散發套件（x64）。"


def _old_project() -> str:
    steps = {
        "audio": {"status": "failed", "updated_at_ms": 5, "error": OLD},
    }
    doc = {"schema_version": 1, "video_path": "talk.mp4", "steps": steps}
    return json.dumps(doc, ensure_ascii=False, indent=2) + "\n"


def test_a_project_file_of_an_earlier_version_loads_and_shows_its_error_as_it_was() -> None:
    project = parse_project(_old_project())

    assert project.steps[Step.AUDIO].error == OLD
    assert "error_notices" not in render_project(project)


EARLIER_STEP_KEYS = {"status", "updated_at_ms", "error", "key", "degraded"}
"""The keys a saved step may have for the builds before notices. Their parser refuses any other, and
the project is then gone from their library."""


def test_a_project_file_that_holds_error_notices_loads_and_saves_without_them() -> None:
    doc = json.loads(_old_project())
    error = f"ServerError: {VC.message}"
    doc["steps"]["audio"] |= {"error": error, "error_notices": to_json([VC])}

    project = parse_project(json.dumps(doc))

    assert project.steps[Step.AUDIO].error == error
    assert set(json.loads(render_project(project))["steps"]["audio"]) <= EARLIER_STEP_KEYS


def _old_queue(path: Path) -> None:
    """A `queue.db` as the earlier version made it, with one failed item."""
    db = sqlite3.connect(path)
    db.executescript(
        """CREATE TABLE items (id TEXT PRIMARY KEY, position INTEGER NOT NULL,
        video_path TEXT NOT NULL, project_id TEXT NOT NULL, options TEXT NOT NULL,
        state TEXT NOT NULL, created_at_ms INTEGER NOT NULL, started_at_ms INTEGER,
        finished_at_ms INTEGER, attempts INTEGER NOT NULL DEFAULT 0, last_error TEXT,
        audio_s REAL);"""
    )
    options = json.dumps(
        {
            "engine": "whispercpp",
            "llm": "q",
            "llm_model": None,
            "cpu": False,
            "glossary": [],
            "summary_en": False,
            "batch_size": 8,
            "target_lang": "zh-TW",
        }
    )
    db.execute(
        "INSERT INTO items VALUES ('a', 0, 'talk.mp4', 'p', ?, 'failed', 1, 2, 3, 1, ?, NULL)",
        (options, OLD),
    )
    db.commit()
    db.close()


def test_a_queue_of_an_earlier_version_opens_and_shows_its_error_as_it_was(tmp_path: Path) -> None:
    _old_queue(tmp_path / "queue.db")

    for _ in range(2):
        store = QueueStore(tmp_path / "queue.db")
        item = store.get("a")
        store.close()
        assert item is not None
        assert (item.last_error, item.last_error_notices) == (OLD, ())


def test_the_queue_keeps_the_code_of_a_stored_error_until_the_item_runs_again(
    tmp_path: Path,
) -> None:
    _old_queue(tmp_path / "queue.db")
    store = QueueStore(tmp_path / "queue.db")
    store.finish("a", ItemState.FAILED, 9, f"ServerError: {VC.message}", (VC,))
    store.close()
    store = QueueStore(tmp_path / "queue.db")
    item = store.get("a")
    assert item is not None and item.last_error_notices == (VC,)

    store.to_end("a")
    claimed = store.claim_next(10)
    store.close()

    assert claimed is not None
    assert (claimed.last_error, claimed.last_error_notices) == (None, ())


def test_a_self_test_file_of_an_earlier_version_loads_as_it_was(tmp_path: Path) -> None:
    stage = {
        "stage": "asr",
        "runtime_id": "r",
        "device": "cpu",
        "installed": True,
        "ok": False,
        "seconds": 0.1,
        "detail": OLD,
    }
    old = {
        "at_ms": 1,
        "profile": "cpu",
        "ok": False,
        "device": "cpu",
        "stages": [stage],
        "fallback": {"reason": OLD, "failed": [stage]},
        "seconds": 0.2,
        "message": OLD,
    }
    (tmp_path / "selftest.json").write_text(json.dumps(old, ensure_ascii=False), encoding="utf-8")
    store = SelfTestStore(tmp_path)

    report = store.load()

    assert report is not None and report.fallback is not None
    assert (report.message, report.message_notices) == (OLD, ())
    assert (report.fallback.reason, report.fallback.reason_notices) == (OLD, ())
    assert (report.stages[0].detail, report.stages[0].detail_notices) == (OLD, ())


def test_a_stored_self_test_keeps_its_codes(tmp_path: Path) -> None:
    store = SelfTestStore(tmp_path)
    test_a_self_test_file_of_an_earlier_version_loads_as_it_was(tmp_path)
    old = store.load()
    assert old is not None and old.fallback is not None
    fallback = old.fallback
    stage = replace(old.stages[0], detail=VC.message, detail_notices=(VC,))
    new = replace(
        old,
        stages=(stage,),
        fallback=replace(fallback, failed=(stage,), reason=VC.message, reason_notices=(VC,)),
        message=VC.message,
        message_notices=(VC,),
    )

    store.save(new)

    assert store.load() == new


# The channels that reach the window.


def _until(check: Callable[[], Any]) -> Any:
    end = time.monotonic() + 20
    while time.monotonic() < end:
        if found := check():
            return found
        time.sleep(0.01)
    raise AssertionError("timed out")


class _NoRuntime(Rig):
    """The resolver refuses the way a PC with no built program does, wrapped twice."""

    refuse = True

    def resolve(self, options: JobOptions, folder: Path) -> tuple[Settings, Ports]:
        if self.refuse:
            try:
                raise noticed(ServerError, VC)
            except ServerError as exc:
                raise OptionsError(str(exc)) from exc
        return SETTINGS, replace(self.ports(), extract_audio=self._broken)

    def _broken(self, video: Path, wav: Path, cancel: threading.Event) -> None:
        raise noticed(AudioError, VC)


def test_a_refused_request_carries_the_notice_beside_an_unchanged_detail(tmp_path: Path) -> None:
    video = tmp_path / "talk.mp4"
    video.write_bytes(b"x")
    with open_client(create_app(AppConfig(tmp_path / "data", GUARD, _NoRuntime().resolve))) as c:
        reply = c.post(f"/api/projects/{make_project(c, video)}/jobs", json={})
        plain = c.get("/api/jobs/nothing")

    assert reply.status_code == 422
    assert reply.json() == {"detail": VC.message, "notices": to_json([VC])}
    assert plain.json() == {"detail": "unknown job 'nothing'"}


def test_a_refused_key_save_carries_the_notice(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    app = create_app(AppConfig(tmp_path / "data", GUARD, _NoRuntime().resolve))
    app.state.manager = replace(app.state.manager, secrets=UnavailableSecretStore())
    llm = {
        "source": "cloud",
        "cloud_url": "https://api.example.test/v1",
        "cloud_model": "m",
        "cloud_consent": True,
        "api_key": "sk-secret-123",
    }
    with open_client(app) as c:
        reply = c.put("/api/settings", json={"llm": llm})

    assert [n["code"] for n in reply.json()["notices"]] == ["secrets.cloudKeyUnavailable"]
    assert reply.json()["detail"] == reply.json()["notices"][0]["message"]


def test_a_failed_job_sends_the_notice_in_its_event_and_its_state(tmp_path: Path) -> None:
    video = tmp_path / "talk.mp4"
    video.write_bytes(b"x")
    rig = _NoRuntime()
    rig.refuse = False
    with open_client(create_app(AppConfig(tmp_path / "data", GUARD, rig.resolve))) as c:
        pid = make_project(c, video)
        job = c.post(f"/api/projects/{pid}/jobs", json={}).json()

        def failed() -> Any:
            state = c.get(f"/api/jobs/{job['id']}").json()
            return state if state["status"] == "failed" else None

        state = _until(failed)
        events = c.get(f"/api/jobs/{job['id']}/events").text

    assert state["error"] == f"audio: {VC.message}"
    assert state["error_notices"] == to_json([VC])
    data = next(b for b in events.split("\n\n") if "event: failed" in b).split("data: ")[1]
    assert json.loads(data)["error_notices"] == to_json([VC])


def test_a_step_that_failed_with_a_notice_is_saved_as_an_earlier_build_reads_it(
    tmp_path: Path,
) -> None:
    video = tmp_path / "talk.mp4"
    video.write_bytes(b"x")
    rig = _NoRuntime()
    rig.refuse = False
    with open_client(create_app(AppConfig(tmp_path / "data", GUARD, rig.resolve))) as c:
        pid = make_project(c, video)
        job = c.post(f"/api/projects/{pid}/jobs", json={}).json()
        _until(lambda: c.get(f"/api/jobs/{job['id']}").json()["status"] == "failed")

    saved = (tmp_path / "data" / "projects" / pid / "project.json").read_text(encoding="utf-8")
    steps = json.loads(saved)["steps"]

    assert steps["audio"]["error"] == f"AudioError: {VC.message}"
    for name, step in steps.items():
        assert set(step) <= EARLIER_STEP_KEYS, name


def test_a_failed_queue_item_stores_the_notice_inside_its_error(tmp_path: Path) -> None:
    video = tmp_path / "talk.mp4"
    video.write_bytes(b"x")
    app = create_app(
        AppConfig(tmp_path / "data", GUARD, _NoRuntime().resolve, probe=lambda _p: 1.0)
    )
    with open_client(app) as c:
        c.post("/api/queue/items", json={"items": [{"path": str(video)}]})

        def failed() -> Any:
            item = c.get("/api/queue").json()["items"][0]
            return item if item["state"] == "failed" else None

        item = _until(failed)

    assert item["last_error"] == f"OptionsError: {VC.message}"
    assert item["last_error_notices"] == to_json([VC])


def test_a_failed_burn_keeps_the_notice(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def no_encoder(_ffmpeg: str, _system: str | None = None) -> tuple[str, ...]:
        raise noticed(EncoderMissing, notices.NO_H264_WINDOWS())

    monkeypatch.setattr(render, "_video_encoder", no_encoder)

    def ffmpeg(_name: str) -> Path:
        return Path("ffmpeg")

    def aac(_video: Path) -> str:
        return "aac"

    monkeypatch.setattr(render, "find_tool", ffmpeg)
    monkeypatch.setattr(render, "_audio_codec", aac)
    book = BurnBook()
    video = tmp_path / "talk.mp4"
    video.write_bytes(b"x")

    job = book.start(
        video,
        tmp_path / "out.mp4",
        cues=[Cue(1, 0, 1000, "a", "b")],
        wrap=render.Wrap.CJK,
        look=SubtitleLook("both", True, 0.05, "#ffffff"),
        offset_ms=0,
        start_s=0.0,
        duration_s=1.0,
    )
    _until(lambda: job.state != "running")
    book.shutdown()

    assert job.error == notices.NO_H264_WINDOWS().message
    assert job.error_notices == (notices.NO_H264_WINDOWS(),)


def test_a_notice_is_plain_data() -> None:
    sent = Notice("c", {"a": ["b"]}, "m")

    assert notices.from_json(json.loads(json.dumps(to_json([sent])))) == (sent,)
