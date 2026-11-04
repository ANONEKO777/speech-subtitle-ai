from __future__ import annotations

import ctypes
import dataclasses
import os
import shutil
import sys
import time
from collections.abc import Callable
from pathlib import Path
from types import MappingProxyType, SimpleNamespace
from typing import Any

import pytest

from backend.manager import hardware, profiles, registry
from backend.manager.hardware import Hardware, detect, parse_nvidia_smi
from backend.manager.profiles import Cause, DriverTooOld, ProfileId

RTX_4090 = "0, NVIDIA GeForce RTX 4090, 24564, 596.36\n"
RTX_3070 = "0, NVIDIA GeForce RTX 3070, 8192, 596.36\n"
REGISTRY = registry.load()


def smi(text: str | None) -> Callable[[], str | None]:
    return lambda: text


def choose(text: str | None, env: dict[str, str] | None = None) -> profiles.Selection:
    return profiles.select(detect(env=env or {}, smi=smi(text)), REGISTRY)


def test_the_4090_reports_its_numbers_and_gets_the_24gb_profile() -> None:
    found = detect(env={}, smi=smi(RTX_4090))

    assert found.gpu_name == "NVIDIA GeForce RTX 4090"
    assert found.vram_mib == 24564
    assert found.driver_version == "596.36"
    assert profiles.select(found, REGISTRY).profile.id is ProfileId.GPU_24GB


@pytest.mark.parametrize(
    ("vram_mib", "expected"),
    [
        (24564, ProfileId.GPU_24GB),
        (16376, ProfileId.GPU_24GB),
        (16000, ProfileId.GPU_24GB),
        (15999, ProfileId.GPU_8GB),
        (12288, ProfileId.GPU_8GB),
        (8192, ProfileId.GPU_8GB),
        (7168, ProfileId.GPU_8GB),
        (7167, ProfileId.CPU),
        (4096, ProfileId.CPU),
    ],
)
def test_vram_picks_the_largest_profile_it_fits(vram_mib: int, expected: ProfileId) -> None:
    assert choose(f"0, NVIDIA GPU, {vram_mib}, 596.36").profile.id is expected


def test_an_8gb_card_gets_no_crispasr_fallback_but_the_24gb_card_does() -> None:
    assert choose(RTX_3070).profile.asr_fallback is None
    assert choose(RTX_4090).profile.asr_fallback is not None


@pytest.mark.parametrize(
    "output", [None, "", "No devices were found\n", "garbage\nmore, garbage\n"]
)
def test_no_usable_nvidia_output_selects_the_cpu_profile(output: str | None) -> None:
    found = detect(env={}, smi=smi(output))
    selection = profiles.select(found, REGISTRY)

    assert (found.gpu_name, found.vram_mib, found.driver_version) == (None, None, None)
    assert selection.profile.id is ProfileId.CPU
    assert selection.reason is Cause.NO_NVIDIA_GPU
    assert selection.profile.recommend_cloud


@pytest.mark.parametrize("value", ["", "-1", "-1,0"])
def test_hidden_cuda_devices_count_as_no_gpu(value: str) -> None:
    selection = choose(RTX_4090, {"CUDA_VISIBLE_DEVICES": value})

    assert selection.profile.id is ProfileId.CPU
    assert selection.reason is Cause.NO_NVIDIA_GPU


def test_cuda_visible_devices_restricts_the_report_to_the_listed_gpus() -> None:
    both = "0, Small GPU, 8192, 596.36\n1, Big GPU, 24564, 596.36\n"

    assert detect(env={}, smi=smi(both)).gpu_name == "Big GPU"
    assert detect(env={"CUDA_VISIBLE_DEVICES": "0"}, smi=smi(both)).gpu_name == "Small GPU"
    assert detect(env={"CUDA_VISIBLE_DEVICES": "GPU-abc"}, smi=smi(both)).gpu_name == "Big GPU"


