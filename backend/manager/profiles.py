from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from enum import StrEnum
from types import MappingProxyType

from backend.core import notices
from backend.manager.hardware import Hardware, parse_driver
from backend.manager.platforms import MACOS_ARM64, WIN_X64, detect_platform
from backend.manager.registry import Registry


class ProfileId(StrEnum):
    GPU_24GB = "gpu-24gb"
    GPU_8GB = "gpu-8gb"
    CPU = "cpu"
    METAL_32GB = "metal-32gb"
    METAL_32GB_PARALLEL = "metal-32gb-parallel"
    METAL_16GB = "metal-16gb"
    APPLE_CPU = "apple-cpu"


class Device(StrEnum):
    CUDA = "cuda"
    CPU = "cpu"
    METAL = "metal"


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
    platform: str = WIN_X64
    min_unified_mib: int | None = None
    """Apple silicon: the least unified memory (MiB) a Mac needs for this profile."""
    auto: bool = True
    """Whether `select` may pick it. A profile with False is only ever chosen by the user."""

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

MAC_WHISPER_RUNTIME = "whispercpp-b5454-macos-metal"
MAC_CRISPASR_RUNTIME = "crispasr-v0.8.49-macos-metal"
MAC_LLAMA_RUNTIME = "llama.cpp-b12068-macos-metal"
# The Apple-silicon limits below are design choices for a first run, not measurements (P37d
# measures). `hw.memsize` of a "32 GB" Mac is 32768 MiB, so 32_000 admits it; 15_000 admits a 16 GB.
METAL_LARGE_MIN_MIB = 32_000
METAL_SMALL_MIN_MIB = 15_000


@dataclass(frozen=True, slots=True)
class RuntimeSet:
    """The runtime ids one platform uses for each job. The CPU twin of a Windows runtime is
    another build; on a Mac it is the same program run with the GPU off."""

    whisper: str
    crispasr: str
    llama: str
    whisper_cpu: str
    llama_cpu: str


RUNTIME_SETS: Mapping[str, RuntimeSet] = MappingProxyType(
    {
        WIN_X64: RuntimeSet(
            WHISPER_RUNTIME,
            CRISPASR_RUNTIME,
            LLAMA_RUNTIME,
            WHISPER_CPU_RUNTIME,
            LLAMA_CPU_RUNTIME,
        ),
        MACOS_ARM64: RuntimeSet(
            MAC_WHISPER_RUNTIME,
            MAC_CRISPASR_RUNTIME,
            MAC_LLAMA_RUNTIME,
            MAC_WHISPER_RUNTIME,
            MAC_LLAMA_RUNTIME,
        ),
    }
)


def runtime_set(platform: str | None = None) -> RuntimeSet:
    """The runtime ids of `platform` (this machine's when None)."""
    return RUNTIME_SETS[detect_platform() if platform is None else platform]


