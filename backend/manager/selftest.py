"""A short check that the active profile's ASR and LLM runtimes start, and the GPU-to-CPU fallback.

The ASR check transcribes one second of silence with the real model, so a broken CUDA install or
driver shows up here and not an hour into a job. The LLM check asks `llama-server` for its device
list, which loads the CUDA backend but not the 5 GB model, to stay near five seconds.

`VST_SIMULATE_CUDA_FAILURE=1` makes every CUDA check fail the way a broken driver would, so the
fallback can be tested without touching a real file."""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import time
import wave
from collections.abc import Callable
from pathlib import Path

from backend.core import vc_runtime
from backend.core.process_guard import adopt
from backend.manager.profiles import Device, Profile, Stage, runtime_set
from backend.manager.registry import Registry
from backend.manager.runtimes import runtime_executable
from backend.manager.selftest_store import Fallback, SelfTestReport, SelfTestStore, StageResult
from backend.manager.storage import Storage

FAULT_ENV = "VST_SIMULATE_CUDA_FAILURE"
PROBE_TIMEOUT_S = 15.0
_ASR, _LLM = "asr", "llm"


class ProbeFailed(Exception):
    pass


Probe = Callable[[str, Path, Path, Device, float], str]
"""(stage, program, model file, device, timeout) -> a short note, or raise ProbeFailed."""


def _run(command: list[str], timeout_s: float) -> str:
    vc_runtime.require(ProbeFailed)
    flags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
    try:
        proc = subprocess.Popen(
            command,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            creationflags=flags,
        )
    except OSError as exc:
        raise ProbeFailed(f"cannot start {command[0]}: {exc}") from exc
    adopt(proc)
    try:
        out, _ = proc.communicate(timeout=timeout_s)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.communicate()
        raise ProbeFailed(f"{Path(command[0]).name} did not finish in {timeout_s:g} s") from None
    text = out.decode("utf-8", errors="replace")
    if proc.returncode != 0:
        tail = " ".join(text.strip().splitlines()[-2:])[:300]
        raise ProbeFailed(f"{Path(command[0]).name} exited with code {proc.returncode}: {tail}")
    return text


def real_probe(stage: str, program: Path, model: Path, device: Device, timeout_s: float) -> str:
    if device is Device.CUDA and os.environ.get(FAULT_ENV):
        raise ProbeFailed(f"CUDA failed to initialise (simulated by {FAULT_ENV})")
    if stage == _ASR:
        with tempfile.TemporaryDirectory(prefix="vst-selftest-") as folder:
            wav = Path(folder) / "silence.wav"
            with wave.open(str(wav), "wb") as sink:
                sink.setnchannels(1)
                sink.setsampwidth(2)
                sink.setframerate(16000)
                sink.writeframes(b"\0\0" * 16000)
            command = [str(program), "-m", str(model), "-l", "en", "-nt", "-f", str(wav)]
            if device is Device.CPU:
                command += ["-ng", "-ac", "128"]
            text = _run(command, timeout_s)
        if device is Device.CUDA and "CUDA0" not in text:
            raise ProbeFailed("whisper.cpp ran without the CUDA backend and used the CPU instead")
        return "transcribed one second of silence"
    if device is Device.CUDA:
        text = _run([str(program), "--list-devices"], timeout_s)
        if "CUDA" not in text:
            raise ProbeFailed("llama-server lists no CUDA device")
        return "llama-server sees a CUDA device"
    _run([str(program), "--version"], timeout_s)
    return "llama-server starts"


def _stages(profile: Profile, device: Device) -> list[tuple[str, str, str]]:
    """(stage, runtime id, model id) for each main stage on `device`."""
    if device is not Device.CPU:
        return [
            (_ASR, profile.asr.runtime, profile.asr.model),
            (_LLM, profile.llm.runtime, profile.llm.model),
        ]
    twins = runtime_set(profile.platform)
    return [
        (_ASR, twins.whisper_cpu, profile.asr.model),
        (_LLM, twins.llama_cpu, profile.llm.model),
    ]


def _attempt(
    profile: Profile,
    device: Device,
    registry: Registry,
    storage: Storage,
    probe: Probe,
) -> list[StageResult]:
    results: list[StageResult] = []
    for stage, runtime_id, model_id in _stages(profile, device):
        program = runtime_executable(runtime_id, registry, storage)
        model = storage.model_file(registry.models[model_id])
        missing = [
            what
            for what, present in ((runtime_id, program is not None), (model_id, model.is_file()))
            if not present
        ]
        if missing or program is None:
            results.append(
                StageResult(
                    stage,
                    runtime_id,
                    device,
                    False,
                    False,
                    0.0,
                    f"not installed: {', '.join(missing)}",
                )
            )
            continue
        started = time.monotonic()
        try:
            note = probe(stage, program, model, device, PROBE_TIMEOUT_S)
            ok = True
        except ProbeFailed as exc:
            note, ok = str(exc), False
        results.append(
            StageResult(
                stage, runtime_id, device, True, ok, round(time.monotonic() - started, 2), note
            )
        )
    return results


def _to_download(results: list[StageResult], profile: Profile) -> str:
    """The CPU runtimes the self-test could not find, as the ids the download route takes."""
    return ", ".join(r.runtime_id for r in results if not r.installed) or profile.id.value


def _all_ok(results: list[StageResult]) -> bool:
    return all(r.ok for r in results)


def _names(results: list[StageResult]) -> str:
    return "; ".join(f"{r.stage.upper()} ({r.runtime_id}): {r.detail}" for r in results if not r.ok)


def run_selftest(
    profile: Profile,
    registry: Registry,
    storage: Storage,
    store: SelfTestStore,
    probe: Probe = real_probe,
) -> SelfTestReport:
    started = time.monotonic()
    wanted: Stage = profile.asr
    first = _attempt(profile, wanted.device, registry, storage, probe)
    fallback: Fallback | None = None
    device = wanted.device
    stages = first
    if _all_ok(first):
        message = f"Self-test passed on {device.value.upper()}."
    elif wanted.device is Device.CPU or not all(r.installed for r in first):
        message = f"Self-test failed: {_names(first)}."
    else:
        cpu = _attempt(profile, Device.CPU, registry, storage, probe)
        if all(r.installed for r in cpu):
            failed = tuple(r for r in first if not r.ok)
            reason = f"The GPU backend failed: {_names(first)}. The CPU backend is used instead."
            fallback = Fallback(reason, failed)
            device = Device.CPU
            stages = cpu
            message = (
                f"{reason} The CPU self-test passed."
                if _all_ok(stages)
                else f"{reason} The CPU backend is not usable either: {_names(stages)}."
            )
        else:
            stages = [*first, *cpu]
            message = (
                f"GPU failed and the CPU runtime is not installed. GPU: {_names(first)}. "
                f"Download {_to_download(cpu, profile)} to have a CPU fallback."
            )
    report = SelfTestReport(
        at_ms=time.time_ns() // 1_000_000,
        profile=profile.id,
        ok=_all_ok(stages),
        device=device,
        stages=tuple(stages),
        fallback=fallback,
        seconds=round(time.monotonic() - started, 2),
        message=message,
    )
    store.save(report)
    return report
