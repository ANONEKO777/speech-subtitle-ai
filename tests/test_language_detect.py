"""Language detection: the rule that turns what Whisper named for each piece of audio into a
suggestion, the pieces it samples, and the two programs it runs (ffmpeg and whisper-cli)."""

from __future__ import annotations

import wave
from collections.abc import Sequence
from pathlib import Path

import pytest

from backend.core import audio, language_detect
from backend.core.language_detect import (
    MIXED_SHARE,
    SAMPLE_COUNT,
    SAMPLE_S,
    Heard,
    Sample,
    decide,
    detect,
    sample_starts,
)
from backend.engines.base import EngineFailedError, EngineOutputError, EngineTimeoutError
from backend.engines.whispercpp import name_languages
from backend.manager.profiles import Device

WAV_15S = Path(__file__).parent / "fixtures" / "en_15s.wav"


def samples(*tags: str, p: float = 0.95) -> list[Sample]:
    return [Sample(i * SAMPLE_S, Heard(tag, p)) for i, tag in enumerate(tags)]


def mixture(ja: int, en: int, other: int = 0) -> list[Sample]:
    return samples(*["ja"] * ja, *["en"] * en, *["ko"] * other)


def test_pieces_are_spread_over_the_video_and_never_leave_it() -> None:
    starts = sample_starts(3600)
    assert len(starts) == SAMPLE_COUNT
    assert starts == sorted(starts)
    assert starts[0] > 0 and starts[-1] + SAMPLE_S < 3600
    gaps = {round(b - a, 3) for a, b in zip(starts, starts[1:], strict=False)}
    assert gaps == {150.0}


def test_a_short_video_gets_the_whole_pieces_that_fit() -> None:
    assert sample_starts(20) == [0.0, 5.0, 10.0, 15.0]
    assert sample_starts(7) == [1.0]
    assert sample_starts(2) == [0.0]
    assert sample_starts(0) == [0.0]


@pytest.mark.parametrize(("code", "other"), [("en", "ja"), ("ja", "en")])
def test_a_talk_in_one_language_is_that_language(code: str, other: str) -> None:
    found = decide(samples(*[code] * 24))
    assert found.code == code
    assert found.confidence == 1.0
    assert found.sure


def test_a_short_stretch_in_another_language_does_not_make_a_talk_mixed() -> None:
    found = decide(mixture(ja=22, en=2))
    assert found.code == "ja"
    assert found.confidence == pytest.approx(22 / 24)
    assert found.sure
    assert not decide(mixture(ja=21, en=3)).sure


def test_a_talk_that_uses_both_languages_is_mixed_from_the_share_in_the_rule() -> None:
    assert MIXED_SHARE == 0.15
    assert decide(mixture(ja=20, en=4)).code == "ja+en"
    assert decide(mixture(ja=21, en=3)).code == "ja"
    mixed = decide(mixture(ja=12, en=12))
    assert mixed.code == "ja+en"
    assert mixed.sure
    assert dict(mixed.shares) == {"ja": 0.5, "en": 0.5}


def test_a_short_video_is_never_called_mixed() -> None:
    found = decide(mixture(ja=2, en=2))
    assert found.code == "ja"
    assert found.confidence == 0.5
    assert not found.sure


def test_pieces_without_a_clear_language_are_left_out() -> None:
    music = [Sample(0, Heard("en", 0.2)), Sample(5, Heard("ja", 0.49))]
    found = decide(samples(*["ja"] * 10) + music + samples("ko", "zh", "de"))
    assert found.code == "ja"
    assert found.clear == 10
    assert found.confidence == 1.0


def test_too_little_speech_says_nothing() -> None:
    found = decide(samples("ja", "ja") + [Sample(0, Heard("en", 0.1))])
    assert found.code is None
    assert not found.sure
    assert found.clear == 2


def test_the_languages_are_the_members_of_the_mixed_source() -> None:
    assert language_detect.LANGUAGES == ("ja", "en")


def fake_cut(seen: list[tuple[list[float], float]]) -> language_detect.Cut:
    def cut(starts: Sequence[float], length: float) -> list[Path]:
        seen.append((list(starts), length))
        return [Path(f"piece{i}.wav") for i in range(len(starts))]

    return cut


