"""Measure language detection on real files: what it suggests, how sure it is, how long it takes.

    python scripts/p24c_detect_table.py --whisper-cli whisper-cli.exe \
        --model ggml-large-v3-turbo.bin "ja talk=ja=D:/videos/talk.mp4" "mix=ja+en=D:/videos/m.mp4"

Each argument is `label=true language=path`. The run uses the same code as the window
(`backend.core.language_detect.detect` with `audio.cut_clips` and `name_languages`), so the numbers
are the product's. `--pieces N` changes the number of pieces, `--length S` their length, and
`--mixed-share` the share that calls a talk mixed, to measure other choices. It prints a
Markdown table and exits 1 when a suggestion is not the true language.
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

from backend.core import audio, language_detect
from backend.engines.base import ascii_temp_dir
from backend.engines.whispercpp import name_languages
from backend.manager.profiles import Device


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument("cases", nargs="+", metavar="LABEL=TRUE=PATH")
    parser.add_argument("--whisper-cli", type=Path, required=True)
    parser.add_argument("--model", type=Path, required=True)
    parser.add_argument("--pieces", type=int, default=language_detect.SAMPLE_COUNT)
    parser.add_argument("--length", type=float, default=language_detect.SAMPLE_S)
    parser.add_argument("--mixed-share", type=float, default=language_detect.MIXED_SHARE)
    parser.add_argument("--repeat", type=int, default=1, help="runs per file, to see the spread")
    args = parser.parse_args(argv)
    language_detect.MIXED_SHARE = args.mixed_share

    print("| file | true | suggested | confidence | ja / en share | clear | seconds | ok |")
    print("|---|---|---|---|---|---|---|---|")
    wrong = 0
    for case in args.cases:
        label, truth, path = case.split("=", 2)
        video = Path(path)
        duration = audio.probe_duration_s(video)
        assert duration is not None, f"cannot read {video}"
        for _ in range(args.repeat):
            started = time.perf_counter()
            with ascii_temp_dir() as work:
                found = _run(video, duration, work, args)
            seconds = time.perf_counter() - started
            shares = dict(found.shares)
            ok = found.code == truth
            wrong += not ok
            print(
                f"| {label} | {truth} | {found.code} | {found.confidence:.2f} "
                f"| {shares.get('ja', 0):.2f} / {shares.get('en', 0):.2f} | {found.clear} "
                f"| {seconds:.1f} | {'yes' if ok else 'NO'} |"
            )
    return 1 if wrong else 0


def _run(
    video: Path, duration: float, work: Path, args: argparse.Namespace
) -> language_detect.Detection:
    starts = language_detect.sample_starts(duration, args.pieces, args.length)
    heard = name_languages(
        args.whisper_cli,
        args.model,
        audio.cut_clips(video, starts, args.length, work),
        device=Device.CUDA,
        timeout_s=120,
    )
    return language_detect.decide(
        [language_detect.Sample(s, h) for s, h in zip(starts, heard, strict=True)]
    )


if __name__ == "__main__":
    sys.exit(main())
