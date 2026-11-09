from __future__ import annotations

import shutil
import subprocess
import time
from collections.abc import Generator
from pathlib import Path
from typing import Any

import pytest
from test_api import GUARD, Client, Rig, events, make_project, open_client, start_job

from backend.core.languages import Wrap
from backend.core.model import Cue
from backend.core.playback import MAX_OFFSET_MS, Playback, read_playback, shift_cues, write_playback
from backend.core.render import parse_rate
from backend.core.subtitle_io import BurnMode, render_burn_ass
from backend.main import AppConfig, create_app


@pytest.fixture
def client(tmp_path: Path) -> Generator[Client]:
    app = create_app(AppConfig(tmp_path / "data", GUARD, Rig().resolve))
    with open_client(app) as c:
        yield c


def pick(tmp_path: Path, folder: Path) -> Path:
    """What the desktop shell does when the person picks `folder` in the native dialog."""
    folder.mkdir(parents=True, exist_ok=True)
    with (tmp_path / "data" / "output-folders.txt").open("a", encoding="utf-8") as f:
        f.write(f"{folder}" + chr(10))
    return folder


needs_ffmpeg = pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg is not installed")
CUES = [Cue(0, 1000, 3000, "Hello there", "你好"), Cue(1, 4000, 6000, "Second line", "第二句")]


@pytest.fixture
def movie(tmp_path: Path) -> Path:
    """A real 8 s picture with sound, so ffmpeg can cut it."""
    path = tmp_path / "talk.mp4"
    subprocess.run(
        [
            *("ffmpeg", "-v", "error", "-y"),
            *("-f", "lavfi", "-i", "color=c=0x203040:s=640x360:d=8:r=25"),
            *("-f", "lavfi", "-i", "sine=frequency=440:duration=8"),
            *("-c:v", "libx264", "-c:a", "aac", "-shortest", str(path)),
        ],
        check=True,
    )
    return path


def test_shift_drops_what_ends_before_zero_and_clamps_the_start() -> None:
    later = shift_cues(CUES, 500)
    assert [(c.start_ms, c.end_ms) for c in later] == [(1500, 3500), (4500, 6500)]
    earlier = shift_cues(CUES, -2000)
    assert [(c.id, c.start_ms, c.end_ms) for c in earlier] == [(0, 0, 1000), (1, 2000, 4000)]
    assert [c.id for c in shift_cues(CUES, -3000)] == [1]


def test_playback_file_survives_damage_and_range(tmp_path: Path) -> None:
    assert read_playback(tmp_path) == Playback()
    write_playback(tmp_path, Playback(12.5, 100, -250, 7))
    assert read_playback(tmp_path) == Playback(12.5, 100, -250, 7)
    (tmp_path / "playback.json").write_text('{"position_s": -4, "offset_ms": 9999999}')
    assert read_playback(tmp_path) == Playback()
    (tmp_path / "playback.json").write_text("not json")
    assert read_playback(tmp_path) == Playback()
    assert MAX_OFFSET_MS == 60_000


def burn_lines(mode: BurnMode, zh_first: bool) -> list[str]:
    ass = render_burn_ass(
        CUES[:1],
        Wrap.CJK,
        mode=mode,
        zh_first=zh_first,
        size_ratio=0.05,
        color="#ff8000",
    )
    assert "Fontsize" in ass and ",36.0," in ass and "&H000080FF" in ass
    return [line for line in ass.splitlines() if line.startswith("Dialogue")]


def test_burned_ass_follows_the_mode_and_the_order() -> None:
    assert burn_lines("en", True)[0].endswith("{\\rEn}Hello there")
    assert burn_lines("zh", True)[0].endswith("{\\rZh}你好")
    assert burn_lines("both", True)[0].endswith("{\\rZh}你好\\N{\\rEn}Hello there")
    assert burn_lines("both", False)[0].endswith("{\\rEn}Hello there\\N{\\rZh}你好")


def processed(client: Client, movie: Path) -> tuple[str, list[dict[str, Any]]]:
    pid = make_project(client, movie)
    events(client, start_job(client, pid)["id"])
    return pid, client.get(f"/api/projects/{pid}/subtitles?format=json").json()["cues"]


@needs_ffmpeg
def test_offset_is_saved_and_moves_every_subtitle_export_but_not_the_cue_list(
    client: Client, movie: Path
) -> None:
    pid, cues = processed(client, movie)
    url = f"/api/projects/{pid}"
    srt_before = client.get(f"{url}/subtitles?format=srt").text
    assert client.put(f"{url}/playback", json={"offset_ms": 1500}).json()["offset_ms"] == 1500
    assert client.get(f"{url}/playback").json()["offset_ms"] == 1500
    assert client.get(f"{url}/subtitles?format=srt").text != srt_before
    assert client.get(f"{url}/subtitles?format=json").json()["cues"] == cues
    assert client.put(f"{url}/playback", json={"offset_ms": 10**7}).status_code == 422


@needs_ffmpeg
def test_library_lists_a_processed_project_with_its_position(client: Client, movie: Path) -> None:
    pid, _ = processed(client, movie)
    assert (
        client.put(
            f"/api/projects/{pid}/playback",
            json={"position_s": 3.5, "duration_s": 8, "opened": True},
        ).status_code
        == 200
    )
    (item,) = client.get("/api/projects").json()["projects"]
    assert (item["id"], item["title"], item["position_s"], item["duration_s"]) == (
        pid,
        "talk",
        3.5,
        8,
    )
    assert item["exists"] and item["langs"] and item["opened_at_ms"] > 0
    thumb = client.get(f"/api/projects/{pid}/thumbnail")
    assert thumb.headers["content-type"] == "image/jpeg" and thumb.content[:2] == b"\xff\xd8"


