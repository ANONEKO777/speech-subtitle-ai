"""Translate an English SRT with a local llama-server and time it.

Each run starts a fresh llama-server bound to 127.0.0.1, translates into its own directory under
--out-dir, stops the server, and prints one JSON summary.

    uv run python scripts/bench_translate.py --srt talk.srt --out-dir D:/work/p05 \
        --server-exe runtimes/llama.cpp-b12068-win-cuda12.4/llama-server.exe \
        --gguf models/llm/Qwen3-8B-Q4_K_M.gguf --runs 2
"""

from __future__ import annotations

import argparse
import json
import logging
import re
import statistics
import subprocess
import threading
import time
import urllib.error
import urllib.request
from collections.abc import Sequence
from pathlib import Path
from typing import cast

from backend.core import translate
from backend.core.model import Cue
from backend.core.subtitle_io import (
    parse_srt,
    parse_subs,
    read_text_file,
    render_subs,
    write_text_file,
)
from backend.core.translate import GlossaryEntry, Progress
from backend.llm.ask import json_chat
from backend.llm.client import LlmConfig

PORT = 18080
NO_THINK = {"chat_template_kwargs": {"enable_thinking": False}}
_EVAL = re.compile(r"(?<!prompt )eval time =\s*([\d.]+) ms /\s*(\d+) tokens")
_FAILED_ATTEMPT = re.compile(r"attempt \d+ (?:rejected|failed)")
_PROMPT_EVAL = re.compile(r"prompt eval time =\s*([\d.]+) ms /\s*(\d+) tokens")


RIVALS = ("whisper-cli.exe", "crispasr.exe")


def rival_running() -> bool:
    raw = subprocess.run(["tasklist"], capture_output=True, check=False).stdout
    out = raw.decode("oem", errors="replace").lower()
    return any(name in out for name in RIVALS)


class GpuSampler(threading.Thread):
    def __init__(self) -> None:
        super().__init__(daemon=True)
        self.util: list[int] = []
        self.mem_mib: list[int] = []
        self.contended = False
        self._halt = threading.Event()

    def run(self) -> None:
        query = [
            "nvidia-smi",
            "--query-gpu=utilization.gpu,memory.used",
            "--format=csv,noheader,nounits",
        ]
        while not self._halt.wait(1.0):
            self.contended |= rival_running()
            out = subprocess.run(query, capture_output=True, text=True, check=False).stdout
            first = out.strip().splitlines()[0].split(",") if out.strip() else []
            if len(first) == 2:
                self.util.append(int(first[0]))
                self.mem_mib.append(int(first[1]))

    def finish(self) -> None:
        self._halt.set()
        self.join()


def wait_healthy(base: str, server: subprocess.Popen[bytes], timeout_s: float = 300.0) -> None:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        if server.poll() is not None:
            raise RuntimeError(f"llama-server exited with code {server.returncode}")
        try:
            with urllib.request.urlopen(base.removesuffix("/v1") + "/health", timeout=2) as resp:
                if resp.status == 200:
                    return
        except (urllib.error.URLError, OSError):
            pass
        time.sleep(1.0)
    raise RuntimeError("llama-server did not become healthy")


def _rate(samples: list[tuple[float, int]]) -> float:
    seconds = sum(ms for ms, _ in samples) / 1000
    return round(sum(n for _, n in samples) / seconds, 1) if samples else 0.0


def server_stats(log_path: Path) -> dict[str, float]:
    text = log_path.read_text(encoding="utf-8", errors="replace")
    decode = [(float(ms), int(n)) for ms, n in _EVAL.findall(text)]
    prompt = [(float(ms), int(n)) for ms, n in _PROMPT_EVAL.findall(text)]
    return {
        "requests": float(len(decode)),
        "decode_tokens": float(sum(n for _, n in decode)),
        "decode_tok_per_s": _rate(decode),
        "prompt_tokens": float(sum(n for _, n in prompt)),
        "prompt_tok_per_s": _rate(prompt),
    }


