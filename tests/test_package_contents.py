"""What the Windows installer holds. The installer is built by `installer/build.ps1`; this test
lists it with 7-Zip. Without a built installer the listing test skips, unless `VST_INSTALLER` names
one (the build script sets it)."""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
NSIS_DIR = ROOT / "app" / "src-tauri" / "target" / "release" / "bundle" / "nsis"
FORBIDDEN = ("cudart", "cublas", "nvblas", "nvrtc", "cudnn", "torch", ".gguf")
REQUIRED = (
    "vst-backend.exe",
    "ffmpeg.exe",
    "ffprobe.exe",
    "registry.json",
    "THIRD_PARTY.md",
    "FFmpeg-external-libraries.txt",
)


def forbidden_in(names: list[str]) -> list[str]:
    return [n for n in names if any(bad in n.lower() for bad in FORBIDDEN)]


def missing_from(names: list[str]) -> list[str]:
    lowered = [n.lower().replace("\\", "/").rsplit("/", 1)[-1] for n in names]
    return [r for r in REQUIRED if r.lower() not in lowered]


def seven_zip() -> str | None:
    found = shutil.which("7z")
    if found:
        return found
    fallback = Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / "7-Zip" / "7z.exe"
    return str(fallback) if fallback.is_file() else None


def list_installer(installer: Path) -> list[str]:
    tool = seven_zip()
    assert tool, "7-Zip is needed to list the installer"
    out = subprocess.run(  # noqa: S603
        [tool, "l", "-slt", str(installer)], capture_output=True, text=True, check=True
    ).stdout
    return [line.removeprefix("Path = ") for line in out.splitlines() if line.startswith("Path = ")]


def find_installer() -> Path | None:
    named = os.environ.get("VST_INSTALLER")
    if named:
        return Path(named)
    found = sorted(NSIS_DIR.glob("*-setup.exe")) if NSIS_DIR.is_dir() else []
    return found[-1] if found else None


def test_the_check_names_cuda_torch_and_model_files():
    bad = forbidden_in(
        ["backend/vst-backend.exe", "x/cudart64_12.dll", "a/cublasLt64_12.dll", "torch/lib.dll",
         "m/qwen3.GGUF", "ffmpeg/avcodec-62.dll"]
    )  # fmt: skip
    assert bad == ["x/cudart64_12.dll", "a/cublasLt64_12.dll", "torch/lib.dll", "m/qwen3.GGUF"]


def test_the_check_names_a_missing_piece():
    assert missing_from(["backend/vst-backend.exe", "ffmpeg/ffmpeg.exe"]) == [
        "ffprobe.exe", "registry.json", "THIRD_PARTY.md", "FFmpeg-external-libraries.txt",
    ]  # fmt: skip


def test_the_installer_holds_no_cuda_torch_or_model_and_has_every_piece():
    installer = find_installer()
    if installer is None or not installer.is_file():
        pytest.skip("no installer built; run installer/build.ps1")
    names = list_installer(installer)
    assert len(names) > 100
    assert forbidden_in(names) == []
    assert missing_from(names) == []
