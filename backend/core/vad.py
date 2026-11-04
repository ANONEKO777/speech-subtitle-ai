from __future__ import annotations

import importlib
import wave
from bisect import bisect_left
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

import numpy as np
from numpy.typing import NDArray

from backend.core.audio import SAMPLE_RATE, wav_duration_ms

WINDOW_SAMPLES = 512
CONTEXT_SAMPLES = 64
FRAME_MS = WINDOW_SAMPLES * 1000 // SAMPLE_RATE

_READ_WINDOWS = 512

Probs = NDArray[np.float32]
SpanMs = tuple[int, int]


@dataclass(frozen=True, slots=True)
class Chunk:
    """A span of the audio for one ASR call. Offsets are from the start of the wav."""

    start_ms: int
    end_ms: int

    def __post_init__(self) -> None:
        if not 0 <= self.start_ms < self.end_ms:
            raise ValueError(f"chunk needs 0 <= start < end, got {self.start_ms}..{self.end_ms}")

    @property
    def duration_ms(self) -> int:
        return self.end_ms - self.start_ms


@dataclass(frozen=True, slots=True)
class VadParams:
    threshold: float = 0.5
    neg_threshold: float = 0.35
    min_speech_ms: int = 250
    min_silence_ms: int = 200
    speech_pad_ms: int = 150
    min_chunk_ms: int = 20_000
    max_chunk_ms: int = 30_000
    max_overlap_ms: int = 500
    long_silence_ms: int = 3000

    def __post_init__(self) -> None:
        if not 0 < self.neg_threshold <= self.threshold < 1:
            raise ValueError("need 0 < neg_threshold <= threshold < 1")
        if not 0 < self.min_chunk_ms < self.max_chunk_ms:
            raise ValueError("need 0 < min_chunk_ms < max_chunk_ms")
        if not 0 <= self.max_overlap_ms < self.max_chunk_ms - self.min_chunk_ms:
            raise ValueError("max_overlap_ms must be smaller than the chunk length range")
        if self.long_silence_ms <= self.min_silence_ms + 2 * self.speech_pad_ms:
            raise ValueError("long_silence_ms must exceed min_silence_ms plus both pads")
        if min(self.min_speech_ms, self.min_silence_ms, self.speech_pad_ms) < 0:
            raise ValueError("durations must not be negative")


