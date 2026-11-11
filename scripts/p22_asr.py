"""P22 lever: run one ASR engine on one wav and save the raw engine output plus run numbers.

Two modes. `whole` hands the whole wav to the engine, as the M0 bake-off did. `chunks` cuts the
wav with the app's own VAD planner (`backend.core.vad`) and gives each chunk to the engine in one
process, as the pipeline does. The saved JSON keeps the engine's own units (whisper.cpp tokens,
CrispASR words) unmerged, because the project's word builder joins tokens that lack a leading
space, and Japanese has none.

    uv run python scripts/p22_asr.py whisper cedec.wav --mode chunks --lang ja --out out/dir
"""

from __future__ import annotations

import argparse
import json
import statistics
import subprocess
import sys
import threading
import time
import wave
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, cast

from backend.core import vad
from backend.engines.chunks import write_chunks

ROOT = Path(__file__).resolve().parents[1]
MAIN = Path(__file__).resolve().parents[3] if ROOT.parent.name == ".worktrees" else ROOT
WHISPER_BIN = MAIN / "runtimes/whispercpp-b5454-win-cuda12.4/Release/whisper-cli.exe"
CRISPASR_BIN = MAIN / "runtimes/crispasr-v0.8.49-win-cuda/crispasr-windows-x86_64-cuda/crispasr.exe"
MODELS = {
    "whisper": MAIN / "models/whisper/ggml-large-v3-turbo.bin",
    "kotoba": MAIN / ".work/p22/models/ggml-kotoba-whisper-v2.0.bin",
    "qwen3": MAIN / "models/qwen3-asr/qwen3-asr-1.7b-q8_0.gguf",
}
ALIGNER = MAIN / "models/qwen3-forced-aligner/qwen3-forced-aligner-0.6b-q8_0.gguf"
SILERO_BIN = MAIN / "models/silero-vad/ggml-silero-v6.2.0.bin"
SILERO_ONNX = MAIN / "models/silero-vad/silero_vad.onnx"
GPU_PROCESSES = ("whisper-cli", "crispasr", "llama-server")
VRAM_QUERY = ["--query-gpu=memory.used", "--format=csv,noheader,nounits"]


@dataclass(frozen=True, slots=True)
class Unit:
    text: str
    start_ms: int
    end_ms: int
    p: float | None = None


@dataclass(frozen=True, slots=True)
class Seg:
    start_ms: int
    end_ms: int
    text: str
    units: list[Unit]


@dataclass(frozen=True, slots=True)
class ChunkOut:
    index: int
    start_ms: int
    end_ms: int
    segments: list[Seg]
    detected: str | None = None


def gpu_busy() -> list[str]:
    out = subprocess.run(["tasklist"], capture_output=True, text=True, check=True).stdout.lower()
    return [name for name in GPU_PROCESSES if name in out]


def wav_seconds(path: Path) -> float:
    with wave.open(str(path), "rb") as reader:
        return reader.getnframes() / reader.getframerate()


def vram_now() -> int:
    out = subprocess.run(["nvidia-smi", *VRAM_QUERY], capture_output=True, text=True, check=True)
    return int(out.stdout.split()[0])


class VramSampler:
    def __init__(self) -> None:
        self.baseline = int(statistics.median(vram_now() for _ in range(5)))
        self.samples: list[int] = []
        self._proc = subprocess.Popen(
            ["nvidia-smi", *VRAM_QUERY, "-lms", "500"], stdout=subprocess.PIPE, text=True
        )
        self._thread = threading.Thread(target=self._read, daemon=True)
        self._thread.start()

    def _read(self) -> None:
        assert self._proc.stdout is not None
        for line in self._proc.stdout:
            if line.strip().isdigit():
                self.samples.append(int(line))

    def stop(self) -> int:
        self._proc.terminate()
        self._proc.wait()
        self._thread.join(timeout=5)
        return max(self.samples, default=self.baseline)


def command_for(
    engine: str,
    lang: str,
    inputs: list[Path],
    bases: list[Path],
    *,
    vad_in_engine: bool,
    strict: bool = True,
) -> list[str]:
    if engine in ("whisper", "kotoba"):
        command = [str(WHISPER_BIN), "-m", str(MODELS[engine]), "-l", lang, "-pp", "-ojf"]
        for base in bases:
            command += ["-of", str(base)]
    else:
        command = [str(CRISPASR_BIN), "--backend", "qwen3", "-m", str(MODELS[engine])]
        command += ["-l", lang, "-am", str(ALIGNER), "-ojf"]
        if strict:
            command.append("--strict-pipeline")
        if vad_in_engine:
            command += ["--vad", "-vm", str(SILERO_BIN)]
        for base in bases:
            command += ["-of", str(base)]
    for wav in inputs:
        command += ["-f", str(wav)]
    return command


def _units_whisper(tokens: list[dict[str, Any]]) -> list[Unit]:
    units: list[Unit] = []
    for token in tokens:
        text = str(token["text"])
        if text.startswith("[_"):
            continue
        start = int(token["offsets"]["from"])
        units.append(
            Unit(text, start, max(start, int(token["offsets"]["to"])), float(token.get("p", 0)))
        )
    return units


