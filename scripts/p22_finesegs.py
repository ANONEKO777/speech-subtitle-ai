"""P22 lever: cut a wav at its pauses into short speech segments, for per-segment language work.

The app's VAD plan makes 20 to 30 s chunks, and one chunk can hold a Japanese passage and its
English interpretation. This cut splits at every pause of MIN_SILENCE_MS or more instead.

    uv run python scripts/p22_finesegs.py WAV OUT.json [MIN_SILENCE_MS]
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from backend.core import vad

ONNX = Path(__file__).resolve().parents[3] / "models/silero-vad/silero_vad.onnx"
PAD_MS = 150
MIN_SEGMENT_MS = 800
MAX_SEGMENT_MS = 28_000


def fine_segments(wav: Path, min_silence_ms: int) -> list[tuple[int, int]]:
    probs = vad.frame_probs(wav, ONNX)
    total_ms = len(probs) * vad.FRAME_MS
    runs = vad.speech_runs(probs, vad.VadParams(min_silence_ms=min_silence_ms))
    out: list[tuple[int, int]] = []
    for start, end in runs:
        start, end = max(0, start - PAD_MS), min(total_ms, end + PAD_MS)
        if end - start < MIN_SEGMENT_MS:
            continue
        while end - start > MAX_SEGMENT_MS:
            out.append((start, start + MAX_SEGMENT_MS))
            start += MAX_SEGMENT_MS
        out.append((start, end))
    return out


if __name__ == "__main__":
    segments = fine_segments(Path(sys.argv[1]), int(sys.argv[3]) if len(sys.argv) > 3 else 700)
    Path(sys.argv[2]).write_text(json.dumps(segments))
    print(f"{len(segments)} segments, {sum(b - a for a, b in segments) / 60000:.1f} min of speech")
