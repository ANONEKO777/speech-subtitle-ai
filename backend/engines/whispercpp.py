from __future__ import annotations

import re
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from backend.core.model import Segment, Word
from backend.engines.base import (
    EngineOutputError,
    MonotonicProgress,
    SubprocessEngine,
    percent_in,
    read_json,
    segment_of,
    strip_annotations,
)
from backend.manager.profiles import Device

ENGINE_ID = "whispercpp-large-v3-turbo"
_PROCESSING = re.compile(r"^main: processing ")


class WhisperCppEngine(SubprocessEngine):
    id = ENGINE_ID

    def command(
        self, inputs: Sequence[Path], output_bases: Sequence[Path], language: str
    ) -> list[str]:
        command = [str(self.binary), "-m", str(self.model), "-l", language, "-pp", "-ojf"]
        if self.device is Device.CPU:
            command.append("-ng")
        for out in output_bases:
            command += ["-of", str(out)]
        for wav in inputs:
            command += ["-f", str(wav)]
        return command

    def output_path(self, base: Path) -> Path:
        return base.parent / f"{base.name}.json"

    def parse(self, output: Path) -> list[Segment]:
        raw = read_json(output)
        try:
            segments = (_segment(item) for item in raw["transcription"])
            return [segment for segment in segments if segment is not None]
        except (KeyError, TypeError, ValueError, AttributeError) as exc:
            raise EngineOutputError(
                f"unexpected whisper.cpp JSON in {output.name}: {exc!r}"
            ) from exc

    def on_stderr_line(self, line: str, progress: MonotonicProgress) -> None:
        if _PROCESSING.match(line):
            progress.start_file()
        elif (fraction := percent_in(line)) is not None:
            progress.within_file(fraction)


def _segment(item: dict[str, Any]) -> Segment | None:
    words = strip_annotations(_words(item["tokens"]))
    if not words:
        return None
    return segment_of(words, item["offsets"]["from"], item["offsets"]["to"])


def _words(tokens: list[dict[str, Any]]) -> list[Word]:
    spans: list[list[Any]] = []
    for token in tokens:
        text: str = token["text"]
        if text.startswith("[_") or not text.strip():
            continue
        start: int = token["offsets"]["from"]
        end = max(start, token["offsets"]["to"])
        if spans and not text.startswith(" "):
            spans[-1][0] += text
            spans[-1][2] = max(end, spans[-1][1])
        else:
            spans.append([text.strip(), start, end])
    return [Word(text, start, end) for text, start, end in spans]


def main(argv: Sequence[str] | None = None) -> int:
    from backend.engines.cli import main as cli_main

    return cli_main(ENGINE_ID, argv)


if __name__ == "__main__":
    sys.exit(main())
