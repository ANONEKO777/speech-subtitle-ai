from __future__ import annotations

import json
import re
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from collections.abc import Callable, Generator, Sequence
from pathlib import Path
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from test_pipeline import SETTINGS, Fakes

from backend.api.auth import GuardConfig
from backend.core.jobs import (
    EventKind,
    Job,
    JobBook,
    JobOptions,
    JobStatus,
    OptionsError,
    ProjectBusy,
)
from backend.core.model import Step, Word
from backend.core.pipeline import Ports, Progress, Settings
from backend.core.vad import Chunk
from backend.main import AppConfig, create_app

TOKEN = "t" * 43
AUTH = {"Authorization": f"Bearer {TOKEN}"}
APP_ORIGIN = "http://tauri.localhost"
EDIT = "人工校對過的第一句。"
GUARD = GuardConfig(TOKEN, frozenset({"testserver"}))
Client = Any


def open_client(app: FastAPI, headers: dict[str, str] | None = AUTH) -> Client:
    return TestClient(app, headers=headers)


class Rig(Fakes):
    """Fake engines whose ASR can be held open until the test says go."""

    def __init__(self) -> None:
        super().__init__()
        self.hold = False
        self.in_asr = threading.Event()
        self.seen: list[JobOptions] = []

    def transcribe(
        self,
        wav: Path,
        chunks: Sequence[Chunk],
        progress: Callable[[float], None],
        cancel: threading.Event,
    ) -> list[Word]:
        self.in_asr.set()
        while self.hold:
            progress(0.5)
            time.sleep(0.005)
        return super().transcribe(wav, chunks, progress, cancel)

    def resolve(self, options: JobOptions, folder: Path) -> tuple[Settings, Ports]:
        self.seen.append(options)
        if options.engine == "nope":
            raise OptionsError("unknown engine 'nope'")
        return SETTINGS, self.ports()


@pytest.fixture
def rig() -> Rig:
    return Rig()


@pytest.fixture
def client(tmp_path: Path, rig: Rig) -> Generator[Client]:
    app = create_app(AppConfig(tmp_path / "data", GUARD, rig.resolve))
    with open_client(app) as c:
        yield c


@pytest.fixture
def video(tmp_path: Path) -> Path:
    path = tmp_path / "talk.mp4"
    path.write_bytes(b"not a real video")
    return path


def make_project(client: Client, video: Path) -> str:
    response = client.post("/api/projects", json={"video_path": str(video)})
    assert response.status_code == 201, response.text
    return response.json()["id"]


def start_job(client: Client, pid: str, **body: Any) -> dict[str, Any]:
    response = client.post(f"/api/projects/{pid}/jobs", json=body)
    assert response.status_code == 202, response.text
    return response.json()


def events(client: Client, job_id: str) -> list[tuple[str, dict[str, Any]]]:
    out: list[tuple[str, dict[str, Any]]] = []
    with client.stream("GET", f"/api/jobs/{job_id}/events") as response:
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/event-stream")
        name = ""
        for line in response.iter_lines():
            if line.startswith("event: "):
                name = line.removeprefix("event: ")
            elif line.startswith("data: "):
                out.append((name, json.loads(line.removeprefix("data: "))))
    return out


def wait_status(client: Client, job_id: str, want: str) -> dict[str, Any]:
    deadline = time.monotonic() + 10
    job: dict[str, Any] = {}
    while time.monotonic() < deadline:
        job = client.get(f"/api/jobs/{job_id}").json()
        if job["status"] == want:
            return job
        time.sleep(0.01)
    raise AssertionError(f"job never became {want}: {job}")


def test_every_route_needs_the_token_including_the_mounted_download_routes(
    client: Client,
) -> None:
    for method, path in (
        ("GET", "/api/health"),
        ("GET", "/api/registry"),
        ("GET", "/api/downloads"),
        ("GET", "/api/models"),
        ("POST", "/api/models/silero_vad/download"),
        ("PUT", "/api/storage"),
        ("POST", "/api/projects"),
        ("GET", "/api/jobs/x/events"),
    ):
        bare = client.request(method, path, headers={"Authorization": ""})
        assert bare.status_code == 401, path
        wrong = client.request(method, path, headers={"Authorization": "Bearer nope"})
        assert wrong.status_code == 401, path
    assert client.get("/api/health").json() == {"status": "ok"}


