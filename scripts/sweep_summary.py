"""Sweep the summary step over talk lengths with a local llama-server.

Each input is cut to its first N minutes, summarised for real, and tabulated: pass or fail, chapter
count, retries, the reasons the reduce reply was rejected, and seconds. One llama-server serves the
whole sweep, bound to 127.0.0.1. It refuses to start while another GPU job is running.

    uv run python scripts/sweep_summary.py --out-dir D:/work/p21/before \
        --server-exe runtimes/llama.cpp-b12068-win-cuda12.4/llama-server.exe \
        --gguf models/llm/Qwen3-8B-Q4_K_M.gguf \
        --input talk38=.work/runs/whispercpp-talk38-r1.srt \
        --input nasa6=.work/p20/failed-6min/projects/9eb6dabb7405b68c/subs.en.json \
        --minutes 1 3 5 6 7 8 10 15 20 30 --langs zh-TW ja

An input is an `.srt` or a `subs*.json`. `--whole` adds the uncut input as a last row.
"""

from __future__ import annotations

import argparse
import json
import logging
import re
import subprocess
import time
from collections.abc import Sequence
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import cast

from bench_summarize import gpu_busy
from bench_translate import NO_THINK, PORT, wait_healthy

from backend.core import summarize
from backend.core.model import Cue
from backend.core.subtitle_io import (
    parse_srt,
    parse_subs,
    read_text_file,
    render_subs,
    write_text_file,
)
from backend.llm.client import LlmConfig

_ATTEMPT = re.compile(r"(map \d+/\d+|reduce \S+) attempt (\d+) rejected: (.*)")
_GAVE_UP = re.compile(r"(map \d+/\d+) gave up")


class _Events(logging.Handler):
    def __init__(self) -> None:
        super().__init__(logging.INFO)
        self.map_rejects = 0
        self.reduce_rejects: list[str] = []
        self.gave_up_maps = 0

    def emit(self, record: logging.LogRecord) -> None:
        message = record.getMessage()
        if found := _ATTEMPT.search(message):
            if found.group(1).startswith("reduce"):
                self.reduce_rejects.append(found.group(3))
            else:
                self.map_rejects += 1
        self.gave_up_maps += bool(_GAVE_UP.search(message))


@dataclass(frozen=True, slots=True)
class Row:
    name: str
    minutes: float
    lang: str
    ok: bool
    chapters: int
    map_retries: int
    reduce_retries: int
    windows: int
    seconds: float
    reasons: tuple[str, ...]
    error: str
    end: float = 0.0
    """The last chapter's start over the length of the talk."""
    degraded: bool = False

    def table(self) -> str:
        status = "PASS" if self.ok else "FAIL"
        return (
            f"{self.name:<8} {self.minutes:>6.1f} {self.lang:<6} {status:<5} {self.chapters:>3} "
            f"{self.map_retries:>3} {self.reduce_retries:>3} {self.windows:>3} {self.seconds:>6.1f}"
            f" {self.end:>5.2f}{' DEGRADED' if self.degraded else ''}"
        )


HEADER = "input    minutes lang   result chap mapR redR  win    sec   end"


def load_cues(path: Path) -> list[Cue]:
    text = read_text_file(path)
    return parse_srt(text, "en") if path.suffix == ".srt" else parse_subs(text)


def cut(cues: Sequence[Cue], minutes: float | None) -> list[Cue]:
    if minutes is None:
        return list(cues)
    limit = round(minutes * 60_000)
    kept = [cue for cue in cues if cue.end_ms <= limit]
    return [Cue(i, c.start_ms, c.end_ms, c.en) for i, c in enumerate(kept, 1)]


