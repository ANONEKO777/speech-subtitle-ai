"""The font a burned-in subtitle writes the spoken language in, and a check that it has the glyphs.

libass picks a replacement font for a glyph the named font lacks, and on a PC with no font that
has kana it draws empty boxes without a word of warning. So before a burn the source text is
checked against the fonts Windows has installed, and a missing glyph is reported by name.
"""

from __future__ import annotations

import os
import struct
import sys
from collections.abc import Callable, Iterable, Sequence
from pathlib import Path

from backend.core.audio import AudioError
from backend.core.languages import DEFAULT_FONT, Language
from backend.core.model import Cue
from backend.core.source_langs import ENGLISH, ENGLISH_SOURCE, SOURCES

CJK_RANGES = (
    (0x3000, 0x30FF),
    (0x3400, 0x4DBF),
    (0x4E00, 0x9FFF),
    (0xF900, 0xFAFF),
    (0xFF00, 0xFFEF),
)
"""CJK symbols and punctuation, kana, ideographs, compatibility ideographs and full-width forms.
General punctuation (curly quotes, em dash, ellipsis) is not here: Arial draws it."""


def needs_cjk_font(char: str) -> bool:
    return any(low <= ord(char) <= high for low, high in CJK_RANGES)


MISSING_FONT_MESSAGE = (
    "這台電腦沒有可以顯示日文字幕的字型（試過 {fonts}），燒錄出來的日文會變成空白方塊。"
    "請到「設定 > 個人化 > 字型」安裝日文字型（例如 Yu Gothic 或 Meiryo），"
    "或到「設定 > 系統 > 選用功能」新增「日文」的補充字型後再試。"
    "字幕檔（SRT、ASS）不受影響，仍可匯出。"
)
MISSING_GLYPH_MESSAGE = (
    "字型 {font} 缺少這些字的字形：{chars}，燒錄出來的字幕會變成空白方塊。"
    "請安裝含有這些字的字型後再試。字幕檔（SRT、ASS）不受影響，仍可匯出。"
)


MISSING_TARGET_GLYPH_MESSAGE = (
    "字型 {font} 缺少{language}字幕要用的字形：{chars}，燒錄出來的字幕會變成空白方塊。"
    "請安裝含有{language}的字型後再試。字幕檔（SRT、ASS）不受影響，仍可匯出。"
)
MISSING_TARGET_FONT_MESSAGE = (
    "這台電腦沒有可以顯示{language}字幕的字型（試過 {fonts}），燒錄出來的字幕會變成空白方塊。"
    "請安裝含有{language}的字型後再試。字幕檔（SRT、ASS）不受影響，仍可匯出。"
)


class FontMissing(AudioError):
    """Burn-in cannot draw the source text: no installed font has all its glyphs."""


Coverage = Callable[[str, str], bool]
"""(font family, character) -> whether the installed font of that family draws the character."""


def _read_table_offsets(data: bytes, start: int) -> dict[bytes, int]:
    count = struct.unpack_from(">H", data, start + 4)[0]
    return {
        data[start + 12 + 16 * i : start + 16 + 16 * i]: struct.unpack_from(
            ">I", data, start + 20 + 16 * i
        )[0]
        for i in range(count)
    }


def _format4(data: bytes, base: int, code: int) -> bool:
    segments = struct.unpack_from(">H", data, base + 6)[0] // 2
    ends = base + 14
    starts = ends + segments * 2 + 2
    deltas = starts + segments * 2
    ranges = deltas + segments * 2
    for i in range(segments):
        if code > struct.unpack_from(">H", data, ends + 2 * i)[0]:
            continue
        if code < struct.unpack_from(">H", data, starts + 2 * i)[0]:
            return False
        delta = struct.unpack_from(">h", data, deltas + 2 * i)[0]
        offset = struct.unpack_from(">H", data, ranges + 2 * i)[0]
        if offset == 0:
            return (code + delta) & 0xFFFF != 0
        first = struct.unpack_from(">H", data, starts + 2 * i)[0]
        glyph = struct.unpack_from(">H", data, ranges + 2 * i + offset + 2 * (code - first))[0]
        return glyph != 0
    return False


def _format12(data: bytes, base: int, code: int) -> bool:
    groups = struct.unpack_from(">I", data, base + 12)[0]
    for i in range(groups):
        start, end, glyph = struct.unpack_from(">III", data, base + 16 + 12 * i)
        if start <= code <= end:
            return glyph + code - start != 0
    return False


def font_covers(data: bytes, offset: int, code: int) -> bool:
    """Whether the font that starts at `offset` in `data` has a glyph for `code` (cmap formats 4
    and 12, the two every font that holds CJK uses)."""
    tables = _read_table_offsets(data, offset)
    cmap = tables.get(b"cmap")
    if cmap is None:
        return False
    count = struct.unpack_from(">H", data, cmap + 2)[0]
    for i in range(count):
        platform, encoding, sub = struct.unpack_from(">HHI", data, cmap + 4 + 8 * i)
        if (platform, encoding) not in ((3, 1), (3, 10), (0, 3), (0, 4)):
            continue
        base = cmap + sub
        form = struct.unpack_from(">H", data, base)[0]
        if form == 4 and _format4(data, base, code):
            return True
        if form == 12 and _format12(data, base, code):
            return True
    return False


