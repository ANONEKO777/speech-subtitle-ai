"""Measure what the engines do at VAD chunk edges on a real talk.

Runs each engine on pairs of neighbouring VAD chunks spread over one wav, then reports
- the first and last four words of each chunk next to the same stretch of a whole-file
  whisper.cpp run, for a person to check for dropped head and tail words,
- how often an engine put a period at the edge between two chunks, before and after
  `repair_boundaries`, and how many of those periods the whole-file run also has as a
  sentence end (true) or not (false), so a person can see which kind the repair removes,
- how far the first word starts after, and the last word ends before, the loudness onset and
  offset in the chunk.
Raw engine output is cached in --cache, so rerunning with the same file redoes only the
analysis.
"""

import argparse
import json
import statistics
import wave
from pathlib import Path
from typing import Any

import numpy as np
from numpy.typing import NDArray

from backend.core.audio import SAMPLE_RATE, wav_duration_ms
from backend.core.model import Word
from backend.core.vad import Chunk, VadParams, frame_probs, plan_chunks
from backend.engines.base import ascii_temp_dir
from backend.engines.chunks import repair_boundaries, write_chunks
from backend.engines.table import create_engine
from backend.manager.profiles import Device

WHISPER_ID = "whispercpp-large-v3-turbo"
CRISPASR_ID = "crispasr-qwen3-asr-1.7b"
LEVEL_FRAME_MS = 20
LEVEL_RISE_DB = 15.0

Levels = NDArray[np.float64]


