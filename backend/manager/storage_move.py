"""Move the installed models to another folder, only when the user asks for it.

Changing the models folder never moves anything. This is the explicit operation. It links or
copies every model file to the target first, switches the configured folder only when all of them
are there, and then removes the originals. If anything fails before the switch, the copies this run
made are removed and the old folder is untouched.

Running it again after a crash converges: a target file that holds the same bytes as its source is
a leftover of the earlier run and is kept, and any half-written `.part` is overwritten. Only a
target file with other content stops the move, and it is never touched."""

from __future__ import annotations

import filecmp
import logging
import os
import threading
from collections.abc import Callable
from dataclasses import dataclass, replace
from enum import StrEnum
from pathlib import Path

from backend.core import notices
from backend.core.notices import Notice, noticed, notices_of
from backend.manager.download import CHUNK, DownloadError, check_space, os_error_said, part_of
from backend.manager.registry import Registry
from backend.manager.storage import Storage, StorageConfig

log = logging.getLogger(__name__)


class MoveError(ValueError):
    pass


class MoveState(StrEnum):
    IDLE = "idle"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"


@dataclass(frozen=True, slots=True)
class MoveStatus:
    state: MoveState = MoveState.IDLE
    source: str | None = None
    target: str | None = None
    files_total: int = 0
    files_done: int = 0
    bytes_total: int = 0
    bytes_done: int = 0
    error: str | None = None
    warnings: tuple[str, ...] = ()
    error_notices: tuple[Notice, ...] = ()
    warnings_notices: tuple[Notice, ...] = ()


def installed_models(registry: Registry, root: Path) -> list[tuple[str, Path, int]]:
    """(model id, file, size) for each registry model that sits under `root`."""
    found: list[tuple[str, Path, int]] = []
    for model in registry.models.values():
        path = root / model.id / model.file
        if path.is_file():
            found.append((model.id, path, path.stat().st_size))
    return found


def _inside(a: Path, b: Path) -> bool:
    try:
        a.resolve().relative_to(b.resolve())
    except ValueError:
        return False
    return True


class MoveRunner:
    def __init__(
        self, storage: Storage, registry: Registry, downloads_active: Callable[[], bool]
    ) -> None:
        self._storage = storage
        self._registry = registry
        self._downloads_active = downloads_active
        self._lock = threading.Lock()
        self._status = MoveStatus()

    def status(self) -> MoveStatus:
        with self._lock:
            return self._status

    def start(self, source: Path, target: Path) -> MoveStatus:
        if not target.is_absolute():
            raise noticed(MoveError, notices.MOVE_NOT_ABSOLUTE())
        if source.resolve() == target.resolve():
            raise noticed(MoveError, notices.MOVE_SAME_FOLDER())
        if _inside(target, source) or _inside(source, target):
            raise noticed(MoveError, notices.MOVE_NESTED())
        files = installed_models(self._registry, source)
        if not files:
            raise noticed(MoveError, notices.MOVE_NO_MODELS(folder=str(source)))
        clash = [m for m, p, s in files if _foreign(p, s, target / m / self._file_of(m))]
        if clash:
            raise noticed(MoveError, notices.MOVE_CLASH(target=str(target), models=clash))
        if self._downloads_active():
            raise noticed(MoveError, notices.MOVE_DOWNLOAD_RUNNING())
        with self._lock:
            if self._status.state is MoveState.RUNNING:
                raise noticed(MoveError, notices.MOVE_ALREADY_RUNNING())
            self._status = MoveStatus(
                MoveState.RUNNING,
                str(source),
                str(target),
                len(files),
                0,
                sum(s for _m, _p, s in files),
            )
        try:
            target.mkdir(parents=True, exist_ok=True)
            check_space([(target, sum(s for _m, _p, s in files))])
        except DownloadError as exc:
            found = exc.failure.message_notices
            self._set(state=MoveState.FAILED, error=str(exc), error_notices=found)
            raise (noticed(MoveError, found[0]) if found else MoveError(str(exc))) from exc
        except OSError as exc:
            self._set(state=MoveState.FAILED, error=str(exc))
            raise MoveError(str(exc)) from exc
        threading.Thread(
            target=self._work, args=(files, target), name="move-models", daemon=True
        ).start()
        return self.status()

    def _file_of(self, model_id: str) -> str:
        return self._registry.models[model_id].file

    def _set(self, **changes: object) -> None:
        with self._lock:
            self._status = replace(self._status, **changes)  # pyright: ignore[reportArgumentType]

    def _work(self, files: list[tuple[str, Path, int]], target: Path) -> None:
        made: list[Path] = []
        try:
            for model_id, path, size in files:
                dest = target / model_id / path.name
                dest.parent.mkdir(parents=True, exist_ok=True)
                if dest.exists():
                    if not _same_bytes(path, dest):
                        said = notices.MOVE_OTHER_CONTENT(dest=str(dest), path=str(path))
                        raise noticed(MoveError, said)
                    self._set(bytes_done=self.status().bytes_done + size)
                else:
                    made.append(dest)
                    self._transfer(path, dest)
                if dest.stat().st_size != size:
                    raise noticed(MoveError, notices.MOVE_WRONG_SIZE(dest=str(dest)))
                self._set(files_done=self.status().files_done + 1)
            config = self._storage.config
            self._storage.update(StorageConfig(target, config.mirrors))
        except Exception as exc:
            for dest in made:
                dest.unlink(missing_ok=True)
                part_of(dest).unlink(missing_ok=True)
                _rmdir(dest.parent)
            if isinstance(exc, MoveError):
                self._set(state=MoveState.FAILED, error=str(exc), error_notices=notices_of(exc))
            else:
                text, found = os_error_said(exc)
                self._set(state=MoveState.FAILED, error=text, error_notices=found)
            return
        warnings: list[Notice] = []
        for _model_id, path, _size in files:
            try:
                path.unlink()
                _rmdir(path.parent)
            except OSError as exc:
                text, found = os_error_said(exc)
                warnings.append(notices.MOVE_COULD_NOT_REMOVE(path=str(path), error=text))
                warnings.extend(found)
        said = notices.unique(warnings)
        shown = tuple(one.message for one in warnings if one.code == "move.couldNotRemove")
        self._set(state=MoveState.DONE, warnings=shown, warnings_notices=said)

    def _transfer(self, src: Path, dest: Path) -> None:
        part = part_of(dest)
        part.unlink(missing_ok=True)
        try:
            os.link(src, dest)
            self._set(bytes_done=self.status().bytes_done + src.stat().st_size)
            return
        except OSError:
            pass
        with src.open("rb") as read, part.open("wb") as write:
            while block := read.read(CHUNK):
                write.write(block)
                self._set(bytes_done=self.status().bytes_done + len(block))
        os.replace(part, dest)


def _foreign(source: Path, size: int, dest: Path) -> bool:
    """A target that cannot be an earlier copy of `source`: not a file, or a different size."""
    if not dest.exists():
        return False
    return not dest.is_file() or dest.stat().st_size != size


def _same_bytes(a: Path, b: Path) -> bool:
    return os.path.samefile(a, b) or filecmp.cmp(a, b, shallow=False)


def _rmdir(folder: Path) -> None:
    try:
        folder.rmdir()
    except OSError:
        pass
