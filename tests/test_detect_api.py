"""POST /api/languages/detect names the language of a picked video so the window can preselect
it, and says plainly when it cannot."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from test_api import GUARD, Client, Rig, open_client
from test_source_availability import BIG_GPU, NO_GPU, install_engine

from backend.core.audio import AudioError
from backend.core.language_detect import Detection, Heard, Sample, decide
from backend.engines.base import EngineFailedError
from backend.main import AppConfig, create_app
from backend.manager.context import ManagerContext, build_context
from backend.manager.detect import Detector, Undetectable
from backend.manager.hardware import Hardware


def heard(*tags: str) -> Detection:
    return decide([Sample(i * 5.0, Heard(tag, 0.95)) for i, tag in enumerate(tags)])


def open_app(
    data: Path, hardware: Hardware, detector: Detector | None
) -> tuple[Client, ManagerContext]:
    context = build_context(data, detect_hardware=lambda: hardware)
    config = AppConfig(data, GUARD, Rig().resolve, manager=context, detector=detector)
    return open_client(create_app(config)), context


def video(tmp_path: Path, name: str = "talk.mp4") -> Path:
    path = tmp_path / name
    path.write_bytes(b"x")
    return path


def ask(client: Client, path: Path) -> Any:
    return client.post("/api/languages/detect", json={"video_path": str(path)})


def test_a_japanese_talk_is_suggested_as_japanese(tmp_path: Path) -> None:
    seen: list[Path] = []

    def detector(path: Path) -> Detection:
        seen.append(path)
        return heard(*["ja"] * 24)

    client, _ = open_app(tmp_path / "data", BIG_GPU, detector)
    with client:
        body = ask(client, video(tmp_path)).json()
    assert seen == [tmp_path / "talk.mp4"]
    assert body["detected"] == body["suggested"] == "ja"
    assert body["mixed_unavailable"] is None
    assert body["confidence"] == 1.0
    assert body["sure"] is True
    assert body["shares"] == {"ja": 1.0, "en": 0.0}
    assert body["clear"] == 24
    assert body["samples"][0] == {"start_s": 0.0, "code": "ja", "probability": 0.95}


def test_a_mixed_talk_is_suggested_as_mixed_when_this_machine_can_run_it(tmp_path: Path) -> None:
    client, context = open_app(
        tmp_path / "data", BIG_GPU, lambda _: heard(*["ja"] * 12, *["en"] * 12)
    )
    with client:
        install_engine(context)
        body = ask(client, video(tmp_path)).json()
    assert body["detected"] == body["suggested"] == "ja+en"
    assert body["mixed_unavailable"] is None


def test_a_mixed_talk_is_suggested_as_its_main_language_when_mixed_cannot_run(
    tmp_path: Path,
) -> None:
    client, _ = open_app(tmp_path / "data", BIG_GPU, lambda _: heard(*["ja"] * 15, *["en"] * 9))
    with client:
        body = ask(client, video(tmp_path)).json()
    assert body["detected"] == "ja+en"
    assert body["suggested"] == "ja"
    assert body["mixed_unavailable"] == "missing_files"


def test_too_little_speech_is_no_suggestion(tmp_path: Path) -> None:
    client, _ = open_app(tmp_path / "data", BIG_GPU, lambda _: heard("ja"))
    with client:
        body = ask(client, video(tmp_path)).json()
    assert body["detected"] is None and body["suggested"] is None


def test_a_path_that_is_not_a_media_file_is_refused(tmp_path: Path) -> None:
    client, _ = open_app(tmp_path / "data", BIG_GPU, lambda _: heard(*["en"] * 24))
    with client:
        assert ask(client, tmp_path / "missing.mp4").status_code == 422
        assert ask(client, video(tmp_path, "notes.txt")).status_code == 422
        assert ask(client, tmp_path).status_code == 422
        assert (
            client.post("/api/languages/detect", json={"video_path": "talk.mp4"}).status_code == 422
        )


def test_a_detector_that_cannot_answer_is_a_503_with_the_reason(tmp_path: Path) -> None:
    for error in (Undetectable("slow"), EngineFailedError("whisper died"), AudioError("no audio")):

        def detector(path: Path, error: Exception = error) -> Detection:
            raise error

        client, _ = open_app(tmp_path / "data", BIG_GPU, detector)
        with client:
            reply = ask(client, video(tmp_path))
        assert reply.status_code == 503
        assert str(error) in reply.json()["detail"]


def test_the_request_needs_the_token(tmp_path: Path) -> None:
    client, _ = open_app(tmp_path / "data", BIG_GPU, lambda _: heard(*["en"] * 24))
    anonymous = open_client(client.app, headers=None)
    with anonymous:
        assert ask(anonymous, video(tmp_path)).status_code == 401


def test_the_real_detector_is_not_asked_on_a_cpu_profile(tmp_path: Path) -> None:
    client, _ = open_app(tmp_path / "data", NO_GPU, None)
    with client:
        reply = ask(client, video(tmp_path))
    assert reply.status_code == 503
    assert "CPU" in reply.json()["detail"]


def test_the_real_detector_needs_whisper_to_be_installed(tmp_path: Path) -> None:
    client, _ = open_app(tmp_path / "data", BIG_GPU, None)
    with client:
        reply = ask(client, video(tmp_path))
    assert reply.status_code == 503
    assert "not installed" in reply.json()["detail"]