def test_a_cross_origin_post_cannot_start_a_download_even_with_the_token(
    client: Client,
) -> None:
    before = client.get("/api/downloads").json()
    evil = {"Origin": "http://evil.test"}
    assert client.post("/api/models/silero_vad/download", headers=evil).status_code == 403
    simple = client.post("/api/models/silero_vad/download", headers={**evil, "Authorization": ""})
    assert simple.status_code == 403
    assert client.get("/api/downloads").json() == before


def test_a_wrong_host_is_refused_and_an_app_origin_gets_cors_headers(client: Client) -> None:
    assert client.get("/api/health", headers={"Host": "evil.test"}).status_code == 403
    ok = client.get("/api/health", headers={"Origin": APP_ORIGIN})
    assert ok.headers["access-control-allow-origin"] == APP_ORIGIN
    pre = client.options(
        "/api/projects",
        headers={
            "Origin": APP_ORIGIN,
            "Access-Control-Request-Method": "POST",
            "Authorization": "",
        },
    )
    assert pre.status_code == 204
    assert pre.headers["access-control-allow-origin"] == APP_ORIGIN
    evil = client.options(
        "/api/projects",
        headers={"Origin": "http://evil.test", "Access-Control-Request-Method": "POST"},
    )
    assert evil.status_code == 403
    assert "access-control-allow-origin" not in evil.headers


def test_the_token_in_the_query_works_for_events_only(client: Client, video: Path) -> None:
    pid = make_project(client, video)
    job = start_job(client, pid)
    bare = open_client(client.app, {})
    with bare.stream("GET", f"/api/jobs/{job['id']}/events?token={TOKEN}") as response:
        assert response.status_code == 200
        response.read()
    assert bare.get(f"/api/projects/{pid}?token={TOKEN}").status_code == 401


def test_creating_a_project_is_idempotent_and_validates_the_video(
    client: Client, video: Path, tmp_path: Path
) -> None:
    pid = make_project(client, video)
    again = client.post("/api/projects", json={"video_path": str(video)})
    assert (again.status_code, again.json()["id"]) == (200, pid)
    info = client.get(f"/api/projects/{pid}").json()
    assert info["video_path"] == str(video.absolute())
    assert set(info["steps"]) == {
        "audio",
        "vad",
        "asr",
        "segment",
        "translate",
        "export",
        "summarize",
    }
    assert info["active_job"] is None
    assert client.post("/api/projects", json={"video_path": "relative.mp4"}).status_code == 422
    missing = {"video_path": str(tmp_path / "no.mp4")}
    assert client.post("/api/projects", json=missing).status_code == 422
    text = tmp_path / "notes.txt"
    text.write_text("x")
    assert client.post("/api/projects", json={"video_path": str(text)}).status_code == 422
    audio = tmp_path / "talk.wav"
    audio.write_bytes(b"x")
    assert client.post("/api/projects", json={"video_path": str(audio)}).status_code == 201
    assert client.get("/api/projects/0123456789abcdef").status_code == 404
    assert client.get("/api/projects/..%2F..").status_code == 404


def test_a_job_runs_the_pipeline_and_the_events_arrive_in_order_ending_with_done(
    client: Client, video: Path, rig: Rig
) -> None:
    pid = make_project(client, video)
    job = start_job(client, pid, engine="whispercpp", glossary=[{"term": "Foo", "zh": "富"}])
    assert rig.seen[0].glossary[0].term == "Foo"
    stream = events(client, job["id"])
    kinds = [kind for kind, _ in stream]
    assert kinds[0] == "status" and kinds[-1] == "done"
    assert set(kinds) == {"status", "progress", "done"}
    assert [d["seq"] for _, d in stream] == list(range(len(stream)))
    steps = [d["step"] for kind, d in stream if kind == "progress"]
    order = ["audio", "vad", "asr", "segment", "translate", "export", "summarize"]
    assert sorted(set(steps), key=steps.index) == order
    overall = [d["overall"] for kind, d in stream if kind != "status"]
    assert overall == sorted(overall) and overall[-1] == 1.0
    assert client.get(f"/api/jobs/{job['id']}").json()["status"] == "done"
    info = client.get(f"/api/projects/{pid}").json()
    assert all(s["status"] == "done" for s in info["steps"].values())
    assert {"zh-TW.srt", "summary.md"} <= set(info["files"])
    assert events(client, job["id"]) == stream


