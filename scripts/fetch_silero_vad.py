import hashlib
import os
import urllib.request
from pathlib import Path

VERSION = "v6.2.3"
SOURCE_URL = (
    f"https://github.com/snakers4/silero-vad/raw/{VERSION}/src/silero_vad/data/silero_vad.onnx"
)
SHA256 = "1a153a22f4509e292a94e67d6f9b85e8deb25b4988682b7e174c65279d8788e3"
SIZE_BYTES = 2_327_524
LICENSE = "MIT (https://github.com/snakers4/silero-vad/blob/master/LICENSE)"

ROOT = Path(__file__).resolve().parent.parent
OUTPUT = ROOT / "models" / "silero-vad" / "silero_vad.onnx"


def sha256_of(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    if OUTPUT.is_file() and sha256_of(OUTPUT) == SHA256:
        print(f"{OUTPUT} is up to date ({VERSION})")
        return
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    partial = OUTPUT.with_name(OUTPUT.name + ".partial")
    try:
        with urllib.request.urlopen(SOURCE_URL, timeout=60) as response:
            partial.write_bytes(response.read())
        actual = sha256_of(partial)
        if actual != SHA256:
            raise SystemExit(f"checksum mismatch: expected {SHA256}, got {actual}")
        os.replace(partial, OUTPUT)
    finally:
        partial.unlink(missing_ok=True)
    print(f"downloaded {OUTPUT} ({VERSION}, {SIZE_BYTES} bytes, license {LICENSE})")


if __name__ == "__main__":
    main()
