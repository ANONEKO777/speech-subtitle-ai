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

import os
import sys
from dataclasses import asdict
from pathlib import Path
from typing import Any, cast

from notice_scenarios import _slashes

from backend.manager import platforms, profiles
from backend.manager import registry as registry_module
from backend.manager.hardware import Hardware
from backend.manager.profiles import ProfileId

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


def collect(tmp: Path) -> dict[str, Entry]:
    found: dict[str, Entry] = {}
    _profiles(found)
    return {name: _slashes(entry) for name, entry in found.items()}


if __name__ == "__main__":
    import json
    import tempfile

    with tempfile.TemporaryDirectory(dir=os.environ.get("VST_SCRATCH")) as folder:
        made = json.dumps(collect(Path(folder)), ensure_ascii=False, indent=2)
        sys.stdout.buffer.write(made.encode("utf-8"))
