"""Collects the license texts of the external libraries the bundled FFmpeg build is linked with.

The BtbN build's configure line (installer/build/ffmpeg-configuration.txt after a build) enables
the libraries below. Their licenses (BSD, MIT, ISC, Apache, MPL, LGPL ...) require the notice to
travel with the binaries, and BtbN's zip carries only FFmpeg's own LICENSE.txt. This script
downloads each project's license file from its upstream and writes one text,
installer/licenses/FFmpeg-external-libraries.txt, which build.ps1 copies into the ffmpeg folder.
Run it again when the pinned FFmpeg build changes, and review the diff.

    uv run python installer/fetch_ffmpeg_licenses.py
"""

from __future__ import annotations

import base64
import json
import subprocess
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

OUT = Path(__file__).parent / "licenses" / "FFmpeg-external-libraries.txt"
FFMPEG_TAG = "n8.1.3"

GH = "github"
RAW = "raw"

# (library, configure flag, license as the project states it, source, location)
LIBRARIES: list[tuple[str, str, str, str, str]] = [
    (
        "FFmpeg LGPL-3.0 text",
        "(FFmpeg itself)",
        "LGPL-3.0-or-later",
        RAW,
        f"https://raw.githubusercontent.com/FFmpeg/FFmpeg/{FFMPEG_TAG}/COPYING.LGPLv3",
    ),
    (
        "FFmpeg LGPL-2.1 text",
        "(FFmpeg itself)",
        "LGPL-2.1-or-later",
        RAW,
        f"https://raw.githubusercontent.com/FFmpeg/FFmpeg/{FFMPEG_TAG}/COPYING.LGPLv2.1",
    ),
    ("zlib", "--enable-zlib", "Zlib", GH, "madler/zlib"),
    ("libxml2", "--enable-libxml2", "MIT", GH, "GNOME/libxml2"),
    (
        "libiconv",
        "--enable-iconv",
        "LGPL-2.1-or-later",
        RAW,
        "https://git.savannah.gnu.org/cgit/libiconv.git/plain/COPYING.LIB",
    ),
    ("libvmaf", "--enable-libvmaf", "BSD-2-Clause-Patent", GH, "Netflix/vmaf"),
    (
        "fontconfig",
        "--enable-fontconfig",
        "HPND-sell-variant",
        RAW,
        "https://gitlab.freedesktop.org/fontconfig/fontconfig/-/raw/main/COPYING",
    ),
    ("HarfBuzz", "--enable-libharfbuzz", "MIT", GH, "harfbuzz/harfbuzz"),
    (
        "FreeType",
        "--enable-libfreetype",
        "FTL or GPL-2.0 (used under the FTL)",
        RAW,
        "https://gitlab.freedesktop.org/freetype/freetype/-/raw/master/docs/FTL.TXT",
    ),
    ("FriBidi", "--enable-libfribidi", "LGPL-2.1-or-later", GH, "fribidi/fribidi"),
    ("Little CMS 2", "--enable-lcms2", "MIT", GH, "mm2/Little-CMS"),
    ("Vulkan-Headers", "--enable-vulkan", "Apache-2.0 or MIT", GH, "KhronosGroup/Vulkan-Headers"),
    ("shaderc", "--enable-libshaderc", "Apache-2.0", GH, "google/shaderc"),
    (
        "dav1d",
        "--enable-libdav1d",
        "BSD-2-Clause",
        RAW,
        "https://code.videolan.org/videolan/dav1d/-/raw/master/COPYING",
    ),
    ("libvorbis", "--enable-libvorbis", "BSD-3-Clause", GH, "xiph/vorbis"),
    ("libogg", "(libvorbis, libtheora)", "BSD-3-Clause", GH, "xiph/ogg"),
    ("rav1e", "--enable-librav1e", "BSD-2-Clause", GH, "xiph/rav1e"),
    ("librsvg", "--enable-librsvg", "LGPL-2.1-or-later", GH, "GNOME/librsvg"),
    (
        "GMP",
        "--enable-gmp",
        "LGPL-3.0-or-later or GPL-2.0-or-later (used under the LGPL)",
        RAW,
        "https://raw.githubusercontent.com/FFmpeg/FFmpeg/n8.1.3/COPYING.LGPLv3",
    ),
    ("XZ Utils (liblzma)", "--enable-lzma", "0BSD / public domain", GH, "tukaani-project/xz"),
    ("LCEVCdec", "--enable-liblcevc-dec", "BSD-3-Clause-Clear", GH, "v-novaltd/LCEVCdec"),
    ("OpenCL-Headers", "--enable-opencl", "Apache-2.0", GH, "KhronosGroup/OpenCL-Headers"),
    ("AMF", "--enable-amf", "MIT", GH, "GPUOpen-LibrariesAndSDKs/AMF"),
    (
        "libaom",
        "--enable-libaom",
        "BSD-2-Clause",
        RAW,
        "https://aomedia.googlesource.com/aom/+/refs/heads/main/LICENSE?format=TEXT",
    ),
    ("Chromaprint", "--enable-chromaprint", "MIT", GH, "acoustid/chromaprint"),
    (
        "nv-codec-headers",
        "--enable-ffnvcodec",
        "MIT",
        RAW,
        "https://raw.githubusercontent.com/BtbN/nv-codec-headers/master/include/ffnvcodec/dynlink_loader.h#head=26",
    ),
    ("Game Music Emu", "--enable-libgme", "LGPL-2.1-or-later", GH, "libgme/game-music-emu"),
    ("Kvazaar", "--enable-libkvazaar", "BSD-3-Clause", GH, "ultravideo/kvazaar"),
    ("aribb24", "--enable-libaribb24", "LGPL-3.0-or-later", GH, "nkoriyama/aribb24"),
    ("libaribcaption", "--enable-libaribcaption", "MIT", GH, "xqq/libaribcaption"),
    ("libass", "--enable-libass", "ISC", GH, "libass/libass"),
    (
        "libbluray",
        "--enable-libbluray",
        "LGPL-2.1-or-later",
        RAW,
        "https://code.videolan.org/videolan/libbluray/-/raw/master/COPYING",
    ),
    ("libjxl", "--enable-libjxl", "BSD-3-Clause", GH, "libjxl/libjxl"),
    (
        "LAME",
        "--enable-libmp3lame",
        "LGPL-2.0-or-later",
        RAW,
        "https://svn.code.sf.net/p/lame/svn/trunk/lame/COPYING",
    ),
    ("Opus", "--enable-libopus", "BSD-3-Clause", GH, "xiph/opus"),
    ("libplacebo", "--enable-libplacebo", "LGPL-2.1-or-later", GH, "haasn/libplacebo"),
    (
        "librist",
        "--enable-librist",
        "BSD-2-Clause",
        RAW,
        "https://code.videolan.org/rist/librist/-/raw/master/COPYING",
    ),
    (
        "libssh",
        "--enable-libssh",
        "LGPL-2.1-or-later",
        RAW,
        "https://git.libssh.org/projects/libssh.git/plain/COPYING",
    ),
    ("libtheora", "--enable-libtheora", "BSD-3-Clause", GH, "xiph/theora"),
    ("libvpx", "--enable-libvpx", "BSD-3-Clause", GH, "webmproject/libvpx"),
    ("libwebp", "--enable-libwebp", "BSD-3-Clause", GH, "webmproject/libwebp"),
    ("ZeroMQ", "--enable-libzmq", "MPL-2.0 (libzmq 4.3.5 and later)", GH, "zeromq/libzmq"),
    ("LV2", "--enable-lv2", "ISC", GH, "lv2/lv2"),
    ("libvpl (oneVPL)", "--enable-libvpl", "MIT", GH, "intel/libvpl"),
    ("OpenAL Soft", "--enable-openal", "LGPL-2.0-or-later", GH, "kcat/openal-soft"),
    ("OpenAPV", "--enable-liboapv", "BSD-3-Clause", GH, "AcademySoftwareFoundation/openapv"),
    (
        "opencore-amr",
        "--enable-libopencore-amrnb/-amrwb",
        "Apache-2.0",
        RAW,
        "https://sourceforge.net/p/opencore-amr/code/ci/master/tree/LICENSE?format=raw",
    ),
    ("OpenH264", "--enable-libopenh264", "BSD-2-Clause", GH, "cisco/openh264"),
    ("OpenJPEG", "--enable-libopenjpeg", "BSD-2-Clause", GH, "uclouvain/openjpeg"),
    (
        "libopenmpt",
        "--enable-libopenmpt",
        "BSD-3-Clause",
        RAW,
        "https://raw.githubusercontent.com/OpenMPT/openmpt/master/LICENSE",
    ),
    ("SDL2", "--enable-sdl2", "Zlib", GH, "libsdl-org/SDL"),
    ("Snappy", "--enable-libsnappy", "BSD-3-Clause", GH, "google/snappy"),
    (
        "SoX Resampler (libsoxr)",
        "--enable-libsoxr",
        "LGPL-2.1-or-later",
        RAW,
        "https://sourceforge.net/p/soxr/code/ci/master/tree/LICENCE?format=raw",
    ),
    ("SRT", "--enable-libsrt", "MPL-2.0", GH, "Haivision/srt"),
    (
        "SVT-AV1",
        "--enable-libsvtav1",
        "BSD-3-Clause-Clear + AOM patent license",
        RAW,
        "https://gitlab.com/AOMediaCodec/SVT-AV1/-/raw/master/LICENSE.md",
    ),
    ("TwoLAME", "--enable-libtwolame", "LGPL-2.1-or-later", GH, "njh/twolame"),
    ("uavs3d", "--enable-libuavs3d", "BSD-3-Clause", GH, "uavs3/uavs3d"),
    ("VapourSynth", "--enable-vapoursynth", "LGPL-2.1-or-later", GH, "vapoursynth/vapoursynth"),
    ("VVenC", "--enable-libvvenc", "BSD-3-Clause-Clear", GH, "fraunhoferhhi/vvenc"),
    ("zimg", "--enable-libzimg", "WTFPL", GH, "sekrit-twc/zimg"),
    (
        "zvbi",
        "--enable-libzvbi",
        "GPL-2.0-or-later / LGPL-2.1-or-later (the library part, used under the LGPL)",
        GH,
        "zapping-vbi/zvbi",
    ),
    (
        "mingw-w64 winpthreads",
        "--enable-pthreads",
        "MIT-style (ZPL-2.1 and others)",
        RAW,
        "https://raw.githubusercontent.com/mingw-w64/mingw-w64/master/COPYING.MinGW-w64-runtime/COPYING.MinGW-w64-runtime.txt",
    ),
]


