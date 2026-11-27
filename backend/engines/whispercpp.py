from __future__ import annotations

import re
import subprocess
import sys
import unicodedata
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from backend.core import notices, process_guard, vc_runtime
from backend.core.language_detect import Heard
from backend.core.model import Segment, Word
from backend.core.notices import noticed
from backend.core.source_langs import is_spaced
from backend.engines.base import (
    EngineFailedError,
    EngineOutputError,
    EngineTimeoutError,
    EngineUnavailableError,
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
_DETECTED = re.compile(r"auto-detected language: (\w+) \(p = ([0-9.]+)\)")


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

    def parse(self, output: Path, language: str = "en") -> list[Segment]:
        raw = read_json(output)
        spaced = is_spaced(language)
        try:
            segments = (_segment(item, spaced) for item in raw["transcription"])
            return [segment for segment in segments if segment is not None]
        except (KeyError, TypeError, ValueError, AttributeError) as exc:
            odd = notices.BAD_WHISPER_JSON(file=output.name, error=repr(exc))
            raise noticed(EngineOutputError, odd) from exc

    def on_stderr_line(self, line: str, progress: MonotonicProgress) -> None:
        if _PROCESSING.match(line):
            progress.start_file()
        elif (fraction := percent_in(line)) is not None:
            progress.within_file(fraction)


def _segment(item: dict[str, Any], spaced: bool) -> Segment | None:
    words = strip_annotations(_words(item["tokens"], spaced))
    if not words:
        return None
    return segment_of(words, item["offsets"]["from"], item["offsets"]["to"])


def _continues(word: str, text: str) -> bool:
    """Whether a token with no leading space goes on a word of a language written without spaces:
    the letters or digits of a Latin word, or punctuation that belongs to what came before. Every
    other token is its own word, because there is no space to say where a word ends."""
    latin = (
        word[-1:].isascii() and word[-1:].isalnum() and text[:1].isascii() and text[:1].isalnum()
    )
    return latin or all(unicodedata.category(char)[0] in "PS" for char in text)


def _words(tokens: list[dict[str, Any]], spaced: bool = True) -> list[Word]:
    """Whisper gives subword tokens. In a spaced language a token with no leading space goes on
    the word before it. A Japanese token is one or two characters and has none, so it stays a word
    of its own and the cue rules decide where a line may break."""
    spans: list[list[Any]] = []
    for token in tokens:
        text: str = token["text"]
        if text.startswith("[_") or not text.strip():
            continue
        start: int = token["offsets"]["from"]
        end = max(start, token["offsets"]["to"])
        if spans and not text.startswith(" ") and (spaced or _continues(spans[-1][0], text)):
            spans[-1][0] += text
            spans[-1][2] = max(end, spans[-1][1])
        else:
            spans.append([text.strip(), start, end])
    return [Word(text, start, end) for text, start, end in spans]


def name_languages(
    binary: Path, model: Path, wavs: Sequence[Path], *, device: Device, timeout_s: float
) -> list[Heard]:
    """The language Whisper names for each wav, from one run that loads the model once
    (`-dl` stops each file after the language is known, so no text is decoded)."""
    vc_runtime.require(EngineUnavailableError)
    command = [str(binary), "-m", str(model), "-l", "auto", "-dl"]
    if device is Device.CPU:
        command.append("-ng")
    for wav in wavs:
        command += ["-f", str(wav)]
    flags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
    try:
        proc = subprocess.Popen(
            command,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            creationflags=flags,
        )
    except OSError as exc:
        raise EngineUnavailableError(f"{ENGINE_ID}: cannot start {binary}: {exc}") from exc
    process_guard.adopt(proc)
    try:
        _, err = proc.communicate(timeout=timeout_s)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.communicate()
        raise EngineTimeoutError(
            f"{ENGINE_ID} did not name the languages in {timeout_s:g} s"
        ) from None
    except BaseException:
        proc.kill()
        raise
    text = err.decode("utf-8", errors="replace")
    if proc.returncode != 0:
        raise EngineFailedError(f"{ENGINE_ID} exited with code {proc.returncode}: {text[-300:]}")
    heard = [Heard(code, float(p)) for code, p in _DETECTED.findall(text)]
    if len(heard) != len(wavs):
        raise EngineOutputError(f"{ENGINE_ID} named {len(heard)} languages for {len(wavs)} files")
    return heard


def main(argv: Sequence[str] | None = None) -> int:
    from backend.engines.cli import main as cli_main

    return cli_main(ENGINE_ID, argv)


if __name__ == "__main__":
    sys.exit(main())
