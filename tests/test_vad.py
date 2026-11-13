import json
import random
import wave
from pathlib import Path

import numpy as np
import pytest

from backend.core import vad
from backend.core.audio import SAMPLE_RATE, AudioError
from backend.core.vad import (
    FRAME_MS,
    Chunk,
    VadParams,
    frame_probs,
    plan_chunks,
    speech_runs,
    speech_seconds,
    split,
)

FIXTURE = Path(__file__).parent / "fixtures" / "en_15s.wav"
FIXTURE_PROBS = Path(__file__).parent / "fixtures" / "en_15s.probs.json"
P = VadParams()


def probs_for(speech: list[tuple[int, int]], total_ms: int) -> np.ndarray:
    frames = np.zeros(total_ms // FRAME_MS, dtype=np.float32)
    for start, end in speech:
        frames[start // FRAME_MS : -(-end // FRAME_MS)] = 0.95
    return frames


def pauses_every(period_ms: int, pause_ms: int, total_ms: int) -> list[tuple[int, int]]:
    spans: list[tuple[int, int]] = []
    t = 0
    while t < total_ms:
        spans.append((t, min(t + period_ms, total_ms)))
        t += period_ms + pause_ms
    return spans


def assert_chunk_rules(chunks: list[Chunk], params: VadParams = P) -> None:
    assert chunks
    for chunk in chunks:
        assert chunk.duration_ms <= params.max_chunk_ms
    for before, after in zip(chunks, chunks[1:], strict=False):
        assert after.start_ms > before.start_ms
        assert before.end_ms - after.start_ms <= params.max_overlap_ms
        long_pause = after.start_ms - before.end_ms >= params.long_silence_ms - 2 * (
            params.speech_pad_ms + FRAME_MS
        )
        assert before.duration_ms >= params.min_chunk_ms or long_pause


def assert_no_long_silence_inside(
    chunks: list[Chunk], probs: np.ndarray, params: VadParams = P
) -> None:
    runs = speech_runs(probs, params)
    slack = params.speech_pad_ms + FRAME_MS
    for (_, gap_start), (gap_end, _) in zip(runs, runs[1:], strict=False):
        if gap_end - gap_start >= params.long_silence_ms:
            for chunk in chunks:
                assert not (chunk.start_ms < gap_end - slack and chunk.end_ms > gap_start + slack)


def covered_frames(chunks: list[Chunk], frames: int) -> np.ndarray:
    covered = np.zeros(frames, dtype=bool)
    for chunk in chunks:
        covered[chunk.start_ms // FRAME_MS : -(-chunk.end_ms // FRAME_MS)] = True
    return covered


def test_silence_gives_no_chunks() -> None:
    assert plan_chunks(probs_for([], 60_000), 60_000) == []
    assert plan_chunks(np.zeros(0, dtype=np.float32), 0) == []


def test_short_speech_is_one_short_chunk_without_the_leading_silence() -> None:
    chunks = plan_chunks(probs_for([(4000, 9000)], 12_000), 12_000)
    assert len(chunks) == 1
    assert chunks[0].start_ms == 4000 - P.speech_pad_ms
    assert 9000 + P.speech_pad_ms <= chunks[0].end_ms <= 9000 + P.speech_pad_ms + FRAME_MS


def test_a_blip_shorter_than_min_speech_is_ignored() -> None:
    assert plan_chunks(probs_for([(1000, 1100)], 5000), 5000) == []


def test_cuts_fall_in_silences_with_no_overlap_when_pauses_exist() -> None:
    total = 200_000
    speech = pauses_every(6000, 400, total)
    chunks = plan_chunks(probs_for(speech, total), total)
    assert_chunk_rules(chunks)
    for before, after in zip(chunks, chunks[1:], strict=False):
        assert before.end_ms <= after.start_ms
        cut = before.end_ms
        assert not any(s < cut < e for s, e in speech), f"cut {cut} is inside speech"


def test_a_cut_lands_in_the_middle_of_the_silence() -> None:
    probs = probs_for([(0, 22_000), (24_000, 70_000)], 70_000)
    cut = plan_chunks(probs, 70_000)[0].end_ms
    assert 22_900 <= cut <= 23_100


def test_a_dip_in_the_middle_of_speech_stays_one_run() -> None:
    probs = probs_for([(0, 3000)], 6000)
    probs[40:50] = 0.4
    assert speech_runs(probs, P) == [(0, 94 * FRAME_MS)]


def test_a_pause_shorter_than_the_minimum_silence_does_not_split_speech() -> None:
    frames = np.full(200, 0.9, dtype=np.float32)
    frames[50:53] = 0.0
    assert speech_runs(frames, P) == [(0, 200 * FRAME_MS)]
    frames[50:60] = 0.0
    assert len(speech_runs(frames, P)) == 2


def test_uses_the_longest_silence_that_fits_the_window() -> None:
    speech = [(0, 22_000), (22_300, 27_000), (28_000, 70_000)]
    chunks = plan_chunks(probs_for(speech, 70_000), 70_000)
    assert 27_000 <= chunks[0].end_ms <= 28_000


def test_a_long_silence_ends_the_chunk_even_when_it_is_shorter_than_20_seconds() -> None:
    probs = probs_for([(0, 5000), (40_000, 70_000)], 70_000)
    first, second, *_ = plan_chunks(probs, 70_000)
    assert 5000 <= first.end_ms <= 5000 + P.speech_pad_ms + FRAME_MS
    assert 40_000 - P.speech_pad_ms - FRAME_MS <= second.start_ms <= 40_000
    assert_no_long_silence_inside(plan_chunks(probs, 70_000), probs)


def test_a_long_silence_inside_the_last_chunk_is_left_out() -> None:
    probs = probs_for([(0, 5000), (25_000, 30_000)], 31_000)
    first, second = plan_chunks(probs, 31_000)
    assert first.end_ms <= 5000 + P.speech_pad_ms + FRAME_MS
    assert second.start_ms >= 25_000 - P.speech_pad_ms - FRAME_MS


def test_a_pause_shorter_than_the_long_silence_does_not_split_a_short_talk() -> None:
    probs = probs_for([(0, 5000), (7500, 12_000)], 13_000)
    assert len(plan_chunks(probs, 13_000)) == 1


def test_unbroken_speech_overlaps_by_at_most_half_a_second() -> None:
    total = 130_000
    chunks = plan_chunks(probs_for([(0, total)], total), total)
    assert_chunk_rules(chunks)
    assert len(chunks) >= 5
    assert any(a.end_ms > b.start_ms for a, b in zip(chunks, chunks[1:], strict=False))
    assert chunks[-1].end_ms <= total


def test_unbroken_speech_cuts_at_the_quietest_frame() -> None:
    probs = probs_for([(0, 80_000)], 80_000)
    probs[24_000 // FRAME_MS] = 0.4
    chunks = plan_chunks(probs, 80_000)
    assert chunks[0].end_ms - P.max_overlap_ms // 2 == 24_000 // FRAME_MS * FRAME_MS


def test_the_final_chunk_is_not_a_sliver() -> None:
    total = 61_000
    chunks = plan_chunks(probs_for(pauses_every(2000, 300, total), total), total)
    assert_chunk_rules(chunks)
    assert chunks[-1].duration_ms >= 5000


def test_the_final_chunk_is_a_full_chunk_when_the_audio_allows_it() -> None:
    total = 45_000
    chunks = plan_chunks(probs_for(pauses_every(2000, 300, total), total), total)
    assert_chunk_rules(chunks)
    assert len(chunks) == 2
    assert chunks[-1].duration_ms >= P.min_chunk_ms


@pytest.mark.parametrize("seed", range(40))
def test_random_speech_patterns_keep_every_rule_and_cover_all_speech(seed: int) -> None:
    rng = random.Random(seed)
    total = rng.randint(25_000, 400_000)
    speech: list[tuple[int, int]] = []
    t = rng.randint(0, 3000)
    while t < total:
        length = rng.choice([rng.randint(300, 3000), rng.randint(3000, 45_000)])
        speech.append((t, min(t + length, total)))
        t += length + rng.choice([rng.randint(200, 600), rng.randint(600, 6000)])
    probs = probs_for(speech, total)
    chunks = plan_chunks(probs, total)
    assert_chunk_rules(chunks)
    assert_no_long_silence_inside(chunks, probs)
    covered = covered_frames(chunks, len(probs))
    for start, end in speech_runs(probs, P):
        assert covered[start // FRAME_MS : end // FRAME_MS].all(), f"speech {start}..{end} is cut"


def test_params_reject_nonsense() -> None:
    with pytest.raises(ValueError):
        VadParams(min_chunk_ms=30_000, max_chunk_ms=20_000)
    with pytest.raises(ValueError):
        VadParams(neg_threshold=0.9, threshold=0.5)
    with pytest.raises(ValueError):
        VadParams(max_overlap_ms=10_000)
    with pytest.raises(ValueError):
        Chunk(5, 5)


def write_wav(path: Path, samples: np.ndarray, rate: int = SAMPLE_RATE) -> None:
    pcm = (np.clip(samples, -1, 1) * 32767).astype("<i2")
    with wave.open(str(path), "wb") as writer:
        writer.setnchannels(1)
        writer.setsampwidth(2)
        writer.setframerate(rate)
        writer.writeframes(pcm.tobytes())


def read_samples(path: Path) -> np.ndarray:
    with wave.open(str(path), "rb") as reader:
        return np.frombuffer(reader.readframes(reader.getnframes()), dtype="<i2") / 32768.0


def test_silence_only_wav_gives_no_chunks(tmp_path: Path, silero_model: Path) -> None:
    wav = tmp_path / "silence.wav"
    write_wav(wav, np.zeros(SAMPLE_RATE * 30))
    assert split(wav, silero_model) == []


def test_noise_floor_is_not_speech(tmp_path: Path, silero_model: Path) -> None:
    wav = tmp_path / "hiss.wav"
    write_wav(wav, np.random.default_rng(1).normal(0, 0.003, SAMPLE_RATE * 30))
    assert split(wav, silero_model) == []


def test_real_speech_is_found_in_the_fixture(silero_model: Path) -> None:
    chunks = split(FIXTURE, silero_model)
    assert len(chunks) == 1
    assert chunks[0].start_ms < 1500 and chunks[0].end_ms > 12_000


def test_long_audio_is_cut_in_the_silence_between_repeated_speech(
    tmp_path: Path, silero_model: Path
) -> None:
    clip = read_samples(FIXTURE)
    gap = np.zeros(SAMPLE_RATE * 600 // 1000)
    wav = tmp_path / "long.wav"
    write_wav(wav, np.concatenate([np.concatenate([clip, gap]) for _ in range(7)]))
    chunks = split(wav, silero_model)
    assert_chunk_rules(chunks)
    assert len(chunks) >= 4
    probs = frame_probs(wav, silero_model)
    for before, after in zip(chunks, chunks[1:], strict=False):
        assert before.end_ms <= after.start_ms
        around = probs[(before.end_ms - 100) // FRAME_MS : (before.end_ms + 100) // FRAME_MS + 1]
        assert (around < P.neg_threshold).all(), f"cut {before.end_ms} is not mid-silence"


def test_frame_count_covers_the_whole_wav(tmp_path: Path, silero_model: Path) -> None:
    clip = read_samples(FIXTURE)
    wav = tmp_path / "x3.wav"
    write_wav(wav, np.concatenate([clip, clip, clip]))
    probs = frame_probs(wav, silero_model)
    assert len(probs) == -(-len(clip) * 3 // 512)
    assert probs.max() > 0.9 and probs.min() < 0.1


def test_frame_probabilities_match_the_pinned_reference(silero_model: Path) -> None:
    expected = np.array(json.loads(FIXTURE_PROBS.read_text(encoding="utf-8")), dtype=np.float32)
    probs = frame_probs(FIXTURE, silero_model)
    assert probs.shape == expected.shape
    assert np.abs(probs - expected).max() < 5e-3


def test_probabilities_do_not_depend_on_the_read_block_size(
    silero_model: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    whole = frame_probs(FIXTURE, silero_model)
    monkeypatch.setattr(vad, "_READ_WINDOWS", 37)
    blocks = frame_probs(FIXTURE, silero_model)
    assert np.abs(whole - blocks).max() < 1e-4


def test_a_missing_model_names_the_fetch_script(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError, match="fetch_silero_vad"):
        frame_probs(FIXTURE, tmp_path / "nope.onnx")


def test_a_non_16k_wav_is_rejected(tmp_path: Path) -> None:
    model = tmp_path / "model.onnx"
    model.write_bytes(b"not a real model")
    bad = tmp_path / "44k.wav"
    write_wav(bad, np.zeros(1000), rate=44_100)
    with pytest.raises(AudioError, match="16 kHz"):
        frame_probs(bad, model)


def test_speech_seconds_counts_the_speech_of_each_wav_and_not_tones_or_noise(
    tmp_path: Path, silero_model: Path
) -> None:
    t = np.arange(SAMPLE_RATE * 5) / SAMPLE_RATE
    chord = (
        np.sin(2 * np.pi * 261.6 * t) + np.sin(2 * np.pi * 329.6 * t) + np.sin(2 * np.pi * 392 * t)
    ) / 4
    hiss = np.random.default_rng(1).normal(0, 0.1, t.size)
    chord_wav, hiss_wav = tmp_path / "chord.wav", tmp_path / "hiss.wav"
    write_wav(chord_wav, chord)
    write_wav(hiss_wav, hiss)
    found = speech_seconds([FIXTURE, chord_wav, hiss_wav], silero_model)
    assert found[0] > 8
    assert found[1:] == [0.0, 0.0]
