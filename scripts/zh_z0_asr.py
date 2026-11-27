"""Z0 E1/E2: run one speech recognition configuration over a set of FLEURS utterances.

The command line and the parsing are the repository's own engine wrappers (`backend/engines`):
`engine.command(...)` builds what the app runs, `engine.parse(...)` reads the output. This script
only adds what a measurement needs around them: the clock, `nvidia-smi` sampling, the stderr
timings, and the few edits a variant needs (`--prompt` for whisper, no `-am` for CrispASR).

    uv run python scripts/zh_z0_asr.py --tag w-zh --engine whisper --lang zh
    uv run python scripts/zh_z0_asr.py --tag w-zh-prompt --engine whisper --lang zh \\
        --prompt "以下是繁體中文的句子。"
    uv run python scripts/zh_z0_asr.py --tag q-zh --engine qwen3 --lang zh
    uv run python scripts/zh_z0_asr.py --tag q-zh-noalign --engine qwen3 --lang zh --no-aligner

Output: `.work/zh-z0/runs/<tag>.json`. One model process at a time, Idle priority.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
import tempfile
import time
from collections import defaultdict
from pathlib import Path
from typing import Any, cast

from zh_z0_common import (
    CRISPASR_ID,
    DATA,
    RUNS,
    WHISPER_ID,
    GpuSampler,
    Utterance,
    free_ram_gb,
    load_utterances,
    make_engine,
    read_json,
    set_idle_priority,
    wait_until_free,
    write_json,
)

_TIMING = re.compile(r"(\w+) time =\s+([\d.]+) ms")


def pick(lang: str, subset: str) -> list[Utterance]:
    rows = load_utterances(lang)
    if subset == "all":
        return rows
    if subset.startswith("every"):
        step = int(subset.removeprefix("every"))
        return rows[::step]
    raise SystemExit(f"unknown subset {subset!r}")


def edit_command(
    command: list[str], engine_id: str, prompt: str | None, no_aligner: bool, extra: list[str]
) -> list[str]:
    out = list(command)
    if no_aligner and engine_id == CRISPASR_ID:
        index = out.index("-am")
        del out[index : index + 2]
    if prompt:
        if engine_id != WHISPER_ID:
            raise SystemExit("--prompt is for whisper only")
        out[1:1] = ["--prompt", prompt]
    out[1:1] = extra
    return out


def run_batch(
    command: list[str], seconds: float, sampler: GpuSampler
) -> tuple[subprocess.CompletedProcess[bytes], float]:
    started = time.monotonic()
    proc = subprocess.run(  # noqa: S603
        command,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        creationflags=subprocess.CREATE_NO_WINDOW,
        timeout=600 + 0.5 * seconds,
        check=False,
    )
    return proc, time.monotonic() - started


def transcript(raw: dict[str, Any]) -> str:
    return "".join(
        str(item.get("text", "")) for item in cast("list[dict[str, Any]]", raw["transcription"])
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--tag", required=True)
    parser.add_argument("--engine", choices=("whisper", "qwen3"), required=True)
    parser.add_argument(
        "--lang", default="zh", help="the -l value; qwen3 also accepts what you try"
    )
    parser.add_argument("--set", dest="lang_set", default="zh", help="FLEURS language of the audio")
    parser.add_argument("--subset", default="all", help="all or everyN")
    parser.add_argument("--no-aligner", action="store_true")
    parser.add_argument("--lenient", action="store_true", help="CrispASR without --strict-pipeline")
    parser.add_argument("--prompt")
    parser.add_argument("--wav-dir", type=Path, help="wavs of a folder instead of FLEURS")
    parser.add_argument("--extra", nargs="*", default=[])
    args = parser.parse_args()

    set_idle_priority()
    wait_until_free()
    engine_id = WHISPER_ID if args.engine == "whisper" else CRISPASR_ID
    engine = make_engine(engine_id, strict=not args.lenient)
    if (issue := engine.problem()) is not None:
        raise SystemExit(issue.message)
    if args.wav_dir:
        items = [
            Utterance(p.stem, "zh", p, "", 0.0, "") for p in sorted(args.wav_dir.glob("*.wav"))
        ]
    else:
        items = pick(args.lang_set, args.subset)
    wavs = [u.wav for u in items]
    import wave

    audio_s = 0.0
    for wav in wavs:
        with wave.open(str(wav), "rb") as reader:
            audio_s += reader.getnframes() / reader.getframerate()

    results: dict[str, str] = {}
    errors: list[str] = []
    timings: dict[str, float] = defaultdict(float)
    batches: list[dict[str, Any]] = []
    stderr_tail = ""
    wrapper_words = 0
    wrapper_failures = 0
    sampler = GpuSampler()
    started = time.monotonic()
    with tempfile.TemporaryDirectory(prefix="zhz0-", dir=str(DATA.parent / "tmp")) as raw_work:
        work = Path(raw_work)
        for start, stop in engine.command_batches(wavs, work):
            outputs = [work / f"o{i:05d}" for i in range(start, stop)]
            command = edit_command(
                engine.command(wavs[start:stop], outputs, args.lang),
                engine_id,
                args.prompt,
                args.no_aligner,
                args.extra,
            )
            proc, wall = run_batch(command, audio_s, sampler)
            err = proc.stderr.decode("utf-8", errors="replace")
            stderr_tail = err[-1500:]
            batches.append({"files": stop - start, "wall_s": wall, "exit": proc.returncode})
            for name, value in _TIMING.findall(err):
                timings[name] += float(value) / 1000
            if proc.returncode != 0:
                errors.append(f"exit {proc.returncode}: {err[-400:]}")
                continue
            for index, base in zip(range(start, stop), outputs, strict=True):
                out = engine.output_path(base)
                try:
                    results[items[index].key] = transcript(read_json(out))
                except (OSError, KeyError, ValueError) as exc:
                    errors.append(f"{items[index].key}: {exc!r}")
                    continue
                try:
                    segments = engine.parse(out, args.lang)
                    wrapper_words += sum(len(s.words or ()) for s in segments)
                except Exception:  # noqa: BLE001 - the count of wrapper failures is the point
                    wrapper_failures += 1
    wall_total = time.monotonic() - started
    gpu = sampler.stop()
    write_json(
        RUNS / f"{args.tag}.json",
        {
            "tag": args.tag,
            "engine": engine_id,
            "lang_flag": args.lang,
            "audio_set": args.lang_set,
            "wav_dir": str(args.wav_dir) if args.wav_dir else None,
            "subset": args.subset,
            "aligner": not args.no_aligner and engine_id == CRISPASR_ID,
            "strict": not args.lenient,
            "prompt": args.prompt,
            "extra": args.extra,
            "utterances": len(items),
            "audio_s": audio_s,
            "wall_s": wall_total,
            "rtf": wall_total / audio_s,
            "gpu": gpu,
            "free_ram_gb_after": free_ram_gb(),
            "stderr_timings_s": dict(timings),
            "batches": batches,
            "errors": errors,
            "wrapper_words": wrapper_words,
            "wrapper_parse_failures": wrapper_failures,
            "stderr_tail": stderr_tail,
            "texts": results,
        },
    )
    print(
        f"{args.tag}: {len(results)}/{len(items)} done, wall {wall_total:.1f}s, "
        f"audio {audio_s:.0f}s, rtf {wall_total / audio_s:.4f}, peak {gpu['peak_mib']} MiB "
        f"(+{gpu['peak_over_baseline_mib']}), errors {len(errors)}",
        flush=True,
    )
    return 1 if errors else 0


if __name__ == "__main__":
    (DATA.parent / "tmp").mkdir(parents=True, exist_ok=True)
    sys.exit(main())
