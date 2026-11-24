"""The platform as data: which machines are supported, and the registry rows for each.

The Windows rows are pinned by a digest taken from `main` before the macOS rows existed, so a
change to them fails here. Mac downloads are pinned to the sizes and SHA-256 values read from the
published archives."""

from __future__ import annotations

import copy
import hashlib
import json
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import jsonschema
import pytest

from backend.manager import platforms, registry
from backend.manager.platforms import MACOS_ARM64, WIN_X64, UnsupportedPlatform, detect_platform
from backend.manager.registry import RegistryError

RAW: dict[str, Any] = json.loads(registry.REGISTRY_PATH.read_text(encoding="utf-8"))
SCHEMA: dict[str, Any] = json.loads(
    registry.REGISTRY_PATH.with_name("registry.schema.json").read_text(encoding="utf-8")
)
VALIDATOR: Any = jsonschema.Draft202012Validator(SCHEMA)
WINDOWS_DIGEST = "09168f2b81d4cffe71e9baa6a97a53a41f53091c645a4909bba401623b4ad7c9"
WINDOWS_RUNTIME_IDS = [
    "whispercpp-b5454-win-cuda12.4",
    "whispercpp-b5454-win-cpu",
    "llama.cpp-b12068-win-cpu",
    "crispasr-v0.8.49-win-cuda",
    "llama.cpp-b12068-win-cuda12.4",
    "cudart-llama-b12068-win-cuda12.4",
]


def windows_only(raw: dict[str, Any]) -> dict[str, Any]:
    out = copy.deepcopy(raw)
    out["runtimes"] = [r for r in out["runtimes"] if r["platform"] == WIN_X64]
    return out


def mac_runtime(rid: str) -> dict[str, Any]:
    return copy.deepcopy(next(r for r in RAW["runtimes"] if r["id"] == rid))


def test_the_windows_rows_are_byte_for_byte_what_main_had() -> None:
    canonical = json.dumps(windows_only(RAW), sort_keys=True, separators=(",", ":"))

    assert hashlib.sha256(canonical.encode()).hexdigest() == WINDOWS_DIGEST


def test_loading_on_windows_gives_the_same_runtimes_as_before_in_the_same_order() -> None:
    table = registry.load(platform=WIN_X64)

    assert list(table.runtimes) == WINDOWS_RUNTIME_IDS


def test_a_windows_machine_loads_only_windows_runtimes_and_a_mac_only_mac_ones() -> None:
    both = registry.load(platform=None)  # this PC is Windows: same as asking for win-x64
    mac = registry.load(platform=MACOS_ARM64)

    assert {r.platform for r in both.runtimes.values()} == {WIN_X64}
    assert {r.platform for r in mac.runtimes.values()} == {MACOS_ARM64}
    assert set(mac.models) == set(both.models)


