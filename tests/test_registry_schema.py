from __future__ import annotations

import copy
import json
from typing import Any

import jsonschema
import pytest

from backend.manager import registry
from backend.manager.registry import RegistryError

SCHEMA: dict[str, Any] = json.loads(
    registry.REGISTRY_PATH.with_name("registry.schema.json").read_text(encoding="utf-8")
)
RAW: dict[str, Any] = json.loads(registry.REGISTRY_PATH.read_text(encoding="utf-8"))
VALIDATOR: Any = jsonschema.Draft202012Validator(SCHEMA)


def accepted_by_schema(raw: Any) -> bool:
    return bool(VALIDATOR.is_valid(raw))


def accepted_by_loader(raw: object) -> bool:
    try:
        registry.parse(raw)
    except RegistryError:
        return False
    return True


def mutated(section: str, key: str, value: object) -> dict[str, Any]:
    raw = copy.deepcopy(RAW)
    raw[section][0][key] = value
    return raw


def test_the_shipped_registry_json_passes_the_schema_and_the_loader() -> None:
    assert accepted_by_schema(RAW)
    assert accepted_by_loader(RAW)


BAD_REGISTRIES: list[tuple[str, dict[str, Any]]] = [
    ("id with a space", mutated("models", "id", "has space")),
    ("id with a leading dash", mutated("runtimes", "id", "-lead")),
    ("platform linux", mutated("runtimes", "platform", "linux-x64")),
    ("backend vulkan", mutated("runtimes", "backend", "vulkan")),
    ("absolute executable", mutated("runtimes", "executable", "/abs/x.exe")),
    ("drive-letter executable", mutated("runtimes", "executable", "C:/Windows/x.exe")),
    ("dot-dot executable", mutated("runtimes", "executable", "../../evil.exe")),
    ("dot-dot in the middle", mutated("runtimes", "executable", "a/../b.exe")),
    ("dot segment executable", mutated("runtimes", "executable", "./x.exe")),
    ("trailing slash executable", mutated("runtimes", "executable", "a/")),
    ("file dot-dot", mutated("models", "file", "..")),
    ("file with a drive", mutated("models", "file", "C:x.zip")),
    ("file with a slash", mutated("models", "file", "a/b.zip")),
    ("zero size", mutated("models", "size_bytes", 0)),
    ("string size", mutated("models", "size_bytes", "5")),
    ("bad id in needs", mutated("runtimes", "needs", ["bad id"])),
    ("empty models", {**RAW, "models": []}),
    ("empty runtimes", {**RAW, "runtimes": []}),
    ("unknown key", mutated("models", "extra", 1)),
]


@pytest.mark.parametrize(("label", "raw"), BAD_REGISTRIES, ids=[b[0] for b in BAD_REGISTRIES])
def test_the_schema_and_the_loader_both_refuse_the_same_bad_registry(
    label: str, raw: dict[str, Any]
) -> None:
    assert not accepted_by_schema(raw), label
    assert not accepted_by_loader(raw), label


@pytest.mark.parametrize("executable", ["Release/whisper-cli.exe", "run.exe", "a/b/c.exe", None])
def test_the_schema_and_the_loader_both_accept_a_plain_relative_executable(
    executable: str | None,
) -> None:
    raw = mutated("runtimes", "executable", executable)

    assert accepted_by_schema(raw)
    assert accepted_by_loader(raw)


def test_the_loader_alone_checks_references_between_entries_and_whole_number_sizes() -> None:
    unknown_need = mutated("models", "needs", ["nope"])
    float_size = mutated("models", "size_bytes", 1.0)

    assert accepted_by_schema(unknown_need) and not accepted_by_loader(unknown_need)
    assert accepted_by_schema(float_size) and not accepted_by_loader(float_size)