def test_detect_cuts_the_pieces_and_asks_for_their_languages() -> None:
    seen: list[tuple[list[float], float]] = []
    asked: list[list[Path]] = []

    def name(wavs: Sequence[Path]) -> list[Heard]:
        asked.append(list(wavs))
        return [Heard("ja" if i % 2 else "en", 0.9) for i in range(len(wavs))]

    found = detect(3000.0, fake_cut(seen), name)
    assert found.code == "ja+en"
    assert len(asked[0]) == SAMPLE_COUNT
    assert seen == [(sample_starts(3000.0), SAMPLE_S)]
    assert [s.start_s for s in found.samples] == seen[0][0]


def test_a_wrong_number_of_answers_is_an_error() -> None:
    with pytest.raises(ValueError, match="languages named"):
        detect(3000.0, fake_cut([]), lambda wavs: [Heard("ja", 0.9)])


def fake_whisper(tmp_path: Path, body: str, code: int = 0) -> Path:
    script = tmp_path / "whisper-cli.cmd"
    script.write_text(f"@echo off\r\n{body}\r\nexit /b {code}\r\n", encoding="ascii")
    return script


def line(language: str, p: str) -> str:
    return f"echo whisper_full_with_state: auto-detected language: {language} (p = {p}) 1>&2"


def test_whisper_names_one_language_per_file_in_order(tmp_path: Path) -> None:
    binary = fake_whisper(tmp_path, "\r\n".join([line("ja", "0.973411"), line("en", "0.61")]))
    heard = name_languages(
        binary, tmp_path / "m.bin", [Path("a.wav"), Path("b.wav")], device=Device.CUDA, timeout_s=20
    )
    assert heard == [Heard("ja", 0.973411), Heard("en", 0.61)]


def test_whisper_that_names_too_few_languages_is_an_error(tmp_path: Path) -> None:
    binary = fake_whisper(tmp_path, line("ja", "0.9"))
    with pytest.raises(EngineOutputError, match="named 1 languages for 2 files"):
        name_languages(
            binary,
            tmp_path / "m.bin",
            [Path("a.wav"), Path("b.wav")],
            device=Device.CUDA,
            timeout_s=20,
        )


def test_whisper_that_fails_is_an_error_with_its_output(tmp_path: Path) -> None:
    binary = fake_whisper(tmp_path, "echo no gpu 1>&2", code=3)
    with pytest.raises(EngineFailedError, match="code 3.*no gpu"):
        name_languages(
            binary, tmp_path / "m.bin", [Path("a.wav")], device=Device.CUDA, timeout_s=20
        )


def test_whisper_that_hangs_is_stopped(tmp_path: Path) -> None:
    binary = fake_whisper(tmp_path, "ping -n 20 127.0.0.1 >nul")
    with pytest.raises(EngineTimeoutError):
        name_languages(binary, tmp_path / "m.bin", [Path("a.wav")], device=Device.CUDA, timeout_s=1)


def test_the_clips_are_cut_at_the_starts_asked_for(tmp_path: Path, ffmpeg_tools: None) -> None:
    video = tmp_path / "talk.wav"
    video.write_bytes(WAV_15S.read_bytes())
    clips = audio.cut_clips(video, [0.0, 4.0, 9.0], 5.0, tmp_path / "clips")
    assert [c.name for c in clips] == ["clip000.wav", "clip001.wav", "clip002.wav"]
    for clip in clips:
        with wave.open(str(clip)) as reader:
            assert (reader.getframerate(), reader.getnchannels()) == (16000, 1)
            assert reader.getnframes() == pytest.approx(5 * 16000, abs=1600)


def test_cutting_a_file_that_is_not_audio_is_an_audio_error(
    tmp_path: Path, ffmpeg_tools: None
) -> None:
    broken = tmp_path / "talk.mp4"
    broken.write_bytes(b"not a video")
    with pytest.raises(audio.AudioError):
        audio.cut_clips(broken, [0.0], 5.0, tmp_path / "clips")
