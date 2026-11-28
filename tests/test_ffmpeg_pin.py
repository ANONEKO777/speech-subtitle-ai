"""The FFmpeg pin (installer/ffmpeg.json), the notices that name it, and the license check build.ps1
runs on the build's configure line."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PIN = json.loads((ROOT / "installer" / "ffmpeg.json").read_text(encoding="utf-8"))

_spec = importlib.util.spec_from_file_location(
    "fetch_ffmpeg_licenses", ROOT / "installer" / "fetch_ffmpeg_licenses.py"
)
assert _spec and _spec.loader
licenses = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(licenses)


def test_notices_name_the_pinned_build() -> None:
    third_party = (ROOT / "installer" / "THIRD_PARTY.md").read_text(encoding="utf-8")
    for value in (PIN["tag"], PIN["file"], PIN["sha256"], PIN["source_commit"]):
        assert value in third_party, f"installer/THIRD_PARTY.md does not mention {value}"
    app_notice = (ROOT / "app" / "src" / "settings" / "LicensesSection.tsx").read_text("utf-8")
    assert PIN["source_commit"] in app_notice, "the app's FFmpeg source link is not the pin"
    assert f"-g{PIN['source_commit'][:10]}-" in PIN["file"]


def test_the_mirror_release_is_not_named_like_an_app_release() -> None:
    assert not PIN["mirror_release"].startswith("v")


def _configure_line(*extra: str) -> str:
    listed = {flag for entry in licenses.LIBRARIES for flag in entry[1].replace(",", " ").split()}
    enabled = sorted(f for f in listed | licenses.NOT_LIBRARIES if f.startswith("--enable-"))
    return " ".join(["--prefix=/ffbuild/prefix", "--disable-libx264", *enabled, *extra])


def test_a_build_whose_libraries_all_have_licenses_passes() -> None:
    assert licenses.unlicensed(_configure_line()) == []


def test_a_library_without_a_license_entry_is_reported() -> None:
    assert licenses.unlicensed(_configure_line("--enable-libnew")) == ["--enable-libnew"]


def test_a_bot_check_page_is_not_a_license() -> None:
    page = "<!doctype html><html><head><title>Making sure you're not a bot!</title>" + "x" * 200
    assert not licenses.looks_like_license(page)
    assert not licenses.looks_like_license("!! HTTP Error 404")
    assert licenses.looks_like_license("Permission is hereby granted, free of charge, " * 5)
