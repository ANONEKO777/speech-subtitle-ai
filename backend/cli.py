"""Turn a talk video into subtitles in its own language, translated subtitles and a summary.

    python -m backend.cli talk.mp4 --engine whispercpp --llm qwen3-8b-q4_k_m --lang ja
    python -m backend.cli talk.mp4 --source-lang ja

The talk is in English unless `--source-lang` says otherwise. Writes en.srt (ja.srt for a
Japanese talk), the translation (zh-TW.srt for the default Traditional Chinese, ja.srt for
`--lang ja`), the bilingual .ass and .vtt, the summary and project.json into a project folder.
Another `--lang` on the same folder adds that language and keeps the others.
Running the same command again does no work. If a run stops, the same command resumes it.
"""

from __future__ import annotations

import argparse
import io
import sys
from collections.abc import Sequence
from pathlib import Path

from backend.core.languages import DEFAULT_CODE, LANGUAGES
from backend.core.languages import get as get_language
from backend.core.media import accepted_extensions, is_media
from backend.core.model import DEFAULT_SOURCE, FormatError
from backend.core.pipeline import (
    PROJECT_JSON,
    Cancelled,
    PipelineError,
    Progress,
    run,
)
from backend.core.source_langs import SOURCES
from backend.core.translate import BATCH_SIZE, GlossaryEntry
from backend.llm.local_server import ServerError
from backend.manager.profiles import QWEN3_8B
from backend.manager.resolve import DEFAULT_KEY_ENV, ENGINE_ALIASES, Request, SettingsError, resolve

EXIT_FAILED = 1
EXIT_USAGE = 2
EXIT_INTERRUPTED = 130
_PROGRESS_STEP = 0.1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m backend.cli",
        description=(
            "Turn a talk video into subtitles in its own language, translated subtitles "
            "and a key-points summary. Steps whose inputs did not change are skipped, so running "
            "the same command again does nothing, and a stopped run resumes where it stopped."
        ),
    )
    parser.add_argument("input", type=Path, help="the video (or audio) file to subtitle")
    parser.add_argument(
        "-o",
        "--project",
        type=Path,
        metavar="DIR",
        help="project folder for all outputs and caches (default: INPUT with the suffix '.vst', "
        "next to the video)",
    )
    parser.add_argument(
        "--engine",
        default="whispercpp",
        help=f"speech recognition engine: {', '.join(ENGINE_ALIASES)} or a full engine id "
        "(default: whispercpp, whisper.cpp large-v3-turbo). A talk in ja+en always uses crispasr",
    )
    parser.add_argument(
        "--llm",
        default=QWEN3_8B,
        help="the model for translation and summary: a registry model id (a local llama-server "
        "is started for the run and stopped after), a path to a .gguf file, or the base URL of "
        f"an OpenAI-compatible server such as Ollama or a cloud API (default: {QWEN3_8B})",
    )
    parser.add_argument(
        "--llm-model", metavar="NAME", help="the model name to send when --llm is a URL"
    )
    parser.add_argument(
        "--llm-key-env",
        default=DEFAULT_KEY_ENV,
        metavar="VAR",
        help="environment variable that holds the API key for a URL --llm "
        f"(default: {DEFAULT_KEY_ENV}); a key is never taken from the command line",
    )
    parser.add_argument(
        "--glossary",
        action="append",
        default=[],
        metavar="TERM[=ZH]",
        help="a term to keep in English (TERM) or to translate in a fixed way (TERM=ZH_TEXT); "
        "may be repeated. Product names such as Cursor and Claude Code are always kept in English",
    )
    parser.add_argument(
        "--lang",
        default=DEFAULT_CODE,
        choices=list(LANGUAGES),
        metavar="CODE",
        help="the language to translate into: "
        + ", ".join(f"{lang.code} ({lang.name})" for lang in LANGUAGES.values())
        + f" (default: {DEFAULT_CODE}). A project keeps one translation per language",
    )
    parser.add_argument(
        "--source-lang",
        default=DEFAULT_SOURCE,
        choices=list(SOURCES),
        metavar="CODE",
        help="the language the talk is spoken in: "
        + ", ".join(f"{source.code} ({source.name})" for source in SOURCES.values())
        + f" (default: {DEFAULT_SOURCE}). Japanese can be translated into Traditional Chinese "
        "(zh-TW) for now",
    )
    parser.add_argument(
        "--summary-en", action="store_true", help="also write summary.en.md in English"
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=BATCH_SIZE,
        metavar="N",
        help="cues per translation request",
    )
    parser.add_argument(
        "--cpu", action="store_true", help="run the speech and language models on the CPU"
    )
    parser.add_argument(
        "--user-data",
        type=Path,
        metavar="DIR",
        help="folder where downloaded runtimes and models live "
        "(default: $VST_USER_DATA or %%LOCALAPPDATA%%/video-subtitle-translator)",
    )
    parser.add_argument("--asr-bin", type=Path, metavar="FILE", help="ASR program to use instead")
    parser.add_argument("--asr-model", type=Path, metavar="FILE", help="ASR model file to use")
    parser.add_argument("--aligner", type=Path, metavar="FILE", help="aligner model for crispasr")
    parser.add_argument(
        "--llama-server", type=Path, metavar="FILE", help="llama-server program to use"
    )
    parser.add_argument("--vad-model", type=Path, metavar="FILE", help="silero VAD ONNX model file")
    parser.add_argument(
        "--ffmpeg-dir", type=Path, metavar="DIR", help="folder with ffmpeg and ffprobe"
    )
    return parser


