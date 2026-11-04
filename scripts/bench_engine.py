"""Time whole-file whisper.cpp through the M0 script (trunk) and through WhisperCppEngine (head).

Runs the two sides alternately on one wav. Both times include loading the model. Every run
starts only when no other whisper-cli, crispasr or llama-server is on the GPU, and prints
the CPU load it saw. The word texts of the first trunk run and of each head run are compared.
"""

import argparse
import json
import statistics
import subprocess
import sys
import time
from pathlib import Path

from backend.engines.table import create_engine
from backend.manager.profiles import Device

ENGINE_ID = "whispercpp-large-v3-turbo"
BUSY = ("whisper-cli", "crispasr", "llama-server")


def gpu_busy() -> list[str]:
    out = subprocess.run(["tasklist"], capture_output=True, text=True, check=True).stdout.lower()
    return [name for name in BUSY if name in out]


def cpu_load() -> int:
    command = "(Get-CimInstance Win32_Processor | Measure-Object LoadPercentage -Average).Average"
    out = subprocess.run(
        ["powershell", "-NoProfile", "-Command", command], capture_output=True, text=True
    )
    return int(float(out.stdout.strip() or -1))


def trunk_run(args: argparse.Namespace, index: int) -> tuple[float, list[str]]:
    out_dir = args.out_dir / "trunk"
    started = subprocess.run(
        [sys.executable, "scripts/m0/run_whispercpp.py", str(args.wav), "--bin", str(args.bin)]
        + ["--model", str(args.model), "--out-dir", str(out_dir), "--run-id", f"b{index}"],
        capture_output=True,
        text=True,
    )
    if started.returncode != 0:
        raise SystemExit(f"trunk run failed: {started.stderr[-500:]}")
    record = next(out_dir.glob(f"*-b{index}.run.json"))
    data = json.loads(record.read_text(encoding="utf-8"))
    words = [w["text"] for s in data["segments"] for w in s["words"]]
    return data["wall_seconds"], words


def head_run(args: argparse.Namespace) -> tuple[float, list[str]]:
    engine = create_engine(ENGINE_ID, args.bin, args.model, device=Device.CUDA)
    started = time.perf_counter()
    segments = engine.transcribe(args.wav)
    wall = time.perf_counter() - started
    return wall, [w.text for s in segments for w in s.words or ()]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("wav", type=Path)
    parser.add_argument("--bin", type=Path, required=True)
    parser.add_argument("--model", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--runs", type=int, default=3)
    args = parser.parse_args()
    args.out_dir.mkdir(parents=True, exist_ok=True)

    walls: dict[str, list[float]] = {"trunk": [], "head": []}
    trunk_words: list[str] | None = None
    for index in range(1, args.runs + 1):
        for side in ("trunk", "head"):
            busy = gpu_busy()
            if busy:
                raise SystemExit(f"GPU is shared and {busy} is running; not measuring")
            load = cpu_load()
            if side == "trunk":
                wall, words = trunk_run(args, index)
                trunk_words = trunk_words or words
            else:
                wall, words = head_run(args)
            walls[side].append(wall)
            same = trunk_words is not None and [w.casefold() for w in words] == [
                w.casefold() for w in trunk_words
            ]
            print(
                json.dumps(
                    {
                        "run": index,
                        "side": side,
                        "wall_s": round(wall, 2),
                        "cpu_load_pct": load,
                        "words": len(words),
                        "same_words_as_first_trunk": same,
                    }
                ),
                flush=True,
            )
    t, h = statistics.median(walls["trunk"]), statistics.median(walls["head"])
    print(f"trunk median {t:.2f}s over {sorted(walls['trunk'])}")
    print(f"head median {h:.2f}s over {sorted(walls['head'])}")
    print(f"head vs trunk {100 * (h / t - 1):+.1f}% (fail above +5%)")


if __name__ == "__main__":
    main()
