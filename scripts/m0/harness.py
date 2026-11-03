import hashlib
import json
import re
import shutil
import statistics
import subprocess
import threading
import time
import wave
from collections.abc import Callable
from dataclasses import asdict, dataclass
from pathlib import Path

VRAM_QUERY = ["--query-gpu=memory.used", "--format=csv,noheader,nounits"]


@dataclass
class Word:
    text: str
    start: float
    end: float


@dataclass
class Segment:
    text: str
    start: float
    end: float
    words: list[Word] | None


@dataclass
class RunRecord:
    engine: str
    audio: str
    audio_seconds: float
    command: list[str]
    exit_code: int
    wall_seconds: float
    rtf: float
    vram_baseline_mib: int
    vram_peak_mib: int
    segments: list[Segment]


def require(tool: str) -> str:
    path = shutil.which(tool)
    if path is None:
        raise SystemExit(f"{tool} not found on PATH")
    return path


def ascii_stem(source: Path) -> str:
    readable = re.sub(r"[^A-Za-z0-9]+", "-", source.stem).strip("-")[:40]
    digest = hashlib.sha256(str(source.resolve()).encode()).hexdigest()[:8]
    return f"{readable}-{digest}" if readable else digest


def to_wav(source: Path, work_dir: Path) -> Path:
    work_dir.mkdir(parents=True, exist_ok=True)
    wav = work_dir / f"{ascii_stem(source)}.wav"
    if not wav.exists():
        subprocess.run(
            [require("ffmpeg"), "-nostdin", "-v", "error", "-y", "-i", str(source)]
            + ["-vn", "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le", str(wav)],
            check=True,
        )
    return wav


def wav_seconds(path: Path) -> float:
    with wave.open(str(path), "rb") as wav:
        return wav.getnframes() / wav.getframerate()


def read_vram_mib(nvidia_smi: str) -> int:
    out = subprocess.run([nvidia_smi, *VRAM_QUERY], capture_output=True, text=True, check=True)
    return int(out.stdout.split()[0])


class VramSampler:
    def __init__(self, log_path: Path) -> None:
        self.nvidia_smi = require("nvidia-smi")
        self.log_path = log_path
        self.samples: list[int] = []
        self.baseline = statistics.median(read_vram_mib(self.nvidia_smi) for _ in range(5))
        self._proc = subprocess.Popen(
            [self.nvidia_smi, *VRAM_QUERY, "-lms", "500"],
            stdout=subprocess.PIPE,
            text=True,
        )
        self._reader = threading.Thread(target=self._read, daemon=True)
        self._reader.start()

    def _read(self) -> None:
        assert self._proc.stdout is not None
        with self.log_path.open("w", encoding="utf-8") as log:
            for line in self._proc.stdout:
                if line.strip().isdigit():
                    self.samples.append(int(line))
                    log.write(f"{time.time():.3f},{line.strip()}\n")

    def stop(self) -> int:
        self._proc.terminate()
        self._proc.wait()
        self._reader.join(timeout=5)
        if not self.samples:
            raise SystemExit("nvidia-smi produced no VRAM samples")
        return max(self.samples)


def sibling(base: Path, suffix: str) -> Path:
    return base.parent / f"{base.name}{suffix}"


def run_engine(
    engine: str,
    command: list[str],
    wav: Path,
    out_base: Path,
    parse: Callable[[Path], list[Segment]],
) -> RunRecord:
    out_base.parent.mkdir(parents=True, exist_ok=True)
    sampler = VramSampler(sibling(out_base, ".vram.csv"))
    started = time.perf_counter()
    with sibling(out_base, ".log").open("w", encoding="utf-8") as log:
        exit_code = subprocess.run(command, stdout=log, stderr=subprocess.STDOUT).returncode
    wall = time.perf_counter() - started
    peak = sampler.stop()
    seconds = wav_seconds(wav)
    segments: list[Segment] = parse(out_base) if exit_code == 0 else []
    record = RunRecord(
        engine=engine,
        audio=wav.name,
        audio_seconds=round(seconds, 3),
        command=command,
        exit_code=exit_code,
        wall_seconds=round(wall, 3),
        rtf=round(wall / seconds, 5),
        vram_baseline_mib=int(sampler.baseline),
        vram_peak_mib=peak,
        segments=segments,
    )
    sibling(out_base, ".run.json").write_text(
        json.dumps(asdict(record), ensure_ascii=False, indent=1), encoding="utf-8"
    )
    print(
        f"{engine} {wav.name}: exit={exit_code} wall={wall:.1f}s rtf={record.rtf:.4f} "
        f"vram_peak={peak}MiB baseline={record.vram_baseline_mib}MiB segments={len(segments)}"
    )
    return record