def test_cuda_hides_every_device_after_the_first_invalid_index() -> None:
    both = "0, Small GPU, 8192, 596.36\n1, Big GPU, 24564, 596.36\n"

    assert detect(env={"CUDA_VISIBLE_DEVICES": "5,1"}, smi=smi(both)).gpu_name is None
    assert detect(env={"CUDA_VISIBLE_DEVICES": "0,5,1"}, smi=smi(both)).gpu_name == "Small GPU"


def test_equal_vram_reports_the_lowest_index() -> None:
    twins = "1, Card B, 8192, 596.36\n0, Card A, 8192, 596.36\n"

    assert detect(env={}, smi=smi(twins)).gpu_name == "Card A"


def test_vram_override_replaces_the_detected_value() -> None:
    selection = choose(RTX_4090, {hardware.VRAM_OVERRIDE_ENV: "8192"})

    assert detect(env={hardware.VRAM_OVERRIDE_ENV: "8192"}, smi=smi(RTX_4090)).vram_mib == 8192
    assert selection.profile.id is ProfileId.GPU_8GB


def test_vram_override_does_not_invent_a_gpu() -> None:
    assert detect(env={hardware.VRAM_OVERRIDE_ENV: "8192"}, smi=smi(None)).vram_mib is None


@pytest.mark.parametrize("value", ["", "abc", "0", "-5", "8 GB"])
def test_a_bad_vram_override_is_an_error_not_a_silent_default(value: str) -> None:
    with pytest.raises(ValueError, match=hardware.VRAM_OVERRIDE_ENV):
        detect(env={hardware.VRAM_OVERRIDE_ENV: value}, smi=smi(RTX_4090))


def test_an_old_driver_asks_for_a_driver_update_and_falls_back_to_cpu() -> None:
    selection = choose("0, NVIDIA GeForce RTX 4090, 24564, 472.12")

    assert selection.profile.id is ProfileId.CPU
    assert isinstance(selection.reason, DriverTooOld)
    assert selection.reason.would_unlock is ProfileId.GPU_24GB
    assert selection.reason.installed == "472.12"
    text = profiles.describe(selection, REGISTRY)
    assert f"Update the NVIDIA driver to {selection.reason.required} or newer" in text
    assert "CUDA Toolkit is not needed" in text


def test_the_driver_floor_is_compared_numerically() -> None:
    floor = profiles.required_driver(profiles.PROFILES[ProfileId.GPU_24GB].main_stages, REGISTRY)
    assert floor == "551.61"

    assert choose("0, GPU, 24564, 551.61").profile.id is ProfileId.GPU_24GB
    assert choose("0, GPU, 24564, 551.60").profile.id is ProfileId.CPU
    assert choose("0, GPU, 24564, 1000.5").profile.id is ProfileId.GPU_24GB
    assert choose("0, GPU, 24564, 99.99").profile.id is ProfileId.CPU


def test_unreadable_cells_become_none_instead_of_failing_the_whole_row() -> None:
    no_memory = detect(env={}, smi=smi("0, NVIDIA GeForce RTX 4090, [N/A], 596.36"))
    no_driver = detect(env={}, smi=smi("0, NVIDIA GeForce RTX 4090, 24564, [N/A]"))

    assert (no_memory.gpu_name, no_memory.vram_mib, no_memory.driver_version) == (
        "NVIDIA GeForce RTX 4090",
        None,
        "596.36",
    )
    assert no_driver.driver_version is None
    assert profiles.select(no_memory, REGISTRY).reason is Cause.VRAM_UNKNOWN
    assert profiles.select(no_driver, REGISTRY).profile.id is ProfileId.GPU_24GB


def test_parse_nvidia_smi_keeps_good_rows_and_drops_bad_ones() -> None:
    text = "0, Card A, 8192, 560.1\nnot a row\n, Nameless index, 1, 1.0\nx, Bad index, 1, 1.0\n"

    assert [(g.index, g.name, g.vram_mib, g.driver_version) for g in parse_nvidia_smi(text)] == [
        (0, "Card A", 8192, "560.1")
    ]