def test_a_late_subscriber_resumes_after_last_event_id(client: Client, video: Path) -> None:
    job = start_job(client, make_project(client, video))
    full = events(client, job["id"])
    with client.stream(
        "GET", f"/api/jobs/{job['id']}/events", headers={"Last-Event-ID": "3"}
    ) as response:
        text = "".join(response.iter_text())
    assert text.startswith("id: 4\n")
    assert text.count("id: ") == len(full) - 4


def test_cancel_stops_a_running_job_and_a_rerun_finishes(
    client: Client, video: Path, rig: Rig
) -> None:
    pid = make_project(client, video)
    rig.hold = True
    job = start_job(client, pid)
    assert rig.in_asr.wait(5)
    cancelled = client.post(f"/api/jobs/{job['id']}/cancel").json()
    assert cancelled["cancel_requested"] is True
    final = wait_status(client, job["id"], "cancelled")
    assert final["error"] is None
    assert events(client, job["id"])[-1][0] == "cancelled"
    assert client.get(f"/api/projects/{pid}").json()["active_job"] is None
    assert client.post(f"/api/jobs/{job['id']}/cancel").json()["status"] == "cancelled"
    rig.hold = False
    second = start_job(client, pid)
    assert events(client, second["id"])[-1][0] == "done"
    assert rig.extracted == 1


def test_a_second_job_on_the_same_project_gets_409(client: Client, video: Path, rig: Rig) -> None:
    pid = make_project(client, video)
    rig.hold = True
    job = start_job(client, pid)
    assert rig.in_asr.wait(5)
    second = client.post(f"/api/projects/{pid}/jobs", json={})
    assert second.status_code == 409
    assert job["id"] in second.json()["detail"]
    other = video.with_name("other.mp4")
    other.write_bytes(b"x")
    queued = start_job(client, make_project(client, other))
    assert queued["status"] == "queued"
    assert client.post(f"/api/jobs/{queued['id']}/cancel").json()["status"] == "cancelled"
    rig.hold = False
    client.post(f"/api/jobs/{job['id']}/cancel")
    wait_status(client, job["id"], "cancelled")


def test_bad_options_and_unknown_things_are_refused(client: Client, video: Path) -> None:
    pid = make_project(client, video)
    url = f"/api/projects/{pid}/jobs"
    assert client.post(url, json={"engine": "nope"}).status_code == 422
    assert client.post(url, json={"asr_bin": "x.exe"}).status_code == 422
    assert client.post(url, json={"batch_size": 0}).status_code == 422
    assert client.post("/api/projects/0123456789abcdef/jobs", json={}).status_code == 404
    assert client.get("/api/jobs/nope").status_code == 404
    assert client.get("/api/jobs/nope/events").status_code == 404
    assert client.post("/api/jobs/nope/cancel").status_code == 404
    assert client.get("/openapi.json").status_code == 404


def test_a_failed_step_ends_the_stream_with_failed(client: Client, video: Path, rig: Rig) -> None:
    rig.transcribe_error = RuntimeError("engine blew up")
    job = start_job(client, make_project(client, video))
    kind, data = events(client, job["id"])[-1]
    assert kind == "failed" and data["step"] == "asr" and "engine blew up" in data["error"]
    assert client.get(f"/api/jobs/{job['id']}").json()["status"] == "failed"


