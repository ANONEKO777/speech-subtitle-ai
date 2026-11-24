"""Apple silicon: hardware read through a faked `sysctl`, and the profile chosen by unified memory.

Nothing here runs a model or reads a Mac. The limits in the profiles are design choices to be
measured on a Mac (P37d), so a test pins what was chosen, not that it is fast or fits."""

from __future__ import annotations

from pathlib import Path

import pytest

from backend.manager import hardware, profiles, registry
from backend.manager.hardware import Hardware, read_apple_silicon
from backend.manager.platforms import MACOS_ARM64, WIN_X64
from backend.manager.profiles import (
    ALL_PROFILES,
    PROFILES,
    Cause,
    Device,
    ProfileId,
    describe,
    fits,
    profiles_for,
    required_assets,
    runtime_set,
    select,
    selection_for,
)

MAC = registry.load(platform=MACOS_ARM64)
WINDOWS = registry.load(platform=WIN_X64)
GIB = 1024
CHIP = "Apple M3 Pro"


def fake_sysctl(values: dict[str, str]):
    def read(name: str) -> str | None:
        return values.get(name)

    return read


def mac(memory_gib: int | None) -> Hardware:
    return Hardware(
        None,
        None,
        None,
        None if memory_gib is None else memory_gib * GIB,
        500_000,
        MACOS_ARM64,
        CHIP,
    )


def test_the_chip_and_the_unified_memory_are_read_through_sysctl() -> None:
    found = read_apple_silicon(
        fake_sysctl({"machdep.cpu.brand_string": CHIP, "hw.memsize": str(36 * GIB * 1024 * 1024)})
    )

    assert found == (CHIP, 36 * GIB)


@pytest.mark.parametrize(
    "values",
    [
        {},
        {"machdep.cpu.brand_string": "Intel(R) Core(TM) i7-9750H", "hw.memsize": "17179869184"},
        {"machdep.cpu.brand_string": ""},
    ],
)
def test_a_machine_that_does_not_say_it_is_apple_silicon_is_not_one(values: dict[str, str]) -> None:
    assert read_apple_silicon(fake_sysctl(values)) is None


def test_a_memory_size_that_is_not_a_number_is_unknown_not_a_crash() -> None:
    found = read_apple_silicon(
        fake_sysctl({"machdep.cpu.brand_string": CHIP, "hw.memsize": "lots"})
    )

    assert found == (CHIP, None)


def test_detect_on_a_mac_has_no_gpu_fields_and_the_memory_from_sysctl(tmp_path: Path) -> None:
    found = hardware.detect(
        env={},
        platform=MACOS_ARM64,
        disk_path=tmp_path,
        sysctl=fake_sysctl(
            {"machdep.cpu.brand_string": CHIP, "hw.memsize": str(36 * GIB * 1024 * 1024)}
        ),
    )

    assert (found.platform, found.chip, found.ram_mib) == (MACOS_ARM64, CHIP, 36 * GIB)
    assert (found.gpu_name, found.vram_mib, found.driver_version) == (None, None, None)
    assert found.disk_free_mib is not None


def test_detect_on_a_mac_never_runs_nvidia_smi(tmp_path: Path) -> None:
    def boom() -> str | None:
        raise AssertionError("nvidia-smi must not run on a Mac")

    found = hardware.detect(
        env={}, smi=boom, platform=MACOS_ARM64, disk_path=tmp_path, sysctl=fake_sysctl({})
    )

    assert found.platform == MACOS_ARM64


def test_detect_on_windows_is_what_it_was(tmp_path: Path) -> None:
    found = hardware.detect(env={}, smi=lambda: None, disk_path=tmp_path)

    assert found.platform == WIN_X64
    assert found.chip is None


def test_the_description_of_a_mac_names_the_chip_and_says_the_memory_is_shared() -> None:
    text = mac(36).describe()

    assert CHIP in text and "36864 MiB" in text and "shared" in text
    assert "VRAM" not in text and "NVIDIA" not in text


def test_the_windows_description_has_no_chip_line() -> None:
    assert "Chip" not in Hardware(None, None, None, 1, 1).describe()


def test_a_36_gb_mac_gets_the_conservative_default_one_model_stage_at_a_time() -> None:
    selection = select(mac(36), MAC)

    assert selection.profile.id is ProfileId.METAL_32GB
    assert selection.reason is Cause.MEMORY_FITS
    assert selection.profile.concurrent_stages is False
    assert selection.profile.asr.device is Device.METAL
    assert selection.asr_fallback == selection.profile.asr_fallback
    assert selection.low_ram is None


