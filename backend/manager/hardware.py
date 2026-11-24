from __future__ import annotations

import csv
import ctypes
import io
import os
import re
import shutil
import subprocess
import sys
import tempfile
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path

from backend.manager.platforms import MACOS_ARM64, WIN_X64, UnsupportedPlatform, detect_platform

VRAM_OVERRIDE_ENV = "VST_VRAM_MIB"
NVIDIA_SMI_ENV = "VST_NVIDIA_SMI"
LEGACY_NVIDIA_SMI = Path(r"C:\Program Files\NVIDIA Corporation\NVSMI\nvidia-smi.exe")

SMI_COLUMNS = ("index", "name", "memory.total", "driver_version")
SMI_QUERY = (f"--query-gpu={','.join(SMI_COLUMNS)}", "--format=csv,noheader,nounits")
_SMI_TIMEOUT_S = 3
_MIB = 1024 * 1024
_DRIVER = re.compile(r"\d+(?:\.\d+)+")
_DIGITS = re.compile(r"\d+")
_CUDA_INDEX = re.compile(r"-?\d+")
SYSCTL = "/usr/sbin/sysctl"
_SYSCTL_TIMEOUT_S = 3


@dataclass(frozen=True, slots=True)
class Gpu:
    index: int
    name: str
    vram_mib: int | None
    driver_version: str | None


@dataclass(frozen=True, slots=True)
class Hardware:
    gpu_name: str | None
    vram_mib: int | None
    driver_version: str | None
    ram_mib: int | None
    disk_free_mib: int | None
    platform: str = WIN_X64
    chip: str | None = None
    """The Apple chip's name on a Mac ("Apple M3 Pro"); None elsewhere. On a Mac `ram_mib` is the
    unified memory the CPU and the GPU share, and there is no separate VRAM."""

    def describe(self) -> str:
        def show(value: object, unit: str = "") -> str:
            return "unknown" if value is None else f"{value}{unit}"

        if self.platform == MACOS_ARM64:
            return "\n".join(
                (
                    f"Chip:       {show(self.chip)}",
                    f"Memory:     {show(self.ram_mib, ' MiB')} (shared by the CPU and the GPU)",
                    f"Disk free:  {show(self.disk_free_mib, ' MiB')}",
                )
            )
        return "\n".join(
            (
                f"GPU:        {show(self.gpu_name)}",
                f"VRAM:       {show(self.vram_mib, ' MiB')}",
                f"Driver:     {show(self.driver_version)}",
                f"RAM:        {show(self.ram_mib, ' MiB')}",
                f"Disk free:  {show(self.disk_free_mib, ' MiB')}",
            )
        )


def parse_driver(text: str) -> tuple[int, ...] | None:
    return tuple(int(part) for part in text.split(".")) if _DRIVER.fullmatch(text) else None


def parse_nvidia_smi(text: str) -> list[Gpu]:
    gpus: list[Gpu] = []
    for row in csv.reader(io.StringIO(text), skipinitialspace=True):
        if len(row) != len(SMI_COLUMNS):
            continue
        index, name, memory, driver = (cell.strip() for cell in row)
        if not _DIGITS.fullmatch(index) or not name:
            continue
        gpus.append(
            Gpu(
                index=int(index),
                name=name,
                vram_mib=int(memory) if _DIGITS.fullmatch(memory) else None,
                driver_version=driver if parse_driver(driver) else None,
            )
        )
    return gpus


def find_nvidia_smi(
    env: Mapping[str, str] | None = None, legacy: Path = LEGACY_NVIDIA_SMI
) -> Path | None:
    env = os.environ if env is None else env
    override = env.get(NVIDIA_SMI_ENV)
    candidates: list[Path] = []
    if override is not None:
        candidates.append(Path(override))
    else:
        if system_root := env.get("SystemRoot"):
            candidates.append(Path(system_root) / "System32" / "nvidia-smi.exe")
        candidates.append(legacy)
        candidates.extend(
            Path(entry) / "nvidia-smi.exe"
            for entry in env.get("PATH", "").split(os.pathsep)
            if entry and Path(entry).is_absolute()
        )
    return next((path for path in candidates if path.is_file()), None)


def run_nvidia_smi(env: Mapping[str, str] | None = None) -> str | None:
    exe = find_nvidia_smi(env)
    if exe is None:
        return None
    try:
        with tempfile.TemporaryFile() as out:
            proc = subprocess.Popen(
                [exe, *SMI_QUERY],
                stdin=subprocess.DEVNULL,
                stdout=out,
                stderr=subprocess.DEVNULL,
                creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
            )
            try:
                code = proc.wait(timeout=_SMI_TIMEOUT_S)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait()
                return None
            out.seek(0)
            return out.read().decode("utf-8", errors="replace") if code == 0 else None
    except OSError:
        return None