def test_subtitles_and_summary_follow_the_files(client: Client, video: Path) -> None:
    pid = make_project(client, video)
    assert client.get(f"/api/projects/{pid}/subtitles?lang=en").status_code == 409
    assert client.get(f"/api/projects/{pid}/summary").status_code == 409
    events(client, start_job(client, pid)["id"])
    folder = Path(client.get(f"/api/projects/{pid}").json()["folder"])
    summary = client.get(f"/api/projects/{pid}/summary")
    assert summary.content == (folder / "summary.md").read_bytes()
    assert summary.headers["content-type"].startswith("text/markdown")
    assert client.get(f"/api/projects/{pid}/summary?lang=en").status_code == 409
    for lang, name in (("en", "en.srt"), ("zh", "zh-TW.srt")):
        got = client.get(f"/api/projects/{pid}/subtitles?lang={lang}&format=srt")
        assert got.content == (folder / name).read_bytes()
    vtt = client.get(f"/api/projects/{pid}/subtitles?lang=bilingual&format=vtt")
    assert vtt.content == (folder / "bilingual.vtt").read_bytes()
    ass = client.get(f"/api/projects/{pid}/subtitles?lang=bilingual&format=ass")
    assert ass.content == (folder / "bilingual.ass").read_bytes()
    assert client.get(f"/api/projects/{pid}/subtitles?lang=zh&format=ass").status_code == 422
    assert client.get(f"/api/projects/{pid}/subtitles?lang=fr").status_code == 422
    cues = client.get(f"/api/projects/{pid}/subtitles?format=json").json()["cues"]
    assert cues and all(c["zh"] for c in cues)


def test_put_subtitles_updates_project_json_and_the_chinese_srt(
    client: Client, video: Path
) -> None:
    pid = make_project(client, video)
    events(client, start_job(client, pid)["id"])
    folder = Path(client.get(f"/api/projects/{pid}").json()["folder"])
    before = (folder / "project.json").read_text(encoding="utf-8")
    cues = client.get(f"/api/projects/{pid}/subtitles?format=json").json()["cues"]
    cues[0]["zh"] = EDIT
    time.sleep(0.01)
    url = f"/api/projects/{pid}/subtitles"
    response = client.put(url, json={"cues": cues})
    assert response.status_code == 200, response.text
    for name in ("zh-TW.srt", "subs.zh-TW.json", "bilingual.ass", "bilingual.vtt"):
        assert EDIT in (folder / name).read_text(encoding="utf-8"), name
    assert (folder / "project.json").read_text(encoding="utf-8") != before
    assert EDIT in client.get(f"{url}?lang=zh&format=srt").text
    events(client, start_job(client, pid)["id"])
    assert EDIT in (folder / "zh-TW.srt").read_text(encoding="utf-8")
    assert client.put(url, json={"cues": cues[1:]}).status_code == 422
    assert client.put(url, json={"cues": [{**cues[0], "zh": " x"}, *cues[1:]]}).status_code == 422
    inverted = [{**cues[0], "start_ms": 9, "end_ms": 1}, *cues[1:]]
    assert client.put(url, json={"cues": inverted}).status_code == 422


def test_put_subtitles_is_refused_before_translation_and_while_a_job_runs(
    client: Client, video: Path, rig: Rig
) -> None:
    pid = make_project(client, video)
    url = f"/api/projects/{pid}/subtitles"
    body = {"cues": [{"id": 0, "start_ms": 0, "end_ms": 1000, "en": "a", "zh": "甲"}]}
    assert client.put(url, json=body).status_code == 409
    rig.hold = True
    job = start_job(client, pid)
    assert rig.in_asr.wait(5)
    assert client.put(url, json=body).status_code == 409
    rig.hold = False
    client.post(f"/api/jobs/{job['id']}/cancel")
    wait_status(client, job["id"], "cancelled")


def test_a_restarted_service_finds_the_project_and_resumes_from_the_cache(
    tmp_path: Path, video: Path
) -> None:
    first, second = Rig(), Rig()
    data = tmp_path / "data"
    with open_client(create_app(AppConfig(data, GUARD, first.resolve))) as one:
        pid = make_project(one, video)
        first.transcribe_error = RuntimeError("killed here")
        events(one, start_job(one, pid)["id"])
    with open_client(create_app(AppConfig(data, GUARD, second.resolve))) as two:
        again = two.post("/api/projects", json={"video_path": str(video)})
        assert (again.status_code, again.json()["id"]) == (200, pid)
        assert two.get(f"/api/projects/{pid}").json()["steps"]["vad"]["status"] == "done"
        assert events(two, start_job(two, pid)["id"])[-1][0] == "done"
    assert (second.extracted, second.split) == (0, 0)
    assert second.transcribed == 1


def test_shutdown_cancels_a_running_job(tmp_path: Path, video: Path) -> None:
    rig = Rig()
    app = create_app(AppConfig(tmp_path / "data", GUARD, rig.resolve))
    with open_client(app) as c:
        pid = make_project(c, video)
        rig.hold = True
        job = start_job(c, pid)
        assert rig.in_asr.wait(5)
    assert app.state.jobs.get(job["id"]).status == "cancelled"


