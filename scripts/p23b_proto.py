"""P23b lever: run the Qwen3 candidates on the Kirby audio and write their language tags.

X is Qwen3-ASR `-l auto` on the 300 ms pause cut and nothing else. C is X with the two repairs of
`backend/engines/mixed.py` (a `-l ja` pass for text that is neither Japanese nor English, and a pass
over speech left without words at the end of a piece). Both come from one first pass. Output, in
OUT_DIR: `words-x.json`, `words-c.json` (every word with its language), `run.json` (seconds, VRAM).
Y is run with `p22_asr.py` (Whisper `-l auto` and `-l ja`); `p23b_tags.py` turns all of it into the
tag files `p23b_score.py` reads.

    uv run python scripts/p23b_proto.py WAV OUT_DIR
"""

from __future__ import annotations

import json
import sys
import time
from dataclasses import asdict
from pathlib import Path

from p22_asr import ALIGNER, CRISPASR_BIN, MODELS, SILERO_ONNX, VramSampler, gpu_busy

from backend.core import vad
from backend.core.model import Word
from backend.engines import mixed
from backend.engines.crispasr import CrispAsrEngine


def dump(path: Path, words: list[Word]) -> None:
    rows = [asdict(w) for w in words]
    path.write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")


def main() -> int:
    wav, out = Path(sys.argv[1]), Path(sys.argv[2])
    out.mkdir(parents=True, exist_ok=True)
    if busy := gpu_busy():
        print("GPU job running:", busy)
        return 1
    chunks = vad.split_at_pauses(wav, SILERO_ONNX)
    engine = CrispAsrEngine(CRISPASR_BIN, MODELS["qwen3"], ALIGNER, strict=False)
    sampler = VramSampler()
    times: dict[str, float] = {}
    t = time.perf_counter()
    pieces = mixed.first_pass(engine, wav, chunks, None, None)
    times["first_pass_s"] = time.perf_counter() - t
    dump(out / "words-x.json", mixed.tag_pieces(pieces))
    t = time.perf_counter()
    pieces = mixed.guard_pass(engine, wav, pieces)
    times["guard_pass_s"] = time.perf_counter() - t
    dump(out / "words-guard.json", mixed.tag_pieces(pieces))
    t = time.perf_counter()
    pieces = mixed.tail_pass(engine, wav, pieces)
    times["tail_pass_s"] = time.perf_counter() - t
    dump(out / "words-c.json", mixed.tag_pieces(pieces))
    info = {
        "chunks": len(chunks),
        **times,
        "vram_baseline_mib": sampler.baseline,
        "vram_peak_mib": sampler.stop(),
    }
    (out / "run.json").write_text(json.dumps(info, indent=1), encoding="utf-8")
    print(info)
    return 0


if __name__ == "__main__":
    sys.exit(main())
