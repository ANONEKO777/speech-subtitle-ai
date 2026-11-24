"""Unpacking a `.tar.gz` runtime (the macOS builds) with the safety the zip path has.

The archives are built here; nothing is downloaded. A permission bit cannot be read back on
Windows, so the tests watch the `chmod` the extractor asks for."""

from __future__ import annotations

import io
import os
import tarfile
from collections.abc import Callable
from pathlib import Path

import pytest

from backend.manager import download
from backend.manager.download import DownloadError, FailureKind, Item, Job, Plan

Entry = Callable[[tarfile.TarFile], None]


def file_entry(name: str, data: bytes = b"x", mode: int = 0o644) -> Entry:
    def add(tar: tarfile.TarFile) -> None:
        info = tarfile.TarInfo(name)
        info.size = len(data)
        info.mode = mode
        tar.addfile(info, io.BytesIO(data))

    return add


def dir_entry(name: str, mode: int = 0o755) -> Entry:
    def add(tar: tarfile.TarFile) -> None:
        info = tarfile.TarInfo(name)
        info.type = tarfile.DIRTYPE
        info.mode = mode
        tar.addfile(info)

    return add


def link_entry(name: str, target: str, *, hard: bool = False) -> Entry:
    def add(tar: tarfile.TarFile) -> None:
        info = tarfile.TarInfo(name)
        info.type = tarfile.LNKTYPE if hard else tarfile.SYMTYPE
        info.linkname = target
        tar.addfile(info)

    return add


def device_entry(name: str) -> Entry:
    def add(tar: tarfile.TarFile) -> None:
        info = tarfile.TarInfo(name)
        info.type = tarfile.CHRTYPE
        tar.addfile(info)

    return add


def make_tar(path: Path, *entries: Entry) -> Path:
    with tarfile.open(path, "w:gz") as tar:
        for add in entries:
            add(tar)
    return path


def unpack_to(archive: Path, out: Path) -> None:
    out.mkdir(exist_ok=True)
    download.extract_tar(archive, out, Job(Plan("x", ())))


def can_symlink(tmp_path: Path) -> bool:
    try:
        os.symlink("target", tmp_path / "probe-link")
    except (OSError, NotImplementedError):
        return False
    (tmp_path / "probe-link").unlink()
    return True


def refused(archive: Path, out: Path) -> DownloadError:
    with pytest.raises(DownloadError) as caught:
        unpack_to(archive, out)
    assert caught.value.failure.kind is FailureKind.ARCHIVE
    return caught.value


def test_a_tarball_unpacks_with_its_folders_and_files(tmp_path: Path) -> None:
    archive = make_tar(
        tmp_path / "rt.tar.gz",
        dir_entry("./"),
        dir_entry("./llama-b12068/"),
        file_entry("./llama-b12068/llama-server", b"MACH-O", 0o755),
        file_entry("llama-b12068/libllama.dylib", b"lib"),
    )
    out = tmp_path / "out"

    unpack_to(archive, out)

    assert (out / "llama-b12068" / "llama-server").read_bytes() == b"MACH-O"
    assert (out / "llama-b12068" / "libllama.dylib").read_bytes() == b"lib"


