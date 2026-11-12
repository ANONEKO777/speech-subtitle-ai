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
        language, as Japanese text over English audio does, so a talk in two languages turns it off."""

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
            segments = (_segment(item) for item in raw["transcription"])
            return [segment for segment in segments if segment is not None]
        except (KeyError, TypeError, ValueError, AttributeError) as exc:
            raise EngineOutputError(f"unexpected CrispASR JSON in {output.name}: {exc!r}") from exc

    def on_stderr_line(self, line: str, progress: MonotonicProgress) -> None:
        if line.startswith("crispasr: audio:"):
            progress.start_file()
        elif line.startswith("crispasr: transcribed"):
            progress.within_file(1.0)


def _segment(item: dict[str, Any]) -> Segment | None:
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
