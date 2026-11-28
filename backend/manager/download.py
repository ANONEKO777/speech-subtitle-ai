from __future__ import annotations

import errno
import gzip
import hashlib
import http.client
import logging
import os
import queue
import re
import shutil
import tarfile
import threading
import time
import urllib.error
import urllib.request
import uuid
import zipfile
import zlib
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, replace
from enum import StrEnum
from pathlib import Path
from types import MappingProxyType
from typing import Any

from backend.core import notices
from backend.core.notices import Notice, noticed, notices_of

log = logging.getLogger(__name__)
CHUNK = 1 << 20
PART_SUFFIX = ".part"
STAGING_SUFFIX = ".extracting"
REPLACING_SUFFIX = ".new"
OLD_SUFFIX = ".old"
USER_AGENT = "video-subtitle-translator/0"
_RETRYABLE_HTTP = frozenset({408, 425, 429})
_SPEED_WINDOW_S = 0.5
_KEEP_JOBS = 100
_NON_NAME = re.compile(r"^[\s.]*$")


class JobState(StrEnum):
    QUEUED = "queued"
    DOWNLOADING = "downloading"
    VERIFYING = "verifying"
    EXTRACTING = "extracting"
    DONE = "done"
    FAILED = "failed"
    CANCELLED = "cancelled"


TERMINAL = frozenset({JobState.DONE, JobState.FAILED, JobState.CANCELLED})

_NEXT: Mapping[JobState, frozenset[JobState]] = MappingProxyType(
    {
        JobState.QUEUED: frozenset({JobState.DOWNLOADING, JobState.DONE, JobState.CANCELLED}),
        JobState.DOWNLOADING: frozenset(
            {
                JobState.VERIFYING,
                JobState.EXTRACTING,
                JobState.DONE,
                JobState.FAILED,
                JobState.CANCELLED,
            }
        ),
        JobState.VERIFYING: frozenset(
            {
                JobState.DOWNLOADING,
                JobState.EXTRACTING,
                JobState.DONE,
                JobState.FAILED,
                JobState.CANCELLED,
            }
        ),
        JobState.EXTRACTING: frozenset({JobState.DONE, JobState.FAILED, JobState.CANCELLED}),
        JobState.DONE: frozenset(),
        JobState.FAILED: frozenset(),
        JobState.CANCELLED: frozenset(),
    }
)


class InstallState(StrEnum):
    NOT_INSTALLED = "not_installed"
    PARTIAL = "partial"
    INSTALLING = "installing"
    INSTALLED = "installed"


class Outcome(StrEnum):
    INSTALLED = "installed"
    ALREADY_PRESENT = "already_present"


class FailureKind(StrEnum):
    NETWORK = "network"
    HTTP = "http"
    HASH_MISMATCH = "hash_mismatch"
    SIZE_MISMATCH = "size_mismatch"
    INSUFFICIENT_SPACE = "insufficient_space"
    ARCHIVE = "archive"
    IO = "io"


@dataclass(frozen=True, slots=True)
class Failure:
    kind: FailureKind
    message: str
    needed_bytes: int | None = None
    available_bytes: int | None = None
    message_notices: tuple[Notice, ...] = ()
    """The notices inside `message`, outermost first. What another program said has none."""


class DownloadError(Exception):
    def __init__(self, failure: Failure) -> None:
        super().__init__(failure.message)
        self.failure = failure


def _failed(kind: FailureKind, said: Notice, *quoted: Notice) -> DownloadError:
    """A failure that says `said`, which may quote the sentences in `quoted`."""
    return DownloadError(Failure(kind, said.message, message_notices=(said, *quoted)))


class Cancelled(Exception):
    pass


class _Transient(Exception):
    pass


@dataclass(frozen=True, slots=True)
class Item:
    url: str
    dest: Path
    sha256: str
    size_bytes: int


@dataclass(frozen=True, slots=True)
class Plan:
    asset_id: str
    items: tuple[Item, ...]
    unpack_to: Path | None = None
    entry_point: str | None = None
    shared: tuple[Item, ...] = ()
    replacing: bool = False

    def is_satisfied(self) -> bool:
        if self.replacing:
            return False
        if self.unpack_to is not None:
            return self.unpack_to.is_dir()
        return all(_present(item) for item in self.items)

    def state(self) -> InstallState:
        if self.is_satisfied():
            return InstallState.INSTALLED
        leftovers = [
            p
            for item in self.items
            if item not in self.shared
            for p in (item.dest, part_of(item.dest))
        ]
        if self.unpack_to is not None:
            leftovers.append(staging_of(self.unpack_to))
        return (
            InstallState.PARTIAL
            if any(p.exists() for p in leftovers)
            else InstallState.NOT_INSTALLED
        )