PROFILES: Mapping[ProfileId, Profile] = MappingProxyType(
    {
        profile.id: profile
        for profile in (
            Profile(
                id=ProfileId.GPU_24GB,
                label=notices.PROFILE_LABELS["gpu-24gb"].english,
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
                label=notices.PROFILE_LABELS["gpu-8gb"].english,
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
                label=notices.PROFILE_LABELS["cpu"].english,
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

_APPLE_PROFILES = (
    Profile(
        id=ProfileId.METAL_32GB,
        label=notices.PROFILE_LABELS["metal-32gb"].english,
        min_vram_mib=None,
        asr=Stage(WHISPER_TURBO, MAC_WHISPER_RUNTIME, Device.METAL),
        asr_fallback=Stage(QWEN3_ASR, MAC_CRISPASR_RUNTIME, Device.METAL),
        llm=Stage(QWEN3_8B, MAC_LLAMA_RUNTIME, Device.METAL),
        recommend_cloud=False,
        concurrent_stages=False,
        llm_ctx=None,
        min_ram_mib=None,
        platform=MACOS_ARM64,
        min_unified_mib=METAL_LARGE_MIN_MIB,
    ),
    Profile(
        id=ProfileId.METAL_32GB_PARALLEL,
        label=notices.PROFILE_LABELS["metal-32gb-parallel"].english,
        min_vram_mib=None,
        asr=Stage(WHISPER_TURBO, MAC_WHISPER_RUNTIME, Device.METAL),
        asr_fallback=Stage(QWEN3_ASR, MAC_CRISPASR_RUNTIME, Device.METAL),
        llm=Stage(QWEN3_8B, MAC_LLAMA_RUNTIME, Device.METAL),
        recommend_cloud=False,
        concurrent_stages=True,
        llm_ctx=None,
        min_ram_mib=None,
        platform=MACOS_ARM64,
        min_unified_mib=METAL_LARGE_MIN_MIB,
        auto=False,
    ),
    Profile(
        id=ProfileId.METAL_16GB,
        label=notices.PROFILE_LABELS["metal-16gb"].english,
        min_vram_mib=None,
        asr=Stage(WHISPER_TURBO, MAC_WHISPER_RUNTIME, Device.METAL),
        asr_fallback=None,
        llm=Stage(QWEN3_8B, MAC_LLAMA_RUNTIME, Device.METAL),
        recommend_cloud=False,
        concurrent_stages=False,
        llm_ctx=LLM_CTX_8GB,
        min_ram_mib=None,
        platform=MACOS_ARM64,
        min_unified_mib=METAL_SMALL_MIN_MIB,
    ),
    Profile(
        id=ProfileId.APPLE_CPU,
        label=notices.PROFILE_LABELS["apple-cpu"].english,
        min_vram_mib=None,
        asr=Stage(WHISPER_TURBO, MAC_WHISPER_RUNTIME, Device.CPU),
        asr_fallback=None,
        llm=Stage(QWEN3_8B, MAC_LLAMA_RUNTIME, Device.CPU),
        recommend_cloud=True,
        concurrent_stages=True,
        llm_ctx=None,
        min_ram_mib=CPU_MIN_RAM_MIB,
        platform=MACOS_ARM64,
    ),
)
MAC_PROFILES: Mapping[ProfileId, Profile] = MappingProxyType({p.id: p for p in _APPLE_PROFILES})
ALL_PROFILES: Mapping[ProfileId, Profile] = MappingProxyType({**PROFILES, **MAC_PROFILES})


def profiles_for(platform: str) -> tuple[Profile, ...]:
    """The profiles a machine of `platform` can choose from, in table order."""
    return tuple(p for p in ALL_PROFILES.values() if p.platform == platform)


_APPLE_AUTO_LARGEST_FIRST = tuple(
    sorted(
        (p for p in MAC_PROFILES.values() if p.auto and p.min_unified_mib is not None),
        key=lambda p: p.min_unified_mib or 0,
        reverse=True,
    )
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
    MEMORY_FITS = "memory-fits"
    MEMORY_UNKNOWN = "memory-unknown"
    MEMORY_TOO_SMALL = "memory-too-small"


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


def _select_apple(hardware: Hardware, registry: Registry) -> Selection:
    memory = hardware.ram_mib
    if memory is None:
        return _cpu(hardware, Cause.MEMORY_UNKNOWN)
    fit = next((p for p in _APPLE_AUTO_LARGEST_FIRST if memory >= (p.min_unified_mib or 0)), None)
    if fit is None:
        return _cpu(hardware, Cause.MEMORY_TOO_SMALL)
    fallback, blocked = _resolve_fallback(fit, None, registry)
    return Selection(fit, Cause.MEMORY_FITS, asr_fallback=fallback, fallback_blocked=blocked)


def select(hardware: Hardware, registry: Registry) -> Selection:
    if hardware.platform == MACOS_ARM64:
        return _select_apple(hardware, registry)
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
    profile = ALL_PROFILES[profile_id]
    fallback, blocked = _resolve_fallback(profile, hardware.driver_version, registry)
    return Selection(profile, Cause.USER_CHOICE, asr_fallback=fallback, fallback_blocked=blocked)


def fits(profile: Profile, hardware: Hardware) -> bool:
    """Whether this machine can run the profile's GPU stages. The CPU profile fits anywhere."""
    if profile.min_unified_mib is not None:
        return (
            hardware.platform == profile.platform
            and hardware.ram_mib is not None
            and hardware.ram_mib >= profile.min_unified_mib
        )
    if profile.min_vram_mib is None:
        return True
    return hardware.vram_mib is not None and hardware.vram_mib >= profile.min_vram_mib


def _cpu(hardware: Hardware, reason: Cause | DriverTooOld) -> Selection:
    cpu = ALL_PROFILES[ProfileId.APPLE_CPU if hardware.platform == MACOS_ARM64 else ProfileId.CPU]
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


_REASONS: Mapping[Cause, notices.Template] = MappingProxyType(
    {
        Cause.VRAM_FITS: notices.WHY_VRAM_FITS,
        Cause.NO_NVIDIA_GPU: notices.WHY_NO_NVIDIA_GPU,
        Cause.VRAM_UNKNOWN: notices.WHY_VRAM_UNKNOWN,
        Cause.VRAM_TOO_SMALL: notices.WHY_VRAM_TOO_SMALL,
        Cause.USER_CHOICE: notices.WHY_USER_CHOICE,
        Cause.MEMORY_FITS: notices.WHY_MEMORY_FITS,
        Cause.MEMORY_UNKNOWN: notices.WHY_MEMORY_UNKNOWN,
        Cause.MEMORY_TOO_SMALL: notices.WHY_MEMORY_TOO_SMALL,
    }
)


def _stage_line(template: notices.Template, stage: Stage, registry: Registry) -> notices.Notice:
    model = registry.models[stage.model]
    runtime = registry.runtimes[stage.runtime]
    size = f", {model.params_b}B" if model.params_b else ""
    return template(
        model=f"{model.id}{size}",
        engine=runtime.engine,
        runtime=runtime.id,
        device=str(stage.device),
    )


@dataclass(frozen=True, slots=True)
class Explanation:
    text: str
    notices: tuple[notices.Notice, ...]
    """One for each line of `text`, and the profile's name after the line that quotes it."""


def explain(selection: Selection, registry: Registry) -> Explanation:
    """Why `selection` is what it is, one sentence on each line."""
    profile = selection.profile
    name = notices.PROFILE_LABELS[profile.id.value]()
    lines = [notices.PROFILE_LINE(profile=str(profile.id), label=name.message)]
    if isinstance(selection.reason, DriverTooOld):
        old = selection.reason
        lines.append(
            notices.DRIVER_TOO_OLD(
                installed=old.installed, profile=str(old.would_unlock), required=old.required
            )
        )
    else:
        lines.append(_REASONS[selection.reason]())
    lines.append(_stage_line(notices.ASR_LINE, profile.asr, registry))
    if selection.asr_fallback:
        lines.append(_stage_line(notices.ASR_FALLBACK_LINE, selection.asr_fallback, registry))
    elif selection.fallback_blocked:
        blocked = selection.fallback_blocked
        lines.append(
            notices.ASR_FALLBACK_BLOCKED(installed=blocked.installed, required=blocked.required)
        )
    lines.append(_stage_line(notices.LLM_LINE, profile.llm, registry))
    if not profile.concurrent_stages:
        lines.append(notices.ONE_STAGE_AT_A_TIME())
    if profile.llm_ctx:
        lines.append(notices.LLM_CONTEXT_CAPPED(tokens=str(profile.llm_ctx)))
    if selection.low_ram:
        ram = selection.low_ram
        lines.append(
            notices.LOW_RAM(installed=str(ram.installed_mib), recommended=str(ram.recommended_mib))
        )
    cloud = profile.recommend_cloud
    lines.append((notices.CLOUD_LLM_RECOMMENDED if cloud else notices.CLOUD_LLM_OPTIONAL)())
    text = "\n".join(line.message for line in lines)
    return Explanation(text, notices.unique((lines[0], name, *lines[1:])))


def describe(selection: Selection, registry: Registry) -> str:
    return explain(selection, registry).text
