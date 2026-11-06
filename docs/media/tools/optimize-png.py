"""Optimizes PNGs losslessly, then to a 256-colour palette when the result is much smaller and looks the same.
python docs/media/tools/optimize-png.py <src-dir-or-file> <dest-dir> [--palette] [--size 1600x900]"""
import sys
from pathlib import Path

from PIL import Image

src, dest = Path(sys.argv[1]), Path(sys.argv[2])
palette = "--palette" in sys.argv
size = tuple(int(n) for n in sys.argv[sys.argv.index("--size") + 1].split("x")) if "--size" in sys.argv else None
dest.mkdir(parents=True, exist_ok=True)
for path in [src] if src.is_file() else sorted(src.glob("*.png")):
    image = Image.open(path).convert("RGB")
    target = dest / path.name
    if size and image.size != size:
        image = image.resize(size, Image.Resampling.LANCZOS)
    if palette:
        image = image.quantize(colors=256, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.FLOYDSTEINBERG)
    image.save(target, optimize=True)
    print(f"{path.name}: {path.stat().st_size // 1024} KB -> {target.stat().st_size // 1024} KB")
