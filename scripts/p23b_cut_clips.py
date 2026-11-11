"""P23b lever: cut the labelling clips of a `p23b_sample.py` manifest out of the video with ffmpeg.

Each clip is one segment plus a 0.3 s lead and tail, mono, 16 kHz, small mp3. Video is read only.
Clips that exist are kept, so a rerun fills in what is missing. Use --force to cut them again.

    uv run python scripts/p23b_cut_clips.py VIDEO [--manifest M.json] [--out CLIPS_DIR]
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MANIFEST = ROOT / ".work/p23b-labels/manifest.json"
DEFAULT_FFMPEG = Path("C:/Program Files/ffmpeg-n6.1-latest-win64-gpl-shared-6.1/bin/ffmpeg.exe")
MARGIN_S = 0.3
BITRATE = "48k"


def clip_window(start_s: float, end_s: float) -> tuple[float, float]:
    """Clip start and length: the segment with MARGIN_S before and after, not before zero."""
    start = max(0.0, start_s - MARGIN_S)
    return start, end_s + MARGIN_S - start


def cut_command(ffmpeg: Path, video: Path, start_s: float, end_s: float, out: Path) -> list[str]:
    start, length = clip_window(start_s, end_s)
    return [
        str(ffmpeg), "-hide_banner", "-loglevel", "error", "-y",
        "-ss", f"{start:.3f}", "-i", str(video), "-t", f"{length:.3f}",
        "-vn", "-map", "0:a:0", "-ac", "1", "-ar", "16000",
        "-c:a", "libmp3lame", "-b:a", BITRATE, str(out),
    ]  # fmt: skip


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("video", type=Path)
    ap.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    ap.add_argument("--out", type=Path, default=DEFAULT_MANIFEST.parent / "clips")
    ap.add_argument("--ffmpeg", type=Path, default=DEFAULT_FFMPEG)
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()
    segments = json.loads(args.manifest.read_text(encoding="utf-8"))["segments"]
    args.out.mkdir(parents=True, exist_ok=True)
    cut = kept = 0
    clip_seconds = 0.0
    for seg in segments:
        target = args.out / f"{seg['id']}.mp3"
        clip_seconds += clip_window(seg["start_s"], seg["end_s"])[1]
        if target.exists() and not args.force:
            kept += 1
            continue
        cmd = cut_command(args.ffmpeg, args.video, seg["start_s"], seg["end_s"], target)
        subprocess.run(cmd, check=True)
        cut += 1
    size = sum(p.stat().st_size for p in args.out.glob("*.mp3"))
    print(f"{cut} cut, {kept} kept, {size / 1e6:.2f} MB in {args.out}")
    print(f"{clip_seconds / 60:.2f} min of clip audio planned")


if __name__ == "__main__":
    main()