def levels_db(wav: Path) -> tuple[Levels, float]:
    with wave.open(str(wav), "rb") as reader:
        pcm = np.frombuffer(reader.readframes(reader.getnframes()), dtype="<i2").astype(np.float64)
    hop = SAMPLE_RATE * LEVEL_FRAME_MS // 1000
    frames = pcm[: len(pcm) // hop * hop].reshape(-1, hop)
    levels = 10 * np.log10((frames**2).mean(axis=1) + 1)
    return levels, float(np.sort(levels)[len(levels) // 10]) + LEVEL_RISE_DB


def loud_span(levels: Levels, threshold: float, chunk: Chunk) -> tuple[int, int] | None:
    first, last = chunk.start_ms // LEVEL_FRAME_MS, chunk.end_ms // LEVEL_FRAME_MS
    loud = np.flatnonzero(levels[first:last] >= threshold)
    if not len(loud):
        return None
    return (first + int(loud[0])) * LEVEL_FRAME_MS, (first + int(loud[-1]) + 1) * LEVEL_FRAME_MS


def whole_file_words(path: Path) -> list[Word]:
    words: list[Word] = []
    for segment in json.loads(path.read_bytes().decode("utf-8"))["transcription"]:
        for token in segment["tokens"]:
            text, o = token["text"], token["offsets"]
            if text.startswith("[_") or not text.strip():
                continue
            if words and not text.startswith(" "):
                last = words[-1]
                words[-1] = Word(last.text + text, last.start_ms, max(o["to"], last.start_ms))
            else:
                words.append(Word(text.strip(), o["from"], max(o["from"], o["to"])))
    return words


def edge_scorecard(
    chunks: list[Chunk],
    placed: list[list[Word]],
    reference: list[Word],
    pairs: list[tuple[int, int]],
) -> tuple[int, int, int, int]:
    """Return (false removed, false total, true removed, true total) for edge periods."""
    removed_false = false = removed_true = true = 0
    for i, j in pairs:
        if not (placed[i] and placed[j]) or not _periodic(placed[i][-1]):
            continue
        cut = (chunks[i].end_ms + chunks[j].start_ms) // 2
        before = [w for w in reference if w.start_ms < cut and w.end_ms <= cut + 100]
        is_true = bool(before) and before[-1].text[-1] in ".?!"
        kept = repair_boundaries([chunks[i], chunks[j]], [placed[i], placed[j]])[0][
            -1
        ].text.endswith(".")
        true += is_true
        false += not is_true
        removed_true += is_true and not kept
        removed_false += not is_true and not kept
    return removed_false, false, removed_true, true


def _periodic(word: Word) -> bool:
    return len(word.text) > 1 and word.text.endswith(".") and not word.text.endswith("..")


def run_engine(engine_id: str, args: argparse.Namespace, wav: Path, chunks: list[Chunk]) -> Any:
    if engine_id == WHISPER_ID:
        engine = create_engine(engine_id, args.whisper_bin, args.whisper_model, device=args.device)
    else:
        engine = create_engine(
            engine_id,
            args.crisp_bin,
            args.crisp_model,
            aligner=args.crisp_aligner,
            device=args.device,
        )
    with ascii_temp_dir() as work:
        results = engine.transcribe_many(write_chunks(wav, chunks, work, None))
    return [
        [[w.text, w.start_ms, w.end_ms] for s in segments for w in s.words or ()]
        for segments in results
    ]


def edge_text(words: list[Word]) -> str:
    return " ".join(w.text for w in words[:4]) + " ... " + " ".join(w.text for w in words[-4:])


def spread(values: list[int]) -> str:
    ordered = sorted(values)
    return f"median {statistics.median(ordered):.0f} ms, range {ordered[0]} to {ordered[-1]}"


def report(
    engine_id: str,
    chunks: list[Chunk],
    picked: list[int],
    raw: list[list[list[Any]]],
    reference: list[Word],
    levels: Levels,
    threshold: float,
) -> None:
    placed = [
        [Word(t, s + c.start_ms, e + c.start_ms) for t, s, e in words]
        for c, words in zip(chunks, raw, strict=True)
    ]
    onset_lag: list[int] = []
    offset_lead: list[int] = []
    print(f"\n{engine_id}, {len(chunks)} chunks")
    for chunk, words in zip(chunks, placed, strict=True):
        window = [w for w in reference if chunk.start_ms <= w.start_ms < chunk.end_ms]
        print(f"  {chunk.start_ms}..{chunk.end_ms} ms")
        print(f"    whole file: {edge_text(window)}")
        print(f"    chunk:      {edge_text(words)}")
        loud = loud_span(levels, threshold, chunk)
        if loud and words:
            onset_lag.append(words[0].start_ms - loud[0])
            offset_lead.append(loud[1] - words[-1].end_ms)
    pairs = [(i, i + 1) for i in range(len(picked) - 1) if picked[i + 1] == picked[i] + 1]
    before = after = capital = 0
    for i, j in pairs:
        if not (placed[i] and placed[j]):
            continue
        has_period = placed[i][-1].text.endswith(".")
        before += has_period
        capital += has_period and placed[j][0].text[0].isupper()
        after += repair_boundaries([chunks[i], chunks[j]], [placed[i], placed[j]])[0][
            -1
        ].text.endswith(".")
    print(
        f"  period at {len(pairs)} chunk edges: {before} before repair "
        f"({capital} with a capital after), {after} after"
    )
    removed_false, false, removed_true, true = edge_scorecard(chunks, placed, reference, pairs)
    print(
        f"  of those periods, repair removed {removed_false} of {false} false ones "
        f"and {removed_true} of {true} true sentence ends"
    )
    print(f"  first word start minus loudness onset: {spread(onset_lag)}, n={len(onset_lag)}")
    print(f"  loudness offset minus last word end: {spread(offset_lead)}")


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("wav", type=Path)
    p.add_argument("--vad-model", type=Path, required=True)
    p.add_argument("--reference", type=Path, required=True, help="whisper.cpp -ojf of the wav")
    p.add_argument("--whisper-bin", type=Path)
    p.add_argument("--whisper-model", type=Path)
    p.add_argument("--crisp-bin", type=Path)
    p.add_argument("--crisp-model", type=Path)
    p.add_argument("--crisp-aligner", type=Path)
    p.add_argument("--count", type=int, default=8, help="pairs of neighbouring chunks")
    p.add_argument("--cpu", action="store_true")
    p.add_argument("--cache", type=Path, required=True)
    args = p.parse_args()
    args.device = Device.CPU if args.cpu else Device.CUDA

    probs = frame_probs(args.wav, args.vad_model)
    all_chunks = plan_chunks(probs, wav_duration_ms(args.wav), VadParams())
    step = max(1, (len(all_chunks) - 1) // args.count)
    starts = list(range(0, len(all_chunks) - 1, step))[: args.count]
    picked = sorted({i for s in starts for i in (s, s + 1)})
    chunks = [all_chunks[i] for i in picked]
    cache: dict[str, Any] = json.loads(args.cache.read_text()) if args.cache.exists() else {}
    for engine_id, binary in ((WHISPER_ID, args.whisper_bin), (CRISPASR_ID, args.crisp_bin)):
        if engine_id not in cache and binary is not None:
            cache[engine_id] = run_engine(engine_id, args, args.wav, chunks)
            args.cache.write_text(json.dumps(cache))
    levels, threshold = levels_db(args.wav)
    reference = whole_file_words(args.reference)
    print(f"{len(all_chunks)} chunks in the wav, measuring {picked}")
    for engine_id in (WHISPER_ID, CRISPASR_ID):
        if engine_id in cache:
            report(engine_id, chunks, picked, cache[engine_id], reference, levels, threshold)


if __name__ == "__main__":
    main()