def test_an_unsupported_machine_sees_every_runtime(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("sys.platform", "linux")

    table = registry.load()

    assert {r.platform for r in table.runtimes.values()} == {WIN_X64, MACOS_ARM64}


def test_the_mac_downloads_are_pinned_to_what_was_read_from_the_published_archives() -> None:
    mac = registry.load(platform=MACOS_ARM64)
    llama = mac.runtimes["llama.cpp-b12068-macos-metal"]
    crisp = mac.runtimes["crispasr-v0.8.49-macos-metal"]

    assert llama.url.endswith("/b12068/llama-b12068-bin-macos-arm64.tar.gz")
    assert llama.size_bytes == 16_548_390
    assert llama.sha256 == "0b12600a3f04acc4d74e876cbe4ca70be8fe04093bb19d825828bb4f49048936"
    assert llama.executable == "llama-b12068/llama-server"
    assert crisp.url.endswith("/v0.8.49/crispasr-macos-arm64.tar.gz")
    assert crisp.size_bytes == 18_165_415
    assert crisp.sha256 == "53fa0b1addeacaafd05f8b0cd10cad6e8f44cbe302be3bd07fdf7fce2eff27ec"
    assert crisp.executable == "crispasr-macos-arm64/crispasr"
    assert {llama.backend, crisp.backend} == {"metal"}


def test_the_llama_runtime_on_a_mac_is_the_same_release_as_on_windows() -> None:
    windows = registry.load(platform=WIN_X64).runtimes["llama.cpp-b12068-win-cuda12.4"]
    mac = registry.load(platform=MACOS_ARM64).runtimes["llama.cpp-b12068-macos-metal"]

    assert windows.version == mac.version


def test_the_whisper_runtime_on_a_mac_is_built_on_the_machine_and_has_nothing_to_download() -> None:
    whisper = registry.load(platform=MACOS_ARM64).runtimes["whispercpp-b5454-macos-metal"]

    assert whisper.is_local_build
    assert whisper.build is not None
    assert whisper.build.script == "scripts/mac/build_whisper_cli.sh"
    assert (whisper.url, whisper.file, whisper.sha256, whisper.size_bytes) == ("", "", "", 0)
    assert whisper.executable == "whisper-cli"
    assert whisper.version == "b5454"


def test_a_downloaded_runtime_has_no_build() -> None:
    table = registry.load(platform=WIN_X64)

    assert all(not r.is_local_build for r in table.runtimes.values())


def test_the_shipped_registry_passes_the_schema_with_the_mac_rows_in() -> None:
    VALIDATOR.validate(RAW)


BAD_BUILDS: list[tuple[str, dict[str, Any]]] = []


def _bad(label: str, **changes: Any) -> None:
    row = mac_runtime("whispercpp-b5454-macos-metal")
    row.update(changes)
    raw = copy.deepcopy(RAW)
    raw["runtimes"] = [row]
    BAD_BUILDS.append((label, raw))


_bad("a build with a url", url="https://example.com/x.tar.gz")
_bad("a build with a sha256", sha256="0" * 64)
_bad("a build with a size", size_bytes=5)
_bad("a build with a file", file="x.tar.gz")
_bad("a build without an executable", executable=None)
_bad("a build script that climbs", build={"script": "../x.sh", "source_url": "https://a.b/c"})
_bad("a build script with a drive", build={"script": "C:/x.sh", "source_url": "https://a.b/c"})
_bad("a build with an http source", build={"script": "x.sh", "source_url": "http://a.b/c"})
_bad("a build with a stray key", build={"script": "x.sh", "source_url": "https://a.b/c", "z": 1})
_bad("a build without a script", build={"source_url": "https://a.b/c"})


@pytest.mark.parametrize(("label", "raw"), BAD_BUILDS, ids=[b[0] for b in BAD_BUILDS])
def test_a_bad_local_build_is_refused_by_the_loader_and_by_the_schema(
    label: str, raw: dict[str, Any]
) -> None:
    with pytest.raises(RegistryError):
        registry.parse(raw)
    assert not VALIDATOR.is_valid(raw), label


def test_a_download_row_that_leaves_its_url_null_is_refused() -> None:
    row = mac_runtime("llama.cpp-b12068-macos-metal")
    row["url"] = None
    raw = copy.deepcopy(RAW)
    raw["runtimes"] = [row]

    with pytest.raises(RegistryError):
        registry.parse(raw)
    assert not VALIDATOR.is_valid(raw)


def test_a_null_build_means_no_build() -> None:
    row = mac_runtime("llama.cpp-b12068-macos-metal")
    row["build"] = None
    raw = copy.deepcopy(RAW)
    raw["runtimes"] = [row]

    assert registry.parse(raw).runtimes[row["id"]].build is None


def test_a_platform_with_no_runtime_is_an_error() -> None:
    with pytest.raises(RegistryError, match="no runtime"):
        registry.for_platform(registry.load(platform=WIN_X64), MACOS_ARM64)


def test_every_runtime_a_mac_runtime_needs_is_a_mac_runtime() -> None:
    mac = registry.load(platform=MACOS_ARM64)

    assert all(
        mac.runtimes[n].platform == MACOS_ARM64 for r in mac.runtimes.values() for n in r.needs
    )


@pytest.mark.parametrize(
    ("system", "machine", "expected"),
    [
        ("win32", "AMD64", WIN_X64),
        ("win32", "ARM64", WIN_X64),
        ("darwin", "arm64", MACOS_ARM64),
        ("darwin", "ARM64", MACOS_ARM64),
    ],
)
def test_the_supported_machines(system: str, machine: str, expected: str) -> None:
    assert detect_platform(system, machine) == expected


@pytest.mark.parametrize(
    ("system", "machine", "named"),
    [("darwin", "x86_64", "macOS x86_64"), ("linux", "x86_64", "Linux x86_64")],
)
def test_an_intel_mac_and_linux_get_one_plain_sentence(
    system: str, machine: str, named: str
) -> None:
    with pytest.raises(UnsupportedPlatform) as caught:
        detect_platform(system, machine)

    text = str(caught.value)
    assert named in text
    assert "Intel" in text and "Apple" in text
    assert "\n" not in text
    assert text.count("。") == 1


def test_the_check_returns_none_on_a_supported_machine_and_the_sentence_otherwise(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert platforms.check_platform() is None
    monkeypatch.setattr("sys.platform", "linux")
    monkeypatch.setattr("platform.machine", lambda: "x86_64")

    assert platforms.check_platform() == platforms.UNSUPPORTED_MESSAGE.format(
        system="Linux", machine="x86_64"
    )


def test_the_command_line_stops_with_the_sentence_and_no_stack_trace(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Any
) -> None:
    from backend import cli

    monkeypatch.setattr("sys.platform", "darwin")
    monkeypatch.setattr("platform.machine", lambda: "x86_64")
    video = tmp_path / "talk.mp4"
    video.write_bytes(b"x")

    code = cli.main([str(video)])

    err = capsys.readouterr().err
    assert code == cli.EXIT_USAGE
    assert err.startswith("error: 這個程式只支援")
    assert "Traceback" not in err
    assert err.count("\n") == 1


def test_the_service_stops_with_the_sentence_and_never_starts_on_an_unsupported_machine(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Any
) -> None:
    from backend import main as service

    started: list[object] = []

    def serve(user_data: Path, projects: Path | None, origins: Sequence[str]) -> None:
        started.append(1)

    monkeypatch.setattr(service, "serve", serve)
    monkeypatch.setattr("sys.platform", "darwin")
    monkeypatch.setattr("platform.machine", lambda: "x86_64")

    code = service.main(["--user-data", str(tmp_path)])

    err = capsys.readouterr().err
    assert code == 2
    assert started == []
    assert err.startswith("error: 這個程式只支援")
    assert "Traceback" not in err
    assert err.count("\n") == 1