@needs_ffmpeg
def test_screenshot_with_the_subtitle_burned_in_differs_from_the_plain_frame(
    client: Client, movie: Path, tmp_path: Path
) -> None:
    pid, cues = processed(client, movie)
    at = (cues[0]["start_ms"] + cues[0]["end_ms"]) / 2000
    shots = pick(tmp_path, tmp_path / "shots")
    body = {"time_s": at, "dir": str(shots), "mode": "both"}
    plain = client.post(f"/api/projects/{pid}/screenshot", json=body).json()
    burned = client.post(f"/api/projects/{pid}/screenshot", json={**body, "burn": True}).json()
    assert Path(plain["path"]).name.endswith(".png") and Path(burned["path"]).name.endswith(
        "_sub.png"
    )
    assert Path(plain["path"]).read_bytes() != Path(burned["path"]).read_bytes()
    assert len(burned["png_base64"]) > len(plain["png_base64"])
    again = client.post(f"/api/projects/{pid}/screenshot", json=body).json()
    assert again["path"] != plain["path"]


@needs_ffmpeg
def test_burn_in_export_runs_in_the_background_and_ends_as_a_playable_clip(
    client: Client, movie: Path, tmp_path: Path
) -> None:
    pid, _ = processed(client, movie)
    start = client.post(
        f"/api/projects/{pid}/burn",
        json={"dir": str(pick(tmp_path, tmp_path / "out")), "start_s": 1, "duration_s": 4},
    )
    assert start.status_code == 202, start.text
    job_id = start.json()["id"]
    job: dict[str, Any] = {}
    for _ in range(300):
        job = client.get(f"/api/burns/{job_id}").json()
        if job["state"] != "running":
            break
        time.sleep(0.1)
    assert job["state"] == "done", job
    out = Path(job["output"])
    probe = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(out)],
        capture_output=True,
        text=True,
        check=True,
    )
    assert 3.5 < float(probe.stdout) < 4.5
    assert not list(out.parent.glob(".*part*"))
    assert client.post("/api/burns/none/cancel").status_code == 404


@needs_ffmpeg
def test_output_folder_must_be_one_the_person_picked(
    client: Client, movie: Path, tmp_path: Path
) -> None:
    pid, _ = processed(client, movie)
    body = {"time_s": 1.0, "mode": "both"}
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    for dir_ in (
        str(elsewhere),
        str(tmp_path / "not-there" / "deep"),
        "relative",
        "//host/share/x",
    ):
        refused = client.post(f"/api/projects/{pid}/screenshot", json={**body, "dir": dir_})
        assert refused.status_code == 422, dir_
    assert not (tmp_path / "not-there").exists()
    assert not list(elsewhere.iterdir())

    pick(tmp_path, elsewhere)
    ok = client.post(f"/api/projects/{pid}/screenshot", json={**body, "dir": str(elsewhere)})
    assert ok.status_code == 200, ok.text
    sub = elsewhere / "inside"
    sub.mkdir()
    inside = client.post(f"/api/projects/{pid}/screenshot", json={**body, "dir": str(sub)})
    assert inside.status_code == 200
    (tmp_path / "movie-folder").mkdir()
    outside = str(elsewhere / ".." / "movie-folder")
    refused = client.post(f"/api/projects/{pid}/screenshot", json={**body, "dir": outside})
    assert refused.status_code == 422
    for other in ("runtimes", "models", ""):
        folder = tmp_path / "data" / other
        folder.mkdir(parents=True, exist_ok=True)
        refused = client.post(f"/api/projects/{pid}/screenshot", json={**body, "dir": str(folder)})
        assert refused.status_code == 422, other
    shots = tmp_path / "data" / "screenshots"
    shots.mkdir(parents=True, exist_ok=True)
    named = client.post(f"/api/projects/{pid}/screenshot", json={**body, "dir": str(shots)})
    assert named.status_code == 200, named.text
    default = client.post(f"/api/projects/{pid}/screenshot", json=body)
    assert default.status_code == 200 and "screenshots" in default.json()["path"]


@needs_ffmpeg
def test_burn_starting_past_the_end_is_refused_even_with_a_duration(
    client: Client, movie: Path
) -> None:
    pid, _ = processed(client, movie)
    past = client.post(f"/api/projects/{pid}/burn", json={"start_s": 5000, "duration_s": 3})
    assert past.status_code == 422


@needs_ffmpeg
def test_media_reports_the_frame_rate_of_the_picture(client: Client, movie: Path) -> None:
    pid, _ = processed(client, movie)
    assert client.get(f"/api/projects/{pid}/media").json() == {"frame_rate": 25.0}


def test_frame_rates_ffprobe_cannot_state_are_not_used() -> None:
    assert parse_rate("30000/1001") == pytest.approx(29.97, abs=0.01)
    assert parse_rate("25/1") == 25.0
    assert parse_rate("0/0") is None
    assert parse_rate("90000/1") is None
    assert parse_rate("") is None