def test_the_real_service_prints_ready_within_three_seconds_and_checks_the_token(
    tmp_path: Path,
) -> None:
    started = time.monotonic()
    proc = subprocess.Popen(
        [sys.executable, "-m", "backend.main", "--user-data", str(tmp_path)],
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
        cwd=Path(__file__).parent.parent,
    )
    try:
        assert proc.stdout is not None
        line = proc.stdout.readline().strip()
        assert time.monotonic() - started < 3, line
        match = re.fullmatch(r"READY port=(\d+) token=([\w-]{43})", line)
        assert match, line
        base = f"http://127.0.0.1:{match[1]}/api/health"

        def get(headers: dict[str, str]) -> int:
            try:
                with urllib.request.urlopen(urllib.request.Request(base, headers=headers)) as r:
                    return r.status
            except urllib.error.HTTPError as exc:
                return exc.code

        assert get({}) == 401
        assert get({"Authorization": f"Bearer {match[2]}"}) == 200
        assert get({"Authorization": f"Bearer {match[2]}", "Origin": "http://evil.test"}) == 403
        assert get({"Authorization": f"Bearer {match[2]}", "Host": "evil.test"}) == 403
    finally:
        proc.kill()
        proc.wait()


def test_overall_progress_never_goes_back_when_a_step_restarts_its_counter() -> None:
    job = Job("p")
    job.start()
    for step, fraction in ((Step.SUMMARIZE, 0.0), (Step.SUMMARIZE, 0.9), (Step.SUMMARIZE, 0.1)):
        job.on_progress(Progress(step, fraction))
    job.on_progress(Progress(Step.TRANSLATE, 0.5))
    seen = [
        float(str(e.data["overall"])) for e in job.log.snapshot() if e.kind == EventKind.PROGRESS
    ]
    assert seen == sorted(seen)
    assert seen[-1] == seen[2]


def test_the_book_refuses_a_second_unfinished_job_for_one_project(
    tmp_path: Path, video: Path
) -> None:
    rig, book = Rig(), JobBook()
    rig.hold = True
    settings, ports = rig.resolve(JobOptions("e", "l", None, False, (), False, 8), tmp_path)
    first = book.submit("p", video, tmp_path / "a", settings, ports)
    with pytest.raises(ProjectBusy) as busy:
        book.submit("p", video, tmp_path / "a", settings, ports)
    assert busy.value.job_id == first.id
    assert book.submit("q", video, tmp_path / "b", settings, ports).status is JobStatus.QUEUED
    rig.hold = False
    book.shutdown()
    assert first.status is JobStatus.CANCELLED


def test_put_subtitles_names_each_bad_cue_and_refuses_an_english_edit(
    client: Client, video: Path
) -> None:
    pid = make_project(client, video)
    events(client, start_job(client, pid)["id"])
    url = f"/api/projects/{pid}/subtitles"
    cues = client.get(f"{url}?format=json").json()["cues"]
    assert client.get(f"/api/projects/{pid}/edits").json() == {"ids": []}

    def problems(body: list[dict[str, Any]]) -> list[tuple[int, str]]:
        response = client.put(url, json={"cues": body})
        assert response.status_code == 422, response.text
        return [(p["id"], p["code"]) for p in response.json()["detail"]["problems"]]

    overlap = [{**cues[0], "end_ms": cues[1]["start_ms"] + 5}, *cues[1:]]
    assert problems(overlap) == [(cues[0]["id"], "overlap")]
    assert problems([{**cues[0], "end_ms": 1, "start_ms": 5}, *cues[1:]]) == [
        (cues[0]["id"], "end_before_start")
    ]
    assert problems([{**cues[0], "en": "changed"}, *cues[1:]]) == [
        (cues[0]["id"], "english_changed")
    ]
    assert problems([{**cues[0], "zh": ""}, *cues[1:]]) == [(cues[0]["id"], "empty")]
    assert client.get(f"/api/projects/{pid}/edits").json() == {"ids": []}
    cues[-1]["zh"] = EDIT
    assert client.put(url, json={"cues": cues}).status_code == 200
    assert client.get(f"/api/projects/{pid}/edits").json() == {"ids": [cues[-1]["id"]]}
