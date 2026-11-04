from __future__ import annotations

import dataclasses
import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from types import MappingProxyType
from typing import Any, TypeVar

REGISTRY_PATH = Path(__file__).with_name("registry.json")
SCHEMA_VERSION = 1

_SHA256 = re.compile(r"[0-9a-f]{64}")
_DRIVER = re.compile(r"\d+\.\d+")
_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*")
PLATFORMS = frozenset({"win-x64"})
BACKENDS = frozenset({"cuda"})


class RegistryError(ValueError):
    pass


class ModelKind(StrEnum):
    ASR = "asr"
    ALIGNER = "aligner"
    VAD = "vad"
    LLM = "llm"


@dataclass(frozen=True, slots=True)
class Model:
    id: str
    kind: ModelKind
    engine: str
    version: str
    url: str
    file: str
    sha256: str
    size_bytes: int
    license: str
    vram_mib: int | None
    params_b: int | None
    needs: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class Runtime:
    id: str
    engine: str
    version: str
    platform: str
    backend: str
    url: str
    file: str
    sha256: str
    size_bytes: int
    license: str
    executable: str | None
    min_driver: str | None
    ascii_paths_only: bool
    needs: tuple[str, ...]


_Entry = TypeVar("_Entry", Model, Runtime)


@dataclass(frozen=True, slots=True)
class Registry:
    models: Mapping[str, Model]
    runtimes: Mapping[str, Runtime]


def load(path: Path = REGISTRY_PATH) -> Registry:
    try:
        raw: object = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise RegistryError(f"cannot read {path}: {exc}") from exc
    return parse(raw)


def parse(raw: object) -> Registry:
    top = _object(raw, "registry", {"schema_version", "models", "runtimes"})
    if top["schema_version"] != SCHEMA_VERSION:
        raise RegistryError(f"unsupported schema_version {top['schema_version']!r}")
    models = _unique([_model(item) for item in _non_empty(top["models"], "models")], "model")
    runtimes = _unique(
        [_runtime(item) for item in _non_empty(top["runtimes"], "runtimes")], "runtime"
    )
    for entry in (*models.values(), *runtimes.values()):
        pool = models if isinstance(entry, Model) else runtimes
        for need in entry.needs:
            if need not in pool:
                raise RegistryError(f"{entry.id} needs unknown id {need!r}")
    return Registry(MappingProxyType(models), MappingProxyType(runtimes))


def _unique(items: list[_Entry], what: str) -> dict[str, _Entry]:
    out: dict[str, _Entry] = {}
    for item in items:
        if item.id in out:
            raise RegistryError(f"duplicate {what} id {item.id!r}")
        out[item.id] = item
    return out


def _model(raw: object) -> Model:
    d = _object(raw, "model", {f.name for f in dataclasses.fields(Model)})
    name = f"model {d['id']!r}"
    try:
        kind = ModelKind(d["kind"])
    except ValueError as exc:
        raise RegistryError(f"{name}: unknown kind {d['kind']!r}") from exc
    return Model(
        id=_id(d, "id", name),
        kind=kind,
        engine=_str(d, "engine", name),
        version=_str(d, "version", name),
        url=_url(d, name),
        file=_file(d, name),
        sha256=_sha256(d, name),
        size_bytes=_positive_int(d, "size_bytes", name),
        license=_str(d, "license", name),
        vram_mib=_optional_positive_int(d, "vram_mib", name),
        params_b=_optional_positive_int(d, "params_b", name),
        needs=_needs(d, name),
    )


