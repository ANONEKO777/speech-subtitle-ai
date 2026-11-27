"""The W4b sentences, each raised at the site the app raises it from.

`app/src/i18n/notices.w4b.fixture.json` holds, for each scenario, the text and notices this module
produces now (`tests/test_notices_w4b.py` keeps them equal), `before`: the text the same call gave
at commit 96dc7b3, and `zh`: what a window in Traditional Chinese shows. `before` was written by
running this module on a clean export of that commit, so it only calls what both versions have.
The English must equal `before`: the window words these sentences, it does not change them.

Paths are written with `/`, so the fixture is the same on every system.
"""

# pyright: reportUnknownLambdaType=false, reportUnknownArgumentType=false
# pyright: reportPrivateUsage=false

from __future__ import annotations

import io
import os
import subprocess
import sys
import urllib.error
from collections.abc import Callable
from dataclasses import asdict, replace
from email.message import Message
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

import pytest
from notice_scenarios import _slashes

from backend.core import vc_runtime
from backend.core.notices import notices_of
from backend.manager import platforms, profiles, selftest, updates
from backend.manager import registry as registry_module
from backend.manager.hardware import Hardware
from backend.manager.profiles import ProfileId
from backend.manager.selftest_store import SelfTestStore
from backend.manager.storage import Storage

Entry = dict[str, Any]


def _entry(text: str, found: object) -> Entry:
    """`found` is the notices beside `text`: dataclasses, JSON, or nothing at an older commit."""
    listed: list[Any] = list(cast("Any", found or ()))
    return {"text": text, "notices": [n if isinstance(n, dict) else asdict(n) for n in listed]}


# Group 1: why a profile was chosen.


def _why(selection: profiles.Selection, registry: registry_module.Registry) -> Entry:
    explain = getattr(profiles, "explain", None)
    found = explain(selection, registry).notices if explain else ()
    return _entry(profiles.describe(selection, registry), found)


def _profiles(found: dict[str, Entry]) -> None:
    win = registry_module.load(platform=platforms.WIN_X64)
    mac = registry_module.load(platform=platforms.MACOS_ARM64)

    def pc(vram: int | None, driver: str = "596.36", ram: int = 65536) -> Hardware:
        return Hardware("RTX", vram, driver, ram, 1)

    def apple(ram: int | None) -> Hardware:
        return Hardware(None, None, None, ram, 1, platforms.MACOS_ARM64, "Apple M3")

    hardware = {
        "vramFits24": pc(24564),
        "vramFits8": pc(8192),
        "noGpuLowRam": Hardware(None, None, None, 8192, 1),
        "vramUnknown": pc(None),
        "vramTooSmall": pc(4096),
        "driverTooOld": pc(24564, "500.00"),
    }
    for name, one in hardware.items():
        found[f"why.{name}"] = _why(profiles.select(one, win), win)
    for name, ram in (("memoryFits", 36864), ("memoryUnknown", None), ("memoryTooSmall", 8192)):
        found[f"why.{name}"] = _why(profiles.select(apple(ram), mac), mac)
    found["why.fallbackBlocked"] = _why(
        profiles.selection_for(ProfileId.GPU_24GB, pc(4096, "560.00"), win), win
    )
    for profile_id in ProfileId:
        on_mac = profile_id in profiles.MAC_PROFILES
        registry, one = (mac, apple(36864)) if on_mac else (win, pc(4096))
        found[f"why.chosen.{profile_id.value}"] = _why(
            profiles.selection_for(profile_id, one, registry), registry
        )


# Group 2: the self-test, each report made by `run_selftest` with the real probe.

PROGRAM = Path("/vst/program.exe")


class _Program:
    """Stands in for `subprocess.Popen`: it ends as `how` says without starting anything."""

    def __init__(self, how: str) -> None:
        self.how, self.waits = how, 0
        self.returncode = 3 if how == "exits" else 0

    def communicate(self, timeout: float | None = None) -> tuple[bytes, None]:
        self.waits += 1
        if self.how == "hangs" and self.waits == 1:
            raise subprocess.TimeoutExpired("program", timeout or 0)
        said = {"exits": b"ggml error\nno kernel image", "cudaOk": b"CUDA0", "noCuda": b"none"}
        return said.get(self.how, b""), None

    def kill(self) -> None:
        pass


def _start(gpu: str, cpu: str) -> Callable[..., _Program]:
    """`gpu` and `cpu` say how a program ends on that device. A CPU command is told apart from a
    GPU one by its flags."""

    def popen(command: list[str], **_kwargs: object) -> _Program:
        how = cpu if "-ng" in command or "--version" in command else gpu
        if how == "missing":
            raise OSError("The system cannot find the file specified")
        return _Program(how)

    return popen


