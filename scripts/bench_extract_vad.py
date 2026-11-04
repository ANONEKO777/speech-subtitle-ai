"""Time audio.extract plus vad.split on one video, with a cold output cache on every run.

Prints one JSON line per run and a summary. Run it only when nothing else loads the machine.
"""

import argparse
import json
import statistics
import tempfile
import time
from pathlib import Path

from backend.core import audio, vad


def one_run(video: Path, model: Path, workdir: Path) -> dict[str, float | int | bool]:
    wav = workdir / "audio.wav"
    for leftover in workdir.iterdir():
        leftover.unlink()
    t0 = time.perf_counter()
    result = audio.extract(video, wav)
    t1 = time.perf_counter()
    chunks = vad.split(wav, model)
    t2 = time.perf_counter()
    lengths = [c.duration_ms for c in chunks]
    overlaps = [a.end_ms - b.start_ms for a, b in zip(chunks, chunks[1:], strict=False)]
    return {
        "extract_s": round(t1 - t0, 2),
        "vad_s": round(t2 - t1, 2),
        "total_s": round(t2 - t0, 2),
        "extract_skipped": result.skipped,
        "audio_s": round(result.duration_ms / 1000, 1),
        "chunks": len(chunks),
        "min_chunk_ms": min(lengths),
        "max_chunk_ms": max(lengths),
        "max_overlap_ms": max(overlaps, default=0),
        "short_chunks_before_last": sum(n < 20_000 for n in lengths[:-1]),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("video", type=Path)
    parser.add_argument("--model", type=Path, default=Path("models/silero-vad/silero_vad.onnx"))
    parser.add_argument("--runs", type=int, default=3)
    args = parser.parse_args()
    totals: list[float] = []
    with tempfile.TemporaryDirectory() as tmp:
        for index in range(args.runs):
            row = one_run(args.video, args.model, Path(tmp))
            totals.append(float(row["total_s"]))
            print(json.dumps({"run": index + 1, **row}))
    print(
        f"median {statistics.median(totals):.2f}s, range {min(totals):.2f} to {max(totals):.2f}s"
        f" over {len(totals)} runs"
    )


if __name__ == "__main__":
    main()