def run_row(
    name: str, minutes: float | None, cues: Sequence[Cue], lang: str, args: argparse.Namespace
) -> Row:
    span = (cues[-1].end_ms - cues[0].start_ms) / 60_000
    out = (
        cast("Path", args.out_dir) / f"{name}-{minutes if minutes is not None else 'whole'}-{lang}"
    )
    out.mkdir(parents=True, exist_ok=True)
    for stale in out.glob("summary*"):
        stale.unlink()
    source, dest = out / "subs.en.json", out / "summary.md"
    write_text_file(source, render_subs(list(cues)))
    config = LlmConfig(f"http://127.0.0.1:{PORT}/v1", "qwen3-8b", extra_body=NO_THINK)
    events = _Events()
    logger = logging.getLogger("backend")
    logger.addHandler(events)
    started = time.monotonic()
    error, chapters, end = "", 0, 0.0
    degraded: list[str] = []
    try:
        written = summarize.summarize_file(
            source,
            dest,
            summarize.summary_chat(config),
            [lang],
            context_tokens=args.ctx,
            on_degraded=degraded.append,
        )
        starts = summarize.CHAPTER_LINK.findall(read_text_file(written[0]))
        chapters = len(starts)
        end = (int(starts[-1]) - cues[0].start_ms / 1000) / (span * 60) if starts else 0.0
    except summarize.SummaryError as exc:
        error = str(exc)
    finally:
        logger.removeHandler(events)
    lines = summarize.lines_from_cues(list(cues))
    return Row(
        name,
        round(span, 1),
        lang,
        not error,
        chapters,
        events.map_rejects,
        len(events.reduce_rejects),
        len(summarize.make_windows(lines)),
        round(time.monotonic() - started, 1),
        tuple(events.reduce_rejects),
        error,
        round(end, 2),
        bool(degraded),
    )


def parse_input(spec: str) -> tuple[str, Path]:
    name, _, path = spec.partition("=")
    return name, Path(path)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", action="append", required=True, help="NAME=PATH")
    parser.add_argument("--minutes", nargs="*", type=float, default=[])
    parser.add_argument("--whole", action="store_true")
    parser.add_argument("--langs", nargs="+", default=["zh-TW"])
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--server-exe", type=Path, required=True)
    parser.add_argument("--gguf", type=Path, required=True)
    parser.add_argument("--ctx", type=int, default=summarize.CONTEXT_TOKENS)
    parser.add_argument("--ngl", type=int, default=99)
    args = parser.parse_args()
    logging.basicConfig(level=logging.WARNING, format="%(asctime)s %(levelname)s %(message)s")
    logging.getLogger("backend").setLevel(logging.INFO)
    if gpu_busy():
        raise SystemExit("another GPU job is running; not starting")
    args.out_dir.mkdir(parents=True, exist_ok=True)
    inputs = [(name, load_cues(path)) for name, path in map(parse_input, args.input)]
    command = [
        str(args.server_exe), "-m", str(args.gguf), "--host", "127.0.0.1", "--port", str(PORT),
        "-ngl", str(args.ngl), "-c", str(args.ctx), "-np", "1", "--no-webui",
    ]  # fmt: skip
    rows: list[Row] = []
    print(HEADER, flush=True)
    with (args.out_dir / "llama-server.log").open("wb") as sink:
        server = subprocess.Popen(command, stdout=sink, stderr=subprocess.STDOUT)
        try:
            wait_healthy(f"http://127.0.0.1:{PORT}/v1", server)
            for name, cues in inputs:
                lengths: list[float | None] = [*args.minutes, *([None] if args.whole else [])]
                for minutes in lengths:
                    part = cut(cues, minutes)
                    if not part:
                        continue
                    if minutes is not None and part[-1].end_ms < minutes * 60_000 * 0.8:
                        continue
                    for lang in args.langs:
                        row = run_row(name, minutes, part, lang, args)
                        rows.append(row)
                        print(row.table(), flush=True)
                        with (args.out_dir / "rows.jsonl").open("a", encoding="utf-8") as sink2:
                            sink2.write(json.dumps(asdict(row), ensure_ascii=False) + "\n")
        finally:
            server.terminate()
            server.wait(timeout=30)
    failed = [row for row in rows if not row.ok]
    print(f"\n{len(rows) - len(failed)} passed, {len(failed)} failed")
    for row in failed:
        print(f"FAIL {row.name} {row.minutes} {row.lang}: {row.error}")


if __name__ == "__main__":
    main()
