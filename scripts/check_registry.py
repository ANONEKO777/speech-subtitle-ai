from __future__ import annotations

import argparse
import hashlib
import importlib
import json
import sys
from pathlib import Path
from typing import Any

MANAGER_DIR = Path(__file__).resolve().parent.parent / "backend" / "manager"
CHUNK = 1024 * 1024


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while block := handle.read(CHUNK):
            digest.update(block)
    return digest.hexdigest()


def find_file(root: Path, name: str) -> Path | None:
    for base in (root / "models", root / "runtimes" / "_archives"):
        found = next(base.rglob(name), None) if base.is_dir() else None
        if found:
            return found
    return None


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate registry.json against its JSON schema and the downloaded files."
    )
    parser.add_argument(
        "--root", type=Path, required=True, help="checkout holding models/ and runtimes/"
    )
    parser.add_argument("--registry", type=Path, default=MANAGER_DIR / "registry.json")
    parser.add_argument("--schema", type=Path, default=MANAGER_DIR / "registry.schema.json")
    args = parser.parse_args()

    jsonschema: Any = importlib.import_module("jsonschema")
    registry: dict[str, Any] = json.loads(args.registry.read_text(encoding="utf-8"))
    schema: dict[str, Any] = json.loads(args.schema.read_text(encoding="utf-8"))
    errors: list[Any] = sorted(
        jsonschema.Draft202012Validator(schema).iter_errors(registry),
        key=lambda error: list(error.path),
    )
    for error in errors:
        print(f"SCHEMA  {'/'.join(map(str, error.path))}: {error.message}")
    print(f"schema: {'ok' if not errors else f'{len(errors)} error(s)'}")

    failures = len(errors)
    entries: list[dict[str, Any]] = [*registry["models"], *registry["runtimes"]]
    for entry in entries:
        path = find_file(args.root, entry["file"])
        if path is None:
            print(f"MISSING {entry['id']}: {entry['file']} not under {args.root}")
            failures += 1
            continue
        actual, size = sha256_of(path), path.stat().st_size
        match = actual == entry["sha256"] and size == entry["size_bytes"]
        failures += not match
        print(
            f"{'ok     ' if match else 'MISMATCH'} {entry['id']}: {path.name} "
            f"sha256 {actual} size {size} "
            f"license {entry.get('license')} version {entry.get('version')}"
        )
    print(f"{len(entries)} entries, {failures} failure(s)")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