def test_the_reason_for_a_memory_choice_says_it_went_by_size_and_not_by_a_measurement() -> None:
    text = describe(select(mac(36), MAC), MAC)

    assert "chosen by the Mac's unified memory size, not by a measurement" in text
    assert "enough" not in text


def test_the_other_choice_is_a_profile_the_operator_can_pick_and_it_runs_both_at_once() -> None:
    chosen = selection_for(ProfileId.METAL_32GB_PARALLEL, mac(36), MAC)

    assert chosen.profile.concurrent_stages is True
    assert chosen.reason is Cause.USER_CHOICE
    assert chosen.profile.auto is False
    default = ALL_PROFILES[ProfileId.METAL_32GB]
    assert (chosen.profile.asr, chosen.profile.llm) == (default.asr, default.llm)


def test_no_memory_size_ever_selects_the_parallel_profile_by_itself() -> None:
    picked = {select(mac(gib), MAC).profile.id for gib in (4, 8, 16, 24, 32, 36, 48, 64, 128)}

    assert ProfileId.METAL_32GB_PARALLEL not in picked


@pytest.mark.parametrize(
    ("gib", "expected"),
    [
        (128, ProfileId.METAL_32GB),
        (64, ProfileId.METAL_32GB),
        (48, ProfileId.METAL_32GB),
        (36, ProfileId.METAL_32GB),
        (32, ProfileId.METAL_32GB),
        (24, ProfileId.METAL_16GB),
        (16, ProfileId.METAL_16GB),
        (8, ProfileId.APPLE_CPU),
    ],
)
def test_the_profile_follows_the_unified_memory(gib: int, expected: ProfileId) -> None:
    assert select(mac(gib), MAC).profile.id is expected


def test_the_boundaries_sit_just_under_the_published_sizes() -> None:
    just_under_32 = Hardware(None, None, None, 31_999, 1, MACOS_ARM64, CHIP)
    exactly_32k = Hardware(None, None, None, 32_000, 1, MACOS_ARM64, CHIP)
    just_under_16 = Hardware(None, None, None, 14_999, 1, MACOS_ARM64, CHIP)

    assert select(just_under_32, MAC).profile.id is ProfileId.METAL_16GB
    assert select(exactly_32k, MAC).profile.id is ProfileId.METAL_32GB
    assert select(just_under_16, MAC).profile.id is ProfileId.APPLE_CPU


def test_a_16_gb_mac_runs_one_stage_at_a_time_with_a_short_context_and_no_second_asr() -> None:
    profile = select(mac(16), MAC).profile

    assert profile.concurrent_stages is False
    assert profile.llm_ctx == 8192
    assert profile.asr_fallback is None


def test_an_8_gb_mac_gets_the_cpu_profile_with_the_cloud_advice_and_a_low_memory_warning() -> None:
    selection = select(mac(8), MAC)

    assert selection.profile.id is ProfileId.APPLE_CPU
    assert selection.reason is Cause.MEMORY_TOO_SMALL
    assert selection.profile.recommend_cloud is True
    assert selection.low_ram is not None and selection.low_ram.installed_mib == 8 * GIB


def test_a_mac_whose_memory_cannot_be_read_gets_the_cpu_profile() -> None:
    selection = select(mac(None), MAC)

    assert selection.profile.id is ProfileId.APPLE_CPU
    assert selection.reason is Cause.MEMORY_UNKNOWN


def test_every_mac_stage_names_a_mac_runtime_and_a_registry_model() -> None:
    for profile in profiles_for(MACOS_ARM64):
        stages = [
            profile.asr,
            profile.llm,
            *([profile.asr_fallback] if profile.asr_fallback else []),
        ]
        for stage in stages:
            assert MAC.runtimes[stage.runtime].platform == MACOS_ARM64
            assert stage.model in MAC.models
            assert (stage.device is Device.CPU) == (profile.id is ProfileId.APPLE_CPU)


def test_a_mac_profile_runs_the_engine_its_model_needs() -> None:
    for profile in profiles_for(MACOS_ARM64):
        assert MAC.runtimes[profile.asr.runtime].engine == MAC.models[profile.asr.model].engine
        assert MAC.runtimes[profile.llm.runtime].engine == MAC.models[profile.llm.model].engine
        if profile.asr_fallback:
            fallback = profile.asr_fallback
            assert MAC.runtimes[fallback.runtime].engine == MAC.models[fallback.model].engine


def test_the_assets_a_36_gb_mac_needs_are_the_three_mac_runtimes_and_the_models() -> None:
    needed = required_assets(select(mac(36), MAC))

    assert set(needed.runtimes) == {
        "whispercpp-b5454-macos-metal",
        "crispasr-v0.8.49-macos-metal",
        "llama.cpp-b12068-macos-metal",
    }
    assert profiles.VAD_MODEL in needed.models
    assert "qwen3-asr-1.7b-q8_0" in needed.models


