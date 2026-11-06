"""Build the seed project the verify skill copies, from a clip of a real talk.

    uv run python scripts/make_verify_seed.py [--audio talk38.wav] [--out DIR] [--user-data DIR]

It cuts a short clip from the talk's audio with ffmpeg, puts it on a plain colour background as an
mp4, and runs the real CLI on that mp4 so the project folder holds real subtitles and a summary.
The video lives inside `--out`, so the seed stays valid when other scratch folders move. It needs
the GPU free and the models installed in `--user-data`. A second run reuses every finished step.

The last line printed is the video path to import. The processed project is in
`<out>/projects/<id>`; copy that folder into the app's projects folder before the import.
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from backend.core.projects import project_id  # noqa: E402


def main_checkout() -> Path:
    """The scratch folder `.work` lives in the main checkout, not in each git worktree."""
    common = subprocess.run(
        ["git", "rev-parse", "--path-format=absolute", "--git-common-dir"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    ).stdout.strip()
    return Path(common).parent if common else ROOT


WORK = main_checkout() / ".work"
DEFAULT_AUDIO = WORK / "audio" / "talk38.wav"
DEFAULT_OUT = WORK / "verify-seed"
GPU_PROGRAMS = ("whisper-cli", "crispasr", "llama-server")
BACKGROUND = "0x1f3a5f"


def gpu_busy() -> list[str]:
    listing = subprocess.run(["tasklist"], capture_output=True, text=True, check=False).stdout
    return [name for name in GPU_PROGRAMS if name in listing.lower()]


def cut_video(audio: Path, video: Path, start_s: float, seconds: float) -> None:
    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg is None:
        raise SystemExit("ffmpeg not found on PATH")
    video.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [
            ffmpeg, "-y", "-loglevel", "error",
            "-f", "lavfi", "-i", f"color=c={BACKGROUND}:s=1280x720:r=10:d={seconds}",
            "-ss", str(start_s), "-t", str(seconds), "-i", str(audio),
            "-map", "0:v", "-map", "1:a",
            "-c:v", "libx264", "-tune", "stillimage", "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-shortest", str(video),
        ],
        check=True,
    )  # fmt: skip


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build the verify skill seed project.")
    parser.add_argument("--audio", type=Path, default=DEFAULT_AUDIO)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--user-data", type=Path, default=None)
    parser.add_argument("--start", type=float, default=300.0, help="clip start, seconds")
    parser.add_argument("--seconds", type=float, default=60.0, help="clip length")
    parser.add_argument("--lang", default="zh-TW")
    args = parser.parse_args(argv)
    if not args.audio.is_file():
        print(f"error: audio not found: {args.audio}", file=sys.stderr)
        return 2
    busy = gpu_busy()
    if busy:
        print(f"error: GPU programs are running: {', '.join(busy)}", file=sys.stderr)
        return 2
    out: Path = args.out.resolve()
    video = out / "seed-clip.mp4"
    if not video.is_file():
        cut_video(args.audio, video, args.start, args.seconds)
    folder = out / "projects" / project_id(video)
    command = [sys.executable, "-m", "backend.cli", "-o", str(folder), "--lang", args.lang]
    if args.user_data is not None:
        command += ["--user-data", str(args.user_data)]
    code = subprocess.run([*command, str(video)], cwd=ROOT, check=False).returncode
    if code != 0:
        print(f"error: the CLI exited {code}", file=sys.stderr)
        return code
    print(f"project folder: {folder}")
    print(f"import this video: {video}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