def test_a_program_keeps_its_execute_bit_and_loses_set_user_id(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    asked: dict[str, int] = {}
    real = Path.chmod

    def chmod(self: Path, mode: int, **kwargs: bool) -> None:
        asked[self.name] = mode
        real(self, mode, **kwargs)

    monkeypatch.setattr(Path, "chmod", chmod)
    archive = make_tar(
        tmp_path / "rt.tar.gz",
        file_entry("tool", b"x", 0o755),
        file_entry("suid", b"x", 0o4755),
        file_entry("data", b"x", 0o444),
    )

    unpack_to(archive, tmp_path / "out")

    assert asked["tool"] == 0o755
    assert asked["suid"] == 0o755
    assert asked["data"] & 0o600 == 0o600
    assert asked["data"] & 0o111 == 0


def test_a_member_never_keeps_write_access_for_the_group_or_others(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    asked: dict[str, int] = {}
    real = Path.chmod

    def chmod(self: Path, mode: int, **kwargs: bool) -> None:
        asked[self.name] = mode
        real(self, mode, **kwargs)

    monkeypatch.setattr(Path, "chmod", chmod)
    archive = make_tar(
        tmp_path / "rt.tar.gz",
        dir_entry("open-dir", 0o1777),
        file_entry("open-tool", b"x", 0o777),
        file_entry("open-data", b"x", 0o666),
        file_entry("group-write", b"x", 0o664),
        file_entry("source", b"x", 0o755),
        link_entry("hard-copy", "source", hard=True),
    )

    unpack_to(archive, tmp_path / "out")

    assert asked["open-dir"] == 0o755
    assert asked["open-tool"] == 0o755
    assert asked["open-data"] == 0o644
    assert asked["group-write"] == 0o644
    assert asked["hard-copy"] & 0o022 == 0


@pytest.mark.parametrize(
    "name",
    [
        "../evil.txt",
        "a/../../evil.txt",
        "/abs/evil.txt",
        "C:evil.txt",
        "..\\evil.txt",
        "a/..",
        "..",
    ],
)
def test_a_member_that_could_leave_the_folder_is_refused_and_nothing_is_written(
    tmp_path: Path, name: str
) -> None:
    archive = make_tar(tmp_path / "rt.tar.gz", file_entry("fine.txt"), file_entry(name))
    out = tmp_path / "data" / "out"
    out.parent.mkdir()

    refused(archive, out)

    assert not (out / "fine.txt").exists()
    assert [p.name for p in tmp_path.rglob("evil*")] == []


@pytest.mark.parametrize("target", ["/etc/passwd", "../outside", "a/../../b", "C:\\x", "", "a\\b"])
def test_a_symlink_that_could_point_outside_is_refused(tmp_path: Path, target: str) -> None:
    archive = make_tar(tmp_path / "rt.tar.gz", link_entry("lib.dylib", target))

    error = refused(archive, tmp_path / "out")

    assert "unsafe link" in error.failure.message
    assert not (tmp_path / "out" / "lib.dylib").is_symlink()


def test_a_hard_link_to_a_path_outside_is_refused(tmp_path: Path) -> None:
    archive = make_tar(tmp_path / "rt.tar.gz", link_entry("copy", "../secret", hard=True))

    refused(archive, tmp_path / "out")


def test_a_hard_link_to_a_file_that_is_not_there_is_refused(tmp_path: Path) -> None:
    archive = make_tar(tmp_path / "rt.tar.gz", link_entry("copy", "missing", hard=True))

    error = refused(archive, tmp_path / "out")

    assert "missing file" in error.failure.message


def test_a_hard_link_becomes_a_copy_of_the_file(tmp_path: Path) -> None:
    archive = make_tar(
        tmp_path / "rt.tar.gz",
        file_entry("a/real", b"data", 0o755),
        link_entry("b", "a/real", hard=True),
    )

    unpack_to(archive, tmp_path / "out")

    assert (tmp_path / "out" / "b").read_bytes() == b"data"


def test_a_device_file_is_refused(tmp_path: Path) -> None:
    archive = make_tar(tmp_path / "rt.tar.gz", device_entry("dev"))

    error = refused(archive, tmp_path / "out")

    assert "unsupported entry" in error.failure.message


def test_a_symlink_to_a_file_next_to_it_is_made(tmp_path: Path) -> None:
    if not can_symlink(tmp_path):
        pytest.skip("this account cannot create symlinks")
    archive = make_tar(
        tmp_path / "rt.tar.gz",
        file_entry("llama/libllama.0.dylib", b"lib"),
        link_entry("llama/libllama.dylib", "libllama.0.dylib"),
    )
    out = tmp_path / "out"

    unpack_to(archive, out)

    assert (out / "llama" / "libllama.dylib").is_symlink()
    assert (out / "llama" / "libllama.dylib").read_bytes() == b"lib"


def test_a_corrupt_gzip_is_an_archive_failure_and_not_a_disk_failure(tmp_path: Path) -> None:
    archive = tmp_path / "rt.tar.gz"
    archive.write_bytes(b"not a gzip file at all")

    refused(archive, tmp_path / "out")


def test_a_truncated_tarball_is_an_archive_failure(tmp_path: Path) -> None:
    good = make_tar(tmp_path / "good.tar.gz", file_entry("big", os.urandom(200_000)))
    cut = tmp_path / "cut.tar.gz"
    cut.write_bytes(good.read_bytes()[:5_000])

    refused(cut, tmp_path / "out")


def test_the_archive_name_decides_how_it_is_unpacked(tmp_path: Path) -> None:
    tar_path = make_tar(tmp_path / "rt.tgz", file_entry("a.txt", b"t"))
    out = tmp_path / "out"
    out.mkdir()

    download.extract_archive(tar_path, out, Job(Plan("x", ())))

    assert (out / "a.txt").read_bytes() == b"t"


def test_a_tar_runtime_installs_through_unpack_and_checks_its_entry_point(tmp_path: Path) -> None:
    archive = make_tar(
        tmp_path / "rt.tar.gz",
        file_entry("crispasr-macos-arm64/crispasr", b"MACH-O", 0o755),
    )
    item = Item("https://example.invalid/rt.tar.gz", archive, "0" * 64, archive.stat().st_size)
    target = tmp_path / "runtimes" / "rt"
    plan = Plan("rt", (item,), unpack_to=target, entry_point="crispasr-macos-arm64/crispasr")

    download.unpack(plan, Job(plan))

    assert (target / "crispasr-macos-arm64" / "crispasr").read_bytes() == b"MACH-O"
    assert not archive.exists()


def test_a_tar_runtime_without_its_entry_point_is_refused_and_leaves_no_folder(
    tmp_path: Path,
) -> None:
    archive = make_tar(tmp_path / "rt.tar.gz", file_entry("other/tool", b"x"))
    item = Item("https://example.invalid/rt.tar.gz", archive, "0" * 64, archive.stat().st_size)
    target = tmp_path / "runtimes" / "rt"
    plan = Plan("rt", (item,), unpack_to=target, entry_point="crispasr-macos-arm64/crispasr")

    with pytest.raises(DownloadError) as caught:
        download.unpack(plan, Job(plan))

    assert "does not contain" in caught.value.failure.message
    assert not target.exists()


def test_a_symlink_is_made_relative_to_its_own_folder(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    made: list[tuple[str, Path]] = []

    def fake_symlink(source: str, link: Path) -> None:
        made.append((source, Path(link)))
        Path(link).write_bytes(b"")

    monkeypatch.setattr(os, "symlink", fake_symlink)
    archive = make_tar(
        tmp_path / "rt.tar.gz", link_entry("llama/libllama.dylib", "libllama.0.dylib")
    )
    out = tmp_path / "out"

    unpack_to(archive, out)

    assert made == [("libllama.0.dylib", out.resolve() / "llama" / "libllama.dylib")]


def test_a_link_that_really_points_outside_after_it_is_made_is_removed_and_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    made: list[Path] = []

    def fake_symlink(source: str, link: Path) -> None:
        made.append(Path(link))
        Path(link).write_bytes(b"")

    monkeypatch.setattr(os, "symlink", fake_symlink)
    real = os.path.realpath

    def realpath(path: str | os.PathLike[str], **kwargs: bool) -> str:
        if made and Path(path).name == "lib.dylib":
            return str(tmp_path.parent / "elsewhere")
        return real(path, **kwargs)

    monkeypatch.setattr(os.path, "realpath", realpath)
    archive = make_tar(tmp_path / "rt.tar.gz", link_entry("lib.dylib", "lib.0.dylib"))
    out = tmp_path / "out"

    error = refused(archive, out)

    assert "unsafe link" in error.failure.message
    assert not (out / "lib.dylib").exists()
