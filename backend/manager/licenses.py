"""The third-party license list, built from registry.json. Every model and runtime appears, with the
license name the registry records and the URL of its license text."""

from __future__ import annotations

import re
from dataclasses import dataclass

from backend.manager.registry import Registry

_NVIDIA_EULA = "https://docs.nvidia.com/cuda/eula/index.html"
_SPLIT = re.compile(r"\s+(?:AND|OR|WITH)\s+")


@dataclass(frozen=True, slots=True)
class Part:
    id: str
    url: str


@dataclass(frozen=True, slots=True)
class LicenseEntry:
    id: str
    type: str
    version: str
    license: str
    """The SPDX-style expression from the registry."""
    license_url: str
    """The license text or model card of this asset."""
    parts: tuple[Part, ...]
    """Each license named in the expression, with its standard text."""
    source_url: str


def _part(name: str) -> Part:
    if name.startswith("LicenseRef-NVIDIA-CUDA-EULA"):
        return Part(name, _NVIDIA_EULA)
    return Part(name, f"https://spdx.org/licenses/{name}.html")


def license_entries(registry: Registry) -> tuple[LicenseEntry, ...]:
    entries: list[LicenseEntry] = []
    for kind, pool in (("model", registry.models), ("runtime", registry.runtimes)):
        for item in pool.values():
            names = dict.fromkeys(_SPLIT.split(item.license))
            entries.append(
                LicenseEntry(
                    id=item.id,
                    type=kind,
                    version=item.version,
                    license=item.license,
                    license_url=item.license_url,
                    parts=tuple(_part(n) for n in names),
                    source_url=item.url,
                )
            )
    return tuple(entries)