def _cuda_visible_gpus(gpus: list[Gpu], cuda_visible_devices: str | None) -> list[Gpu]:
    if cuda_visible_devices is None:
        return gpus
    present = {gpu.index: gpu for gpu in gpus}
    visible: list[Gpu] = []
    for token in (t.strip() for t in cuda_visible_devices.split(",")):
        if token and not _CUDA_INDEX.fullmatch(token):
            return gpus
        if not token or int(token) not in present:
            break
        visible.append(present[int(token)])
    return visible


def _largest_vram_gpu(gpus: list[Gpu]) -> Gpu | None:
    return max(gpus, key=lambda g: (g.vram_mib or 0, -g.index), default=None)


def _vram_override(env: Mapping[str, str]) -> int | None:
    raw = env.get(VRAM_OVERRIDE_ENV)
    if raw is None:
        return None
    if not _DIGITS.fullmatch(raw.strip()) or int(raw) < 1:
        raise ValueError(f"{VRAM_OVERRIDE_ENV} must be a positive integer of MiB, got {raw!r}")
    return int(raw)


class _MemoryStatus(ctypes.Structure):
    _fields_ = (
        ("length", ctypes.c_ulong),
        ("memory_load", ctypes.c_ulong),
        ("total_phys", ctypes.c_ulonglong),
        ("avail_phys", ctypes.c_ulonglong),
        ("total_page_file", ctypes.c_ulonglong),
        ("avail_page_file", ctypes.c_ulonglong),
        ("total_virtual", ctypes.c_ulonglong),
        ("avail_virtual", ctypes.c_ulonglong),
        ("avail_extended_virtual", ctypes.c_ulonglong),
    )


Sysctl = Callable[[str], str | None]
"""(name) -> the value `sysctl -n name` prints, or None when it cannot be read."""


def run_sysctl(name: str) -> str | None:
    try:
        done = subprocess.run(  # noqa: S603
            [SYSCTL, "-n", name],
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            timeout=_SYSCTL_TIMEOUT_S,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    return done.stdout.strip() if done.returncode == 0 else None


def read_apple_silicon(sysctl: Sysctl = run_sysctl) -> tuple[str, int | None] | None:
    """The chip name and the unified memory in MiB of an Apple-silicon Mac, or None when the
    machine does not say it is one. A memory that cannot be read comes back as None."""
    brand = sysctl("machdep.cpu.brand_string")
    if not brand or not brand.startswith("Apple"):
        return None
    raw = sysctl("hw.memsize")
    memory = int(raw) // _MIB if raw is not None and _DIGITS.fullmatch(raw) else None
    return brand, memory


def _total_ram_mib() -> int | None:
    try:
        if sys.platform == "win32":
            status = _MemoryStatus()
            status.length = ctypes.sizeof(_MemoryStatus)
            if not ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
                return None
            return int(status.total_phys) // _MIB
        return os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES") // _MIB
    except (OSError, ValueError, AttributeError):
        return None


def _disk_free_mib(path: Path) -> int | None:
    target = path
    while not target.exists() and target != target.parent:
        target = target.parent
    try:
        return shutil.disk_usage(target).free // _MIB
    except OSError:
        return None


def detect(
    *,
    env: Mapping[str, str] | None = None,
    smi: Callable[[], str | None] | None = None,
    disk_path: Path | None = None,
    platform: str | None = None,
    sysctl: Sysctl = run_sysctl,
) -> Hardware:
    env = os.environ if env is None else env
    if platform is None:
        try:
            platform = detect_platform()
        except UnsupportedPlatform:
            platform = WIN_X64
    if platform == MACOS_ARM64:
        apple = read_apple_silicon(sysctl)
        chip, memory = apple if apple is not None else (None, None)
        return Hardware(
            None,
            None,
            None,
            memory if memory is not None else _total_ram_mib(),
            _disk_free_mib(_disk_root(disk_path)),
            MACOS_ARM64,
            chip,
        )
    output = smi() if smi is not None else run_nvidia_smi(env)
    detected = parse_nvidia_smi(output) if output else []
    gpu = _largest_vram_gpu(_cuda_visible_gpus(detected, env.get("CUDA_VISIBLE_DEVICES")))
    if gpu is None:
        return Hardware(None, None, None, _total_ram_mib(), _disk_free_mib(_disk_root(disk_path)))
    override = _vram_override(env)
    return Hardware(
        gpu_name=gpu.name,
        vram_mib=gpu.vram_mib if override is None else override,
        driver_version=gpu.driver_version,
        ram_mib=_total_ram_mib(),
        disk_free_mib=_disk_free_mib(_disk_root(disk_path)),
    )


def _disk_root(disk_path: Path | None) -> Path:
    return Path.home() if disk_path is None else disk_path


def main() -> int:
    from backend.manager import profiles, registry

    try:
        hardware = detect()
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    table = registry.load()
    print(hardware.describe())
    print()
    print(profiles.describe(profiles.select(hardware, table), table))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
