"""Shared helpers of the Z0 Chinese-source experiments (`scripts/zh_z0_*.py`, `docs/ZH-ASR-DECISION.md`).

Everything is read-only against the app: engines are built with the repository's own wrappers
(`backend/engines`) from the files the app keeps in its user-data folder, nothing is written there,
and nothing is installed. Outputs go to `<main checkout>/.work/zh-z0/`, which git ignores. One model
process runs at a time, at Idle priority, and a run stops when less than 8 GB of RAM is free.
"""
# ruff: noqa: E501

from __future__ import annotations

import ctypes
import statistics
import subprocess
import sys
import threading
import time
from dataclasses import dataclass
from pathlib import Path

from zh_z0_text import (
    DATA,
    FLEURS_LANGS,
    MAIN,
    ROOT,
    RUNS,
    SAMPLE_RATE,
    WORK,
    Utterance,
    load_utterances,
    read_json,
    wav_seconds,
    write_json,
)

from backend.engines.base import SubprocessEngine
from backend.engines.crispasr import ENGINE_ID as CRISPASR_ID
from backend.engines.table import create_engine, spec_for
from backend.engines.whispercpp import ENGINE_ID as WHISPER_ID
from backend.manager.profiles import QWEN3_ASR, WHISPER_TURBO, Device, runtime_set
from backend.manager.registry import ModelKind
from backend.manager.registry import load as load_registry
from backend.manager.runtimes import program_of
from backend.manager.storage import Storage, default_user_data

__all__ = [
    "CRISPASR_ID", "DATA", "FLEURS_LANGS", "MAIN", "ROOT", "RUNS", "SAMPLE_RATE", "WHISPER_ID",
    "WORK", "Device", "Utterance", "load_utterances", "read_json", "wav_seconds", "write_json",
    "engine_files", "make_engine", "storage", "llama_server_files", "set_idle_priority",
    "wait_until_free", "free_ram_gb", "GpuSampler",
]  # fmt: skip

GPU_PROCESSES = ("whisper-cli", "crispasr", "llama-server")
MIN_FREE_RAM_GB = 8.0
VRAM_QUERY = ["--query-gpu=memory.used,utilization.gpu", "--format=csv,noheader,nounits"]


def storage() -> Storage:
    return Storage(default_user_data())


@dataclass(frozen=True, slots=True)
class Files:
    binary: Path
    model: Path
    aligner: Path | None


def engine_files(engine_id: str) -> Files:
    """The files `backend.engines.table.engine_paths` names, without its `recover_runtime` step, so
    nothing in the app's folder is touched."""
    registry = load_registry()
    spec = spec_for(engine_id)
    runtime = registry.runtimes[getattr(runtime_set(), spec.role)]
    model = registry.models[spec.model_id]
    aligner = next(
        (registry.models[n] for n in model.needs if registry.models[n].kind is ModelKind.ALIGNER),
        None,
    )
    store = storage()
    return Files(
        program_of(runtime, store),
        store.model_file(model),
        store.model_file(aligner) if aligner else None,
    )


def make_engine(engine_id: str, *, strict: bool = True) -> SubprocessEngine:
    found = engine_files(engine_id)
    return create_engine(
        engine_id,
        found.binary,
        found.model,
        aligner=found.aligner,
        device=Device.CUDA,
        strict=strict,
    )


def llama_server_files() -> tuple[Path, Path]:
    store = storage()
    root = store.runtimes_root / "llama.cpp-b12068-win-cuda12.4"
    gguf = store.models_root / "qwen3-8b-q4_k_m" / "Qwen3-8B-Q4_K_M.gguf"
    return root / "llama-server.exe", gguf


def asset_ids() -> dict[str, str]:
    return {"whisper_model": WHISPER_TURBO, "qwen3_model": QWEN3_ASR}