def frame_probs(wav: Path, model: Path) -> Probs:
    if not model.is_file():
        raise FileNotFoundError(
            f"silero-vad model not found: {model}. Run scripts/fetch_silero_vad.py."
        )
    wav_duration_ms(wav)
    ort: Any = importlib.import_module("onnxruntime")
    options = ort.SessionOptions()
    options.intra_op_num_threads = 1
    options.inter_op_num_threads = 1
    session = ort.InferenceSession(
        str(model), sess_options=options, providers=["CPUExecutionProvider"]
    )
    state = np.zeros((2, 1, 128), dtype=np.float32)
    sample_rate = np.array(SAMPLE_RATE, dtype=np.int64)
    context = np.zeros(CONTEXT_SAMPLES, dtype=np.float32)
    probs: list[float] = []
    with wave.open(str(wav), "rb") as reader:
        while True:
            raw = reader.readframes(WINDOW_SAMPLES * _READ_WINDOWS)
            if not raw:
                break
            samples = np.frombuffer(raw, dtype="<i2").astype(np.float32) / 32768.0
            windows = -(-len(samples) // WINDOW_SAMPLES)
            padded = np.zeros(windows * WINDOW_SAMPLES, dtype=np.float32)
            padded[: len(samples)] = samples
            buffer = np.concatenate([context, padded])
            for i in range(windows):
                begin = i * WINDOW_SAMPLES
                window = buffer[begin : begin + CONTEXT_SAMPLES + WINDOW_SAMPLES][None, :]
                out, state = cast(
                    "tuple[Probs, Probs]",
                    session.run(None, {"input": window, "state": state, "sr": sample_rate}),
                )
                probs.append(float(out[0, 0]))
            context = buffer[-CONTEXT_SAMPLES:]
    return np.array(probs, dtype=np.float32)


def speech_runs(probs: Probs, params: VadParams) -> list[SpanMs]:
    runs: list[SpanMs] = []
    begin: int | None = None
    for i, p in enumerate(probs.tolist()):
        if begin is None:
            if p >= params.threshold:
                begin = i
        elif p < params.neg_threshold:
            runs.append((begin * FRAME_MS, i * FRAME_MS))
            begin = None
    if begin is not None:
        runs.append((begin * FRAME_MS, len(probs) * FRAME_MS))
    merged: list[SpanMs] = []
    for start, end in runs:
        if merged and start - merged[-1][1] < params.min_silence_ms:
            merged[-1] = (merged[-1][0], end)
        else:
            merged.append((start, end))
    return [(s, e) for s, e in merged if e - s >= params.min_speech_ms]


def plan_chunks(probs: Probs, total_ms: int, params: VadParams | None = None) -> list[Chunk]:
    """Cut the audio into chunks of min_chunk..max_chunk ms, cutting inside silences.

    Only the last chunk, or one that ends where a silence of long_silence_ms or more
    begins, may be shorter than min_chunk. That chunk stops speech_pad_ms after the speech
    ends and the next starts speech_pad_ms before the speech resumes, so a long pause or
    music is never sent to the ASR engine. A cut inside a shorter silence leaves no
    overlap. When no silence fits the window, the chunks overlap by up to max_overlap_ms
    around the quietest frame, so a word on the cut appears whole in one of them.
    """
    params = params or VadParams()
    runs = speech_runs(probs, params)
    if not runs:
        return []
    run_ends = [end for _, end in runs]
    gaps = [(runs[k][1], runs[k + 1][0]) for k in range(len(runs) - 1)]
    gap_starts = [start for start, _ in gaps]
    gap_ends = [end for _, end in gaps]
    pad = params.speech_pad_ms
    half = params.max_overlap_ms // 2
    last_speech_end = runs[-1][1]
    last_end = min(total_ms, last_speech_end + pad)

    def onset_at_or_after(position: int) -> int:
        k = bisect_left(run_ends, position + 1)
        return max(position, runs[k][0] - pad)

    def long_silence_after(start: int) -> SpanMs | None:
        for k in range(bisect_left(gap_starts, start + 1), len(gaps)):
            g_start, g_end = gaps[k]
            if g_start + pad > start + params.max_chunk_ms:
                return None
            if g_end - g_start >= params.long_silence_ms:
                return g_start, g_end
        return None

    chunks: list[Chunk] = []
    start = onset_at_or_after(0)
    while True:
        long_gap = long_silence_after(start)
        if long_gap is not None:
            chunks.append(Chunk(start, long_gap[0] + pad))
            start = long_gap[1] - pad
            continue
        if last_speech_end <= start + params.max_chunk_ms:
            chunks.append(Chunk(start, min(last_end, start + params.max_chunk_ms)))
            return chunks
        lo = start + params.min_chunk_ms
        hi = start + params.max_chunk_ms
        if last_end - params.min_chunk_ms >= lo:
            hi = min(hi, last_end - params.min_chunk_ms)
        best_gap: tuple[int, int] | None = None
        for k in range(bisect_left(gap_ends, lo + 1), len(gaps)):
            g_start, g_end = gaps[k]
            if g_start >= hi:
                break
            if best_gap is None or g_end - g_start >= best_gap[1] - best_gap[0]:
                best_gap = (g_start, g_end)
        if best_gap is not None:
            cut = (max(best_gap[0], lo) + min(best_gap[1], hi)) // 2
            chunks.append(Chunk(start, cut))
            start = onset_at_or_after(cut)
        else:
            first = -(-lo // FRAME_MS)
            last = max(first, (hi - half) // FRAME_MS)
            quietest = first + int(np.argmin(probs[first : last + 1]))
            cut = quietest * FRAME_MS
            chunks.append(Chunk(start, cut + half))
            start = cut - half


def split(wav: Path, model: Path, params: VadParams | None = None) -> list[Chunk]:
    return plan_chunks(frame_probs(wav, model), wav_duration_ms(wav), params)
