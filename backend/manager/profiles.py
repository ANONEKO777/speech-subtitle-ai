from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from enum import StrEnum
from types import MappingProxyType

from backend.manager.hardware import Hardware, parse_driver
from backend.manager.registry import Registry


class ProfileId(StrEnum):
    GPU_24GB = "gpu-24gb"
    GPU_8GB = "gpu-8gb"
    CPU = "cpu"


class Device(StrEnum):
    CUDA = "cuda"
    CPU = "cpu"


@dataclass(frozen=True, slots=True)
class Stage:
    model: str
    runtime: str
    device: Device


@dataclass(frozen=True, slots=True)
class Profile:
    id: ProfileId
    label: str
    min_vram_mib: int | None
    asr: Stage
    asr_fallback: Stage | None
    llm: Stage
    recommend_cloud: bool
    concurrent_stages: bool
    llm_ctx: int | None
    min_ram_mib: int | None

    @property
    def main_stages(self) -> tuple[Stage, Stage]:
        return (self.asr, self.llm)


WHISPER_TURBO = "whisper-large-v3-turbo"
WHISPER_RUNTIME = "whispercpp-b5454-win-cuda12.4"
QWEN3_ASR = "qwen3-asr-1.7b-q8_0"
CRISPASR_RUNTIME = "crispasr-v0.8.49-win-cuda"
QWEN3_8B = "qwen3-8b-q4_k_m"
LLAMA_RUNTIME = "llama.cpp-b12068-win-cuda12.4"
WHISPER_CPU_RUNTIME = "whispercpp-b5454-win-cpu"
LLAMA_CPU_RUNTIME = "llama.cpp-b12068-win-cpu"
VAD_MODEL = "silero-vad-onnx-v6.2.3"
LLM_CTX_8GB = 8192
CPU_MIN_RAM_MIB = 15_000

PROFILES: Mapping[ProfileId, Profile] = MappingProxyType(
    {
        profile.id: profile
        for profile in (
            Profile(
                id=ProfileId.GPU_24GB,
                label="24 GB VRAM, default",
                min_vram_mib=16_000,
                asr=Stage(WHISPER_TURBO, WHISPER_RUNTIME, Device.CUDA),
                asr_fallback=Stage(QWEN3_ASR, CRISPASR_RUNTIME, Device.CUDA),
                llm=Stage(QWEN3_8B, LLAMA_RUNTIME, Device.CUDA),
                recommend_cloud=False,
                concurrent_stages=True,
                llm_ctx=None,
                min_ram_mib=None,
            ),
            Profile(
                id=ProfileId.GPU_8GB,
                label="8 GB VRAM",
                min_vram_mib=7_168,
                asr=Stage(WHISPER_TURBO, WHISPER_RUNTIME, Device.CUDA),
                asr_fallback=None,
                llm=Stage(QWEN3_8B, LLAMA_RUNTIME, Device.CUDA),
                recommend_cloud=False,
                concurrent_stages=False,
                llm_ctx=LLM_CTX_8GB,
                min_ram_mib=None,
            ),
            Profile(
                id=ProfileId.CPU,
                label="CPU only, no GPU acceleration",
                min_vram_mib=None,
                asr=Stage(WHISPER_TURBO, WHISPER_CPU_RUNTIME, Device.CPU),
                asr_fallback=None,
                llm=Stage(QWEN3_8B, LLAMA_CPU_RUNTIME, Device.CPU),
                recommend_cloud=True,
                concurrent_stages=True,
                llm_ctx=None,
                min_ram_mib=CPU_MIN_RAM_MIB,
            ),
        )
    }
)

_GPU_PROFILES_LARGEST_FIRST = tuple(
    sorted(
        (p for p in PROFILES.values() if p.min_vram_mib is not None),
        key=lambda p: p.min_vram_mib or 0,
        reverse=True,
    )
)


class Cause(StrEnum):
    VRAM_FITS = "vram-fits"
    NO_NVIDIA_GPU = "no-nvidia-gpu"
    VRAM_UNKNOWN = "vram-unknown"
    VRAM_TOO_SMALL = "vram-too-small"
    USER_CHOICE = "user-choice"


@dataclass(frozen=True, slots=True)
class DriverTooOld:
    installed: str
    required: str
    would_unlock: ProfileId


@dataclass(frozen=True, slots=True)
class LowRam:
    installed_mib: int
    recommended_mib: int


@dataclass(frozen=True, slots=True)
class Selection:
    profile: Profile
    reason: Cause | DriverTooOld
    asr_fallback: Stage | None = None
    fallback_blocked: DriverTooOld | None = None
    low_ram: LowRam | None = None


@dataclass(frozen=True, slots=True)
class Assets:
    models: tuple[str, ...]
    runtimes: tuple[str, ...]


def required_assets(selection: Selection) -> Assets:
    stages = [selection.profile.asr, selection.profile.llm]
    if selection.asr_fallback is not None:
        stages.insert(1, selection.asr_fallback)
    models = dict.fromkeys([VAD_MODEL, *(stage.model for stage in stages)])
    runtimes = dict.fromkeys(stage.runtime for stage in stages)
    return Assets(tuple(models), tuple(runtimes))


def required_driver(stages: Iterable[Stage], registry: Registry) -> str | None:
    minimums = [
        registry.runtimes[stage.runtime].min_driver
        for stage in stages
        if stage.device is Device.CUDA
    ]
    known = [m for m in minimums if m is not None]
    return max(known, key=lambda m: parse_driver(m) or (), default=None)


