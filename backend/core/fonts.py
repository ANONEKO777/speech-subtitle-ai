"""The font a burned-in subtitle writes the spoken language in, and a check that it has the glyphs.

libass picks a replacement font for a glyph the named font lacks, and on a PC with no font that
has kana it draws empty boxes without a word of warning. So before a burn the source text is
checked against the fonts Windows has installed, and a missing glyph is reported by name.
"""

from __future__ import annotations

import os
import struct
import sys
from collections.abc import Callable, Iterable, Mapping, Sequence
from pathlib import Path
from types import MappingProxyType

from backend.core.audio import AudioError
from backend.core.languages import DEFAULT_FONT, Language
from backend.core.model import Cue
from backend.core.notices import (
    MISSING_GLYPHS,
    MISSING_TARGET_GLYPHS,
    NO_JAPANESE_FONT,
    NO_JAPANESE_FONT_MACOS,
    NO_TARGET_FONT,
    Notice,
    Template,
    noticed,
)
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


MACOS_SUBSTITUTES: Mapping[str, tuple[str, ...]] = MappingProxyType(
    {
        "Microsoft JhengHei": ("PingFang TC",),
        "Malgun Gothic": ("Apple SD Gothic Neo",),
        "Yu Gothic": ("Hiragino Sans", "Yu Gothic", "Hiragino Kaku Gothic ProN"),
        "Meiryo": ("Hiragino Maru Gothic ProN",),
        "MS Gothic": (),
    }
)
"""For each family a Windows PC has, the families to try on a Mac, best first. A family that is
not listed (Arial ships with macOS) stays as it is."""
MACOS_FONT_DIRS = (
    "/System/Library/Fonts",
    "/Library/Fonts",
    "~/Library/Fonts",
    "/System/Library/AssetsV2",
)
"""Where macOS keeps fonts. The system folder has a `Supplemental` folder with Arial in it, and the
newer CJK families (PingFang among them) are said to live in font assets under `AssetsV2`: that
last one is an assumption not yet checked on a Mac (P37d)."""
_FONT_SUFFIXES = frozenset({".ttf", ".otf", ".ttc", ".otc"})
_NAME_FAMILY_IDS = (1, 16)
_MAX_COLLECTION = 64
_MAX_NAME_TABLE = 1 << 20


def fonts_for(families: Sequence[str], system: str | None = None) -> tuple[str, ...]:
    """`families` as this machine knows them: unchanged on Windows, the Mac counterparts (see
    `MACOS_SUBSTITUTES`) on macOS."""
    if (sys.platform if system is None else system) != "darwin":
        return tuple(families)
    mapped = [name for family in families for name in MACOS_SUBSTITUTES.get(family, (family,))]
    return tuple(dict.fromkeys(mapped))


def no_japanese_font(system: str | None = None) -> Template:
    if (sys.platform if system is None else system) == "darwin":
        return NO_JAPANESE_FONT_MACOS
    return NO_JAPANESE_FONT


def _names_of_table(table: bytes) -> set[str]:
    """The family names (name ids 1 and 16, in every language the font gives) in a `name` table."""
    names: set[str] = set()
    count, string_base = struct.unpack_from(">HH", table, 2)
    for i in range(count):
        platform, _encoding, _language, name_id, length, offset = struct.unpack_from(
            ">HHHHHH", table, 6 + 12 * i
        )
        if name_id in _NAME_FAMILY_IDS:
            raw = table[string_base + offset : string_base + offset + length]
            text = raw.decode("utf-16-be" if platform in (0, 3) else "mac-roman", "replace")
            if text:
                names.add(text)
    return names


def read_family_names(path: Path) -> list[tuple[int, set[str]]]:
    """(offset, family names) of each font in the file `path`. Only the header and the `name`
    table of each font are read, so listing a large collection does not load it."""
    found: list[tuple[int, set[str]]] = []
    try:
        with path.open("rb") as handle:
            head = handle.read(12 + 4 * _MAX_COLLECTION)
            offsets = [0]
            if head[:4] == b"ttcf":
                count = min(struct.unpack_from(">I", head, 8)[0], _MAX_COLLECTION)
                offsets = [struct.unpack_from(">I", head, 12 + 4 * i)[0] for i in range(count)]
            for offset in offsets:
                handle.seek(offset)
                header = handle.read(12)
                tables = struct.unpack_from(">H", header, 4)[0]
                directory = header + handle.read(16 * tables)
                entry = next(
                    (
                        12 + 16 * i
                        for i in range(tables)
                        if directory[12 + 16 * i : 16 + 16 * i] == b"name"
                    ),
                    None,
                )
                if entry is None:
                    continue
                where, length = struct.unpack_from(">II", directory, entry + 8)
                handle.seek(where)
                names = _names_of_table(handle.read(min(length, _MAX_NAME_TABLE)))
                found.append((offset, names))
    except (OSError, struct.error):
        pass
    return found


def _font_files(dirs: Sequence[str]) -> list[Path]:
    files: list[Path] = []
    for folder in dirs:
        root = Path(folder).expanduser()
        if root.is_dir():
            files.extend(sorted(p for p in root.rglob("*") if p.suffix.lower() in _FONT_SUFFIXES))
    return [p for p in files if p.is_file()]