def test_a_failing_disk_query_leaves_only_that_field_none(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail(path: object) -> object:
        raise PermissionError("denied")

    monkeypatch.setattr(shutil, "disk_usage", fail)
    found = detect(env={}, smi=smi(RTX_4090))

    assert found.disk_free_mib is None
    assert found.gpu_name == "NVIDIA GeForce RTX 4090"
    assert found.ram_mib is not None


def test_disk_space_is_read_from_the_nearest_existing_parent(tmp_path: Path) -> None:
    missing = tmp_path / "not" / "created" / "yet"

    found = detect(env={}, smi=smi(None), disk_path=missing)

    assert found.disk_free_mib == shutil.disk_usage(tmp_path).free // (1024 * 1024)


def test_the_machines_ram_is_read_and_plausible() -> None:
    ram = detect(env={}, smi=smi(None)).ram_mib

    assert ram is not None and ram >= 512


def test_unknown_fields_print_as_unknown() -> None:
    text = Hardware(None, None, None, None, None).describe()

    assert text.count("unknown") == 5


def fake_smi(directory: Path, *lines: str) -> Path:
    path = directory / "nvidia-smi.cmd"
    path.write_text(os.linesep.join(["@echo off", *lines, ""]), encoding="ascii")
    return path


@pytest.mark.skipif(sys.platform != "win32", reason="the fake nvidia-smi is a .cmd file")
class TestRealSubprocessBoundary:
    def test_stdout_of_the_overridden_nvidia_smi_is_parsed(self, tmp_path: Path) -> None:
        exe = fake_smi(tmp_path, "echo 0, NVIDIA GeForce RTX 4090, 24564, 596.36")

        found = detect(env={hardware.NVIDIA_SMI_ENV: str(exe)})

        assert (found.gpu_name, found.vram_mib, found.driver_version) == (
            "NVIDIA GeForce RTX 4090",
            24564,
            "596.36",
        )

    def test_a_failing_nvidia_smi_means_no_gpu(self, tmp_path: Path) -> None:
        exe = fake_smi(tmp_path, "echo 0, NVIDIA GeForce RTX 4090, 24564, 596.36", "exit /b 9")

        assert detect(env={hardware.NVIDIA_SMI_ENV: str(exe)}).gpu_name is None

    @pytest.mark.parametrize("override", ["", "missing.exe"])
    def test_pointing_the_override_nowhere_simulates_a_machine_without_a_gpu(
        self, tmp_path: Path, override: str
    ) -> None:
        found = detect(env={hardware.NVIDIA_SMI_ENV: str(tmp_path / override) if override else ""})

        assert (found.gpu_name, found.vram_mib, found.driver_version) == (None, None, None)

    def test_a_hung_nvidia_smi_gives_up_quickly_and_reports_no_gpu(self, tmp_path: Path) -> None:
        exe = fake_smi(tmp_path, "ping -n 30 127.0.0.1 >nul")

        start = time.perf_counter()
        found = detect(env={hardware.NVIDIA_SMI_ENV: str(exe)})
        elapsed = time.perf_counter() - start

        assert (found.gpu_name, found.vram_mib, found.driver_version) == (None, None, None)
        assert found.ram_mib is not None
        assert elapsed < 6


class TestFindingNvidiaSmi:
    def make(self, directory: Path) -> Path:
        directory.mkdir(parents=True, exist_ok=True)
        exe = directory / "nvidia-smi.exe"
        exe.write_bytes(b"")
        return exe

    def test_system32_wins_over_the_legacy_folder_and_over_path(self, tmp_path: Path) -> None:
        system32 = self.make(tmp_path / "root" / "System32")
        legacy = self.make(tmp_path / "legacy")
        on_path = self.make(tmp_path / "bin")
        env = {"SystemRoot": str(tmp_path / "root"), "PATH": str(on_path.parent)}

        assert hardware.find_nvidia_smi(env, legacy=legacy / "nvidia-smi.exe") == system32

    def test_the_legacy_folder_is_tried_before_path(self, tmp_path: Path) -> None:
        legacy = self.make(tmp_path / "legacy")
        on_path = self.make(tmp_path / "bin")
        env = {"SystemRoot": str(tmp_path / "root"), "PATH": str(on_path.parent)}

        assert hardware.find_nvidia_smi(env, legacy=legacy) == legacy

    def test_path_is_the_last_resort(self, tmp_path: Path) -> None:
        on_path = self.make(tmp_path / "bin")
        env = {"SystemRoot": str(tmp_path / "root"), "PATH": str(on_path.parent)}

        assert hardware.find_nvidia_smi(env, legacy=tmp_path / "none.exe") == on_path

    def test_the_current_directory_is_never_searched(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        planted = self.make(tmp_path / "cwd")
        monkeypatch.chdir(planted.parent)
        for path_value in ("", ".", os.pathsep.join(["", "."])):
            env = {"SystemRoot": str(tmp_path / "root"), "PATH": path_value}

            assert hardware.find_nvidia_smi(env, legacy=tmp_path / "none.exe") is None

    def test_the_override_replaces_every_other_candidate(self, tmp_path: Path) -> None:
        system32 = self.make(tmp_path / "root" / "System32")
        env = {"SystemRoot": str(tmp_path / "root"), hardware.NVIDIA_SMI_ENV: str(tmp_path / "x")}

        assert system32.is_file()
        assert hardware.find_nvidia_smi(env) is None


def synthetic_registry(**min_drivers: str | None) -> registry.Registry:
    runtimes = {
        runtime_id: dataclasses.replace(REGISTRY.runtimes[runtime_id], min_driver=floor)
        for runtime_id, floor in {
            profiles.WHISPER_RUNTIME: "551.61",
            profiles.LLAMA_RUNTIME: "551.61",
            profiles.CRISPASR_RUNTIME: "570.65",
        }.items()
    }
    for runtime_id, floor in min_drivers.items():
        runtimes[runtime_id] = dataclasses.replace(runtimes[runtime_id], min_driver=floor)
    return registry.Registry(REGISTRY.models, MappingProxyType({**REGISTRY.runtimes, **runtimes}))


@pytest.mark.parametrize(
    ("whisper_floor", "llama_floor"), [("560.00", "551.61"), ("551.61", "566.00")]
)
def test_the_driver_floor_is_the_highest_of_all_main_stages(
    whisper_floor: str, llama_floor: str
) -> None:
    table = synthetic_registry(
        **{profiles.WHISPER_RUNTIME: whisper_floor, profiles.LLAMA_RUNTIME: llama_floor}
    )
    highest = max(whisper_floor, llama_floor)
    just_below = f"{int(highest.split('.')[0]) - 1}.99"

    below = profiles.select(detect(env={}, smi=smi(f"0, GPU, 24564, {just_below}")), table)
    at = profiles.select(detect(env={}, smi=smi(f"0, GPU, 24564, {highest}")), table)

    assert isinstance(below.reason, DriverTooOld) and below.reason.required == highest
    assert below.profile.id is ProfileId.CPU
    assert at.profile.id is ProfileId.GPU_24GB


def test_a_high_fallback_floor_never_raises_the_main_stage_floor() -> None:
    table = synthetic_registry(**{profiles.CRISPASR_RUNTIME: "999.00"})

    selection = profiles.select(detect(env={}, smi=smi("0, GPU, 24564, 560.94")), table)

    assert selection.profile.id is ProfileId.GPU_24GB
    assert selection.reason is Cause.VRAM_FITS


def test_a_driver_between_the_two_floors_keeps_24gb_but_drops_the_crispasr_fallback() -> None:
    selection = choose("0, NVIDIA GeForce RTX 4090, 24564, 560.94")

    assert selection.profile.id is ProfileId.GPU_24GB
    assert selection.reason is Cause.VRAM_FITS
    assert selection.asr_fallback is None
    assert selection.fallback_blocked == DriverTooOld("560.94", "570.65", ProfileId.GPU_24GB)
    assert (
        "ASR fallback:  unavailable, driver 560.94 < 570.65; "
        "update the NVIDIA driver (CUDA Toolkit not needed)"
    ) in profiles.describe(selection, REGISTRY)


@pytest.mark.parametrize(
    ("driver", "kept"),
    [("570.65", True), ("570.64", False), ("596.36", True), ("551.61", False), ("unknown", True)],
)
def test_the_fallback_needs_driver_570_65_and_an_unknown_driver_keeps_it(
    driver: str, kept: bool
) -> None:
    selection = choose(f"0, NVIDIA GeForce RTX 4090, 24564, {driver}")

    assert selection.profile.id is ProfileId.GPU_24GB
    assert (selection.asr_fallback is not None) is kept
    assert (selection.fallback_blocked is None) is kept


def test_a_kept_fallback_is_listed_and_a_profile_without_one_blocks_nothing() -> None:
    kept = choose(RTX_4090)
    plain = choose(RTX_3070)
    cpu = choose(None)

    assert kept.asr_fallback == profiles.PROFILES[ProfileId.GPU_24GB].asr_fallback
    assert "ASR fallback:  qwen3-asr" in profiles.describe(kept, REGISTRY)
    for other in (plain, cpu):
        assert (other.asr_fallback, other.fallback_blocked) == (None, None)
        assert "ASR fallback" not in profiles.describe(other, REGISTRY)


def test_a_driver_too_old_for_the_main_stages_still_drops_to_cpu_without_a_fallback() -> None:
    selection = choose("0, GPU, 24564, 472.12")

    assert selection.profile.id is ProfileId.CPU
    assert (selection.asr_fallback, selection.fallback_blocked) == (None, None)


def test_the_cpu_profile_warns_when_ram_is_low_and_keeps_local_as_the_default() -> None:
    low = profiles.select(Hardware(None, None, None, 8192, 100_000), REGISTRY)
    enough = profiles.select(Hardware(None, None, None, 32768, 100_000), REGISTRY)
    unknown = profiles.select(Hardware(None, None, None, None, None), REGISTRY)

    assert low.low_ram == profiles.LowRam(8192, profiles.CPU_MIN_RAM_MIB)
    assert "RAM warning:   8192 MiB" in profiles.describe(low, REGISTRY)
    assert enough.low_ram is None and unknown.low_ram is None
    assert "RAM warning" not in profiles.describe(enough, REGISTRY)
    assert low.profile.llm.device is profiles.Device.CPU
    assert "recommended, only after you opt in" in profiles.describe(low, REGISTRY)


def test_the_cpu_label_does_not_claim_integrated_graphics() -> None:
    label = profiles.PROFILES[ProfileId.CPU].label.lower()

    assert "integrated" not in label and "graphics" not in label
    assert "integrated" not in profiles.describe(choose(None), REGISTRY).lower()


def test_ram_is_total_installed_memory_not_the_free_amount(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    mib = 1024 * 1024
    total, available = 16384 * mib, 3000 * mib

    if sys.platform == "win32":

        class Kernel32:
            @staticmethod
            def GlobalMemoryStatusEx(ref: Any) -> int:
                ref._obj.total_phys, ref._obj.avail_phys = total, available
                return 1

        monkeypatch.setattr(ctypes, "windll", SimpleNamespace(kernel32=Kernel32), raising=False)
    else:
        values = {"SC_PAGE_SIZE": 4096, "SC_PHYS_PAGES": total // 4096}
        monkeypatch.setattr(os, "sysconf", lambda name: values[name])

    assert detect(env={}, smi=smi(None)).ram_mib == 16384
