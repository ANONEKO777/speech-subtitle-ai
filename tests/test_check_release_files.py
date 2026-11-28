"""scripts/check_release_files.py on folders shaped like installer/build/release."""

from __future__ import annotations

import base64
import hashlib
import json
from pathlib import Path

import pytest

from scripts.check_release_files import TAURI_CONF, main, problems

INSTALLER = "Video-Subtitle-Translator_1.2.3_x64-setup.exe"
URL = f"https://github.com/o/r/releases/download/v1.2.3/{INSTALLER}"

# A throwaway key made with `tauri signer generate` (id 092CB20C52193D1B), and its `tauri signer
# sign` signature of CONTENT. The private half was never kept anywhere a test can reach.
CONTENT = b"hello\n"
THROWAWAY_KEY = (
    "dW50cnVzdGVkIGNvbW1lbnQ6IG1pbmlzaWduIHB1YmxpYyBrZXk6IDA5MkNCMjBDNTIxOTNEMUIKUldRYlBSbFNETEl"
    "zQ2Vrd0JNYjFNR28xS2ZzMldaVURDeDAzNUxmeitZQ1VvWnFheDNSaStMN3MK"
)
SIGNATURE = (
    "dW50cnVzdGVkIGNvbW1lbnQ6IHNpZ25hdHVyZSBmcm9tIHRhdXJpIHNlY3JldCBrZXkKUlVRYlBSbFNETElzQ2JGMlZ0"
    "clV6eW93NlRHeUo5RXJFQnV1UnVrZFJPRnFjTnBiWEV1Wm44eGxPTm1JVFVpRWVjcERGRUNvMzJWZStKT3h5d0Fsamw0"
    "RFc0dndyRW1sUndBPQp0cnVzdGVkIGNvbW1lbnQ6IHRpbWVzdGFtcDoxNzk1ODEyOTA5CWZpbGU6c21hbGwuYmluClpN"
    "VDJNanhDZnZhZW0wMnN1ZWl2UGJxTVkycGlZZ1hpZVc1TCtuTjFJeXU2NG5JdGlDRElNaWN0OEZ1WDV6QU16a2VOcmVq"
    "WWt0NkltZjgrZXFuYURBPT0K"
)


def _write_sums(folder: Path) -> None:
    lines = [
        f"{hashlib.sha256(p.read_bytes()).hexdigest()}  {p.name}"
        for p in sorted(folder.iterdir())
        if p.name != "SHA256SUMS.txt"
    ]
    (folder / "SHA256SUMS.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")


def _sign(folder: Path, signature: str) -> None:
    (folder / f"{INSTALLER}.sig").write_text(signature, encoding="utf-8")
    latest = {
        "version": "1.2.3",
        "notes": "",
        "platforms": {"windows-x86_64": {"signature": signature, "url": URL}},
    }
    (folder / "latest.json").write_text(json.dumps(latest), encoding="utf-8")
    _write_sums(folder)


def _damaged(line: int, flip: int) -> str:
    """SIGNATURE with one bit changed in the decoded byte `flip` of its line `line`."""
    lines = base64.b64decode(SIGNATURE).decode().splitlines()
    raw = bytearray(base64.b64decode(lines[line]))
    raw[flip] ^= 1
    lines[line] = base64.b64encode(raw).decode()
    return base64.b64encode(("\n".join(lines) + "\n").encode()).decode()


@pytest.fixture
def signed(tmp_path: Path) -> Path:
    (tmp_path / INSTALLER).write_bytes(CONTENT)
    _sign(tmp_path, SIGNATURE)
    return tmp_path


def test_a_folder_signed_with_the_trusted_key_passes(signed: Path) -> None:
    assert problems(signed, "1.2.3", trusted_key=THROWAWAY_KEY) == []


def test_a_signature_from_another_key_names_both_keys(signed: Path) -> None:
    app_key = json.loads(TAURI_CONF.read_text(encoding="utf-8"))["plugins"]["updater"]["pubkey"]
    assert problems(signed, "1.2.3", trusted_key=app_key) == [
        f"{INSTALLER}.sig was made with key 092CB20C52193D1B, but tauri.conf.json trusts key"
        " 501D2BFE8D7BD4B3: every installed copy would refuse this update"
    ]


