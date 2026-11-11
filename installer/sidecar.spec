# PyInstaller spec for the backend sidecar: `python -m backend.main` as one executable.
# Run through installer/build.ps1. No PyTorch and no CUDA go in: speech and language models run in
# the whisper.cpp, CrispASR and llama.cpp runtimes the app downloads, and onnxruntime is the CPU
# build (the VAD model is tiny).
import os
from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files, collect_dynamic_libs, collect_submodules

root = Path(SPECPATH).parent
onefile = os.environ.get("VST_ONEFILE") == "1"

# backend/core/vad.py imports onnxruntime by name at run time, so the analysis cannot see it.
hiddenimports = (
    collect_submodules("backend")
    + collect_submodules("uvicorn")
    + ["onnxruntime", "onnxruntime.capi", "onnxruntime.capi.onnxruntime_pybind11_state"]
)
datas = collect_data_files("backend", includes=["**/*.md", "**/*.json"])
binaries = collect_dynamic_libs("onnxruntime")

a = Analysis(
    [str(root / "backend" / "main.py")],
    pathex=[str(root)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    excludes=["torch", "tkinter", "onnxruntime.tools", "onnxruntime.transformers", "onnxruntime.quantization", "onnxruntime.datasets", "pytest", "pyright", "ruff", "httpx", "jsonschema"],
    noarchive=False,
)
pyz = PYZ(a.pure)

if onefile:
    exe = EXE(
        pyz, a.scripts, a.binaries, a.datas, [],
        name="vst-backend", console=True, upx=False,
    )
else:
    exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="vst-backend", console=True, upx=False)
    COLLECT(exe, a.binaries, a.datas, name="vst-backend", upx=False)
