"""P30 lever: translate the Japanese cues of a saved project with the real local model and time it.

    uv run python scripts/p30_translate_run.py SUBS.json --source ja|ja+en --out OUT.json

Starts llama-server on a free port (stopped on exit), runs `translate.translate_file` the way the
pipeline does (default glossary, default batch size, seed, no thinking), and writes the translated
cue file. For `ja+en` the English cues are given a stand-in so only the Japanese cues are asked for.
Prints one JSON line with the seconds spent translating (the server start is not in it).
With `--windows EVAL.json --run full|mixed` only the Japanese cues inside the windows of that run
(the evaluation set of `scripts/p30_quality_check.py`) are asked for, each window with the real
cues around it as context.
Set `PYTHONPATH` to another checkout to run the same script against its code.
"""

from __future__ import annotations

import argparse
import json
import logging
import time
from dataclasses import replace
from pathlib import Path

from backend.core import translate
from backend.core.model import Cue
from backend.core.source_langs import SourceLanguage, get_source
from backend.core.subtitle_io import parse_subs, read_text_file, render_subs, write_text_file
from backend.llm.ask import json_chat
from backend.llm.client import LLM_SEED, LlmConfig
from backend.llm.local_server import NO_THINK, LlamaServer

ROOT = Path(__file__).resolve().parents[1]
SERVER = "runtimes/llama.cpp-b12068-win-cuda12.4/llama-server.exe"
MODEL = "models/llm/Qwen3-8B-Q4_K_M.gguf"


def in_windows(cues: list[Cue], source: SourceLanguage, path: Path, run: str) -> set[int]:
    """The ids of the cues of the windows of `run`, widened to the whole sentence units they touch
    so that a window never starts inside a sentence whose first half is only context."""
    windows = json.loads(path.read_text(encoding="utf-8"))
    spans = [(w["t0"], w["t1"] + 1) for w in windows if w["run"] == run]
    wanted: set[int] = set()
    for unit in translate.sentence_units(cues, 0, len(cues), translate.MAX_UNIT_CUES, source):
        group = cues[unit.start : unit.stop]
        if any(t0 <= c.start_ms and c.end_ms <= t1 for c in group for t0, t1 in spans):
            wanted.update(c.id for c in group)
    return wanted


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("subs", type=Path)
    parser.add_argument("--source", choices=("ja", "ja+en"), default="ja")
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--assets", type=Path, default=Path("D:/WebProject/speech-subtitle-ai"))
    parser.add_argument("--first", type=int, default=0, help="translate only cue ids from this one")
    parser.add_argument("--last", type=int, default=0, help="translate only cue ids up to this one")
    parser.add_argument("--windows", type=Path, help="evaluation windows: translate only these")
    parser.add_argument("--run", default="", help="which run of the windows file this subs file is")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    source = get_source(args.source)
    cues = parse_subs(read_text_file(args.subs))
    wanted = in_windows(cues, source, args.windows, args.run) if args.windows else None
    skipped = {
        cue.id
        for cue in cues
        if cue.lang != "ja"
        or cue.id < args.first
        or (args.last and cue.id > args.last)
        or (wanted is not None and cue.id not in wanted)
    }
    staged = args.out.with_suffix(".in.json")
    write_text_file(
        staged,
        render_subs([replace(c, zh=c.src if c.id in skipped else "") for c in cues]),
    )
    dest = args.out.with_suffix(".work.json")
    dest.unlink(missing_ok=True)
    log = args.out.with_suffix(".server.log")
    with LlamaServer(args.assets / SERVER, args.assets / MODEL, log_path=log, ctx=8192) as running:
        config = LlmConfig(running.base_url, "local", extra_body={**NO_THINK, "seed": LLM_SEED})
        started = time.monotonic()
        result = translate.translate_file(
            staged,
            dest,
            json_chat(config),
            translate.default_glossary(source.code),
            keep_english=True,
            lang=translate.DEFAULT,
            source_lang=source,
        )
        seconds = time.monotonic() - started
    final = [replace(c, zh="") if c.id in skipped else c for c in result]
    write_text_file(args.out, render_subs(final))
    asked = len(cues) - len(skipped)
    print(
        json.dumps({"out": str(args.out), "cues_translated": asked, "seconds": round(seconds, 1)})
    )


if __name__ == "__main__":
    main()
