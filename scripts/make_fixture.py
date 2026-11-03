import hashlib
import shutil
import subprocess
import sys
import urllib.request
from pathlib import Path

SOURCE_URL = (
    "https://archive.org/download/gettysburg_address_librivox/gettysburg_address_lincoln.mp3"
)
SOURCE_SHA256 = "33e3cd5ac877db1cb08d1f4e2d75d120d7d1760a14da8c2c79435dc3383bd9b8"
START_SECONDS = 5
DURATION_SECONDS = 15

ROOT = Path(__file__).resolve().parent.parent
CACHE_DIR = ROOT / ".cache"
OUTPUT = ROOT / "tests" / "fixtures" / "en_15s.wav"


def sha256_of(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def fetch_source() -> Path:
    CACHE_DIR.mkdir(exist_ok=True)
    source = CACHE_DIR / "gettysburg_address_lincoln.mp3"
    if not source.exists() or sha256_of(source) != SOURCE_SHA256:
        with urllib.request.urlopen(SOURCE_URL, timeout=60) as response:
            source.write_bytes(response.read())
    actual = sha256_of(source)
    if actual != SOURCE_SHA256:
        raise SystemExit(f"source checksum mismatch: expected {SOURCE_SHA256}, got {actual}")
    return source


def cut(source: Path, output: Path) -> None:
    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg is None:
        raise SystemExit("ffmpeg not found on PATH")
    output.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [
            ffmpeg,
            "-y",
            "-v",
            "error",
            "-ss",
            str(START_SECONDS),
            "-t",
            str(DURATION_SECONDS),
            "-i",
            str(source),
            "-map_metadata",
            "-1",
            "-fflags",
            "+bitexact",
            "-flags:a",
            "+bitexact",
            "-ar",
            "16000",
            "-ac",
            "1",
            "-c:a",
            "pcm_s16le",
            str(output),
        ],
        check=True,
    )


def main() -> int:
    cut(fetch_source(), OUTPUT)
    print(f"{OUTPUT} sha256={sha256_of(OUTPUT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
