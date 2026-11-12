from __future__ import annotations

import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from backend.core.model import Segment, Word
from backend.engines.base import (
    EngineOutputError,
    MonotonicProgress,
    SubprocessEngine,
    read_json,
    segment_of,
    strip_annotations,
)
from backend.manager.profiles import Device

ENGINE_ID = "crispasr-qwen3-asr-1.7b"


class CrispAsrEngine(SubprocessEngine):
    """v0.8.49 cannot open a non-ASCII path, so a wav at one is copied to an ASCII work folder."""

    id = ENGINE_ID
    ascii_paths_only = True

    def __init__(
        self,
        binary: Path,
        model: Path,
        aligner: Path,
        *,
        device: Device = Device.CUDA,
        timeout_s: float | None = None,
        strict: bool = True,
    ) -> None:
        super().__init__(binary, model, device=device, timeout_s=timeout_s)
        self.aligner = aligner
        self.strict = strict
        """`--strict-pipeline` exits with code 31 when the text and the audio disagree on the
        language, as Japanese text over English audio does, so a mixed talk turns it off."""

    def required_files(self) -> dict[str, Path]:
        return {**super().required_files(), "aligner": self.aligner}

    def command(
        self, inputs: Sequence[Path], output_bases: Sequence[Path], language: str
    ) -> list[str]:
        command = [str(self.binary), "--backend", "qwen3", "-m", str(self.model)]
        command += ["-l", language, "-am", str(self.aligner)]
        if self.strict:
            command.append("--strict-pipeline")
        command.append("-ojf")
        if self.device is Device.CPU:
            command += ["--gpu-backend", "cpu"]
        for out in output_bases:
            command += ["-of", str(out)]
        for wav in inputs:
            command += ["-f", str(wav)]
        return command

    def output_path(self, base: Path) -> Path:
        return base.parent / f"{base.name}.json"

    def parse(self, output: Path, language: str = "en") -> list[Segment]:
        raw = read_json(output)
        try:
            segments = (_segment(item, self.strict) for item in raw["transcription"])
            return [segment for segment in segments if segment is not None]
        except (KeyError, TypeError, ValueError, AttributeError) as exc:
            raise EngineOutputError(f"unexpected CrispASR JSON in {output.name}: {exc!r}") from exc

    def on_stderr_line(self, line: str, progress: MonotonicProgress) -> None:
        if line.startswith("crispasr: audio:"):
            progress.start_file()
        elif line.startswith("crispasr: transcribed"):
            progress.within_file(1.0)


def _spread(text: str, start_ms: int, end_ms: int) -> list[Word]:
    """Words for text the aligner gave none for: a Latin word each, or a character each in text
    with no spaces, in equal shares of the segment."""
    units = text.split() if " " in text.strip() else list(text.strip())
    step = max(1, (end_ms - start_ms) // len(units))
    return [
        Word(
            unit,
            start_ms + i * step,
            max(start_ms + i * step, min(end_ms, start_ms + (i + 1) * step)),
        )
        for i, unit in enumerate(units)
    ]


def _segment(item: dict[str, Any], strict: bool = True) -> Segment | None:
    """A segment the aligner gave no words for is an error, except in a talk in two languages
    (`strict` off), where text Qwen3 wrote over the other language's audio cannot be aligned: it is
    spread evenly over the segment."""
    if "words" not in item:
        text = str(item.get("text", "")).strip()
        if not text:
            return None
        if strict:
            raise KeyError("words")
        start, end = item["offsets"]["from"], item["offsets"]["to"]
        spread = strip_annotations(_spread(text, start, end))
        return segment_of(spread, start, end) if spread else None
    words = strip_annotations(
        [
            Word(
                w["text"].strip(),
                w["offsets"]["from"],
                max(w["offsets"]["from"], w["offsets"]["to"]),
            )
            for w in item["words"]
            if w["text"].strip()
        ]
    )
    if not words:
        return None
    return segment_of(words, item["offsets"]["from"], item["offsets"]["to"])


def main(argv: Sequence[str] | None = None) -> int:
    from backend.engines.cli import main as cli_main

    return cli_main(ENGINE_ID, argv)


if __name__ == "__main__":
    sys.exit(main())