def select(hardware: Hardware, registry: Registry) -> Selection:
    if hardware.gpu_name is None:
        return _cpu(hardware, Cause.NO_NVIDIA_GPU)
    if hardware.vram_mib is None:
        return _cpu(hardware, Cause.VRAM_UNKNOWN)
    vram_mib = hardware.vram_mib
    fit = next((p for p in _GPU_PROFILES_LARGEST_FIRST if vram_mib >= (p.min_vram_mib or 0)), None)
    if fit is None:
        return _cpu(hardware, Cause.VRAM_TOO_SMALL)
    required = required_driver(fit.main_stages, registry)
    driver = hardware.driver_version
    if driver is not None and required is not None and _older(driver, required):
        return _cpu(hardware, DriverTooOld(driver, required, fit.id))
    fallback, blocked = _resolve_fallback(fit, driver, registry)
    return Selection(fit, Cause.VRAM_FITS, asr_fallback=fallback, fallback_blocked=blocked)


def selection_for(profile_id: ProfileId, hardware: Hardware, registry: Registry) -> Selection:
    """The selection a user gets by choosing `profile_id` on this machine. The detected profile
    keeps its own selection, so its driver-gated fallback stays. Any other profile is a choice,
    whether or not the hardware fits it."""
    detected = select(hardware, registry)
    if detected.profile.id is profile_id:
        return detected
    profile = PROFILES[profile_id]
    fallback, blocked = _resolve_fallback(profile, hardware.driver_version, registry)
    return Selection(profile, Cause.USER_CHOICE, asr_fallback=fallback, fallback_blocked=blocked)


def fits(profile: Profile, hardware: Hardware) -> bool:
    """Whether this machine can run the profile's GPU stages. The CPU profile fits anywhere."""
    if profile.min_vram_mib is None:
        return True
    return hardware.vram_mib is not None and hardware.vram_mib >= profile.min_vram_mib


def _cpu(hardware: Hardware, reason: Cause | DriverTooOld) -> Selection:
    cpu = PROFILES[ProfileId.CPU]
    low_ram = None
    if (
        cpu.min_ram_mib is not None
        and hardware.ram_mib is not None
        and hardware.ram_mib < cpu.min_ram_mib
    ):
        low_ram = LowRam(hardware.ram_mib, cpu.min_ram_mib)
    return Selection(cpu, reason, low_ram=low_ram)


def _resolve_fallback(
    profile: Profile, driver: str | None, registry: Registry
) -> tuple[Stage | None, DriverTooOld | None]:
    fallback = profile.asr_fallback
    if fallback is None:
        return None, None
    required = required_driver([fallback], registry)
    if driver is not None and required is not None and _older(driver, required):
        return None, DriverTooOld(driver, required, profile.id)
    return fallback, None


def _older(installed: str, minimum: str) -> bool:
    have, need = parse_driver(installed), parse_driver(minimum)
    return have is not None and need is not None and have < need


_REASON_TEXT: Mapping[Cause, str] = MappingProxyType(
    {
        Cause.VRAM_FITS: "The GPU has enough VRAM for this profile.",
        Cause.NO_NVIDIA_GPU: "No NVIDIA GPU was found, so GPU runtimes are not used.",
        Cause.VRAM_UNKNOWN: "An NVIDIA GPU was found but its VRAM could not be read.",
        Cause.VRAM_TOO_SMALL: "The GPU has less VRAM than the smallest GPU profile needs.",
        Cause.USER_CHOICE: "You chose this profile.",
    }
)


def _stage_line(stage: Stage, registry: Registry) -> str:
    model = registry.models[stage.model]
    runtime = registry.runtimes[stage.runtime]
    size = f", {model.params_b}B" if model.params_b else ""
    return f"{model.id}{size} via {runtime.engine} ({runtime.id}) on {stage.device}"


def describe(selection: Selection, registry: Registry) -> str:
    profile = selection.profile
    lines = [f"Profile:       {profile.id} ({profile.label})"]
    if isinstance(selection.reason, DriverTooOld):
        old = selection.reason
        lines.append(
            f"Driver:        {old.installed} is too old for the {old.would_unlock} profile. "
            f"Update the NVIDIA driver to {old.required} or newer. "
            "The CUDA Toolkit is not needed."
        )
    else:
        lines.append(f"Why:           {_REASON_TEXT[selection.reason]}")
    lines.append(f"ASR:           {_stage_line(profile.asr, registry)}")
    if selection.asr_fallback:
        lines.append(f"ASR fallback:  {_stage_line(selection.asr_fallback, registry)}")
    elif selection.fallback_blocked:
        blocked = selection.fallback_blocked
        lines.append(
            f"ASR fallback:  unavailable, driver {blocked.installed} < {blocked.required}; "
            "update the NVIDIA driver (CUDA Toolkit not needed)"
        )
    lines.append(f"Local LLM:     {_stage_line(profile.llm, registry)}")
    if not profile.concurrent_stages:
        lines.append("Stages:        run one after the other; the ASR exits before the LLM loads")
    if profile.llm_ctx:
        lines.append(f"LLM context:   capped at {profile.llm_ctx} tokens")
    if selection.low_ram:
        ram = selection.low_ram
        lines.append(
            f"RAM warning:   {ram.installed_mib} MiB is below the {ram.recommended_mib} MiB "
            "the local 8B model needs; use a cloud LLM or expect swapping"
        )
    cloud = "recommended, only after you opt in" if profile.recommend_cloud else "optional"
    lines.append(f"Cloud LLM:     {cloud}")
    return "\n".join(lines)