def fetch(entry: tuple[str, str, str, str, str]) -> tuple[str, str]:
    name, _flag, _license, kind, where = entry
    if kind == GH:
        out = subprocess.run(  # noqa: S603
            ["gh", "api", f"repos/{where}/license"],  # noqa: S607
            capture_output=True,
            text=True,
            check=False,
        )
        if out.returncode != 0:
            return name, f"!! {out.stderr.strip()[:200]}"
        data = json.loads(out.stdout)
        return name, base64.b64decode(data["content"]).decode("utf-8", "replace")
    where, _, head = where.partition("#head=")
    request = urllib.request.Request(where, headers={"User-Agent": "vst-license-fetch"})  # noqa: S310
    try:
        with urllib.request.urlopen(request, timeout=60) as reply:  # noqa: S310
            body = reply.read()
    except OSError as exc:
        return name, f"!! {exc}"
    if "googlesource" in where:
        body = base64.b64decode(body)
    text = body.decode("utf-8", "replace")
    lines = text.splitlines()
    return name, "\n".join(lines[: int(head)] if head else lines)


def main() -> None:
    with ThreadPoolExecutor(8) as pool:
        texts = dict(pool.map(fetch, LIBRARIES))
    failed = [n for n, t in texts.items() if t.startswith("!!") or len(t.strip()) < 100]
    parts = [
        "License texts of the external libraries linked into the bundled FFmpeg build\n"
        f"(BtbN/FFmpeg-Builds, FFmpeg {FFMPEG_TAG}+, LGPL variant, shared). Each text is the\n"
        "license file of the project's upstream repository, fetched by\n"
        "installer/fetch_ffmpeg_licenses.py. The first two are the LGPL texts FFmpeg itself and\n"
        "several libraries are licensed under.\n"
    ]
    for name, flag, license_id, _kind, where in LIBRARIES:
        rule = "=" * 78
        parts.append(
            f"\n{rule}\n{name}   [{flag}]   License: {license_id}\nSource: {where}\n{rule}\n"
        )
        parts.append(texts[name].strip() + "\n")
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text("".join(parts), encoding="utf-8", newline="\n")
    print(f"{len(LIBRARIES) - len(failed)} of {len(LIBRARIES)} texts written to {OUT}")
    for name in failed:
        print(f"MISSING {name}: {texts[name][:120]!r}")


if __name__ == "__main__":
    main()
