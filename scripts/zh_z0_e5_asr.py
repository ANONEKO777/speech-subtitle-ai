"""Z0 E5: the app's own ASR path over the minutes of the operator's video, with Chinese unspaced.

    uv run python scripts/zh_z0_e5_asr.py --tag e5-w --engine whisper --lang zh
    uv run python scripts/zh_z0_e5_asr.py --tag e5-q --engine qwen3 --lang zh

It does what `pipeline._vad`, `_asr` and `_segment` do: `vad.split` plans the chunks of
`e5/window.wav`, `transcribe_chunks` runs the engine over them, and `to_cues` builds the cues. `zh`
is not a source of the app yet, so `is_spaced("zh")` would be true and merge Chinese tokens into
one word; the script makes it false in the two modules that ask, which is what a `zh` row with
`CueRules(unspaced=True)` will do in Z1. The cue rules are an argument (`--max-line`, `--max-cps`).
Output: `.work/zh-z0/e5/<tag>.json` (words and cues in video time, in ms).
"""
# ruff: noqa: E501

from __future__ import annotations

import argparse
import sys
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

from zh_z0_common import (
    CRISPASR_ID,
    WHISPER_ID,
    make_engine,
    set_idle_priority,
    storage,
    wait_until_free,
)
from zh_z0_text import WORK, read_json, wav_seconds, write_json

import backend.core.source_langs as source_langs
import backend.engines.chunks as chunks_module
import backend.engines.whispercpp as whisper_module
from backend.core import vad
from backend.core.model import Segment
from backend.core.segmenter import CueRules, to_cues
from backend.engines.chunks import transcribe_chunks

E5 = WORK / "e5"


def unspaced_zh(code: str) -> bool:
    return False if code == "zh" else source_langs.is_spaced(code)


def prompted(
    original: Callable[[Sequence[Path], Sequence[Path], str], list[str]], prompt: str
) -> Callable[[Sequence[Path], Sequence[Path], str], list[str]]:
    """`original` with a whisper `--prompt` after the program name."""

    def command(inputs: Sequence[Path], outputs: Sequence[Path], language: str) -> list[str]:
        built = original(inputs, outputs, language)
        return [built[0], "--prompt", prompt, *built[1:]]

    return command


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--tag", required=True)
    parser.add_argument(
        "--set", dest="folder", default="e5", help="e5 (the anime video) or e6 (the talk)"
    )
    parser.add_argument("--engine", choices=("whisper", "qwen3"), required=True)
    parser.add_argument("--lang", default="zh")
    parser.add_argument("--prompt", help="whisper initial prompt")
    parser.add_argument(
        "--max-line", type=int, default=40, help="CueRules.max_line_chars (columns)"
    )
    parser.add_argument("--max-cps", type=float, default=14.0)
    parser.add_argument("--unspaced-merge", action="store_true", help="keep the shipped is_spaced")
    args = parser.parse_args()

    set_idle_priority()
    wait_until_free()
    if not args.unspaced_merge:
        whisper_module.is_spaced = unspaced_zh
        chunks_module.is_spaced = unspaced_zh
    folder = WORK / args.folder
    timeline = folder / "timeline.json"
    offset_ms = int(float(read_json(timeline)["start"]) * 1000) if timeline.exists() else 0
    wav = folder / "window.wav"
    engine = make_engine(WHISPER_ID if args.engine == "whisper" else CRISPASR_ID)
    if args.prompt:
        setattr(engine, "command", prompted(engine.command, args.prompt))  # noqa: B010
    onnx = storage().models_root / "silero-vad-onnx-v6.2.3" / "silero_vad.onnx"
    chunks = vad.split(wav, onnx)
    words = transcribe_chunks(engine, wav, chunks, args.lang)
    segment = Segment(
        " ".join(w.text for w in words), words[0].start_ms, words[-1].end_ms, tuple(words)
    )
    rules = CueRules(max_line_chars=args.max_line, unspaced=True, max_cps=args.max_cps)
    cues = to_cues([segment], rules, "zh")
    out: dict[str, Any] = {
        "tag": args.tag,
        "engine": engine.id,
        "lang_flag": args.lang,
        "offset_ms": offset_ms,
        "audio_s": wav_seconds(wav),
        "chunks": [[c.start_ms + offset_ms, c.end_ms + offset_ms] for c in chunks],
        "rules": {"max_line_chars": args.max_line, "max_cps": args.max_cps},
        "words": [[w.text, w.start_ms + offset_ms, w.end_ms + offset_ms] for w in words],
        "cues": [[c.start_ms + offset_ms, c.end_ms + offset_ms, c.src] for c in cues],
    }
    write_json(folder / f"{args.tag}.json", out)
    print(f"{args.tag}: {len(chunks)} chunks, {len(words)} words, {len(cues)} cues")
    return 0


if __name__ == "__main__":
    sys.exit(main())