def _glossary(spec: Sequence[str]) -> list[GlossaryEntry]:
    pairs = (item.partition("=") for item in spec)
    return [GlossaryEntry(term, zh) for term, _, zh in pairs]


class _Retries(logging.Handler):
    def __init__(self) -> None:
        super().__init__(logging.WARNING)
        self.rejected = 0
        self.splits = 0

    def emit(self, record: logging.LogRecord) -> None:
        message = record.getMessage()
        self.rejected += _FAILED_ATTEMPT.search(message) is not None
        self.splits += "splitting the batch" in message


def run_once(args: argparse.Namespace, index: int, cues: list[Cue]) -> dict[str, object]:
    if rival_running():
        raise SystemExit("another GPU job (whisper-cli or crispasr) is running; not starting")
    out_dir = cast("Path", args.out_dir) / f"run{index}"
    out_dir.mkdir(parents=True, exist_ok=True)
    source, dest = out_dir / "subs.en.json", out_dir / "subs.zh-TW.json"
    dest.unlink(missing_ok=True)
    write_text_file(source, render_subs(cues))
    base = f"http://127.0.0.1:{PORT}/v1"
    server_log = out_dir / "llama-server.log"
    command = [
        str(args.server_exe), "-m", str(args.gguf), "--host", "127.0.0.1", "--port", str(PORT),
        "-ngl", str(args.ngl), "-c", str(args.ctx), "-np", "1", "--no-webui",
    ]  # fmt: skip
    retries = _Retries()
    logging.getLogger("backend.core.translate").addHandler(retries)
    with server_log.open("wb") as sink:
        server = subprocess.Popen(command, stdout=sink, stderr=subprocess.STDOUT)
        try:
            wait_healthy(base, server)
            config = LlmConfig(base, "qwen3-8b", extra_body=NO_THINK)
            progress: list[Progress] = []

            sampler = GpuSampler()
            sampler.start()
            started = time.monotonic()
            translate.translate_file(
                source,
                dest,
                json_chat(config),
                _glossary(args.glossary),
                batch_size=args.batch_size,
                on_progress=progress.append,
            )
            total_s = time.monotonic() - started
            sampler.finish()
        finally:
            server.terminate()
            server.wait(timeout=30)
    result = parse_subs(read_text_file(dest))
    latencies = [p.batch_seconds for p in progress]
    return {
        "run": index,
        "batch_size": args.batch_size,
        "total_s": round(total_s, 1),
        "batches": len(progress),
        "batch_mean_s": round(statistics.mean(latencies), 1),
        "batch_max_s": round(max(latencies), 1),
        "batch_latencies_s": [round(x, 1) for x in latencies],
        "first_attempt_batches": sum(p.attempts == 1 for p in progress),
        "rejected_replies": retries.rejected,
        "splits": retries.splits,
        "cues_in": len(cues),
        "cues_out": len(result),
        "all_translated": all(c.zh for c in result),
        "timing_and_english_unchanged": [(c.id, c.start_ms, c.end_ms, c.src) for c in result]
        == [(c.id, c.start_ms, c.end_ms, c.src) for c in cues],
        "contended_by_other_gpu_job": sampler.contended,
        "gpu_util_mean_pct": round(statistics.mean(sampler.util), 1) if sampler.util else None,
        "gpu_mem_max_mib": max(sampler.mem_mib) if sampler.mem_mib else None,
        "server": server_stats(server_log),
        "output": str(dest),
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
    parser.add_argument("--batch-size", type=int, default=translate.BATCH_SIZE)
    parser.add_argument("--ctx", type=int, default=8192)
    parser.add_argument("--glossary", action="append", default=[], help="term or term=繁體譯名")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    cues = parse_srt(read_text_file(args.srt), "en")
    for index in range(args.first_run, args.first_run + args.runs):
        print(json.dumps(run_once(args, index, cues), ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