def set_idle_priority() -> None:
    """Windows gives a child the priority class of an Idle parent, so every engine runs at Idle."""
    if sys.platform == "win32":
        kernel = ctypes.windll.kernel32  # type: ignore[attr-defined]
        kernel.GetCurrentProcess.restype = ctypes.c_void_p
        kernel.SetPriorityClass.argtypes = [ctypes.c_void_p, ctypes.c_ulong]
        if not kernel.SetPriorityClass(kernel.GetCurrentProcess(), 0x40):
            raise OSError("cannot set the Idle priority class")


class _MemoryStatus(ctypes.Structure):
    _fields_ = [  # noqa: RUF012
        ("length", ctypes.c_ulong),
        ("load", ctypes.c_ulong),
        ("total_phys", ctypes.c_ulonglong),
        ("avail_phys", ctypes.c_ulonglong),
        ("total_page", ctypes.c_ulonglong),
        ("avail_page", ctypes.c_ulonglong),
        ("total_virtual", ctypes.c_ulonglong),
        ("avail_virtual", ctypes.c_ulonglong),
        ("avail_ext", ctypes.c_ulonglong),
    ]


def free_ram_gb() -> float:
    status = _MemoryStatus()
    status.length = ctypes.sizeof(_MemoryStatus)
    ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status))  # type: ignore[attr-defined]
    return status.avail_phys / 2**30


def gpu_busy() -> list[str]:
    out = subprocess.run(["tasklist"], capture_output=True, check=True).stdout
    names = out.decode("utf-8", errors="replace").lower()
    return [name for name in GPU_PROCESSES if name in names]


def wait_until_free(max_wait_s: float = 1800.0) -> None:
    """Wait while any model process that is not ours runs (the operator may be using the app),
    and refuse to start with less than 8 GB of RAM free."""
    started = time.monotonic()
    while busy := gpu_busy():
        if time.monotonic() - started > max_wait_s:
            raise RuntimeError(f"model processes still running after {max_wait_s:g} s: {busy}")
        print(f"waiting: {busy} is running", flush=True)
        time.sleep(20)
    if (free := free_ram_gb()) < MIN_FREE_RAM_GB:
        raise RuntimeError(f"only {free:.1f} GB RAM free; need {MIN_FREE_RAM_GB:g} GB")


def _gpu_now() -> tuple[int, int]:
    out = subprocess.run(["nvidia-smi", *VRAM_QUERY], capture_output=True, text=True, check=True)
    used, util = out.stdout.strip().splitlines()[0].split(",")
    return int(used), int(util)


class GpuSampler:
    """`nvidia-smi` every 0.5 s: the peak of GPU memory in use and the mean GPU load, with the
    memory in use before the run as the baseline (the desktop holds about 2 to 4 GB)."""

    def __init__(self) -> None:
        self.baseline = int(statistics.median(_gpu_now()[0] for _ in range(5)))
        self.memory: list[int] = []
        self.load: list[int] = []
        self._proc = subprocess.Popen(
            ["nvidia-smi", *VRAM_QUERY, "-lms", "500"], stdout=subprocess.PIPE, text=True
        )
        self._thread = threading.Thread(target=self._read, daemon=True)
        self._thread.start()

    def _read(self) -> None:
        assert self._proc.stdout is not None
        for line in self._proc.stdout:
            parts = line.strip().split(",")
            if len(parts) == 2 and parts[0].strip().isdigit():
                self.memory.append(int(parts[0]))
                self.load.append(int(parts[1]))

    def stop(self) -> dict[str, float]:
        self._proc.terminate()
        self._proc.wait()
        self._thread.join(timeout=5)
        peak = max(self.memory, default=self.baseline)
        return {
            "baseline_mib": self.baseline,
            "peak_mib": peak,
            "peak_over_baseline_mib": peak - self.baseline,
            "gpu_load_mean_pct": statistics.fmean(self.load) if self.load else 0.0,
            "gpu_load_p90_pct": (
                statistics.quantiles(self.load, n=10)[-1] if len(self.load) >= 10 else 0.0
            ),
            "samples": len(self.memory),
        }
