import array
import json
import math
import wave
from pathlib import Path

import pytest

from scripts.m0.compare import (
    RunJson,
    SegmentJson,
    WordJson,
    disagreements,
    longest_gap,
    matched_start_deltas,
    onset_offsets,
    pick_windows,
    repeat_loops,
    speech_onsets,
    timeline_violations,
    window_words,
)

FIXTURES = Path(__file__).parent / "fixtures" / "m0"


def load(name: str) -> RunJson:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def test_clean_timeline_has_no_violations() -> None:
    assert timeline_violations(load("clean.run.json")["segments"]) == []


def test_broken_timeline_reports_each_backward_step() -> None:
    problems = timeline_violations(load("broken.run.json")["segments"])

    assert problems == [
        "segment 1 starts at 0.2, before 0.5",
        "word 'Each' in segment 1 ends before it starts",
        "word 'one' in segment 1 starts before 2.5",
        "segment 2 ends before it starts (9.0 > 8.0)",
    ]


def segment(text: str, start: float, end: float, word_start: float | None = None) -> SegmentJson:
    words: list[WordJson] | None = (
        None if word_start is None else [{"text": text, "start": word_start, "end": end}]
    )
    return {"text": text, "start": start, "end": end, "words": words}


def test_word_going_back_across_a_segment_boundary_is_a_violation() -> None:
    segments = [segment("first", 0.0, 3.0, word_start=2.5), segment("second", 3.5, 4.0, 2.0)]

    assert timeline_violations(segments) == ["word 'second' in segment 1 starts before 2.5"]


def test_longest_gap_measures_silence_between_segments_not_segment_length() -> None:
    segments = [segment("long", 0.5, 6.5), segment("short", 7.0, 8.0)]

    assert longest_gap(segments, duration=10.0) == pytest.approx(2.0)


def test_repeat_loop_counts_each_run_of_three_same_lines_once() -> None:
    texts = ["Thank you.", "thank you", "Thank you!", "Thank you.", "Next.", "Next.", "Done."]
    segments = [segment(t, i, i + 1) for i, t in enumerate(texts)]

    assert repeat_loops(segments) == 1


def test_windows_are_seeded_spread_and_inside_the_audio() -> None:
    windows = pick_windows(2282.0, seed="talk38.wav")

    assert windows == pick_windows(2282.0, seed="talk38.wav")
    assert windows != pick_windows(2282.0, seed="talk57.wav")
    assert len(windows) == 3
    for i, (lo, hi) in enumerate(windows):
        assert hi - lo == pytest.approx(120.0)
        assert i * 2282.0 / 3 <= lo and hi <= (i + 1) * 2282.0 / 3 + 0.1


def test_windows_refuse_audio_too_short_to_sample() -> None:
    with pytest.raises(ValueError, match="too short"):
        pick_windows(300.0, seed="short.wav")


def test_window_takes_words_by_start_time_and_segments_by_midpoint() -> None:
    segments = load("clean.run.json")["segments"]

    assert window_words(segments, (1.2, 4.5)) == [
        "talk",
        "about",
        "agents.",
        "Each",
        "one",
        "opens",
        "a",
        "PR.",
    ]


def test_diff_ignores_case_and_punctuation_and_reports_real_word_changes() -> None:
    a = ["So", "today", "we", "talk", "about", "agents."]
    b = ["so", "today,", "we", "talk", "about", "agent"]

    assert disagreements(a, b) == [("agents.", "agent")]


def test_matched_words_report_start_shift_and_skip_mismatches() -> None:
    clean = load("clean.run.json")["segments"]
    shifted = load("clean.run.json")["segments"]
    for seg in shifted:
        for word in seg["words"] or []:
            word["start"] += 0.3
    assert shifted[0]["words"] is not None
    shifted[0]["words"][5]["text"] = "robots."

    deltas = matched_start_deltas(shifted, clean)

    assert deltas == pytest.approx([0.3] * 5)


def test_onsets_found_where_tone_follows_long_silence(tmp_path: Path) -> None:
    rate = 16000
    tone = [int(8000 * math.sin(2 * math.pi * 440 * i / rate)) for i in range(rate)]
    short_pause = [0] * int(0.3 * rate)
    pcm = array.array("h", [0] * rate + tone + [0] * rate + tone + short_pause + tone)
    path = tmp_path / "tones.wav"
    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(rate)
        wav.writeframes(pcm.tobytes())

    onsets = speech_onsets(path)

    assert onsets == pytest.approx([1.0, 3.0], abs=0.02)
    segments = load("clean.run.json")["segments"]
    assert onset_offsets(segments, [0.65, 2.5]) == pytest.approx([0.05, -0.5])
