"""Checks the folder installer/build.ps1 fills with the files to upload, before they are uploaded.

    python scripts/check_release_files.py <folder> <version> [--unsigned]

Every file is listed in SHA256SUMS.txt with its hash. There is one installer for the version, with
no space in its name. A signed build also has the installer's .sig and a latest.json that names the
version, the installer and that signature; an unsigned build has neither. Prints the installer's
name. Standard library only.
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

SUMS = "SHA256SUMS.txt"


def problems(folder: Path, version: str, *, signed: bool) -> list[str]:
    out: list[str] = []
    files = sorted(p.name for p in folder.iterdir() if p.is_file())
    listed: dict[str, str] = {}
    if SUMS in files:
        for line in (folder / SUMS).read_text(encoding="utf-8").splitlines():
            digest, _, name = line.partition("  ")
            listed[name] = digest
    else:
        out.append(f"{SUMS} is missing")
    for name in files:
        if name == SUMS:
            continue
        digest = hashlib.sha256((folder / name).read_bytes()).hexdigest()
        if listed.get(name) != digest:
            out.append(f"{name}: its SHA-256 is not the one in {SUMS}")
    out += [f"{SUMS} lists {name}, which is not here" for name in listed.keys() - set(files)]

    installers = [n for n in files if n.endswith(f"_{version}_x64-setup.exe")]
    if len(installers) != 1:
        return [*out, f"expected one installer for {version}, found {installers}"]
    installer = installers[0]
    if " " in installer:
        out.append(f"{installer}: GitHub would rename a file with spaces")

    signature = folder / f"{installer}.sig"
    latest = folder / "latest.json"
    if not signed:
        out += [f"{p.name} is in an unsigned build" for p in (signature, latest) if p.exists()]
        return out
    if not signature.exists() or not latest.exists():
        return [*out, f"a signed build needs {signature.name} and latest.json"]
    data = json.loads(latest.read_text(encoding="utf-8"))
    windows = data.get("platforms", {}).get("windows-x86_64", {})
    if data.get("version") != version:
        out.append(f"latest.json names version {data.get('version')!r}, not {version}")
    if not str(windows.get("url", "")).endswith(f"/{installer}"):
        out.append(f"latest.json points at {windows.get('url')!r}, not at {installer}")
    if windows.get("signature") != signature.read_text(encoding="utf-8").strip():
        out.append(f"latest.json holds a signature other than {signature.name}")
    return out


def main(argv: list[str]) -> int:
    folder, version, *flags = argv
    errors = problems(Path(folder), version, signed="--unsigned" not in flags)
    for line in errors:
        print(line, file=sys.stderr)
    if errors:
        return 1
    print(next(p.name for p in Path(folder).glob(f"*_{version}_x64-setup.exe")))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
