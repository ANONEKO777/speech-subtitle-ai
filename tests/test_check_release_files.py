"""scripts/check_release_files.py on folders shaped like installer/build/release."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from scripts.check_release_files import problems

INSTALLER = "Video-Subtitle-Translator_1.2.3_x64-setup.exe"
URL = f"https://github.com/o/r/releases/download/v1.2.3/{INSTALLER}"


def _write_sums(folder: Path) -> None:
    lines = [
        f"{hashlib.sha256(p.read_bytes()).hexdigest()}  {p.name}"
        for p in sorted(folder.iterdir())
        if p.name != "SHA256SUMS.txt"
    ]
    (folder / "SHA256SUMS.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")


@pytest.fixture
def signed(tmp_path: Path) -> Path:
    (tmp_path / INSTALLER).write_bytes(b"MZ installer")
    (tmp_path / f"{INSTALLER}.sig").write_text("c2lnbmF0dXJl", encoding="utf-8")
    latest = {
        "version": "1.2.3",
        "notes": "",
        "platforms": {"windows-x86_64": {"signature": "c2lnbmF0dXJl", "url": URL}},
    }
    (tmp_path / "latest.json").write_text(json.dumps(latest), encoding="utf-8")
    _write_sums(tmp_path)
    return tmp_path


def test_a_complete_signed_folder_passes(signed: Path) -> None:
    assert problems(signed, "1.2.3", signed=True) == []


def test_an_unsigned_folder_passes_without_sig_and_latest_json(signed: Path) -> None:
    (signed / f"{INSTALLER}.sig").unlink()
    (signed / "latest.json").unlink()
    _write_sums(signed)
    assert problems(signed, "1.2.3", signed=False) == []
    assert problems(signed, "1.2.3", signed=True) != []


def test_a_changed_file_fails_its_checksum(signed: Path) -> None:
    (signed / INSTALLER).write_bytes(b"MZ other")
    assert problems(signed, "1.2.3", signed=True) == [
        f"{INSTALLER}: its SHA-256 is not the one in SHA256SUMS.txt"
    ]


def test_latest_json_must_match_the_version_and_signature(signed: Path) -> None:
    (signed / f"{INSTALLER}.sig").write_text("b3RoZXI=", encoding="utf-8")
    _write_sums(signed)
    assert problems(signed, "1.2.3", signed=True) == [
        f"latest.json holds a signature other than {INSTALLER}.sig"
    ]
    latest = signed / "latest.json"
    latest.write_text(latest.read_text("utf-8").replace('"1.2.3"', '"1.2.4"'), encoding="utf-8")
    _write_sums(signed)
    assert "latest.json names version '1.2.4', not 1.2.3" in problems(signed, "1.2.3", signed=True)


def test_an_installer_name_with_spaces_is_refused(signed: Path) -> None:
    (signed / INSTALLER).rename(signed / INSTALLER.replace("-", " ", 2))
    _write_sums(signed)
    assert any("spaces" in p for p in problems(signed, "1.2.3", signed=False))


def test_latest_json_with_a_byte_order_mark_is_refused(signed: Path) -> None:
    latest = signed / "latest.json"
    latest.write_bytes(b"\xef\xbb\xbf" + latest.read_bytes())
    _write_sums(signed)
    with pytest.raises(json.JSONDecodeError):
        problems(signed, "1.2.3", signed=True)
