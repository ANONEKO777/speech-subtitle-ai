"""The whisper-cli build script and the page that tells the operator how to run it.

The script cannot run here (it builds for macOS). These tests keep it tied to the registry row it
serves and refuse the things it must never do."""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

import pytest

from backend.manager import registry
from backend.manager.platforms import MACOS_ARM64
from backend.manager.profiles import ProfileId, profiles_for

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "mac" / "build_whisper_cli.sh"
DOC = ROOT / "docs" / "MACOS.md"
ROW = registry.load(platform=MACOS_ARM64).runtimes["whispercpp-b5454-macos-metal"]


def script_text() -> str:
    return SCRIPT.read_text(encoding="utf-8")


def code_lines() -> list[str]:
    return [
        line.strip()
        for line in script_text().splitlines()
        if line.strip() and not line.strip().startswith("#")
    ]


def test_the_registry_row_names_a_script_that_exists() -> None:
    assert ROW.build is not None
    assert (ROOT / ROW.build.script).is_file()
    assert ROW.build.script == "scripts/mac/build_whisper_cli.sh"


def test_the_script_builds_the_tag_and_the_folder_the_registry_row_names() -> None:
    text = script_text()

    assert f'RUNTIME_ID="{ROW.id}"' in text
    assert f'TAG="${{WHISPER_CPP_TAG:-{ROW.version}}}"' in text
    assert f'REPO_URL="{ROW.build.source_url if ROW.build else ""}"' in text
    assert ROW.executable is not None
    assert f'DEST="$DEST_DIR/{ROW.executable}"' in text


def test_the_script_stops_on_the_first_error_and_never_uses_sudo() -> None:
    assert "set -euo pipefail" in code_lines()
    assert not [line for line in code_lines() if re.search(r"\bsudo\b", line)]


def test_the_script_builds_with_metal_and_only_the_one_program() -> None:
    text = script_text()

    assert "-DGGML_METAL=ON" in text
    assert "-DGGML_METAL_EMBED_LIBRARY=ON" in text
    assert "--target whisper-cli" in text


def test_the_script_only_writes_to_a_temporary_folder_and_the_runtimes_folder() -> None:
    writes = [line for line in code_lines() if re.match(r"(cp|mv|mkdir|rm|chmod)\b", line)]

    assert all(('"$DEST' in line) or ('"$WORK' in line) or ("$WORK" in line) for line in writes)
    assert not [line for line in code_lines() if "rm -rf /" in line or "rm -rf ~" in line]


def test_the_script_refuses_a_machine_that_is_not_an_apple_silicon_mac() -> None:
    text = script_text()

    assert '"$(uname -s)" = "Darwin"' in text
    assert '"$(uname -m)" = "arm64"' in text


def test_the_script_is_valid_shell() -> None:
    bash = shutil.which("bash")
    if bash is None:
        pytest.skip("no bash on this machine")

    done = subprocess.run(
        [bash, "-n"], input=script_text(), capture_output=True, text=True, check=False
    )

    assert done.returncode == 0, done.stderr


def test_the_script_has_unix_line_endings() -> None:
    assert b"\r" not in SCRIPT.read_bytes()


def test_the_page_names_the_script_the_folders_and_every_mac_profile() -> None:
    text = DOC.read_text(encoding="utf-8")

    assert "scripts/mac/build_whisper_cli.sh" in text
    assert "~/Library/Application Support/video-subtitle-translator" in text
    for profile in profiles_for(MACOS_ARM64):
        assert f"`{profile.id.value}`" in text
    for runtime_id in registry.load(platform=MACOS_ARM64).runtimes:
        assert runtime_id in text
    assert ProfileId.METAL_32GB.value in text


def test_the_page_says_it_has_not_been_run_on_a_mac_and_lists_what_a_mac_must_prove() -> None:
    text = DOC.read_text(encoding="utf-8")

    assert "not yet run on a Mac" in text
    assert "What only a Mac can prove" in text
    assert "Intel" in text