@dataclass(frozen=True, slots=True)
class RetryPolicy:
    max_failures: int = 10
    backoff_s: float = 1.0
    max_backoff_s: float = 30.0
    timeout_s: float = 30.0


@dataclass(frozen=True, slots=True)
class JobStatus:
    id: str
    asset_id: str
    state: JobState
    bytes_done: int
    bytes_total: int
    speed_bps: float
    resumed_from: int
    retries: int
    note: str | None
    outcome: Outcome | None
    failure: Failure | None


Opener = Callable[[urllib.request.Request, float], Any]


def _urlopen(request: urllib.request.Request, timeout: float) -> Any:
    return urllib.request.urlopen(request, timeout=timeout)


def part_of(dest: Path) -> Path:
    return dest.with_name(dest.name + PART_SUFFIX)


def staging_of(folder: Path) -> Path:
    return folder.with_name(folder.name + STAGING_SUFFIX)


def replacing_of(dest: Path) -> Path:
    return dest.with_name(dest.name + REPLACING_SUFFIX)


def _present(item: Item) -> bool:
    try:
        return item.dest.stat().st_size == item.size_bytes
    except OSError:
        return False


def format_bytes(count: int) -> str:
    power = min((count.bit_length() - 1) // 10, 3)
    if power < 1:
        return f"{count} B"
    return f"{count / (1 << 10 * power):.1f} {('KiB', 'MiB', 'GiB')[power - 1]}"


class Job:
    def __init__(self, plan: Plan) -> None:
        self.id = uuid.uuid4().hex[:12]
        self.plan = plan
        self.cancel = threading.Event()
        self.finished = threading.Event()
        self._lock = threading.Lock()
        self._state = JobState.QUEUED
        self._total = sum(item.size_bytes for item in plan.items)
        self._settled = 0
        self._current = 0
        self._speed = 0.0
        self._window = (time.monotonic(), 0)
        self._resumed_from = 0
        self._retries = 0
        self._note: str | None = None
        self._outcome: Outcome | None = None
        self._failure: Failure | None = None

    def snapshot(self) -> JobStatus:
        with self._lock:
            done = self._total if self._outcome else self._settled + self._current
            return JobStatus(
                id=self.id,
                asset_id=self.plan.asset_id,
                state=self._state,
                bytes_done=done,
                bytes_total=self._total,
                speed_bps=self._speed if self._state is JobState.DOWNLOADING else 0.0,
                resumed_from=self._resumed_from,
                retries=self._retries,
                note=self._note,
                outcome=self._outcome,
                failure=self._failure,
            )

    def move(self, state: JobState) -> None:
        with self._lock:
            if state is self._state:
                return
            if state not in _NEXT[self._state]:
                raise AssertionError(f"illegal job transition {self._state} -> {state}")
            self._state = state
            if state in TERMINAL:
                self.finished.set()

    def try_start(self) -> bool:
        with self._lock:
            if self._state is not JobState.QUEUED:
                return False
            self._state = JobState.DOWNLOADING
            self._window = (time.monotonic(), self._settled)
            return True

    def request_cancel(self) -> None:
        self.cancel.set()
        with self._lock:
            if self._state is JobState.QUEUED:
                self._state = JobState.CANCELLED
                self.finished.set()

    def complete(self, outcome: Outcome) -> None:
        self.move(JobState.DONE)
        with self._lock:
            self._outcome = outcome
            self._note = None

    def fail(self, failure: Failure) -> None:
        with self._lock:
            self._failure = failure
            self._note = None
        self.move(JobState.FAILED)

    def raise_if_cancelled(self) -> None:
        if self.cancel.is_set():
            raise Cancelled

    def advance(self, received: int) -> None:
        with self._lock:
            self._current = received
            now = time.monotonic()
            began, base = self._window
            if now - began >= _SPEED_WINDOW_S:
                rate = (self._settled + received - base) / (now - began)
                self._speed = rate if self._speed == 0 else (self._speed + rate) / 2
                self._window = (now, self._settled + received)

    def settle(self, size: int) -> None:
        with self._lock:
            self._settled += size
            self._current = 0
            self._window = (time.monotonic(), self._settled)

    def note_resume(self, offset: int) -> None:
        with self._lock:
            self._resumed_from = offset

    def note_retry(self, note: str | None) -> None:
        with self._lock:
            if note is not None:
                self._retries += 1
            self._note = note


def _anchor(path: Path) -> Path:
    probe = path
    while not probe.exists() and probe != probe.parent:
        probe = probe.parent
    return probe


def check_space(needs: Iterable[tuple[Path, int]]) -> None:
    by_volume: dict[int, tuple[Path, int]] = {}
    for folder, count in needs:
        anchor = _anchor(folder)
        volume = anchor.stat().st_dev
        first, total = by_volume.get(volume, (anchor, 0))
        by_volume[volume] = (first, total + count)
    for anchor, needed in by_volume.values():
        available = shutil.disk_usage(anchor).free
        if needed > available:
            said = notices.NOT_ENOUGH_SPACE(
                folder=str(anchor), needed=format_bytes(needed), free=format_bytes(available)
            )
            raise DownloadError(
                Failure(
                    FailureKind.INSUFFICIENT_SPACE,
                    said.message,
                    needed_bytes=needed,
                    available_bytes=available,
                    message_notices=(said,),
                )
            )


def _remaining(item: Item) -> int:
    if _present(item):
        return 0
    try:
        held = part_of(item.dest).stat().st_size
    except OSError:
        held = 0
    return item.size_bytes - (held if held <= item.size_bytes else 0)


def _hash_existing(path: Path, job: Job) -> Any:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while block := handle.read(CHUNK):
            job.raise_if_cancelled()
            digest.update(block)
    return digest


def _content_range_start(header: str | None) -> int | None:
    match = re.fullmatch(r"bytes (\d+)-\d+/(?:\d+|\*)", header or "")
    return int(match.group(1)) if match else None


def _attempt(item: Item, job: Job, url: str, opener: Opener, policy: RetryPolicy) -> str:
    part = part_of(item.dest)
    start = part.stat().st_size if part.exists() else 0
    if start > item.size_bytes:
        part.unlink()
        start = 0
    digest = _hash_existing(part, job) if start else hashlib.sha256()
    job.advance(start)
    if start == item.size_bytes:
        return digest.hexdigest()
    check_space([(item.dest.parent, item.size_bytes - start)])
    headers = {"User-Agent": USER_AGENT}
    if start:
        headers["Range"] = f"bytes={start}-"
    try:
        response = opener(urllib.request.Request(url, headers=headers), policy.timeout_s)
    except urllib.error.HTTPError as exc:
        exc.close()
        if exc.code == 416 and start:
            part.unlink(missing_ok=True)
            raise noticed(_Transient, notices.RESUME_REFUSED()) from exc
        if exc.code in _RETRYABLE_HTTP or exc.code >= 500:
            raise _Transient(f"HTTP {exc.code}") from exc
        answered = notices.DOWNLOAD_HTTP(url=url, status=str(exc.code))
        raise _failed(FailureKind.HTTP, answered) from exc
    except (urllib.error.URLError, OSError, http.client.HTTPException) as exc:
        raise _Transient(str(exc)) from exc
    with response:
        append = False
        if start:
            if (
                response.status == 206
                and _content_range_start(response.headers.get("Content-Range")) == start
            ):
                append = True
                job.note_resume(start)
            else:
                start, digest = 0, hashlib.sha256()
        length = response.headers.get("Content-Length")
        if length and length.isdigit() and int(length) != item.size_bytes - start:
            wrong = notices.WRONG_SIZE(url=url, sent=length, expected=str(item.size_bytes - start))
            raise _failed(FailureKind.SIZE_MISMATCH, wrong)
        received = start
        buffer = bytearray(CHUNK)
        view = memoryview(buffer)
        try:
            with part.open("ab" if append else "wb", buffering=CHUNK) as out:
                job.advance(received)
                while received < item.size_bytes:
                    job.raise_if_cancelled()
                    want = min(CHUNK, item.size_bytes - received)
                    try:
                        got = response.readinto(view[:want])
                    except (OSError, http.client.HTTPException) as exc:
                        raise _Transient(str(exc)) from exc
                    if not got:
                        break
                    out.write(view[:got])
                    digest.update(view[:got])
                    received += got
                    job.advance(received)
                out.flush()
                os.fsync(out.fileno())
        except OSError as exc:
            raise _disk_failure(exc) from exc
    if received < item.size_bytes:
        raise noticed(_Transient, notices.CONNECTION_CUT())
    return digest.hexdigest()


_LOCKED_WINERRORS = frozenset({5, 32, 33})
_LOCKED_ERRNOS = frozenset({errno.EACCES, errno.EPERM, errno.EBUSY})


def is_locked(exc: BaseException) -> bool:
    """A Windows permission or sharing error: another program holds the file or folder."""
    return isinstance(exc, OSError) and (
        isinstance(exc, PermissionError)
        or getattr(exc, "winerror", None) in _LOCKED_WINERRORS
        or exc.errno in _LOCKED_ERRNOS
    )


def _locked(exc: OSError) -> Notice:
    log.warning("locked path: %r", exc)
    path, other = exc.filename, exc.filename2
    if path and other:
        return notices.LOCKED_WHILE_MOVING(path=str(path), target=str(other))
    if path or other:
        return notices.LOCKED(path=str(path or other))
    return notices.LOCKED_SOMEWHERE()


def os_error_said(exc: Exception) -> tuple[str, tuple[Notice, ...]]:
    """What to show a user for a failed file operation, and the notices inside it. A locked path
    is named, with what to do about it. The original error goes to the log."""
    if isinstance(exc, OSError) and is_locked(exc):
        said = _locked(exc)
        return said.message, (said,)
    text = f"{type(exc).__name__}: {exc}"
    return text, notices_of(exc, text)


def _disk_failure(exc: OSError) -> DownloadError:
    if is_locked(exc):
        text, found = os_error_said(exc)
        return DownloadError(Failure(FailureKind.IO, text, message_notices=found))
    kind = FailureKind.INSUFFICIENT_SPACE if exc.errno == errno.ENOSPC else FailureKind.IO
    return _failed(kind, notices.DISK_WRITE_FAILED(error=str(exc)))


def fetch(item: Item, job: Job, url: str, opener: Opener, policy: RetryPolicy) -> None:
    if _present(item):
        job.settle(item.size_bytes)
        return
    item.dest.parent.mkdir(parents=True, exist_ok=True)
    part = part_of(item.dest)
    failures = 0
    while True:
        job.raise_if_cancelled()
        before = part.stat().st_size if part.exists() else 0
        try:
            actual = _attempt(item, job, url, opener, policy)
            break
        except _Transient as exc:
            after = part.stat().st_size if part.exists() else 0
            failures = 1 if after > before else failures + 1
            if failures > policy.max_failures:
                stopped = notices.DOWNLOAD_INTERRUPTED(
                    retries=str(policy.max_failures), reason=str(exc)
                )
                raise _failed(FailureKind.NETWORK, stopped, *notices_of(exc)) from exc
            delay = min(policy.backoff_s * 2 ** (failures - 1), policy.max_backoff_s)
            job.note_retry(f"{exc}; retrying in {delay:.0f}s ({failures}/{policy.max_failures})")
            job.cancel.wait(delay)
    job.note_retry(None)
    job.move(JobState.VERIFYING)
    if actual != item.sha256:
        part.unlink(missing_ok=True)
        bad = notices.HASH_MISMATCH(file=item.dest.name, expected=item.sha256, actual=actual)
        raise _failed(FailureKind.HASH_MISMATCH, bad)
    try:
        os.replace(part, item.dest)
    except OSError as exc:
        raise _disk_failure(exc) from exc
    job.settle(item.size_bytes)


def _unsafe_path(name: str) -> DownloadError:
    return _failed(FailureKind.ARCHIVE, notices.UNSAFE_PATH(name=repr(name)))


def safe_members(archive: zipfile.ZipFile, into: Path) -> list[tuple[zipfile.ZipInfo, Path]]:
    root = into.resolve()
    members: list[tuple[zipfile.ZipInfo, Path]] = []
    for info in archive.infolist():
        name = info.filename
        parts = [p for p in re.split(r"[\\/]", name) if p != ""]
        if (
            not parts
            or name.startswith(("/", "\\"))
            or any(":" in p or _NON_NAME.match(p) or "\x00" in p for p in parts)
            or (info.external_attr >> 16) & 0o170000 == 0o120000
        ):
            raise _unsafe_path(name)
        target = (root.joinpath(*parts)).resolve()
        if not target.is_relative_to(root):
            raise _unsafe_path(name)
        members.append((info, target))
    return members


def extract_zip(archive_path: Path, into: Path, job: Job) -> None:
    try:
        with zipfile.ZipFile(archive_path) as archive:
            members = safe_members(archive, into)
            check_space([(into, sum(info.file_size for info, _ in members))])
            for info, target in members:
                job.raise_if_cancelled()
                if info.is_dir():
                    target.mkdir(parents=True, exist_ok=True)
                    continue
                target.parent.mkdir(parents=True, exist_ok=True)
                with archive.open(info) as source, target.open("wb") as out:
                    shutil.copyfileobj(source, out, CHUNK)
    except zipfile.BadZipFile as exc:
        raise DownloadError(Failure(FailureKind.ARCHIVE, f"{archive_path.name}: {exc}")) from exc
    except OSError as exc:
        raise _disk_failure(exc) from exc


TAR_SUFFIXES = (".tar.gz", ".tgz")
_DIR_MODE = 0o700
_FILE_MODE = 0o600
_KEPT_MODE_BITS = 0o755


def _tar_target(name: str, root: Path) -> Path | None:
    """Where the archive path `name` lands under `root`, or None for the archive's own folder
    entry ("./"). Raises for a name that could leave `root`."""
    parts = [p for p in re.split(r"[\\/]", name) if p not in ("", ".")]
    if not parts:
        if name.strip("/") in ("", "."):
            return None
        raise _unsafe_path(name)
    target = root.joinpath(*parts).resolve()
    if (
        name.startswith(("/", "\\"))
        or any(":" in p or _NON_NAME.match(p) or "\x00" in p for p in parts)
        or not target.is_relative_to(root)
    ):
        raise _unsafe_path(name)
    return target


def _safe_link_name(link: str, member: str) -> str:
    """A symlink may point at a plain relative path under the archive: no `..`, no absolute
    path, no drive. With no `..` a chain of links cannot climb out of the folder."""
    parts = link.split("/")
    if (
        not link
        or link.startswith(("/", "\\"))
        or "\\" in link
        or any(p in ("", "..") or ":" in p or "\x00" in p for p in parts if p != ".")
    ):
        unsafe = notices.UNSAFE_LINK(name=repr(member), target=repr(link))
        raise _failed(FailureKind.ARCHIVE, unsafe)
    return link


def safe_tar_members(
    archive: tarfile.TarFile, into: Path
) -> list[tuple[tarfile.TarInfo, Path | None]]:
    """Every member with the place it lands, after the checks `safe_members` makes for a zip.
    Only folders, files, symlinks and hard links under the archive are accepted; a device, a
    pipe, or a link that could point outside is an archive error."""
    root = into.resolve()
    members: list[tuple[tarfile.TarInfo, Path | None]] = []
    for info in archive.getmembers():
        target = _tar_target(info.name, root)
        if info.issym():
            _safe_link_name(info.linkname, info.name)
        elif info.islnk():
            if _tar_target(info.linkname, root) is None:
                unsafe = notices.UNSAFE_LINK_ENTRY(name=repr(info.name))
                raise _failed(FailureKind.ARCHIVE, unsafe)
        elif not (info.isdir() or info.isfile()):
            unsupported = notices.UNSUPPORTED_ENTRY(name=repr(info.name))
            raise _failed(FailureKind.ARCHIVE, unsupported)
        members.append((info, target))
    return members


def _link_in(archive_name: str, target: Path, root: Path, *, link: str) -> None:
    """Make `target` a symlink to `link` and check where it really points."""
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.is_symlink() or target.exists():
        target.unlink()
    os.symlink(link, target)
    if not Path(os.path.realpath(target)).is_relative_to(root):
        target.unlink()
        unsafe = notices.UNSAFE_LINK(name=repr(archive_name), target=repr(link))
        raise _failed(FailureKind.ARCHIVE, unsafe)


def _unpacked_mode(archive_mode: int, floor: int) -> int:
    """The mode of an unpacked entry: the archive's owner bits and group and other read and
    execute bits (so a program stays runnable), plus `floor` so this program can read it. Never
    a set-user-id, set-group-id or sticky bit, and never group or other write."""
    return (archive_mode & _KEPT_MODE_BITS) | floor


def extract_tar(archive_path: Path, into: Path, job: Job) -> None:
    """Unpack a `.tar.gz` with the same safety as `extract_zip`. A file keeps its permission
    bits (so a program stays runnable) but never a set-user-id bit or write access for the group or
    others."""
    root = into.resolve()
    try:
        with tarfile.open(archive_path, "r:gz") as archive:
            members = safe_tar_members(archive, into)
            check_space([(into, sum(info.size for info, _ in members if info.isfile()))])
            for info, target in members:
                job.raise_if_cancelled()
                if target is None:
                    continue
                if info.isdir():
                    target.mkdir(parents=True, exist_ok=True)
                    target.chmod(_unpacked_mode(info.mode, _DIR_MODE))
                elif info.issym():
                    _link_in(info.name, target, root, link=info.linkname)
                elif info.islnk():
                    source = _tar_target(info.linkname, root)
                    if source is None or not source.is_file():
                        absent = notices.LINK_TO_NOTHING(name=repr(info.name))
                        raise _failed(FailureKind.ARCHIVE, absent)
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copyfile(source, target)
                    target.chmod(_unpacked_mode(info.mode, _FILE_MODE))
                else:
                    target.parent.mkdir(parents=True, exist_ok=True)
                    source_file = archive.extractfile(info)
                    assert source_file is not None
                    with source_file, target.open("wb") as out:
                        shutil.copyfileobj(source_file, out, CHUNK)
                    target.chmod(_unpacked_mode(info.mode, _FILE_MODE))
    except (tarfile.TarError, gzip.BadGzipFile, EOFError, zlib.error) as exc:
        raise DownloadError(Failure(FailureKind.ARCHIVE, f"{archive_path.name}: {exc}")) from exc
    except OSError as exc:
        raise _disk_failure(exc) from exc


def extract_archive(archive_path: Path, into: Path, job: Job) -> None:
    """Unpack by the archive's name: `.tar.gz` and `.tgz` as a tarball, anything else as a zip."""
    if archive_path.name.lower().endswith(TAR_SUFFIXES):
        extract_tar(archive_path, into, job)
    else:
        extract_zip(archive_path, into, job)


_swap_lock = threading.Lock()


def old_of(folder: Path) -> Path:
    return folder.with_name(folder.name + OLD_SUFFIX)


def recover_swap(folder: Path, entry_point: str | None) -> bool:
    """Settle what a swap killed halfway leaves behind. With no live `folder` the set-aside copy
    is the working install, so it goes back. With a live folder that holds its `entry_point`
    (the swap finished and the new files were checked) the leftover copy is deleted. Returns
    whether it changed anything."""
    old = old_of(folder)
    with _swap_lock:
        if not old.exists():
            return False
        if not folder.exists():
            os.replace(old, folder)
            log.warning("restored %s from %s: an earlier swap was interrupted", folder, old)
            return True
        if entry_point is not None and not (folder / entry_point).is_file():
            return False
        shutil.rmtree(old, ignore_errors=True)
        log.info("removed %s, left over from an earlier swap", old)
        return True


def _swap_folder(staging: Path, folder: Path) -> None:
    """Put `staging` at `folder`. An existing folder is set aside first and put back if the
    swap fails, so a failed replace leaves the old files as they were. A kill between the two
    renames is settled by `recover_swap`."""
    old = old_of(folder)
    with _swap_lock:
        if not folder.exists():
            os.replace(staging, folder)
            shutil.rmtree(old, ignore_errors=True)
            return
        shutil.rmtree(old, ignore_errors=True)
        os.replace(folder, old)
        try:
            os.replace(staging, folder)
        except BaseException:
            os.replace(old, folder)
            raise
        shutil.rmtree(old, ignore_errors=True)


def unpack(plan: Plan, job: Job) -> None:
    folder = plan.unpack_to
    if folder is None:
        return
    staging = staging_of(folder)
    shutil.rmtree(staging, ignore_errors=True)
    staging.mkdir(parents=True)
    try:
        for item in plan.items:
            extract_archive(item.dest, staging, job)
        if plan.entry_point and not (staging / plan.entry_point).is_file():
            lacking = notices.ARCHIVE_LACKS_PROGRAM(file=plan.entry_point)
            raise _failed(FailureKind.ARCHIVE, lacking)
        _swap_folder(staging, folder)
    except BaseException:
        shutil.rmtree(staging, ignore_errors=True)
        raise
    for item in plan.items:
        item.dest.unlink(missing_ok=True)


def _staged_items(plan: Plan) -> dict[Item, Item]:
    """For a replace of single files, where each new file is downloaded and checked before it
    takes the old one's place. A runtime replaces its folder in `unpack`."""
    if not plan.replacing or plan.unpack_to is not None:
        return {}
    return {
        item: replace(item, dest=replacing_of(item.dest))
        for item in plan.items
        if item not in plan.shared
    }


class JobRunner:
    def __init__(
        self,
        resolve_url: Callable[[str], str] = lambda url: url,
        policy: RetryPolicy | None = None,
        opener: Opener | None = None,
        on_installed: Callable[[Plan, tuple[Item, ...]], None] | None = None,
    ) -> None:
        self._on_installed = on_installed
        self._resolve_url = resolve_url
        self._policy = policy or RetryPolicy()
        self._opener = opener or _urlopen
        self._lock = threading.Lock()
        self._jobs: dict[str, Job] = {}
        self._active: dict[str, Job] = {}
        self._queue: queue.Queue[Job] = queue.Queue()
        threading.Thread(target=self._work, name="downloads", daemon=True).start()

    def submit(self, plan: Plan) -> JobStatus:
        with self._lock:
            running = self._active.get(plan.asset_id)
            if running is not None:
                return running.snapshot()
            job = Job(plan)
            self._jobs[job.id] = job
            self._prune()
            if plan.is_satisfied():
                job.complete(Outcome.ALREADY_PRESENT)
            else:
                self._active[plan.asset_id] = job
                self._queue.put(job)
            return job.snapshot()

    def state(self, plan: Plan) -> InstallState:
        with self._lock:
            if plan.asset_id in self._active:
                return InstallState.INSTALLING
        return plan.state()

    def active_job(self, asset_id: str) -> JobStatus | None:
        with self._lock:
            job = self._active.get(asset_id)
        return job.snapshot() if job else None

    def status(self, job_id: str) -> JobStatus | None:
        job = self._jobs.get(job_id)
        return job.snapshot() if job else None

    def jobs(self) -> list[JobStatus]:
        with self._lock:
            return [job.snapshot() for job in self._jobs.values()]

    def cancel(self, job_id: str) -> JobStatus | None:
        job = self._jobs.get(job_id)
        if job is None:
            return None
        job.request_cancel()
        if job.finished.is_set():
            self._release(job)
        return job.snapshot()

    def wait(self, job_id: str, timeout: float | None = None) -> JobStatus | None:
        job = self._jobs.get(job_id)
        if job is None:
            return None
        job.finished.wait(timeout)
        return job.snapshot()

    def shutdown(self) -> None:
        with self._lock:
            for job in self._jobs.values():
                job.request_cancel()

    def _prune(self) -> None:
        stale = [j for j in self._jobs.values() if j.finished.is_set()]
        for job in stale[: max(0, len(stale) - _KEEP_JOBS)]:
            del self._jobs[job.id]

    def _release(self, job: Job) -> None:
        with self._lock:
            if self._active.get(job.plan.asset_id) is job:
                del self._active[job.plan.asset_id]

    def _work(self) -> None:
        while True:
            job = self._queue.get()
            if job.try_start():
                self._run(job)
            self._release(job)

    def _note_installed(self, plan: Plan, fresh: tuple[Item, ...]) -> None:
        if self._on_installed is None:
            return
        try:
            self._on_installed(plan, fresh)
        except Exception:
            log.exception("could not record the install of %s", plan.asset_id)

    def _run(self, job: Job) -> None:
        plan = job.plan
        try:
            staged = _staged_items(plan)
            work = tuple(staged.get(item, item) for item in plan.items)
            check_space((item.dest.parent, _remaining(item)) for item in work)
            fresh = tuple(item for item in plan.items if item in staged or not _present(item))
            for item in work:
                job.move(JobState.DOWNLOADING)
                fetch(item, job, self._resolve_url(item.url), self._opener, self._policy)
            for item, new in staged.items():
                os.replace(new.dest, item.dest)
            if plan.unpack_to is not None:
                job.move(JobState.EXTRACTING)
                unpack(plan, job)
            self._note_installed(plan, fresh)
            job.complete(Outcome.INSTALLED)
        except Cancelled:
            job.move(JobState.CANCELLED)
        except DownloadError as exc:
            job.fail(exc.failure)
        except Exception as exc:
            text, found = os_error_said(exc)
            job.fail(Failure(FailureKind.IO, text, message_notices=found))