def _runtime(raw: object) -> Runtime:
    d = _object(raw, "runtime", {f.name for f in dataclasses.fields(Runtime)})
    name = f"runtime {d['id']!r}"
    executable = d["executable"]
    if executable is not None and not _is_safe_relative_path(executable):
        raise RegistryError(
            f"{name}: executable must be a relative path of plain segments, "
            "with forward slashes and no drive letter, '.' or '..', or null"
        )
    min_driver = d["min_driver"]
    if min_driver is not None and not (
        isinstance(min_driver, str) and _DRIVER.fullmatch(min_driver)
    ):
        raise RegistryError(f"{name}: min_driver must look like '551.61' or be null")
    ascii_only = d["ascii_paths_only"]
    if type(ascii_only) is not bool:
        raise RegistryError(f"{name}: ascii_paths_only must be a boolean")
    return Runtime(
        id=_id(d, "id", name),
        engine=_str(d, "engine", name),
        version=_str(d, "version", name),
        platform=_one_of(d, "platform", name, PLATFORMS),
        backend=_one_of(d, "backend", name, BACKENDS),
        url=_url(d, name),
        file=_file(d, name),
        sha256=_sha256(d, name),
        size_bytes=_positive_int(d, "size_bytes", name),
        license=_str(d, "license", name),
        executable=executable,
        min_driver=min_driver,
        ascii_paths_only=ascii_only,
        needs=_needs(d, name),
    )


def _object(raw: object, what: str, keys: set[str]) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise RegistryError(f"{what} must be an object")
    d: dict[str, Any] = dict(raw)  # pyright: ignore[reportUnknownArgumentType]
    if set(d) != keys:
        missing, extra = sorted(keys - set(d)), sorted(set(d) - keys)
        raise RegistryError(f"{what}: missing keys {missing}, unexpected keys {extra}")
    return d


def _array(raw: object, what: str) -> list[object]:
    if not isinstance(raw, list):
        raise RegistryError(f"{what} must be an array")
    return list(raw)  # pyright: ignore[reportUnknownArgumentType]


def _non_empty(raw: object, what: str) -> list[object]:
    items = _array(raw, what)
    if not items:
        raise RegistryError(f"{what} must not be empty")
    return items


def _is_safe_relative_path(value: object) -> bool:
    if not isinstance(value, str) or not value or "\\" in value or ":" in value:
        return False
    return all(segment not in ("", ".", "..") for segment in value.split("/"))


def _id(d: dict[str, Any], key: str, name: str) -> str:
    value = _str(d, key, name)
    if not _ID.fullmatch(value):
        raise RegistryError(f"{name}: {key} must match {_ID.pattern}")
    return value


def _one_of(d: dict[str, Any], key: str, name: str, allowed: frozenset[str]) -> str:
    value = _str(d, key, name)
    if value not in allowed:
        raise RegistryError(f"{name}: {key} must be one of {sorted(allowed)}, got {value!r}")
    return value


def _str(d: dict[str, Any], key: str, name: str) -> str:
    value = d[key]
    if not isinstance(value, str) or not value:
        raise RegistryError(f"{name}: {key} must be a non-empty string")
    return value


def _url(d: dict[str, Any], name: str) -> str:
    value = _str(d, "url", name)
    if not value.startswith("https://") or any(c.isspace() for c in value):
        raise RegistryError(f"{name}: url must be an https URL")
    return value


def _file(d: dict[str, Any], name: str) -> str:
    value = _str(d, "file", name)
    if "/" in value or "\\" in value or ":" in value or value in (".", ".."):
        raise RegistryError(f"{name}: file must be a bare file name")
    return value


def _sha256(d: dict[str, Any], name: str) -> str:
    value = _str(d, "sha256", name)
    if not _SHA256.fullmatch(value):
        raise RegistryError(f"{name}: sha256 must be 64 lowercase hex digits")
    return value


def _positive_int(d: dict[str, Any], key: str, name: str) -> int:
    value = d[key]
    if type(value) is not int or value < 1:
        raise RegistryError(f"{name}: {key} must be a positive integer")
    return value


def _optional_positive_int(d: dict[str, Any], key: str, name: str) -> int | None:
    return None if d[key] is None else _positive_int(d, key, name)


def _needs(d: dict[str, Any], name: str) -> tuple[str, ...]:
    values = _array(d["needs"], f"{name}: needs")
    if not all(isinstance(v, str) and _ID.fullmatch(v) for v in values) or len(set(values)) != len(
        values
    ):
        raise RegistryError(f"{name}: needs must be a list of distinct ids")
    return tuple(str(v) for v in values)
