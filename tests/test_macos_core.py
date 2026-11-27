# pyright: reportUnknownLambdaType=false, reportUnknownArgumentType=false
"""The parts of the backend core that differ on a Mac: process guard, fonts, burn-in encoder and
the ffmpeg search. The platform is faked; fonts are tiny files built here with only the tables the
code reads (`name` and `cmap`), so no Mac font is needed."""

from __future__ import annotations

import os
import shutil
import signal
import struct
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Any

import pytest

from backend.core import audio, fonts, process_guard, render
from backend.core.fonts import FontMissing, burn_font, fonts_for, macos_coverage, target_font
from backend.core.languages import get as get_language
from backend.core.model import Cue
from backend.core.notices import notices_of

windows_host = pytest.mark.skipif(
    sys.platform != "win32", reason="asserts what the real Windows host does"
)

# --- tiny fonts -------------------------------------------------------------------------------


def _name_table(families: list[str]) -> bytes:
    records = b""
    strings = b""
    for family in families:
        raw = family.encode("utf-16-be")
        records += struct.pack(">HHHHHH", 3, 1, 0x409, 1, len(raw), len(strings))
        strings += raw
    header = struct.pack(">HHH", 0, len(families), 6 + 12 * len(families))
    return header + records + strings


def _cmap_table(ranges: list[tuple[int, int]]) -> bytes:
    groups = b"".join(struct.pack(">III", lo, hi, 1 + i) for i, (lo, hi) in enumerate(ranges))
    sub = struct.pack(">HHIII", 12, 0, 16 + len(groups), 0, len(ranges)) + groups
    return struct.pack(">HH", 0, 1) + struct.pack(">HHI", 3, 10, 12) + sub


def sfnt(families: list[str], covered: list[tuple[int, int]], at: int = 0) -> bytes:
    """A font whose tables sit at absolute offsets that start from `at`."""
    tables = sorted({b"cmap": _cmap_table(covered), b"name": _name_table(families)}.items())
    directory_size = 12 + 16 * len(tables)
    offset = at + directory_size
    entries = b""
    body = b""
    for tag, data in tables:
        entries += struct.pack(">4sIII", tag, 0, offset + len(body), len(data))
        body += data
    return struct.pack(">IHHHH", 0x00010000, len(tables), 0, 0, 0) + entries + body


def collection(fonts_: list[tuple[list[str], list[tuple[int, int]]]]) -> bytes:
    header = 12 + 4 * len(fonts_)
    offsets: list[int] = []
    blobs: list[bytes] = []
    cursor = header
    for families, covered in fonts_:
        blob = sfnt(families, covered, at=cursor)
        offsets.append(cursor)
        blobs.append(blob)
        cursor += len(blob)
    head = struct.pack(">4sII", b"ttcf", 0x00010000, len(fonts_)) + b"".join(
        struct.pack(">I", o) for o in offsets
    )
    return head + b"".join(blobs)


HANGUL = [(0xAC00, 0xD7A3)]
KANA_KANJI = [(0x3040, 0x30FF), (0x4E00, 0x9FFF)]
CYRILLIC = [(0x0400, 0x04FF)]


def folder_with(tmp_path: Path, **files: bytes) -> str:
    root = tmp_path / "Fonts"
    root.mkdir()
    for name, data in files.items():
        (root / name).write_bytes(data)
    return str(root)


def cues(text: str, lang: str = "ja", zh: str = "") -> list[Cue]:
    return [Cue(1, 0, 1000, text, zh, lang)]


