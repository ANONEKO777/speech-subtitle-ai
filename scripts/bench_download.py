from __future__ import annotations

import argparse
import hashlib
import statistics
import subprocess
import time
from pathlib import Path

from backend.manager import registry
from backend.manager.download import Item, JobRunner, JobState, Plan

CHUNK = 1 << 20


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while block := handle.read(CHUNK):
            digest.update(block)
    return digest.hexdigest()


def run_curl(item: Item, work: Path) -> tuple[float, float]:
    target = work / "curl.bin"
    target.unlink(missing_ok=True)
    start = time.perf_counter()
    subprocess.run(["curl", "-sSL", "--fail", "-o", str(target), item.url], check=True)
    seconds = time.perf_counter() - start
    assert sha256_of(target) == item.sha256, "curl produced a wrong file"
    target.unlink()
    return seconds, 0.0


def run_downloader(item: Item, work: Path) -> tuple[float, float]:
    dest = work / "dl" / "file.bin"
    dest.unlink(missing_ok=True)
    runner = JobRunner()
    cpu = time.process_time()
    start = time.perf_counter()
    job = runner.submit(Plan("bench", (Item(item.url, dest, item.sha256, item.size_bytes),)))
    final = runner.wait(job.id, 3600)
    seconds = time.perf_counter() - start
    cpu = time.process_time() - cpu
    assert final is not None
    assert final.state is JobState.DONE, final.failure
    assert dest.stat().st_size == item.size_bytes
    assert sha256_of(dest) == item.sha256, "downloader produced a wrong file"
    dest.unlink()
    return seconds, cpu


def main() -> None:
    parser = argparse.ArgumentParser(description="Interleave curl and the downloader on one file.")
    parser.add_argument("--model", default="whisper-large-v3-turbo")
    parser.add_argument("--rounds", type=int, default=3)
    parser.add_argument("--work", type=Path, required=True)
    args = parser.parse_args()
    model = registry.load().models[args.model]
    item = Item(model.url, args.work / "x", model.sha256, model.size_bytes)
    args.work.mkdir(parents=True, exist_ok=True)
    seconds: dict[str, list[float]] = {"curl": [], "downloader": []}
    for round_no in range(1, args.rounds + 1):
        for name, run in (("curl", run_curl), ("downloader", run_downloader)):
            took, cpu = run(item, args.work)
            seconds[name].append(took)
            mib_s = item.size_bytes / took / 2**20
            print(f"round {round_no} {name:10} {took:7.1f} s {mib_s:7.1f} MiB/s cpu {cpu:5.1f} s")
    median = {name: statistics.median(times) for name, times in seconds.items()}
    ratio = median["curl"] / median["downloader"]
    print(f"median curl {median['curl']:.1f} s, downloader {median['downloader']:.1f} s")
    print(f"downloader throughput = {ratio:.1%} of curl (fail below 85%)")


if __name__ == "__main__":
    main()