def _glossary(items: Sequence[str]) -> tuple[GlossaryEntry, ...]:
    entries: list[GlossaryEntry] = []
    for item in items:
        term, _, zh = item.partition("=")
        entries.append(GlossaryEntry(term.strip(), zh.strip()))
    return tuple(entries)


class _Printer:
    def __init__(self) -> None:
        self._last: tuple[str, float] | None = None

    def __call__(self, progress: Progress) -> None:
        step = progress.step.value
        if progress.message == "cached":
            print(f"{step:<10} cached", file=sys.stderr, flush=True)
        elif progress.fraction <= 0.0:
            print(f"{step:<10} start", file=sys.stderr, flush=True)
        elif progress.fraction >= 1.0:
            print(f"{step:<10} done", file=sys.stderr, flush=True)
        elif (
            self._last is None
            or self._last[0] != step
            or progress.fraction >= self._last[1] + _PROGRESS_STEP
        ):
            self._last = (step, progress.fraction)
            print(f"{step:<10} {progress.fraction:4.0%}", file=sys.stderr, flush=True)


def main(argv: Sequence[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        if isinstance(stream, io.TextIOWrapper):
            stream.reconfigure(errors="backslashreplace")
    args = build_parser().parse_args(argv)
    video: Path = args.input
    if not video.is_file():
        print(f"error: input file not found: {video}", file=sys.stderr)
        return EXIT_USAGE
    if not is_media(video):
        print(
            f"error: not a media file extension: {video}; accepted: {accepted_extensions()}",
            file=sys.stderr,
        )
        return EXIT_USAGE
    folder: Path = args.project or video.with_suffix(".vst")
    try:
        request = Request(
            engine=args.engine,
            asr_bin=args.asr_bin,
            asr_model=args.asr_model,
            aligner=args.aligner,
            cpu=args.cpu,
            llm=args.llm,
            llm_model=args.llm_model,
            llm_key_env=args.llm_key_env,
            llama_server=args.llama_server,
            vad_model=args.vad_model,
            ffmpeg_dir=args.ffmpeg_dir,
            user_data=args.user_data,
            glossary=_glossary(args.glossary),
            summary_en=args.summary_en,
            batch_size=args.batch_size,
            target_lang=args.lang,
            source_lang=args.source_lang,
        )
        settings, ports = resolve(request, folder)
    except (SettingsError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_USAGE
    try:
        report = run(video, folder, settings, ports, progress=_Printer())
    except KeyboardInterrupt:
        print("\ninterrupted; run the same command to resume", file=sys.stderr)
        return EXIT_INTERRUPTED
    except Cancelled as exc:
        print(f"{exc}; run the same command to resume", file=sys.stderr)
        return EXIT_INTERRUPTED
    except (PipelineError, ServerError, FormatError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_FAILED
    print(report.describe())
    files = get_language(args.lang).files
    source_srt = SOURCES[args.source_lang].files.srt
    print(
        f"project: {folder}  ({PROJECT_JSON}, {source_srt}, {files.srt}, {files.ass}, "
        f"{files.summary})"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
