from __future__ import annotations

import random
import statistics
import sys
import tempfile
import timeit
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from backend.core.model import Cue
from backend.core.subtitle_io import (
    parse_ass,
    parse_srt,
    parse_subs,
    parse_vtt,
    read_text_file,
    render_ass,
    render_srt,
    render_subs,
    render_vtt,
    write_text_file,
)

CUE_COUNT = 2000
ROUNDS = 5
CALLS_PER_SAMPLE = 5
LIMIT_MS = 200.0

EN_WORDS = "the talk about model training data we think people really ideas work first".split()
ZH_CHARS = "我們今天要談論模型訓練資料的重點想法工作第一個人們其實認為"


def make_cues(count: int, seed: int = 7) -> list[Cue]:
    rng = random.Random(seed)

    def en_line() -> str:
        return " ".join(rng.choice(EN_WORDS) for _ in range(7)).capitalize() + ","

    def zh_line() -> str:
        return "".join(rng.choice(ZH_CHARS) for _ in range(16)) + "，"

    cues: list[Cue] = []
    clock = 0
    for cue_id in range(1, count + 1):
        start = clock + rng.randint(80, 600)
        end = start + rng.randint(1500, 6000)
        cues.append(
            Cue(cue_id, start, end, f"{en_line()}\n{en_line()}", f"{zh_line()}\n{zh_line()}")
        )
        clock = end
    return cues


@dataclass(frozen=True)
class Format:
    name: str
    suffix: str
    render: Callable[[list[Cue]], str]
    parse: Callable[[str], list[Cue]]


FORMATS = [
    Format(
        "srt",
        ".srt",
        lambda cues: render_srt(cues, "bilingual"),
        lambda text: parse_srt(text, "en"),
    ),
    Format(
        "vtt",
        ".vtt",
        lambda cues: render_vtt(cues, "bilingual"),
        lambda text: parse_vtt(text, "en"),
    ),
    Format("ass", ".ass", render_ass, parse_ass),
    Format("subs.json", ".json", render_subs, parse_subs),
]


def measure(fmt: Format, cues: list[Cue], directory: Path, *, files: bool) -> tuple[float, float]:
    path = directory / f"bench{fmt.suffix}"
    text = fmt.render(cues)

    def write() -> None:
        if files:
            write_text_file(path, fmt.render(cues))
        else:
            fmt.render(cues)

    def read() -> None:
        result = fmt.parse(read_text_file(path) if files else text)
        if len(result) != CUE_COUNT:
            raise AssertionError(f"{fmt.name}: parsed {len(result)} cues, expected {CUE_COUNT}")

    write()
    read()
    writes: list[float] = []
    reads: list[float] = []
    for _ in range(ROUNDS):
        writes.append(timeit.timeit(write, number=CALLS_PER_SAMPLE) / CALLS_PER_SAMPLE * 1000)
        reads.append(timeit.timeit(read, number=CALLS_PER_SAMPLE) / CALLS_PER_SAMPLE * 1000)
    return statistics.median(writes), statistics.median(reads)


def main() -> int:
    cues = make_cues(CUE_COUNT)
    worst = 0.0
    print(f"{CUE_COUNT} bilingual cues, {ROUNDS} rounds x {CALLS_PER_SAMPLE} calls, median ms")
    print(f"{'format':<10}{'io':<8}{'bytes':>9}{'write':>9}{'read':>9}{'total':>9}")
    with tempfile.TemporaryDirectory() as tmp:
        for fmt in FORMATS:
            size = len(fmt.render(cues).encode("utf-8"))
            for files in (False, True):
                write_ms, read_ms = measure(fmt, cues, Path(tmp), files=files)
                total = write_ms + read_ms
                worst = max(worst, total)
                label = "file" if files else "memory"
                print(
                    f"{fmt.name:<10}{label:<8}{size:>9}{write_ms:>9.2f}{read_ms:>9.2f}{total:>9.2f}"
                )
    verdict = "PASS" if worst < LIMIT_MS else "FAIL"
    print(f"worst read+write {worst:.2f} ms, limit {LIMIT_MS:.0f} ms: {verdict}")
    return 0 if worst < LIMIT_MS else 1


if __name__ == "__main__":
    sys.exit(main())