def test_fitting_is_by_unified_memory_on_a_mac_and_a_windows_pc_fits_no_mac_profile() -> None:
    big = ALL_PROFILES[ProfileId.METAL_32GB]
    windows_pc = Hardware("GPU", 24564, "596.36", 65536, 1)

    assert fits(big, mac(36))
    assert not fits(big, mac(16))
    assert not fits(big, windows_pc)


def test_the_description_says_unified_memory_and_makes_no_speed_claim() -> None:
    text = describe(select(mac(36), MAC), MAC)

    assert "metal" in text
    assert "unified memory" in text
    assert "run one after the other" in text
    assert not any(word in text.lower() for word in ("fast", "faster", "tokens", "x realtime"))


def test_the_listing_of_profiles_is_by_platform() -> None:
    assert [p.id for p in profiles_for(WIN_X64)] == [
        ProfileId.GPU_24GB,
        ProfileId.GPU_8GB,
        ProfileId.CPU,
    ]
    assert [p.id for p in profiles_for(MACOS_ARM64)] == [
        ProfileId.METAL_32GB,
        ProfileId.METAL_32GB_PARALLEL,
        ProfileId.METAL_16GB,
        ProfileId.APPLE_CPU,
    ]
    assert set(ALL_PROFILES) == set(ProfileId)


def test_the_windows_profiles_and_their_runtime_ids_are_unchanged() -> None:
    assert list(PROFILES) == [ProfileId.GPU_24GB, ProfileId.GPU_8GB, ProfileId.CPU]
    gpu24, gpu8, cpu = PROFILES.values()
    assert (gpu24.asr.runtime, gpu24.asr_fallback and gpu24.asr_fallback.runtime) == (
        "whispercpp-b5454-win-cuda12.4",
        "crispasr-v0.8.49-win-cuda",
    )
    assert gpu24.llm.runtime == gpu8.llm.runtime == "llama.cpp-b12068-win-cuda12.4"
    assert (cpu.asr.runtime, cpu.llm.runtime) == (
        "whispercpp-b5454-win-cpu",
        "llama.cpp-b12068-win-cpu",
    )
    assert (gpu24.min_vram_mib, gpu8.min_vram_mib, cpu.min_vram_mib) == (16_000, 7_168, None)
    assert [p.platform for p in PROFILES.values()] == [WIN_X64] * 3
    assert [p.min_unified_mib for p in PROFILES.values()] == [None] * 3


def test_a_windows_machine_still_selects_as_it_did() -> None:
    four_090 = Hardware("NVIDIA GeForce RTX 4090", 24564, "596.36", 65536, 500_000)
    nothing = Hardware(None, None, None, 32768, 500_000)

    assert select(four_090, WINDOWS).profile.id is ProfileId.GPU_24GB
    assert select(nothing, WINDOWS).profile.id is ProfileId.CPU
    assert select(nothing, WINDOWS).reason is Cause.NO_NVIDIA_GPU


def test_the_runtime_ids_of_each_platform_come_from_one_table() -> None:
    win, mac_ids = runtime_set(WIN_X64), runtime_set(MACOS_ARM64)

    assert (win.whisper, win.crispasr, win.llama) == (
        "whispercpp-b5454-win-cuda12.4",
        "crispasr-v0.8.49-win-cuda",
        "llama.cpp-b12068-win-cuda12.4",
    )
    assert (win.whisper_cpu, win.llama_cpu) == (
        "whispercpp-b5454-win-cpu",
        "llama.cpp-b12068-win-cpu",
    )
    assert mac_ids.whisper_cpu == mac_ids.whisper and mac_ids.llama_cpu == mac_ids.llama
    assert {mac_ids.whisper, mac_ids.crispasr, mac_ids.llama} <= set(MAC.runtimes)
    assert set(
        map(str, (win.whisper, win.crispasr, win.llama, win.whisper_cpu, win.llama_cpu))
    ) <= set(WINDOWS.runtimes)


def test_the_run_time_set_follows_this_machine(monkeypatch: pytest.MonkeyPatch) -> None:
    assert runtime_set() == runtime_set(WIN_X64)
    monkeypatch.setattr("sys.platform", "darwin")
    monkeypatch.setattr("platform.machine", lambda: "arm64")

    assert runtime_set() == runtime_set(MACOS_ARM64)


def test_the_apple_cpu_profile_is_the_only_mac_profile_that_names_the_cpu() -> None:
    cpu_profiles = [p.id for p in profiles_for(MACOS_ARM64) if p.asr.device is Device.CPU]

    assert cpu_profiles == [ProfileId.APPLE_CPU]
