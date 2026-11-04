from __future__ import annotations

import argparse
import statistics
import subprocess
import sys
import time
from collections.abc import Callable

from backend.manager import hardware

LIMIT_S = 1.5


def timed(call: Callable[[], object]) -> float:
    start = time.perf_counter()
    call()
    return time.perf_counter() - start


def bare_nvidia_smi() -> object:
    return subprocess.run(
        [hardware.find_nvidia_smi() or "nvidia-smi", *hardware.SMI_QUERY],
        capture_output=True,
        check=False,
    )


def cold_cli() -> object:
    return subprocess.run(
        [sys.executable, "-m", "backend.manager.hardware"], capture_output=True, check=True
    )


def summarize(name: str, samples: list[float]) -> str:
    return (
        f"{name:<28} median {statistics.median(samples):.3f} s"
        f"  min {min(samples):.3f}  max {max(samples):.3f}  n={len(samples)}"
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Time hardware.detect() against two controls.")
    parser.add_argument("--runs", type=int, default=10)
    args = parser.parse_args()

    probes: dict[str, Callable[[], object]] = {
        "detect() in process": hardware.detect,
        "bare nvidia-smi query": bare_nvidia_smi,
        "python -m ...hardware (cold)": cold_cli,
    }
    samples: dict[str, list[float]] = {name: [] for name in probes}
    for _ in range(args.runs):
        for name, call in probes.items():
            samples[name].append(timed(call))

    for name, values in samples.items():
        print(summarize(name, values))
    found = hardware.detect()
    print(f"work check: detect() returned {found.gpu_name}, {found.vram_mib} MiB")
    median = statistics.median(samples["detect() in process"])
    verdict = "PASS" if median <= LIMIT_S else "FAIL"
    print(f"detect() median {median:.3f} s, limit {LIMIT_S} s: {verdict}")
    return 0 if verdict == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
