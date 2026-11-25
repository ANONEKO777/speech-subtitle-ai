"""What the desktop shell and the build on a Mac rely on, checked from here: the fonts a Mac burn
gets, the page's profile list against the backend's, the bundle config, and the build script. The
Rust side has its own unit tests in `app/src-tauri/src`."""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from dataclasses import asdict
from pathlib import Path
from typing import Any

import pytest

from backend.api import player
from backend.core import render
from backend.core.languages import get as get_language
from backend.core.model import Cue
from backend.manager import hardware
from backend.manager.profiles import ProfileId

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "app"
CONF = json.loads((APP / "src-tauri" / "tauri.conf.json").read_text(encoding="utf-8"))
MAC_OVERLAY = json.loads((ROOT / "installer" / "tauri.bundle.mac.conf.json").read_text("utf-8"))
SCRIPT = ROOT / "scripts" / "mac" / "build_app.sh"
DOC = ROOT / "docs" / "MACOS.md"


@pytest.fixture
def as_mac(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("sys.platform", "darwin")
    monkeypatch.setattr("platform.machine", lambda: "arm64")


# --- the burned subtitle names fonts of this machine ---


def test_a_burn_on_a_mac_names_pingfang_and_arial_in_the_ass_file(
    tmp_path: Path, as_mac: None
) -> None:
    cues = [Cue(1, 0, 1000, "Hello", "你好", "en")]
    body = player.StillBody(time_s=0)
    look = player._look(body, cues, get_language("zh-TW"))  # pyright: ignore[reportPrivateUsage]
    render._ass_file(tmp_path, cues, get_language("zh-TW").wrap, look, 0)  # pyright: ignore[reportPrivateUsage]

    ass = (tmp_path / "sub.ass").read_text(encoding="utf-8-sig")
    assert "Style: Zh,PingFang TC," in ass
    assert "Style: En,Arial," in ass
    assert "JhengHei" not in ass


def test_a_burn_on_windows_keeps_the_windows_fonts(tmp_path: Path) -> None:
    cues = [Cue(1, 0, 1000, "Hello", "你好", "en")]
    look = player._look(player.StillBody(time_s=0), cues, get_language("zh-TW"))  # pyright: ignore[reportPrivateUsage]
    render._ass_file(tmp_path, cues, get_language("zh-TW").wrap, look, 0)  # pyright: ignore[reportPrivateUsage]

    assert "Style: Zh,Microsoft JhengHei," in (tmp_path / "sub.ass").read_text(encoding="utf-8-sig")


# --- the page can read what the backend sends ---


def ts_profile_ids() -> list[str]:
    text = (APP / "src" / "manage" / "types.ts").read_text(encoding="utf-8")
    match = re.search(r"PROFILE_IDS: readonly ProfileId\[\] = \[(.*?)\]", text, re.S)
    assert match
    return re.findall(r'"([^"]+)"', match.group(1))


def test_the_page_knows_every_profile_id_the_backend_can_send() -> None:
    assert sorted(ts_profile_ids()) == sorted(p.value for p in ProfileId)


def test_the_page_reads_the_hardware_fields_the_backend_sends() -> None:
    sent = asdict(hardware.Hardware(None, None, None, 36864, 500000, "macos-arm64", "Apple M3 Pro"))
    parse = (APP / "src" / "manage" / "parse.ts").read_text(encoding="utf-8")
    block = parse[parse.index("function parseHardware") :]
    block = block[: block.index("\n}\n")]
    for key in sent:
        assert f'"{key}"' in block, key


# --- the bundle ---


def test_the_mac_bundle_is_signed_ad_hoc_for_apple_silicon_and_names_a_floor() -> None:
    mac: dict[str, Any] = CONF["bundle"]["macOS"]

    assert mac["signingIdentity"] == "-"
    assert mac["minimumSystemVersion"] == "13.0"
    assert {"app", "dmg"} <= set(CONF["bundle"]["targets"])


def test_the_windows_bundle_is_what_it_was() -> None:
    bundle = CONF["bundle"]

    assert "nsis" in bundle["targets"]
    assert bundle["createUpdaterArtifacts"] is True
    assert bundle["windows"]["webviewInstallMode"] == {"type": "embedBootstrapper"}
    assert bundle["windows"]["nsis"]["installMode"] == "currentUser"
    assert bundle["windows"]["nsis"]["installerHooks"] == "../../installer/hooks.nsh"
    assert CONF["plugins"]["updater"]["windows"] == {"installMode": "passive"}
    ps1 = (ROOT / "installer" / "build.ps1").read_text(encoding="utf-8")
    assert "--bundles nsis" in ps1


def test_the_mac_overlay_adds_only_the_backend_folder_and_turns_updater_files_off() -> None:
    bundle = MAC_OVERLAY["bundle"]

    assert set(MAC_OVERLAY) == {"bundle"}
    assert bundle["createUpdaterArtifacts"] is False
    assert bundle["resources"] == {"../../installer/build/backend/": "backend/"}
    assert "ffmpeg" not in json.dumps(MAC_OVERLAY)


def test_the_resource_folder_the_shell_looks_in_is_the_one_the_overlay_fills() -> None:
    sidecar = (APP / "src-tauri" / "src" / "sidecar.rs").read_text(encoding="utf-8")

    assert 'resources.join("backend")' in sidecar
    assert "backend/" in MAC_OVERLAY["bundle"]["resources"].values()


# --- the build script ---


def script_lines() -> list[str]:
    return [
        line.strip()
        for line in SCRIPT.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.strip().startswith("#")
    ]


def test_the_build_script_stops_on_errors_and_never_asks_for_root() -> None:
    lines = script_lines()

    assert "set -euo pipefail" in lines
    assert not any(re.search(r"\bsudo\b", line) for line in lines)
    assert not any(re.search(DANGEROUS_RM, line) for line in lines)


DANGEROUS_RM = r"\brm\b[^;&|]*\s[\"']?(/|~|\$\{?HOME\}?)[\"']?(\s|/?$)"


@pytest.mark.parametrize(
    "line",
    ['rm -rf "$BUILD/pyi" ~', "rm -rf $BUILD/x /", "rm -rf ~", "rm -r -f $HOME", 'rm -rf "$HOME"'],
)
def test_the_rm_check_catches_a_dangerous_target_in_any_argument(line: str) -> None:
    assert re.search(DANGEROUS_RM, line)


def test_the_rm_check_lets_the_scripts_own_folders_pass() -> None:
    assert not re.search(DANGEROUS_RM, 'rm -rf "$BUILD/pyi" "$BUILD/pyi-work" "$BUILD/backend"')


def test_a_missing_bundle_folder_stops_with_a_plain_message_before_find_runs() -> None:
    text = SCRIPT.read_text(encoding="utf-8")

    assert text.index('[ -d "$BUNDLE/macos" ] || fail') < text.index('find "$BUNDLE/macos"')
    assert text.index('[ -d "$BUNDLE/dmg" ] || fail') < text.index('find "$BUNDLE/dmg"')


def test_the_build_script_builds_both_bundles_with_the_mac_overlay_and_checks_the_signature() -> (
    None
):
    text = SCRIPT.read_text(encoding="utf-8")

    assert "--bundles app,dmg" in text
    assert "--config ../installer/tauri.bundle.mac.conf.json" in text
    assert "installer/sidecar.spec" in text
    assert "codesign --verify" in text
    assert 'BUILD="$ROOT/installer/build"' in text


def test_the_build_script_refuses_to_run_anywhere_but_an_apple_silicon_mac() -> None:
    text = SCRIPT.read_text(encoding="utf-8")

    assert '[ "$(uname -s)" = "Darwin" ]' in text
    assert '[ "$(uname -m)" = "arm64" ]' in text


def test_the_build_script_parses_in_bash() -> None:
    bash = shutil.which("bash")
    if bash is None:
        pytest.skip("no bash on this machine")
    script = SCRIPT.read_bytes().replace(b"\r\n", b"\n")
    result = subprocess.run([bash, "-n"], input=script, capture_output=True, check=False)

    assert result.returncode == 0, result.stderr.decode(errors="replace")


# --- the page the operator reads ---


def test_the_page_walks_through_a_first_build_and_the_first_launch() -> None:
    text = DOC.read_text(encoding="utf-8")

    for needle in (
        "scripts/mac/build_app.sh",
        ".dmg",
        "Open Anyway",
        "xattr",
        "Cmd",
        "Not run on a Mac",
    ):
        assert needle in text, needle