@pytest.fixture
def as_mac(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("sys.platform", "darwin")
    monkeypatch.setattr("platform.machine", lambda: "arm64")


# --- font names on a Mac ----------------------------------------------------------------------


def test_the_family_name_is_read_from_a_plain_font_and_from_each_member_of_a_collection(
    tmp_path: Path,
) -> None:
    single = tmp_path / "a.ttf"
    single.write_bytes(sfnt(["Apple SD Gothic Neo"], HANGUL))
    pack = tmp_path / "b.ttc"
    pack.write_bytes(collection([(["PingFang TC"], KANA_KANJI), (["PingFang SC"], KANA_KANJI)]))

    assert fonts.read_family_names(single) == [(0, {"Apple SD Gothic Neo"})]
    found = fonts.read_family_names(pack)
    assert [names for _, names in found] == [{"PingFang TC"}, {"PingFang SC"}]
    assert found[0][0] != found[1][0]


def test_a_file_that_is_not_a_font_or_is_cut_short_gives_no_names_and_no_error(
    tmp_path: Path,
) -> None:
    junk = tmp_path / "x.ttf"
    junk.write_bytes(b"not a font")
    cut = tmp_path / "y.ttf"
    cut.write_bytes(sfnt(["Cut"], HANGUL)[:20])

    assert fonts.read_family_names(junk) == []
    assert fonts.read_family_names(cut) == []
    assert fonts.read_family_names(tmp_path / "missing.ttf") == []


def test_the_lookup_reports_the_characters_a_family_lacks_by_the_font_that_has_the_name(
    tmp_path: Path,
) -> None:
    folder = folder_with(
        tmp_path,
        **{"one.ttc": collection([(["Family Han"], KANA_KANJI), (["Family Hangul"], HANGUL)])},
    )
    lookup = macos_coverage("한漢", [folder])

    han = lookup("family han")
    hangul = lookup("Family Hangul")

    assert han is not None and hangul is not None
    assert han[1] == {"한"}
    assert hangul[1] == {"漢"}
    assert lookup("Nothing Like It") is None


def test_the_lookup_walks_folders_inside_a_font_folder_and_skips_other_files(
    tmp_path: Path,
) -> None:
    root = tmp_path / "Fonts" / "Supplemental"
    root.mkdir(parents=True)
    (root / "Arial.ttf").write_bytes(sfnt(["Arial"], CYRILLIC))
    (root / "readme.txt").write_text("Arial")

    found = macos_coverage("я", [str(tmp_path / "Fonts")])("Arial")

    assert found is not None and found[1] == set()


def test_a_font_installed_after_a_miss_is_found_by_the_next_lookup_without_a_restart(
    tmp_path: Path,
) -> None:
    folder = folder_with(tmp_path, **{"one.ttf": sfnt(["Family One"], KANA_KANJI)})
    assert macos_coverage("漢", [folder])("Family Two") is None

    (Path(folder) / "two.ttf").write_bytes(sfnt(["Family Two"], KANA_KANJI))

    found = macos_coverage("漢", [folder])("Family Two")
    assert found is not None and found[1] == set()


def test_a_font_installed_between_the_lookup_and_its_first_question_is_found(
    tmp_path: Path,
) -> None:
    folder = folder_with(tmp_path, **{"one.ttf": sfnt(["Family One"], KANA_KANJI)})
    lookup = macos_coverage("漢", [folder])

    (Path(folder) / "two.ttf").write_bytes(sfnt(["Family Two"], KANA_KANJI))

    assert lookup("Family Two") is not None


def test_the_folders_are_listed_again_only_for_a_family_that_is_not_found(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    folder = folder_with(tmp_path, **{"one.ttf": sfnt(["Family One"], KANA_KANJI)})
    listed: list[int] = []
    real_list = fonts._font_files  # pyright: ignore[reportPrivateUsage]
    monkeypatch.setattr(fonts, "_font_files", lambda dirs: (listed.append(1), real_list(dirs))[1])
    macos_coverage("漢", [folder])("Family One")
    assert len(listed) == 1

    hits = macos_coverage("漢", [folder])
    for _ in range(5):
        assert hits("family one") is not None
    assert len(listed) == 1

    misses = macos_coverage("漢", [folder])
    for _ in range(5):
        assert misses("No Such Family") is None
    assert len(listed) == 2


def test_listing_again_reads_only_the_files_that_are_new_or_changed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    folder = folder_with(tmp_path, **{"one.ttf": sfnt(["Family One"], KANA_KANJI)})
    macos_coverage("漢", [folder])("Family One")
    read: list[str] = []
    real_read = fonts.read_family_names

    def recording(path: Path) -> list[tuple[int, set[str]]]:
        read.append(path.name)
        return real_read(path)

    monkeypatch.setattr(fonts, "read_family_names", recording)
    (Path(folder) / "two.ttf").write_bytes(sfnt(["Family Two"], KANA_KANJI))

    assert macos_coverage("漢", [folder])("Family Two") is not None
    assert read == ["two.ttf"]

    (Path(folder) / "two.ttf").write_bytes(sfnt(["Family Two Renamed"], KANA_KANJI))
    assert macos_coverage("漢", [folder])("Family Two Renamed") is not None
    assert read == ["two.ttf", "two.ttf"]


def test_a_font_folder_that_does_not_exist_is_ignored(tmp_path: Path) -> None:
    assert macos_coverage("я", [str(tmp_path / "nope")])("Arial") is None


# --- the fonts a Mac burns in -----------------------------------------------------------------


def test_the_families_are_mapped_for_a_mac_and_left_alone_for_windows() -> None:
    assert fonts_for(["Microsoft JhengHei"], "win32") == ("Microsoft JhengHei",)
    assert fonts_for(["Malgun Gothic"], "win32") == ("Malgun Gothic",)
    assert fonts_for(["Yu Gothic", "Meiryo", "MS Gothic"], "win32") == (
        "Yu Gothic",
        "Meiryo",
        "MS Gothic",
    )
    assert fonts_for(["Microsoft JhengHei"], "darwin") == ("PingFang TC",)
    assert fonts_for(["Malgun Gothic"], "darwin") == ("Apple SD Gothic Neo",)
    assert fonts_for(["Arial"], "darwin") == ("Arial",)
    assert fonts_for(["Yu Gothic", "Meiryo", "MS Gothic"], "darwin") == (
        "Hiragino Sans",
        "Yu Gothic",
        "Hiragino Kaku Gothic ProN",
        "Hiragino Maru Gothic ProN",
    )


def test_the_default_chinese_font_on_a_mac_is_pingfang_with_no_lookup(as_mac: None) -> None:
    def boom(_chars: Any) -> Any:
        raise AssertionError("no lookup for the default font")

    assert target_font(cues("x", "en", "你好"), get_language("zh-TW"), boom) == "PingFang TC"


@windows_host
def test_the_default_chinese_font_on_windows_is_what_it_was() -> None:
    assert target_font(
        cues("x", "en", "你好"), get_language("zh-TW"), lambda _c: lambda _f: None
    ) == ("Microsoft JhengHei")


def test_korean_on_a_mac_uses_apple_sd_gothic_neo_when_it_draws_the_text(
    tmp_path: Path, as_mac: None
) -> None:
    folder = folder_with(tmp_path, **{"ASGN.ttc": collection([(["Apple SD Gothic Neo"], HANGUL)])})

    found = target_font(
        cues("x", "en", "안녕하세요"),
        get_language("ko"),
        lambda chars: macos_coverage(chars, [folder]),
    )

    assert found == "Apple SD Gothic Neo"


def test_korean_on_a_mac_with_no_korean_font_is_refused_and_names_the_language(
    tmp_path: Path, as_mac: None
) -> None:
    folder = folder_with(tmp_path)

    with pytest.raises(FontMissing) as caught:
        target_font(
            cues("x", "en", "안녕하세요"),
            get_language("ko"),
            lambda chars: macos_coverage(chars, [folder]),
        )

    [notice] = notices_of(caught.value)
    assert (notice.code, notice.params["language"]) == ("fonts.noTargetFont", "ko")
    assert "Korean" in str(caught.value)
    assert "Apple SD Gothic Neo" in str(caught.value)


def test_russian_on_a_mac_uses_arial_from_the_supplemental_folder(
    tmp_path: Path, as_mac: None
) -> None:
    folder = folder_with(tmp_path, **{"Arial.ttf": sfnt(["Arial"], CYRILLIC)})

    found = target_font(
        cues("x", "en", "привет"),
        get_language("ru"),
        lambda chars: macos_coverage(chars, [folder]),
    )

    assert found == "Arial"


def test_russian_with_a_font_that_lacks_a_letter_names_the_font_and_the_letter(
    tmp_path: Path, as_mac: None
) -> None:
    folder = folder_with(tmp_path, **{"Arial.ttf": sfnt(["Arial"], [(0x0410, 0x042F)])})

    with pytest.raises(FontMissing) as caught:
        target_font(
            cues("x", "en", "привет"),
            get_language("ru"),
            lambda chars: macos_coverage(chars, [folder]),
        )

    [notice] = notices_of(caught.value)
    assert (notice.code, notice.params["language"]) == ("fonts.missingTargetGlyphs", "ru")
    assert "Arial" in str(caught.value) and "Russian" in str(caught.value)


def test_japanese_source_text_on_a_mac_picks_hiragino_sans_when_it_draws_the_text(
    tmp_path: Path, as_mac: None
) -> None:
    folder = folder_with(tmp_path, **{"HS.ttc": collection([(["Hiragino Sans"], KANA_KANJI)])})

    found = burn_font(cues("日本語です"), lambda chars: macos_coverage(chars, [folder]))

    assert found == "Hiragino Sans"


def test_japanese_source_text_on_a_mac_with_no_font_gets_the_mac_message(
    tmp_path: Path, as_mac: None
) -> None:
    folder = folder_with(tmp_path)

    with pytest.raises(FontMissing) as caught:
        burn_font(cues("日本語です"), lambda chars: macos_coverage(chars, [folder]))

    [notice] = notices_of(caught.value)
    assert notice.code == "fonts.noJapaneseMac"
    assert "Hiragino Sans" in notice.params["fonts"]
    assert str(caught.value) == notice.message


@windows_host
def test_japanese_source_text_on_windows_gets_the_windows_message() -> None:
    with pytest.raises(FontMissing) as caught:
        burn_font(cues("日本語です"), lambda _chars: lambda _family: None)

    [notice] = notices_of(caught.value)
    assert notice.code == "fonts.noJapaneseWindows"
    assert notice.params == {"fonts": ["Yu Gothic", "Meiryo", "MS Gothic"]}
    assert "Yu Gothic, Meiryo, MS Gothic" in str(caught.value)


def test_english_source_text_keeps_arial_on_both_platforms(as_mac: None) -> None:
    assert burn_font(cues("Hello", "en"), lambda _c: lambda _f: None) == "Arial"


def test_the_system_lookup_is_the_mac_one_on_a_mac(
    as_mac: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    seen: list[str] = []
    monkeypatch.setattr(
        fonts, "macos_coverage", lambda chars: seen.append("mac") or (lambda f: None)
    )
    monkeypatch.setattr(
        fonts, "windows_coverage", lambda chars: seen.append("win") or (lambda f: None)
    )

    fonts.system_coverage("x")

    assert seen == ["mac"]


@windows_host
def test_the_system_lookup_is_the_windows_one_on_windows(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: list[str] = []
    monkeypatch.setattr(
        fonts, "macos_coverage", lambda chars: seen.append("mac") or (lambda f: None)
    )
    monkeypatch.setattr(
        fonts, "windows_coverage", lambda chars: seen.append("win") or (lambda f: None)
    )

    fonts.system_coverage("x")

    assert seen == ["win"]


# --- the burn-in encoder on a Mac -------------------------------------------------------------

LGPL = (
    " V....D libopenh264         OpenH264\n V....D h264_videotoolbox  VideoToolbox H.264 Encoder\n"
)


def fake_ffmpeg(
    monkeypatch: pytest.MonkeyPatch, listing: str, *, probe_code: int = 0
) -> list[list[str]]:
    calls: list[list[str]] = []

    def run(command: list[str], **kwargs: Any) -> subprocess.CompletedProcess[Any]:
        calls.append(command)
        if "-encoders" in command:
            return subprocess.CompletedProcess(command, 0, stdout=listing)
        return subprocess.CompletedProcess(command, probe_code, stdout=b"", stderr=b"")

    render._video_encoder.cache_clear()  # pyright: ignore[reportPrivateUsage]
    monkeypatch.setattr(render.subprocess, "run", run)
    return calls


def test_a_mac_uses_videotoolbox_when_the_ffmpeg_lists_it_and_one_frame_encodes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = fake_ffmpeg(monkeypatch, LGPL)

    args = render._video_encoder("ffmpeg", "darwin")  # pyright: ignore[reportPrivateUsage]

    assert args[:2] == ("-c:v", "h264_videotoolbox")
    assert "libx264" not in args and "-crf" not in args
    probes = [c for c in calls if "-encoders" not in c]
    assert len(probes) == 1 and "h264_videotoolbox" in probes[0] and "h264_mf" not in probes[0]


def test_libx264_still_wins_on_a_mac_when_the_ffmpeg_has_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_ffmpeg(monkeypatch, " V....D libx264  libx264 H.264\n" + LGPL)

    args = render._video_encoder("ffmpeg-gpl", "darwin")  # pyright: ignore[reportPrivateUsage]

    assert args[:2] == ("-c:v", "libx264")


@pytest.mark.parametrize(
    ("listing", "probe_code"),
    [(" V....D libopenh264  OpenH264\n", 0), (LGPL, 1)],
    ids=["not listed", "listed but fails one frame"],
)
def test_a_mac_ffmpeg_without_a_working_encoder_says_to_install_ffmpeg_with_brew(
    monkeypatch: pytest.MonkeyPatch, listing: str, probe_code: int
) -> None:
    fake_ffmpeg(monkeypatch, listing, probe_code=probe_code)

    with pytest.raises(render.EncoderMissing) as caught:
        render._video_encoder("ffmpeg", "darwin")  # pyright: ignore[reportPrivateUsage]

    [notice] = notices_of(caught.value)
    assert notice.code == "render.noH264Mac"
    assert "brew install ffmpeg" in str(caught.value)
    assert "Windows" not in str(caught.value)


def test_the_windows_encoder_command_is_the_one_it_was(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = fake_ffmpeg(monkeypatch, " V....D h264_mf  H264 via MF\n")

    args = render._video_encoder("ffmpeg", "win32")  # pyright: ignore[reportPrivateUsage]

    assert args == ("-c:v", "h264_mf", "-rate_control", "quality", "-quality", "75")
    probe = next(c for c in calls if "-encoders" not in c)
    assert probe[probe.index("-frames:v") :] == [
        "-frames:v", "1", "-c:v", "h264_mf", "-rate_control", "quality", "-quality", "75",
        "-pix_fmt", "yuv420p", "-f", "null", os.devnull,
    ]  # fmt: skip


def test_the_no_h264_simulation_also_stops_a_mac_probe(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_ffmpeg(monkeypatch, LGPL)
    monkeypatch.setenv("VST_SIMULATE_NO_H264", "1")

    with pytest.raises(render.EncoderMissing):
        render._video_encoder("ffmpeg", "darwin")  # pyright: ignore[reportPrivateUsage]


# --- finding ffmpeg ---------------------------------------------------------------------------


def which_only_in(folder: str, found: str) -> Any:
    def which(name: str, mode: int = 0, path: str | None = None) -> str | None:
        return found if path is not None and folder in path.split(os.pathsep) else None

    return which


def test_a_mac_finds_ffmpeg_in_the_homebrew_folder_when_path_lacks_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv(audio.TOOL_DIR_ENV, raising=False)
    monkeypatch.setattr(
        shutil, "which", which_only_in("/opt/homebrew/bin", "/opt/homebrew/bin/ffmpeg")
    )

    assert audio.find_tool("ffmpeg", system="darwin") == Path("/opt/homebrew/bin/ffmpeg")


def test_windows_does_not_look_in_the_homebrew_folders(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(audio.TOOL_DIR_ENV, raising=False)
    monkeypatch.setattr(
        shutil, "which", which_only_in("/opt/homebrew/bin", "/opt/homebrew/bin/ffmpeg")
    )

    with pytest.raises(audio.AudioError) as caught:
        audio.find_tool("ffmpeg", system="win32")

    assert "Install ffmpeg, add it to PATH" in str(caught.value)
    assert "brew" not in str(caught.value)


def test_a_mac_without_ffmpeg_is_told_to_brew_install_it(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(audio.TOOL_DIR_ENV, raising=False)
    monkeypatch.setattr(shutil, "which", lambda *a, **k: None)

    with pytest.raises(audio.AudioError) as caught:
        audio.find_tool("ffprobe", system="darwin")

    assert "ffprobe was not found" in str(caught.value)
    assert "brew install ffmpeg" in str(caught.value)


def test_path_comes_before_homebrew_and_the_tool_dir_before_both(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv(audio.TOOL_DIR_ENV, raising=False)
    order: list[str | None] = []

    def which(name: str, mode: int = 0, path: str | None = None) -> str | None:
        order.append(path)
        return "/x/ffmpeg" if path is None or (path and "tooldir" in path) else None

    monkeypatch.setattr(shutil, "which", which)

    audio.find_tool("ffmpeg", tmp_path / "tooldir", "darwin")
    audio.find_tool("ffmpeg", system="darwin")

    assert order[0] is not None and "tooldir" in order[0]
    assert order[1] is None


# --- the process guard on a Mac ---------------------------------------------------------------


def sleeper() -> subprocess.Popen[bytes]:
    return subprocess.Popen([sys.executable, "-c", "import time; time.sleep(120)"])


@pytest.fixture
def mac_guard(monkeypatch: pytest.MonkeyPatch) -> Any:
    monkeypatch.setattr("sys.platform", "darwin")
    monkeypatch.setattr(process_guard, "_hooked", True)  # no atexit or signal hooks in a test
    monkeypatch.setattr(process_guard, "_signals_hooked", True)
    return process_guard.KillOnClose


def test_closing_the_guard_on_a_mac_stops_a_child_that_ignores_nothing(mac_guard: Any) -> None:
    child = sleeper()
    guard = mac_guard()
    guard.adopt(child)

    started = time.monotonic()
    guard.close()

    assert child.poll() is not None
    assert time.monotonic() - started < 10


def test_a_child_that_already_ended_is_left_alone(mac_guard: Any) -> None:
    child = subprocess.Popen([sys.executable, "-c", "pass"])
    child.wait()
    guard = mac_guard()
    guard.adopt(child)

    guard.close()

    assert child.returncode == 0


def test_closing_twice_is_harmless(mac_guard: Any) -> None:
    child = sleeper()
    guard = mac_guard()
    guard.adopt(child)

    guard.close()
    guard.close()

    assert child.poll() is not None


class FakeChild:
    def __init__(self, pid: int, *, stubborn: bool = False) -> None:
        self.pid = pid
        self.stubborn = stubborn
        self.signals: list[int] = []
        self.code: int | None = None

    def poll(self) -> int | None:
        return self.code

    def send_signal(self, sig: int) -> None:
        self.signals.append(sig)
        if not self.stubborn or sig == getattr(signal, "SIGKILL", signal.SIGTERM):
            self.code = -sig

    def wait(self, timeout: float | None = None) -> int:
        if self.code is None:
            raise subprocess.TimeoutExpired("fake", timeout or 0)
        return self.code


def test_a_child_that_leads_its_own_group_is_stopped_through_the_group(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sent: list[tuple[int, int]] = []
    monkeypatch.setattr(os, "getpgid", lambda pid: pid, raising=False)
    monkeypatch.setattr(os, "killpg", lambda pid, sig: sent.append((pid, sig)), raising=False)
    child = FakeChild(4242)

    process_guard._stop(child, signal.SIGTERM)  # pyright: ignore[reportPrivateUsage, reportArgumentType]

    assert sent == [(4242, signal.SIGTERM)]
    assert child.signals == []


def test_a_child_in_our_own_group_is_signalled_alone_never_through_the_group(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sent: list[tuple[int, int]] = []
    monkeypatch.setattr(os, "getpgid", lambda pid: 1, raising=False)
    monkeypatch.setattr(os, "killpg", lambda pid, sig: sent.append((pid, sig)), raising=False)
    child = FakeChild(4242)

    process_guard._stop(child, signal.SIGTERM)  # pyright: ignore[reportPrivateUsage, reportArgumentType]

    assert sent == []
    assert child.signals == [signal.SIGTERM]


def test_a_child_that_ignores_the_polite_stop_is_killed_after_the_grace_time(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(process_guard, "_TERM_GRACE_S", 0.01)
    monkeypatch.delattr(os, "getpgid", raising=False)
    stubborn, polite = FakeChild(1, stubborn=True), FakeChild(2)

    process_guard._stop_all([stubborn, polite])  # pyright: ignore[reportPrivateUsage, reportArgumentType]

    kill = getattr(signal, "SIGKILL", signal.SIGTERM)
    assert stubborn.signals[0] == signal.SIGTERM and stubborn.signals[-1] == kill
    assert polite.signals == [signal.SIGTERM]


def test_the_exit_hook_closes_every_guard_that_is_still_alive(mac_guard: Any) -> None:
    child = sleeper()
    guard = mac_guard()
    guard.adopt(child)

    process_guard._stop_every_watched()  # pyright: ignore[reportPrivateUsage]

    assert child.poll() is not None


def test_a_stop_signal_stops_the_children_then_lets_the_signal_do_what_it_would_have(
    mac_guard: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    child = sleeper()
    guard = mac_guard()
    guard.adopt(child)
    handlers: list[tuple[int, Any]] = []
    killed: list[tuple[int, int]] = []
    monkeypatch.setattr(
        signal, "signal", lambda number, handler: handlers.append((number, handler))
    )
    real_kill = os.kill

    def kill(pid: int, sig: int) -> None:
        if pid == os.getpid():
            killed.append((pid, sig))
        else:
            real_kill(pid, sig)

    monkeypatch.setattr(os, "kill", kill)

    process_guard._on_stop_signal(signal.SIGTERM, None)  # pyright: ignore[reportPrivateUsage]

    assert child.poll() is not None
    assert handlers == [(signal.SIGTERM, signal.SIG_DFL)]
    assert killed == [(os.getpid(), signal.SIGTERM)]


def test_the_handlers_go_in_only_where_nothing_else_has_one(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("sys.platform", "darwin")
    monkeypatch.setattr(process_guard, "_hooked", False)
    monkeypatch.setattr(process_guard, "_signals_hooked", False)
    installed: list[int] = []
    registered: list[Any] = []
    monkeypatch.setattr(process_guard.atexit, "register", lambda fn: registered.append(fn))
    monkeypatch.setattr(signal, "signal", lambda number, handler: installed.append(number))
    monkeypatch.setattr(signal, "getsignal", lambda number: signal.SIG_DFL)
    monkeypatch.setattr(process_guard, "_STOP_SIGNALS", ("SIGTERM", "SIGINT"))

    process_guard.KillOnClose()

    assert registered == [process_guard._stop_every_watched]  # pyright: ignore[reportPrivateUsage]
    assert installed == [signal.SIGTERM, signal.SIGINT]
    monkeypatch.setattr(signal, "getsignal", lambda number: lambda *a: None)
    installed.clear()
    monkeypatch.setattr(process_guard, "_hooked", False)
    monkeypatch.setattr(process_guard, "_signals_hooked", False)

    process_guard.KillOnClose()

    assert installed == []


def fake_signals(monkeypatch: pytest.MonkeyPatch) -> tuple[list[int], list[Any]]:
    monkeypatch.setattr("sys.platform", "darwin")
    monkeypatch.setattr(process_guard, "_hooked", False)
    monkeypatch.setattr(process_guard, "_signals_hooked", False)
    installed: list[int] = []
    registered: list[Any] = []
    monkeypatch.setattr(process_guard.atexit, "register", lambda fn: registered.append(fn))
    monkeypatch.setattr(signal, "signal", lambda number, handler: installed.append(number))
    monkeypatch.setattr(signal, "getsignal", lambda number: signal.SIG_DFL)
    monkeypatch.setattr(process_guard, "_STOP_SIGNALS", ("SIGTERM", "SIGINT"))
    return installed, registered


def test_a_first_guard_made_in_a_worker_thread_does_not_use_up_the_signal_handlers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    installed, registered = fake_signals(monkeypatch)
    guards: list[process_guard.KillOnClose] = []
    worker = threading.Thread(target=lambda: guards.append(process_guard.KillOnClose()))
    worker.start()
    worker.join()

    assert installed == []
    assert registered == [process_guard._stop_every_watched]  # pyright: ignore[reportPrivateUsage]

    process_guard.stop_children_on_signals()

    assert installed == [signal.SIGTERM, signal.SIGINT]


def test_a_server_that_only_makes_guards_in_workers_still_gets_the_handlers_at_start(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    installed, _ = fake_signals(monkeypatch)
    worker = threading.Thread(target=process_guard.stop_children_on_signals)
    worker.start()
    worker.join()
    assert installed == []

    process_guard.stop_children_on_signals()
    process_guard.stop_children_on_signals()

    assert installed == [signal.SIGTERM, signal.SIGINT]


def test_a_closed_terminal_stops_the_children_because_sighup_is_one_of_the_signals(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("sys.platform", "darwin")
    monkeypatch.setattr(process_guard, "_signals_hooked", False)
    monkeypatch.setattr(signal, "SIGHUP", 1, raising=False)
    installed: list[int] = []
    monkeypatch.setattr(signal, "signal", lambda number, handler: installed.append(number))
    monkeypatch.setattr(signal, "getsignal", lambda number: signal.SIG_DFL)

    process_guard.stop_children_on_signals()

    assert installed == [signal.SIGTERM, 1]


def test_the_handlers_are_left_out_on_windows(monkeypatch: pytest.MonkeyPatch) -> None:
    installed, _ = fake_signals(monkeypatch)
    monkeypatch.setattr("sys.platform", "win32")

    process_guard.stop_children_on_signals()

    assert installed == []


def test_the_service_asks_for_the_handlers_before_it_serves(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from backend import main as service

    order: list[str] = []
    monkeypatch.setattr(service, "stop_children_on_signals", lambda: order.append("handlers"))
    monkeypatch.setattr(service, "serve", lambda *args: order.append("serve"))

    assert service.main(["--user-data", str(tmp_path)]) == 0

    assert order == ["handlers", "serve"]


def test_a_child_that_ignores_the_polite_stop_gets_a_kill_signal_of_its_own(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_kill = 9
    monkeypatch.setattr(signal, "SIGKILL", fake_kill, raising=False)
    monkeypatch.setattr(process_guard, "_TERM_GRACE_S", 0.01)
    monkeypatch.delattr(os, "getpgid", raising=False)
    stubborn = FakeChild(1, stubborn=True)

    process_guard._stop_all([stubborn])  # pyright: ignore[reportPrivateUsage, reportArgumentType]

    assert stubborn.signals == [signal.SIGTERM, fake_kill]
    assert stubborn.code == -fake_kill


@pytest.mark.skipif(sys.platform == "win32", reason="needs real signals")
def test_a_real_child_that_ignores_sigterm_is_killed_after_the_grace_time(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(process_guard, "_TERM_GRACE_S", 0.3)
    code = (
        "import signal, time; signal.signal(signal.SIGTERM, signal.SIG_IGN); "
        "print(1, flush=True); time.sleep(120)"
    )
    child = subprocess.Popen([sys.executable, "-c", code], stdout=subprocess.PIPE)
    assert child.stdout is not None
    child.stdout.readline()

    process_guard._stop_all([child])  # pyright: ignore[reportPrivateUsage]

    assert child.wait(timeout=10) == -signal.SIGKILL  # pyright: ignore[reportAttributeAccessIssue, reportUnknownMemberType]
    child.stdout.close()