_FileNames = tuple[tuple[int, int], list[tuple[int, set[str]]]]
"""A font file's (modified time, size) and what `read_family_names` found in it."""
_Index = Mapping[str, tuple[tuple[Path, int], ...]]
_indexed: dict[tuple[str, ...], tuple[dict[Path, _FileNames], _Index]] = {}


def _macos_index(dirs: tuple[str, ...], *, rescan: bool = False) -> _Index:
    """Family name (lower case) -> the (file, offset in the file) pairs that hold it. The index is
    kept for the life of the process. `rescan` lists the folders again and reads only the files
    that are new or changed, so a font installed while the service runs is found."""
    known = _indexed.get(dirs)
    if known is not None and not rescan:
        return known[1]
    before = known[0] if known is not None else {}
    reads: dict[Path, _FileNames] = {}
    for path in _font_files(dirs):
        try:
            stat = path.stat()
        except OSError:
            continue
        stamp = (stat.st_mtime_ns, stat.st_size)
        old = before.get(path)
        reads[path] = (
            old if old is not None and old[0] == stamp else (stamp, read_family_names(path))
        )
    found: dict[str, list[tuple[Path, int]]] = {}
    for path, (_, names_at) in reads.items():
        for offset, names in names_at:
            for name in names:
                found.setdefault(name.lower(), []).append((path, offset))
    index = MappingProxyType({name: tuple(places) for name, places in found.items()})
    _indexed[dirs] = (reads, index)
    return index


def file_covers_at(path: Path, offset: int, chars: Iterable[str]) -> set[str]:
    """The characters of `chars` that the one font at `offset` in the file `path` does not draw."""
    data = path.read_bytes()
    return {c for c in chars if not font_covers(data, offset, ord(c))}


def macos_coverage(
    chars: Iterable[str], dirs: Sequence[str] = MACOS_FONT_DIRS
) -> Callable[[str], tuple[Path, set[str]] | None]:
    """A lookup from a font family to the file that holds it and the characters it lacks, for the
    fonts in the macOS font folders. The family is matched by its whole name, in any letter case.
    A family that is not found makes the folders be listed again, once for this lookup, because the
    person may have installed it since the service started."""
    key = tuple(dirs)
    index = _macos_index(key)
    wanted = list(chars)
    rescanned = False

    def lookup(family: str) -> tuple[Path, set[str]] | None:
        nonlocal index, rescanned
        places = index.get(family.lower())
        if not places and not rescanned:
            rescanned = True
            index = _macos_index(key, rescan=True)
            places = index.get(family.lower())
        if not places:
            return None
        path, offset = places[0]
        return path, file_covers_at(path, offset, wanted)

    return lookup


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


def system_coverage(chars: Iterable[str]) -> Callable[[str], tuple[Path, set[str]] | None]:
    """The coverage lookup of the machine this runs on."""
    return macos_coverage(chars) if sys.platform == "darwin" else windows_coverage(chars)


def _first_covering(
    needed: set[str],
    candidates: Sequence[str],
    lookup: Lookup,
    no_font: Callable[[Sequence[str]], Notice],
    glyphs: Callable[[str, str], Notice],
) -> str:
    """The first family of `candidates` that draws every character of `needed`. When none does,
    raises `FontMissing`: the `glyphs` notice for the family that lacks the fewest, or `no_font`
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
        raise noticed(FontMissing, glyphs(family, "".join(sorted(missing)[:12])))
    raise noticed(FontMissing, no_font(tried))


def burn_font(cues: Sequence[Cue], lookup: Lookup | None = None) -> str:
    """The font to burn the source text of `cues` in. An English source keeps the font the first
    release used, with no lookup, whatever punctuation it has. Japanese text with kana or kanji goes
    to the first installed font of its language that draws all of it. When there is none, raises
    `FontMissing` saying what is missing."""
    needed = {c for cue in cues if cue.lang != ENGLISH for c in cue.src if needs_cjk_font(c)}
    if not needed:
        return fonts_for(ENGLISH_SOURCE.fonts)[0]
    langs = [code for code in dict.fromkeys(cue.lang for cue in cues) if code in SOURCES]
    families = [font for code in langs if code != ENGLISH for font in SOURCES[code].fonts]
    japanese = no_japanese_font()
    return _first_covering(
        needed,
        fonts_for(families),
        lookup or system_coverage,
        lambda tried: japanese(fonts=tried),
        lambda font, chars: MISSING_GLYPHS(font=font, chars=chars),
    )


def target_font(cues: Sequence[Cue], lang: Language, lookup: Lookup | None = None) -> str:
    """The font to burn the translation of `cues` in. A language that keeps the default font
    (Chinese, English) is not looked up, as before. A language with fonts of its own (Korean,
    Russian) goes to the first installed one that draws every character of its text, or raises
    `FontMissing` saying what is missing."""
    families = fonts_for(lang.fonts)
    if lang.fonts == (DEFAULT_FONT,):
        return families[0]
    needed = {c for cue in cues for c in cue.zh if ord(c) > 0x7F and not c.isspace()}
    if not needed:
        return families[0]
    return _first_covering(
        needed,
        families,
        lookup or system_coverage,
        lambda tried: NO_TARGET_FONT(language=lang, fonts=tried),
        lambda font, chars: MISSING_TARGET_GLYPHS(font=font, language=lang, chars=chars),
    )
