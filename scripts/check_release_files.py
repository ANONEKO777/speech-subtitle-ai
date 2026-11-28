"""Checks the folder installer/build.ps1 fills with the files to upload, before they are uploaded.

    python scripts/check_release_files.py <folder> <version> [--unsigned]

Every file is listed in SHA256SUMS.txt with its hash. There is one installer for the version, with
no space in its name. A signed build also has the installer's .sig and a latest.json that names the
version, the installer and that signature, and the .sig verifies against the updater public key in
app/src-tauri/tauri.conf.json the way the app's updater checks it; an unsigned build has neither
file. Prints the installer's name. Standard library only.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import json
import sys
from pathlib import Path

SUMS = "SHA256SUMS.txt"
TAURI_CONF = Path(__file__).resolve().parents[1] / "app" / "src-tauri" / "tauri.conf.json"

# Ed25519 verification as in RFC 8032 section 6, enough to check a minisign signature.
_P = 2**255 - 19
_L = 2**252 + 27742317777372353535851937790883648493
_D = -121665 * pow(121666, _P - 2, _P) % _P
_SQRT_M1 = pow(2, (_P - 1) // 4, _P)
_Point = tuple[int, int, int, int]


def _add(a: _Point, b: _Point) -> _Point:
    e = (a[1] + a[0]) * (b[1] + b[0]) - (a[1] - a[0]) * (b[1] - b[0])
    f = 2 * a[2] * b[2] - 2 * a[3] * b[3] * _D
    g = 2 * a[2] * b[2] + 2 * a[3] * b[3] * _D
    h = (a[1] + a[0]) * (b[1] + b[0]) + (a[1] - a[0]) * (b[1] - b[0])
    return (e * f % _P, g * h % _P, f * g % _P, e * h % _P)


def _times(n: int, a: _Point) -> _Point:
    out: _Point = (0, 1, 1, 0)
    while n:
        if n & 1:
            out = _add(out, a)
        a = _add(a, a)
        n >>= 1
    return out


def _point(y: int, sign: int) -> _Point | None:
    if y >= _P:
        return None
    x2 = (y * y - 1) * pow(_D * y * y + 1, _P - 2, _P) % _P
    x = pow(x2, (_P + 3) // 8, _P)
    if (x * x - x2) % _P:
        x = x * _SQRT_M1 % _P
    if (x * x - x2) % _P or (x == 0 and sign):
        return None
    if x & 1 != sign:
        x = _P - x
    return (x, y, 1, x * y % _P)


def _decode(raw: bytes) -> _Point | None:
    y = int.from_bytes(raw, "little")
    return _point(y & (2**255 - 1), y >> 255)


_BASE = _point(4 * pow(5, _P - 2, _P) % _P, 0)


def ed25519_verify(public: bytes, message: bytes, signature: bytes) -> bool:
    a, r = _decode(public), _decode(signature[:32])
    s = int.from_bytes(signature[32:], "little")
    if a is None or r is None or _BASE is None or s >= _L:
        return False
    k = int.from_bytes(hashlib.sha512(signature[:32] + public + message).digest(), "little")
    left, right = _times(s, _BASE), _add(r, _times(k % _L, a))
    return (left[0] * right[2] - right[0] * left[2]) % _P == 0 and (
        left[1] * right[2] - right[1] * left[2]
    ) % _P == 0


def _minisign_lines(text: str) -> list[str]:
    """The lines of a Tauri key or signature string, which is a minisign file in base64."""
    return base64.b64decode(text.strip(), validate=True).decode("utf-8").splitlines()


def key_id(raw: bytes) -> str:
    """The id minisign prints for the key bytes after the two algorithm bytes."""
    return f"{int.from_bytes(raw[2:10], 'little'):016X}"


def signature_problems(data: bytes, signature: str, pubkey: str, name: str) -> list[str]:
    """Why the app's updater would refuse `data` with this .sig, checked as minisign-verify does."""
    try:
        key = base64.b64decode(_minisign_lines(pubkey)[1], validate=True)
    except (binascii.Error, UnicodeDecodeError, IndexError):
        return ["the updater pubkey in tauri.conf.json is not a minisign public key"]
    try:
        _, sig_line, trusted, global_line = _minisign_lines(signature)[:4]
        sig = base64.b64decode(sig_line, validate=True)
        global_sig = base64.b64decode(global_line, validate=True)
    except (binascii.Error, UnicodeDecodeError, ValueError):
        return [f"{name} is not a minisign signature"]
    if len(key) != 42 or key[:2] != b"Ed":
        return ["the updater pubkey in tauri.conf.json is not an Ed25519 minisign key"]
    comment = trusted.removeprefix("trusted comment: ")
    if len(sig) != 74 or sig[:2] not in (b"Ed", b"ED") or comment == trusted:
        return [f"{name} is not a minisign signature"]
    if sig[2:10] != key[2:10]:
        return [
            f"{name} was made with key {key_id(sig)}, but tauri.conf.json trusts key {key_id(key)}:"
            " every installed copy would refuse this update"
        ]
    message = hashlib.blake2b(data).digest() if sig[:2] == b"ED" else data
    if not ed25519_verify(key[10:], message, sig[10:]) or not ed25519_verify(
        key[10:], sig[10:] + comment.encode("utf-8"), global_sig
    ):
        damaged = "the signature or file is damaged"
        return [f"{name} does not verify against key {key_id(key)}: {damaged}"]
    return []


def problems(folder: Path, version: str, *, trusted_key: str | None) -> list[str]:
    """`trusted_key` is the updater pubkey a signed build must verify against; None for unsigned."""
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
    if trusted_key is None:
        out += [f"{p.name} is in an unsigned build" for p in (signature, latest) if p.exists()]
        return out
    if not signature.exists() or not latest.exists():
        return [*out, f"a signed build needs {signature.name} and latest.json"]
    sig_text = signature.read_text(encoding="utf-8").strip()
    out += signature_problems(
        (folder / installer).read_bytes(), sig_text, trusted_key, signature.name
    )
    try:
        data = json.loads(latest.read_text(encoding="utf-8"))
    except ValueError as error:
        return [*out, f"latest.json is not JSON the updater can read: {error}"]
    windows = data.get("platforms", {}).get("windows-x86_64", {})
    if data.get("version") != version:
        out.append(f"latest.json names version {data.get('version')!r}, not {version}")
    if not str(windows.get("url", "")).endswith(f"/{installer}"):
        out.append(f"latest.json points at {windows.get('url')!r}, not at {installer}")
    if windows.get("signature") != sig_text:
        out.append(f"latest.json holds a signature other than {signature.name}")
    return out


def main(argv: list[str]) -> int:
    folder, version, *flags = argv
    trusted_key = None
    if "--unsigned" not in flags:
        trusted_key = json.loads(TAURI_CONF.read_text(encoding="utf-8"))["plugins"]["updater"][
            "pubkey"
        ]
    errors = problems(Path(folder), version, trusted_key=trusted_key)
    for line in errors:
        print(line, file=sys.stderr)
    if errors:
        return 1
    print(next(p.name for p in Path(folder).glob(f"*_{version}_x64-setup.exe")))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