def _units_crisp(words: list[dict[str, Any]]) -> list[Unit]:
    return [
        Unit(
            str(w["text"]),
            int(w["offsets"]["from"]),
            max(int(w["offsets"]["from"]), int(w["offsets"]["to"])),
        )
        for w in words
    ]


def parse_raw(engine: str, path: Path) -> tuple[list[Seg], str | None]:
    raw = cast("dict[str, Any]", json.loads(path.read_text(encoding="utf-8", errors="replace")))
    result = raw.get("result")
    detected = (
        str(cast("dict[str, Any]", result).get("language")) if isinstance(result, dict) else None
    )
    segs: list[Seg] = []
    for item in cast("list[dict[str, Any]]", raw["transcription"]):
        if engine == "qwen3":
            units = _units_crisp(cast("list[dict[str, Any]]", item.get("words", [])))
        else:
            units = _units_whisper(cast("list[dict[str, Any]]", item.get("tokens", [])))
        segs.append(
            Seg(
                int(item["offsets"]["from"]),
                int(item["offsets"]["to"]),
                str(item["text"]).strip(),
                units,
            )
        )
    return segs, detected


def plan(wav: Path, chunks_json: Path) -> list[vad.Chunk]:
    if chunks_json.is_file():
        data = cast("list[list[int]]", json.loads(chunks_json.read_text()))
        return [vad.Chunk(a, b) for a, b in data]
    chunks = vad.split(wav, SILERO_ONNX)
    chunks_json.write_text(json.dumps([[c.start_ms, c.end_ms] for c in chunks]))
    return chunks


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("engine", choices=("whisper", "kotoba", "qwen3"))
    parser.add_argument("wav", type=Path)
    parser.add_argument("--mode", choices=("whole", "chunks"), required=True)
    parser.add_argument("--lang", required=True, help="ja, en or auto")
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--chunks-json", type=Path, help="VAD plan to reuse or create")
    parser.add_argument("--suffix", default="", help="added to the run name")
    parser.add_argument("--lenient", action="store_true", help="CrispASR without --strict-pipeline")
    parser.add_argument("--engine-vad", action="store_true", help="whole mode: CrispASR --vad")
    args = parser.parse_args()
    wav: Path = args.wav
    out: Path = args.out
    out.mkdir(parents=True, exist_ok=True)
    lenient = "-lenient" if args.lenient else ""
    tag = f"{args.engine}-{wav.stem}-{args.mode}-{args.lang}{lenient}{args.suffix}"
    if busy := gpu_busy():
        raise SystemExit(f"GPU busy: {busy}")

    chunks: list[vad.Chunk]
    if args.mode == "chunks":
        chunks = plan(wav, args.chunks_json or out / f"{wav.stem}.chunks.json")
        work = out / f"{tag}.work"
        work.mkdir(exist_ok=True)
        paths = write_chunks(wav, chunks, work, None)
    else:
        chunks = [vad.Chunk(0, int(wav_seconds(wav) * 1000))]
        paths = [wav]
    bases = [out / f"{tag}.raw{i:04d}" for i in range(len(paths))]
    command = command_for(
        args.engine, args.lang, paths, bases, vad_in_engine=args.engine_vad, strict=not args.lenient
    )
    sampler = VramSampler()
    started = time.perf_counter()
    with (out / f"{tag}.log").open("w", encoding="utf-8") as log:
        code = subprocess.run(command, stdout=log, stderr=subprocess.STDOUT).returncode
    wall = time.perf_counter() - started
    peak = sampler.stop()
    seconds = wav_seconds(wav)
    audio_s = sum(c.duration_ms for c in chunks) / 1000 if args.mode == "chunks" else seconds
    outs: list[ChunkOut] = []
    if code == 0:
        for index, (chunk, base) in enumerate(zip(chunks, bases, strict=True)):
            segs, detected = parse_raw(args.engine, base.parent / f"{base.name}.json")
            outs.append(ChunkOut(index, chunk.start_ms, chunk.end_ms, segs, detected))
    record = {
        "engine": args.engine,
        "mode": args.mode,
        "lang": args.lang,
        "wav": wav.name,
        "wav_seconds": round(seconds, 1),
        "chunk_audio_seconds": round(audio_s, 1),
        "exit_code": code,
        "wall_s": round(wall, 1),
        "rtf_wav": round(wall / seconds, 4),
        "vram_baseline_mib": sampler.baseline,
        "vram_peak_mib": peak,
        "command": [Path(c).name if i == 0 else c for i, c in enumerate(command[:14])],
        "chunks": [asdict(c) for c in outs],
    }
    (out / f"{tag}.json").write_text(json.dumps(record, ensure_ascii=False), encoding="utf-8")
    print(
        f"{tag}: exit={code} wall={wall:.1f}s rtf={wall / seconds:.4f} "
        f"vram_peak={peak}MiB (baseline {sampler.baseline}) chunks={len(outs)}"
    )
    for base in bases:
        base.parent.joinpath(f"{base.name}.json").unlink(missing_ok=True)
    return code


if __name__ == "__main__":
    sys.exit(main())