def file_covers(path: Path, chars: Iterable[str]) -> set[str]:
    """The characters of `chars` that no font in the file `path` (a font or a collection) draws."""
    data = path.read_bytes()
    offsets = [0]
    if data[:4] == b"ttcf":
        count = struct.unpack_from(">I", data, 8)[0]
        offsets = [struct.unpack_from(">I", data, 12 + 4 * i)[0] for i in range(count)]
    return {c for c in chars if not any(font_covers(data, o, ord(c)) for o in offsets)}


def _registry_fonts() -> dict[str, Path]:
    """Installed fonts as the registry lists them: the display name, which holds every family of a
    collection, and the file."""
    if sys.platform != "win32":
        return {}
    import winreg

    found: dict[str, Path] = {}
    windir = Path(os.environ.get("WINDIR", r"C:\Windows")) / "Fonts"
    for hive in (winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER):
        try:
            with winreg.OpenKey(hive, r"SOFTWARE\Microsoft\Windows NT\CurrentVersion\Fonts") as key:
                count = winreg.QueryInfoKey(key)[1]
                for i in range(count):
                    name, value, _ = winreg.EnumValue(key, i)
                    path = Path(str(value))
                    found[str(name)] = path if path.is_absolute() else windir / path
        except OSError:
            continue
    return found


def windows_coverage(chars: Iterable[str]) -> Callable[[str], tuple[Path, set[str]] | None]:
    """A lookup from a font family to the file that holds it and the characters it lacks."""
    listing = _registry_fonts()
    wanted = list(chars)

    def lookup(family: str) -> tuple[Path, set[str]] | None:
        for name, path in listing.items():
            if family.lower() in name.lower() and path.is_file():
                return path, file_covers(path, wanted)
        return None

    return lookup


Lookup = Callable[[Iterable[str]], Callable[[str], tuple[Path, set[str]] | None]]


def _first_covering(
    needed: set[str],
    candidates: Sequence[str],
    lookup: Lookup,
    no_font: str,
    glyphs: str = MISSING_GLYPH_MESSAGE,
) -> str:
    """The first family of `candidates` that draws every character of `needed`. When none does,
    raises `FontMissing`: the `glyphs` message for the family that lacks the fewest, or `no_font`
    when no family is installed."""
    find = lookup(needed)
    tried: list[str] = []
    lacking: dict[str, set[str]] = {}
    for family in candidates:
        found = find(family)
        tried.append(family)
        if found is None:
            continue
        missing = found[1]
        if not missing:
            return family
        lacking[family] = missing
    if lacking:
        family, missing = min(lacking.items(), key=lambda item: len(item[1]))
        raise FontMissing(glyphs.format(font=family, chars="".join(sorted(missing)[:12])))
    raise FontMissing(no_font.format(fonts="、".join(tried)))


def burn_font(cues: Sequence[Cue], lookup: Lookup = windows_coverage) -> str:
    """The font to burn the source text of `cues` in. An English source keeps the font the first
    release used, with no lookup, whatever punctuation it has. Japanese text with kana or kanji goes
    to the first installed font of its language that draws all of it. When there is none, raises
    `FontMissing` saying what is missing."""
    needed = {c for cue in cues if cue.lang != ENGLISH for c in cue.src if needs_cjk_font(c)}
    if not needed:
        return ENGLISH_SOURCE.fonts[0]
    langs = [code for code in dict.fromkeys(cue.lang for cue in cues) if code in SOURCES]
    candidates = [font for code in langs if code != ENGLISH for font in SOURCES[code].fonts]
    return _first_covering(needed, candidates, lookup, MISSING_FONT_MESSAGE)


def target_font(cues: Sequence[Cue], lang: Language, lookup: Lookup = windows_coverage) -> str:
    """The font to burn the translation of `cues` in. A language that keeps the default font
    (Chinese, English) is not looked up, as before. A language with fonts of its own (Korean,
    Russian) goes to the first installed one that draws every character of its text, or raises
    `FontMissing` saying what is missing."""
    if lang.fonts == (DEFAULT_FONT,):
        return DEFAULT_FONT
    needed = {c for cue in cues for c in cue.zh if ord(c) > 0x7F and not c.isspace()}
    if not needed:
        return lang.fonts[0]
    no_font = MISSING_TARGET_FONT_MESSAGE.replace("{language}", lang.native)
    glyphs = MISSING_TARGET_GLYPH_MESSAGE.replace("{language}", lang.native)
    return _first_covering(needed, lang.fonts, lookup, no_font, glyphs)
