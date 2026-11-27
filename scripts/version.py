"""The app's version: one source, mirrored where each tool insists on its own copy.

The source is `version` in app/src-tauri/tauri.conf.json. Tauri stamps it into the installer name
and the exe, and the updater compares it with latest.json, so it is the version people see. npm,
Cargo and the Python packaging each need a version field too. They mirror the source, and so do
their lock files.

    python scripts/version.py                  check that every copy agrees and print the version
    python scripts/version.py --tag v0.2.0     also check that a release tag names that version
    python scripts/version.py --set 0.2.0      write a new version into every copy

Standard library only, so a CI step can run it before anything is installed.
"""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
VERSION = re.compile(r"\d+\.\d+\.\d+")
NL = r"\r?\n"


@dataclass(frozen=True)
class Copy:
    """One place a version is written: a file and a pattern whose group 2 is the version."""

    path: str
    pattern: re.Pattern[str]

    def find(self, text: str) -> list[re.Match[str]]:
        return list(self.pattern.finditer(text))


def _copy(path: str, before: str) -> Copy:
    return Copy(path, re.compile(f'({before})([^"]+)(")', re.MULTILINE))


PACKAGE = "video-subtitle-translator"
SOURCE = _copy("app/src-tauri/tauri.conf.json", r'^  "version": "')
COPIES = (
    SOURCE,
    _copy("app/package.json", r'^  "version": "'),
    _copy("app/package-lock.json", r'^  "version": "'),
    _copy("app/package-lock.json", rf'^    "": \{{{NL} +"name": "[^"]+",{NL} +"version": "'),
    _copy("app/src-tauri/Cargo.toml", rf'^\[package\]{NL}name = "{PACKAGE}"{NL}version = "'),
    _copy("app/src-tauri/Cargo.lock", rf'^name = "{PACKAGE}"{NL}version = "'),
    _copy("pyproject.toml", rf'^\[project\]{NL}name = "{PACKAGE}"{NL}version = "'),
    _copy("uv.lock", rf'^name = "{PACKAGE}"{NL}version = "'),
)


def _read(root: Path, path: str) -> str:
    with (root / path).open(encoding="utf-8", newline="") as f:
        return f.read()


def found(root: Path) -> list[tuple[Copy, str | None]]:
    """Each copy with the version it holds, or None when its pattern does not match exactly once."""
    result: list[tuple[Copy, str | None]] = []
    for copy in COPIES:
        matches = copy.find(_read(root, copy.path))
        result.append((copy, matches[0].group(2) if len(matches) == 1 else None))
    return result


def problems(root: Path, tag: str | None = None) -> list[str]:
    copies = found(root)
    source = copies[0][1]
    out: list[str] = []
    if source is None or not VERSION.fullmatch(source):
        out.append(f"{SOURCE.path}: no X.Y.Z version found (got {source!r})")
    for copy, version in copies[1:]:
        if version is None:
            out.append(f"{copy.path}: the version field was not found exactly once")
        elif version != source:
            out.append(f"{copy.path}: {version}, but {SOURCE.path} says {source}")
    if tag is not None and tag != f"v{source}":
        out.append(f"tag {tag} does not name the version {source}; tag it v{source}")
    return out


def set_version(root: Path, version: str) -> None:
    if not VERSION.fullmatch(version):
        raise ValueError(f"{version!r} is not X.Y.Z")
    missing = [copy.path for copy, held in found(root) if held is None]
    if missing:
        raise ValueError(f"the version field was not found exactly once in {', '.join(missing)}")
    for copy in COPIES:
        text = _read(root, copy.path)
        text = copy.pattern.sub(lambda m: m.group(1) + version + m.group(3), text)
        with (root / copy.path).open("w", encoding="utf-8", newline="") as f:
            f.write(text)


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="Check or set the app version.")
    parser.add_argument("--tag", help="a release tag that must be v<version>")
    parser.add_argument("--set", dest="new", metavar="X.Y.Z", help="write this version everywhere")
    args = parser.parse_args(argv)
    if args.new:
        set_version(ROOT, args.new)
    errors = problems(ROOT, args.tag)
    for line in errors:
        print(line, file=sys.stderr)
    if errors:
        return 1
    print(found(ROOT)[0][1])
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
