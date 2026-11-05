"""Summarise an English SRT with a local llama-server and time it.

Each run starts a fresh llama-server bound to 127.0.0.1, summarises into its own directory under
--out-dir, stops the server, and prints one JSON summary. It refuses to start while another GPU
job (whisper-cli, crispasr or llama-server) is running.

    uv run python scripts/bench_summarize.py --srt talk.srt --out-dir D:/work/p06 \
        --server-exe runtimes/llama.cpp-b12068-win-cuda12.4/llama-server.exe \
        --gguf models/llm/Qwen3-8B-Q4_K_M.gguf --runs 2 --langs zh-TW en
"""

from __future__ import annotations

import argparse
import json
import logging
import re
import statistics
import subprocess
import time
from collections.abc import Sequence
from pathlib import Path
from typing import cast

from bench_translate import NO_THINK, PORT, GpuSampler, server_stats, wait_healthy

from backend.core import summarize
from backend.core.subtitle_io import parse_srt, read_text_file, render_subs, write_text_file
from backend.core.summarize import Lang, Progress
from backend.llm.client import LlmConfig

GPU_JOBS = ("whisper-cli.exe", "crispasr.exe", "llama-server.exe")
_RELEASED = re.compile(r"stop processing: n_tokens = (\d+)")
_REQUEST = re.compile(r"(map \d+/\d+|reduce \S+) request about (\d+) tokens")


def gpu_busy() -> bool:
    raw = subprocess.run(["tasklist"], capture_output=True, check=False).stdout
    out = raw.decode("oem", errors="replace").lower()
    return any(name in out for name in GPU_JOBS)


class _Requests(logging.Handler):
    def __init__(self) -> None:
        super().__init__(logging.INFO)
        self.estimates: dict[str, int] = {}
        self.gave_up = 0

    def emit(self, record: logging.LogRecord) -> None:
        message = record.getMessage()
        if found := _REQUEST.search(message):
            self.estimates[found.group(1)] = int(found.group(2))
        self.gave_up += "gave up after" in message


def run_once(args: argparse.Namespace, index: int) -> dict[str, object]:
    if gpu_busy():
        raise SystemExit("another GPU job is running; not starting")
    out_dir = cast("Path", args.out_dir) / f"run{index}"
    out_dir.mkdir(parents=True, exist_ok=True)
    source, dest = out_dir / "subs.en.json", out_dir / "summary.md"
    cues = parse_srt(read_text_file(args.srt), "en")
    write_text_file(source, render_subs(cues))
    if not args.keep:
        for stale in out_dir.glob("summary*"):
            stale.unlink()
    base = f"http://127.0.0.1:{PORT}/v1"
    server_log = out_dir / "llama-server.log"
    command = [
        str(args.server_exe), "-m", str(args.gguf), "--host", "127.0.0.1", "--port", str(PORT),
        "-ngl", str(args.ngl), "-c", str(args.ctx), "-np", "1", "--no-webui",
    ]  # fmt: skip
    requests = _Requests()
    logging.getLogger("backend.core.summarize").addHandler(requests)
    logging.getLogger("backend.core.summarize").setLevel(logging.INFO)
    with server_log.open("wb") as sink:
        server = subprocess.Popen(command, stdout=sink, stderr=subprocess.STDOUT)
        try:
            wait_healthy(base, server)
            config = LlmConfig(base, "qwen3-8b", extra_body=NO_THINK)
            progress: list[Progress] = []
            sampler = GpuSampler()
            sampler.start()
            started = time.monotonic()
            written = summarize.summarize_file(
                source,
                dest,
                summarize.summary_chat(config),
                cast("Sequence[Lang]", args.langs),
                context_tokens=args.ctx,
                on_progress=progress.append,
            )
            total_s = time.monotonic() - started
            sampler.finish()
        finally:
            server.terminate()
            server.wait(timeout=30)
    log_text = server_log.read_text(encoding="utf-8", errors="replace")
    peaks = [int(n) for n in _RELEASED.findall(log_text)]
    stats = server_stats(server_log)
    texts = [read_text_file(path) for path in written]
    return {
        "run": index,
        "total_s": round(total_s, 1),
        "map_s": [round(p.seconds, 1) for p in progress if p.stage == "map"],
        "reduce_s": [round(p.seconds, 1) for p in progress if p.stage == "reduce"],
        "windows": len(summarize.make_windows(summarize.lines_from_cues(cues))),
        "gave_up_windows": requests.gave_up,
        "chapters": [len(summarize.CHAPTER_LINK.findall(text)) for text in texts],
        "ctx": args.ctx,
        "requests": len(peaks),
        "peak_context_tokens": peaks,
        "peak_context_share": round(max(peaks) / args.ctx, 3) if peaks else None,
        "estimated_request_tokens": requests.estimates,
        "contended_by_other_gpu_job": sampler.contended,
        "gpu_util_mean_pct": round(statistics.mean(sampler.util), 1) if sampler.util else None,
        "gpu_mem_max_mib": max(sampler.mem_mib) if sampler.mem_mib else None,
        "server": stats,
        "output": [str(path) for path in written],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--srt", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--server-exe", type=Path, required=True)
    parser.add_argument("--gguf", type=Path, required=True)
    parser.add_argument("--runs", type=int, default=1)
    parser.add_argument("--first-run", type=int, default=1)
    parser.add_argument("--ngl", type=int, default=99)
    parser.add_argument("--ctx", type=int, default=summarize.CONTEXT_TOKENS)
    parser.add_argument("--langs", nargs="+", choices=["zh-TW", "en"], default=["zh-TW"])
    parser.add_argument("--keep", action="store_true", help="resume from the files already there")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    for index in range(args.first_run, args.first_run + args.runs):
        print(json.dumps(run_once(args, index), ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
