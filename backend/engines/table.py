from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType

from backend.engines.base import SubprocessEngine
from backend.engines.crispasr import ENGINE_ID as CRISPASR_ID
from backend.engines.crispasr import CrispAsrEngine
from backend.engines.whispercpp import ENGINE_ID as WHISPERCPP_ID
from backend.engines.whispercpp import WhisperCppEngine
from backend.manager.profiles import (
    CRISPASR_RUNTIME,
    QWEN3_ASR,
    WHISPER_RUNTIME,
    WHISPER_TURBO,
    Device,
)
from backend.manager.registry import ModelKind, Registry
from backend.manager.registry import load as load_registry
from backend.manager.runtimes import recover_runtime
from backend.manager.storage import Storage

Factory = Callable[[Path, Path, Path | None, Device, float | None, bool], SubprocessEngine]


@dataclass(frozen=True, slots=True)
class EngineSpec:
    id: str
    model_id: str
    runtime_id: str
    needs_aligner: bool
    factory: Factory


def _whispercpp(
    binary: Path,
    model: Path,
    aligner: Path | None,
    device: Device,
    timeout_s: float | None,
    strict: bool,
) -> SubprocessEngine:
    return WhisperCppEngine(binary, model, device=device, timeout_s=timeout_s)


def _crispasr(
    binary: Path,
    model: Path,
    aligner: Path | None,
    device: Device,
    timeout_s: float | None,
    strict: bool,
) -> SubprocessEngine:
    assert aligner is not None
    return CrispAsrEngine(binary, model, aligner, device=device, timeout_s=timeout_s, strict=strict)


ENGINES: Mapping[str, EngineSpec] = MappingProxyType(
    {
        spec.id: spec
        for spec in (
            EngineSpec(WHISPERCPP_ID, WHISPER_TURBO, WHISPER_RUNTIME, False, _whispercpp),
            EngineSpec(CRISPASR_ID, QWEN3_ASR, CRISPASR_RUNTIME, True, _crispasr),
        )
    }
)


@dataclass(frozen=True, slots=True)
class EnginePaths:
    binary: Path
    model: Path
    aligner: Path | None


def engine_paths(
    engine_id: str,
    storage: Storage,
    *,
    registry: Registry | None = None,
    runtime_id: str | None = None,
) -> EnginePaths:
    """Where the downloader puts the engine's files. Nothing is checked, so an engine
    that is not installed yet reports its own missing path. `runtime_id` picks another
    build of the engine, such as the CPU one a hardware profile names."""
    registry = registry or load_registry()
    spec = spec_for(engine_id)
    runtime = registry.runtimes[runtime_id or spec.runtime_id]
    model = registry.models[spec.model_id]
    aligner = next(
        (registry.models[n] for n in model.needs if registry.models[n].kind is ModelKind.ALIGNER),
        None,
    )
    recover_runtime(runtime, storage)
    return EnginePaths(
        binary=storage.runtime_dir(runtime) / (runtime.executable or ""),
        model=storage.model_file(model),
        aligner=storage.model_file(aligner) if aligner else None,
    )


def spec_for(engine_id: str) -> EngineSpec:
    try:
        return ENGINES[engine_id]
    except KeyError:
        raise ValueError(f"unknown ASR engine {engine_id!r}; known: {sorted(ENGINES)}") from None


def spec_for_model(model_id: str) -> EngineSpec:
    for spec in ENGINES.values():
        if spec.model_id == model_id:
            return spec
    raise ValueError(f"no ASR engine runs model {model_id!r}")


def create_engine(
    engine_id: str,
    binary: Path,
    model: Path,
    *,
    aligner: Path | None = None,
    device: Device = Device.CUDA,
    timeout_s: float | None = None,
    strict: bool = True,
) -> SubprocessEngine:
    """`strict` is for CrispASR: whether it checks the text against the language it was given."""
    spec = spec_for(engine_id)
    if spec.needs_aligner and aligner is None:
        raise ValueError(f"{engine_id} needs an aligner model path")
    return spec.factory(binary, model, aligner, device, timeout_s, strict)