def test_the_command_checks_against_the_key_in_tauri_conf(
    signed: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main([str(signed), "1.2.3"]) == 1
    assert "tauri.conf.json trusts key 501D2BFE8D7BD4B3" in capsys.readouterr().err


@pytest.mark.parametrize(
    ("line", "flip"),
    [(1, 20), (1, 73), (3, 0)],
    ids=["signature", "signature-last-byte", "global-signature"],
)
def test_a_damaged_signature_fails(signed: Path, line: int, flip: int) -> None:
    _sign(signed, _damaged(line, flip))
    assert problems(signed, "1.2.3", trusted_key=THROWAWAY_KEY) == [
        f"{INSTALLER}.sig does not verify against key 092CB20C52193D1B:"
        " the signature or file is damaged"
    ]


def test_an_installer_changed_after_signing_fails(signed: Path) -> None:
    (signed / INSTALLER).write_bytes(b"hellp\n")
    _write_sums(signed)
    assert problems(signed, "1.2.3", trusted_key=THROWAWAY_KEY) == [
        f"{INSTALLER}.sig does not verify against key 092CB20C52193D1B:"
        " the signature or file is damaged"
    ]


def test_a_sig_that_is_not_minisign_fails(signed: Path) -> None:
    _sign(signed, "c2lnbmF0dXJl")
    assert problems(signed, "1.2.3", trusted_key=THROWAWAY_KEY) == [
        f"{INSTALLER}.sig is not a minisign signature"
    ]


def test_an_unsigned_folder_passes_without_sig_and_latest_json(signed: Path) -> None:
    (signed / f"{INSTALLER}.sig").unlink()
    (signed / "latest.json").unlink()
    _write_sums(signed)
    assert problems(signed, "1.2.3", trusted_key=None) == []
    assert problems(signed, "1.2.3", trusted_key=THROWAWAY_KEY) != []


def test_a_changed_file_fails_its_checksum(signed: Path) -> None:
    (signed / "latest.json").write_text("{}", encoding="utf-8")
    assert "latest.json: its SHA-256 is not the one in SHA256SUMS.txt" in problems(
        signed, "1.2.3", trusted_key=THROWAWAY_KEY
    )


def test_latest_json_must_match_the_version_and_signature(signed: Path) -> None:
    latest = signed / "latest.json"
    data = json.loads(latest.read_text("utf-8"))
    data["platforms"]["windows-x86_64"]["signature"] = _damaged(1, 20)
    latest.write_text(json.dumps(data), encoding="utf-8")
    _write_sums(signed)
    assert problems(signed, "1.2.3", trusted_key=THROWAWAY_KEY) == [
        f"latest.json holds a signature other than {INSTALLER}.sig"
    ]
    latest.write_text(latest.read_text("utf-8").replace('"1.2.3"', '"1.2.4"'), encoding="utf-8")
    _write_sums(signed)
    assert "latest.json names version '1.2.4', not 1.2.3" in problems(
        signed, "1.2.3", trusted_key=THROWAWAY_KEY
    )


def test_an_installer_name_with_spaces_is_refused(signed: Path) -> None:
    (signed / f"{INSTALLER}.sig").unlink()
    (signed / "latest.json").unlink()
    (signed / INSTALLER).rename(signed / INSTALLER.replace("-", " ", 2))
    _write_sums(signed)
    assert any("spaces" in p for p in problems(signed, "1.2.3", trusted_key=None))


def test_latest_json_with_a_byte_order_mark_is_a_problem_line(signed: Path) -> None:
    latest = signed / "latest.json"
    latest.write_bytes(b"\xef\xbb\xbf" + latest.read_bytes())
    _write_sums(signed)
    found = problems(signed, "1.2.3", trusted_key=THROWAWAY_KEY)
    assert len(found) == 1
    assert found[0].startswith("latest.json is not JSON the updater can read: Unexpected UTF-8 BOM")
