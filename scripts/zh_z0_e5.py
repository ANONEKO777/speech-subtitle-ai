"""Z0 E5: the operator's long-form Taiwanese video, with burned-in subtitles as a reference.

Nothing derived from the video is kept outside `.work/zh-z0/e5/` (git ignores it), and the video is
not copied. The path is read from `.work/zh-z0/talk-path.txt`.

    uv run python scripts/zh_z0_e5.py timeline --start 300 --dur 600
    uv run python scripts/zh_z0_e5.py strips        # one cropped frame per detected subtitle
    uv run python scripts/zh_z0_e5.py ocr           # Windows OCR (zh-Hant-TW) over the strips
    uv run python scripts/zh_z0_e5.py sheets        # contact sheets for reading by eye
    uv run python scripts/zh_z0_e5.py audio         # the same minutes as a 16 kHz wav

`timeline` finds when a burned-in line is on screen: the frames of the strip at the bottom of the
picture are read at 10 per second, the near-white pixels are counted, and a line starts where the
count passes a threshold or the pixel pattern changes while it stays on. The result is a list of
(start, end) of each line. The text of each line is read afterwards, by OCR and by eye.
"""

from __future__ import annotations

import argparse
import importlib
import subprocess
import sys
from pathlib import Path
from typing import Any, cast

from zh_z0_text import WORK, read_json, write_json

E5 = WORK / "e5"
FPS = 10
CROP_X, CROP_Y, CROP_W, CROP_H = 360, 950, 1200, 110
BRIGHT = 200
ON_PIXELS = 400
CHANGE_FRACTION = 0.25
MIN_LINE_S = 0.3


def video() -> str:
    text = (WORK / "talk-path.txt").read_text(encoding="utf-8-sig").strip().strip('"')
    if not Path(text).is_file():
        raise SystemExit(f"talk-path.txt names a missing file: {text}")
    return text


def timeline(start: float, dur: float) -> None:
    np = cast("Any", importlib.import_module("numpy"))
    command = [
        "ffmpeg", "-v", "error", "-ss", str(start), "-t", str(dur), "-i", video(),
        "-vf", f"fps={FPS},crop={CROP_W}:{CROP_H}:{CROP_X}:{CROP_Y},format=gray",
        "-f", "rawvideo", "-",
    ]  # fmt: skip
    proc = subprocess.Popen(command, stdout=subprocess.PIPE)  # noqa: S603
    assert proc.stdout is not None
    size = CROP_W * CROP_H
    previous: Any = None
    lines: list[list[float]] = []
    current: list[float] | None = None
    counts: list[int] = []
    index = 0
    while True:
        raw = proc.stdout.read(size)
        if len(raw) < size:
            break
        mask = np.frombuffer(raw, dtype=np.uint8) > BRIGHT
        count = int(mask.sum())
        counts.append(count)
        time = start + index / FPS
        on = count >= ON_PIXELS
        changed = (
            previous is not None
            and on
            and int((mask ^ previous).sum()) > CHANGE_FRACTION * max(count, int(previous.sum()))
        )
        if current is not None and (not on or changed):
            current[1] = time
            lines.append(current)
            current = None
        if on and current is None:
            current = [time, time]
        previous = mask
        index += 1
    proc.wait()
    if current is not None:
        current[1] = start + index / FPS
        lines.append(current)
    kept = [
        {"id": i, "start": round(a, 2), "end": round(b, 2)}
        for i, (a, b) in enumerate(x for x in lines if x[1] - x[0] >= MIN_LINE_S)
    ]
    write_json(E5 / "timeline.json", {"start": start, "dur": dur, "fps": FPS, "lines": kept})
    on_total = sum(float(k["end"]) - float(k["start"]) for k in kept)  # type: ignore[arg-type]
    print(f"{len(kept)} lines, {on_total:.0f} s of {dur:.0f} s with a subtitle on screen")


def strips() -> None:
    data = cast("dict[str, Any]", read_json(E5 / "timeline.json"))
    folder = E5 / "strips"
    folder.mkdir(parents=True, exist_ok=True)
    for line in cast("list[dict[str, Any]]", data["lines"]):
        mid = (float(line["start"]) + float(line["end"])) / 2
        target = folder / f"{int(line['id']):04d}.png"
        if target.exists():
            continue
        subprocess.run(  # noqa: S603
            ["ffmpeg", "-v", "error", "-y", "-ss", f"{mid:.2f}", "-i", video(), "-frames:v", "1",
             "-vf", f"crop={CROP_W}:{CROP_H}:{CROP_X}:{CROP_Y}", str(target)],
            check=True,
        )  # fmt: skip
    print(f"strips in {folder}")


def ocr() -> None:
    script = Path(__file__).with_name("zh_z0_ocr.ps1")
    out = E5 / "ocr.jsonl"
    subprocess.run(  # noqa: S603
        ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(script),
         "-Folder", str(E5 / "strips"), "-Out", str(out)],
        check=True,
    )  # fmt: skip
    print(f"wrote {out}")


def sheets(per_sheet: int) -> None:
    data = cast("dict[str, Any]", read_json(E5 / "timeline.json"))
    ids = [int(x["id"]) for x in cast("list[dict[str, Any]]", data["lines"])]
    folder = E5 / "sheets"
    folder.mkdir(parents=True, exist_ok=True)
    for first in range(0, len(ids), per_sheet):
        part = ids[first : first + per_sheet]
        command = ["ffmpeg", "-v", "error", "-y"]
        for i in part:
            command += ["-i", str(E5 / "strips" / f"{i:04d}.png")]
        stack = "".join(f"[{k}:v]" for k in range(len(part)))
        command += [
            "-filter_complex", f"{stack}vstack=inputs={len(part)}",
            str(folder / f"sheet-{part[0]:04d}.png"),
        ]  # fmt: skip
        subprocess.run(command, check=True)  # noqa: S603
    print(f"sheets in {folder}")


def audio() -> None:
    data = cast("dict[str, Any]", read_json(E5 / "timeline.json"))
    target = E5 / "window.wav"
    subprocess.run(  # noqa: S603
        ["ffmpeg", "-v", "error", "-y", "-ss", str(data["start"]), "-t", str(data["dur"]),
         "-i", video(), "-vn", "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le", str(target)],
        check=True,
    )  # fmt: skip
    print(f"wrote {target}")


def main() -> int:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="cmd", required=True)
    t = sub.add_parser("timeline")
    t.add_argument("--start", type=float, default=300.0)
    t.add_argument("--dur", type=float, default=600.0)
    sub.add_parser("strips")
    sub.add_parser("ocr")
    s = sub.add_parser("sheets")
    s.add_argument("--per-sheet", type=int, default=10)
    sub.add_parser("audio")
    args = parser.parse_args()
    if args.cmd == "timeline":
        timeline(args.start, args.dur)
    elif args.cmd == "strips":
        strips()
    elif args.cmd == "ocr":
        ocr()
    elif args.cmd == "sheets":
        sheets(args.per_sheet)
    else:
        audio()
    return 0


if __name__ == "__main__":
    sys.exit(main())