def _report(
    name: str,
    profile_id: ProfileId,
    tmp: Path,
    found: dict[str, Entry],
    *,
    gpu: str = "cudaOk",
    cpu: str = "ok",
    absent: tuple[str, ...] = (),
    simulate: bool = False,
) -> None:
    registry = registry_module.load(platform=platforms.WIN_X64)
    profile = next(p for p in profiles.profiles_for(platforms.WIN_X64) if p.id is profile_id)
    model = tmp / "model.bin"
    model.write_bytes(b"x")

    def executable(runtime_id: str, *_rest: object) -> Path | None:
        return None if runtime_id.endswith(absent or ("\0",)) else PROGRAM

    with pytest.MonkeyPatch.context() as mp:
        mp.delenv("VST_SIMULATE_NO_VCRUNTIME", raising=False)
        if simulate:
            mp.setenv(selftest.FAULT_ENV, "1")
        else:
            mp.delenv(selftest.FAULT_ENV, raising=False)
        mp.setattr(vc_runtime, "require", lambda _error: None)
        mp.setattr(selftest, "runtime_executable", executable)
        mp.setattr(Storage, "model_file", lambda *_a: model)
        mp.setattr(selftest, "adopt", lambda _proc: None)
        mp.setattr(selftest.subprocess, "Popen", _start(gpu, cpu))
        report = asdict(selftest.run_selftest(profile, registry, Storage(tmp), SelfTestStore(tmp)))
    found[f"{name}.message"] = _entry(report["message"], report.get("message_notices"))
    if report["fallback"]:
        fallback = report["fallback"]
        found[f"{name}.reason"] = _entry(fallback["reason"], fallback.get("reason_notices"))
    for index, stage in enumerate(report["stages"]):
        found[f"{name}.stage{index}"] = _entry(stage["detail"], stage.get("detail_notices"))


def _selftests(found: dict[str, Entry], tmp: Path) -> None:
    gpu, cpu = ProfileId.GPU_24GB, ProfileId.CPU
    _report("selftest.passedGpu", gpu, tmp, found)
    _report("selftest.passedCpu", cpu, tmp, found)
    _report("selftest.exits", cpu, tmp, found, cpu="exits")
    _report("selftest.hangs", cpu, tmp, found, cpu="hangs")
    _report("selftest.cannotStart", cpu, tmp, found, cpu="missing")
    _report("selftest.fellBack", gpu, tmp, found, simulate=True)
    _report("selftest.bothFail", gpu, tmp, found, gpu="noCuda", cpu="exits")
    _report("selftest.noCpuRuntime", gpu, tmp, found, simulate=True, absent=("cpu",))
    _report("selftest.notInstalled", cpu, tmp, found, absent=("cpu",))


# Group 3: the update check.

REMOTE = "https://example.test/registry.json"


def _said(carrier: object) -> Entry:
    """A report or an item: its `message`, and the notices a newer commit sends beside it."""
    return _entry(carrier.message, getattr(carrier, "message_notices", ()))  # pyright: ignore


def _raised(call: Callable[[], object]) -> Entry:
    """What `call` raises, with the notices it or its causes carry."""
    try:
        call()
    except Exception as exc:
        return _entry(str(exc), notices_of(exc))
    raise AssertionError("nothing was raised")


def _updates(found: dict[str, Entry]) -> None:
    bundled = registry_module.load(platform=platforms.WIN_X64)
    first, second = list(bundled.models.values())[:2]
    newer = replace(
        bundled, models={**bundled.models, first.id: replace(first, version="v9", sha256="f" * 64)}
    )
    installed: dict[str, object] = {}

    def record(ok: bool = True, version: str = first.version, sha: str = first.sha256) -> object:
        return SimpleNamespace(ok=ok, version=version, sha256=sha)

    inv: Any = SimpleNamespace(
        registry=bundled,
        manifest=SimpleNamespace(get=lambda asset_id: installed.get(asset_id)),
        is_installed=lambda asset_id: asset_id in installed,
    )

    def item(name: str, remote: registry_module.Registry | None = None) -> None:
        url = REMOTE if remote else None
        found[f"updates.item.{name}"] = _said(updates._item(inv, first.id, remote, url))

    item("notInstalled")
    found["updates.noRemote"] = _said(updates.check_updates(inv, None))
    installed[first.id] = None
    item("unrecorded")
    installed[first.id] = record(ok=False)
    item("checkFailed")
    installed[first.id] = record()
    item("matchesBundle")
    item("matchesRemote", bundled)
    item("needsApp", newer)
    found["updates.allMatch"] = _said(updates.check_updates(inv, REMOTE, lambda _url: bundled))
    installed[first.id] = record(version="v0", sha="0" * 64)
    installed[second.id] = record(version="v0", sha="0" * 64)
    item("older")
    found["updates.available"] = _said(updates.check_updates(inv, None))

    def reading(name: str, answer: Callable[..., object]) -> None:
        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(updates.urllib.request, "urlopen", answer)
            found[f"updates.read.{name}"] = _raised(lambda: updates.fetch_registry(REMOTE))

    def fails(error: Exception) -> Callable[..., object]:
        def open_it(*_args: object, **_kwargs: object) -> object:
            raise error

        return open_it

    reading("http", fails(urllib.error.HTTPError(REMOTE, 404, "Not Found", Message(), None)))
    reading("connect", fails(urllib.error.URLError("refused")))
    reading("invalid", lambda *_a, **_k: io.BytesIO(b"<html>"))
    reading("failed", fails(TimeoutError("timed out")))


def collect(tmp: Path) -> dict[str, Entry]:
    found: dict[str, Entry] = {}
    _profiles(found)
    _selftests(found, tmp)
    _updates(found)
    return {name: _slashes(entry) for name, entry in found.items()}


if __name__ == "__main__":
    import json
    import tempfile

    with tempfile.TemporaryDirectory(dir=os.environ.get("VST_SCRATCH")) as folder:
        made = json.dumps(collect(Path(folder)), ensure_ascii=False, indent=2)
        sys.stdout.buffer.write(made.encode("utf-8"))
