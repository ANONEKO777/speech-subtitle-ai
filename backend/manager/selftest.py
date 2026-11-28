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
from collections.abc import Callable, Sequence
from pathlib import Path

from backend.core import notices as sentences
from backend.core import vc_runtime
from backend.core.notices import Notice, noticed, notices_of, unique
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


Probe = Callable[[str, Path, Path, Device, float], str | Notice]
"""(stage, program, model file, device, timeout) -> a short note, or raise ProbeFailed. A note the
window can word is a `Notice`."""


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
        failed = sentences.PROGRAM_CANNOT_START(program=command[0], error=str(exc))
        raise noticed(ProbeFailed, failed) from exc
    adopt(proc)
    try:
        out, _ = proc.communicate(timeout=timeout_s)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.communicate()
        slow = sentences.PROGRAM_TIMED_OUT(program=Path(command[0]).name, seconds=f"{timeout_s:g}")
        raise noticed(ProbeFailed, slow) from None
    text = out.decode("utf-8", errors="replace")
    if proc.returncode != 0:
        name, code = Path(command[0]).name, str(proc.returncode)
        tail = " ".join(text.strip().splitlines()[-2:])[:300]
        exited = (
            sentences.PROGRAM_EXITED(program=name, code=code, output=tail)
            if tail
            else sentences.PROGRAM_EXITED_SILENT(program=name, code=code)
        )
        raise noticed(ProbeFailed, exited)
    return text


def real_probe(stage: str, program: Path, model: Path, device: Device, timeout_s: float) -> Notice:
    if device is Device.CUDA and os.environ.get(FAULT_ENV):
        raise noticed(ProbeFailed, sentences.SIMULATED_CUDA_FAILURE(variable=FAULT_ENV))
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
            raise noticed(ProbeFailed, sentences.WHISPER_USED_THE_CPU())
        return sentences.HEARD_SILENCE()
    if device is Device.CUDA:
        text = _run([str(program), "--list-devices"], timeout_s)
        if "CUDA" not in text:
            raise noticed(ProbeFailed, sentences.NO_CUDA_DEVICE())
        return sentences.SEES_CUDA()
    _run([str(program), "--version"], timeout_s)
    return sentences.LLAMA_STARTS()


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
            absent = sentences.STAGE_NOT_INSTALLED(missing=missing)
            results.append(
                StageResult(stage, runtime_id, device, False, False, 0.0, absent.message, (absent,))
            )
            continue
        started = time.monotonic()
        notices: tuple[Notice, ...] = ()
        try:
            said = probe(stage, program, model, device, PROBE_TIMEOUT_S)
            note = said.message if isinstance(said, Notice) else said
            notices = (said,) if isinstance(said, Notice) else ()
            ok = True
        except ProbeFailed as exc:
            note, ok, notices = str(exc), False, notices_of(exc)
        seconds = round(time.monotonic() - started, 2)
        results.append(StageResult(stage, runtime_id, device, True, ok, seconds, note, notices))
    return results


def _to_download(results: list[StageResult], profile: Profile) -> list[str]:
    """The CPU runtimes the self-test could not find, as the ids the download route takes."""
    return [r.runtime_id for r in results if not r.installed] or [profile.id.value]


def _all_ok(results: list[StageResult]) -> bool:
    return all(r.ok for r in results)


_STAGE_FAILED = {_ASR: sentences.ASR_STAGE_FAILED, _LLM: sentences.LLM_STAGE_FAILED}


def _failed(result: StageResult) -> Notice:
    return _STAGE_FAILED[result.stage](runtime=result.runtime_id, detail=result.detail)


def _names(results: Sequence[StageResult]) -> list[str]:
    return [_failed(r).message for r in results if not r.ok]


def _notices(results: Sequence[StageResult]) -> tuple[Notice, ...]:
    """The notices in the clauses `_names` makes of the failed results: every stage's own before
    what the stages quote, because the window words the outer sentences first and two stages can
    quote the same one."""
    failed = [r for r in results if not r.ok]
    return unique([*map(_failed, failed), *(n for r in failed for n in r.detail_notices)])


def _inside(summary: Notice, results: Sequence[StageResult]) -> tuple[Notice, ...]:
    """`summary` and the stage notices its sentence quotes."""
    quoted = (n for n in _notices(results) if n.message in summary.message)
    return unique((summary, *quoted))


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
        summary = sentences.SELFTEST_PASSED(device=device.value.upper())
    elif wanted.device is Device.CPU or not all(r.installed for r in first):
        summary = sentences.SELFTEST_FAILED(failures=_names(first))
    else:
        cpu = _attempt(profile, Device.CPU, registry, storage, probe)
        if all(r.installed for r in cpu):
            failed = tuple(r for r in first if not r.ok)
            reason = sentences.GPU_FELL_BACK(failures=_names(first))
            fallback = Fallback(reason.message, failed, unique((reason, *_notices(failed))))
            device = Device.CPU
            stages = cpu
            summary = (
                sentences.FELL_BACK_AND_PASSED(failures=_names(first))
                if _all_ok(stages)
                else sentences.FELL_BACK_AND_UNUSABLE(
                    failures=_names(first), cpuFailures=_names(stages)
                )
            )
        else:
            stages = [*first, *cpu]
            summary = sentences.NO_CPU_FALLBACK(
                failures=_names(first), download=_to_download(cpu, profile)
            )
    report = SelfTestReport(
        at_ms=time.time_ns() // 1_000_000,
        profile=profile.id,
        ok=_all_ok(stages),
        device=device,
        stages=tuple(stages),
        fallback=fallback,
        seconds=round(time.monotonic() - started, 2),
        message=summary.message,
        message_notices=_inside(summary, [*first, *stages]),
    )
    store.save(report)
    return report
