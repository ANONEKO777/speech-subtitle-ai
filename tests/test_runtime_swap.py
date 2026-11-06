"""A runtime folder that a kill or a lock left half swapped, and how that is reported."""

from __future__ import annotations

import contextlib
import ctypes
import logging
import os
import shutil
import sys
from collections.abc import Generator
from pathlib import Path
from typing import Any

import pytest
from manage_support import Rig
from test_manage import (
    SILERO_GGML,
    VAD_MODEL,
    _wait_move,  # pyright: ignore[reportPrivateUsage]
)

from backend.manager import download, runtimes, storage_move
from backend.manager.profiles import WHISPER_CPU_RUNTIME, WHISPER_RUNTIME
from backend.manager.registry import Runtime


def runtime_of(rig: Rig) -> Runtime:
    return rig.registry.runtimes[WHISPER_CPU_RUNTIME]


def killed_between_the_renames(rig: Rig) -> tuple[Path, Path]:
    rig.install("runtimes", WHISPER_CPU_RUNTIME)
    folder = Path(rig.asset(WHISPER_CPU_RUNTIME)["path"])
    (folder / "marker.txt").write_text("working")
    old = download.old_of(folder)
    os.replace(folder, old)
    return folder, old


def locked(path: Path, other: Path | None = None) -> PermissionError:
    return PermissionError(13, "Access is denied", str(path), 5, str(other) if other else None)


def test_a_restart_after_a_kill_between_the_renames_puts_the_runtime_back(
    rig: Rig, caplog: pytest.LogCaptureFixture
) -> None:
    folder, old = killed_between_the_renames(rig)
    assert not folder.exists()

    with caplog.at_level(logging.WARNING, logger="backend.manager.download"):
        rig.start()

    assert (folder / "marker.txt").read_text() == "working" and not old.exists()
    assert rig.asset(WHISPER_CPU_RUNTIME)["installed"]
    assert "restored" in caplog.text and str(old) in caplog.text


def test_using_the_runtime_restores_it_without_a_restart(rig: Rig) -> None:
    folder, old = killed_between_the_renames(rig)

    exe = runtimes.runtime_executable(WHISPER_CPU_RUNTIME, rig.registry, rig.ctx.storage)

    assert exe is not None and exe.is_file() and not old.exists()
    assert (folder / "marker.txt").exists()


def test_a_leftover_old_copy_is_removed_when_the_live_runtime_is_complete(rig: Rig) -> None:
    rig.install("runtimes", WHISPER_CPU_RUNTIME)
    folder = Path(rig.asset(WHISPER_CPU_RUNTIME)["path"])
    old = download.old_of(folder)
    old.mkdir()
    (old / "stale.txt").write_text("old")

    rig.start()

    assert not old.exists() and rig.asset(WHISPER_CPU_RUNTIME)["installed"]


def test_an_old_copy_stays_when_the_live_runtime_lacks_its_executable(rig: Rig) -> None:
    rig.install("runtimes", WHISPER_CPU_RUNTIME)
    folder = Path(rig.asset(WHISPER_CPU_RUNTIME)["path"])
    shutil.rmtree(folder)
    folder.mkdir()
    old = download.old_of(folder)
    old.mkdir()

    rig.start()

    assert old.exists()


def test_a_redownload_after_a_kill_leaves_no_old_copy(rig: Rig) -> None:
    folder, old = killed_between_the_renames(rig)

    rig.client.post(f"/api/inventory/{WHISPER_CPU_RUNTIME}/redownload")
    rig.wait_jobs()

    assert rig.asset(WHISPER_CPU_RUNTIME)["installed"] and not old.exists()
    assert not (folder / "marker.txt").exists()


def test_deleting_a_runtime_also_removes_its_old_copy(rig: Rig) -> None:
    rig.install("runtimes", WHISPER_RUNTIME)
    rig.set_profile("cpu")
    folder = Path(rig.asset(WHISPER_RUNTIME)["path"])
    old = download.old_of(folder)
    old.mkdir()
    (old / "running.exe").write_text("x")

    assert rig.client.delete(f"/api/runtimes/{WHISPER_RUNTIME}").status_code == 204

    assert not folder.exists() and not old.exists()


def test_a_locked_runtime_folder_on_swap_names_the_path_and_keeps_the_old_files(
    rig: Rig, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    rig.install("runtimes", WHISPER_CPU_RUNTIME)
    folder = Path(rig.asset(WHISPER_CPU_RUNTIME)["path"])
    real = os.replace

    def replace(src: Any, dst: Any) -> None:
        if Path(src) == folder:
            raise locked(folder, Path(dst))
        real(src, dst)

    monkeypatch.setattr(os, "replace", replace)
    with caplog.at_level(logging.WARNING):
        rig.client.post(f"/api/inventory/{WHISPER_CPU_RUNTIME}/redownload")
        rig.wait_jobs()

    failure = rig.client.get("/api/downloads").json()[-1]["failure"]
    assert str(folder) in failure["message"]
    assert "locked by another program" in failure["message"]
    assert "Close the program" in failure["message"]
    assert "WinError" not in failure["message"] and "PermissionError" not in failure["message"]
    assert "Access is denied" in caplog.text
    assert rig.asset(WHISPER_CPU_RUNTIME)["installed"]


@contextlib.contextmanager
def exclusive_lock(path: Path) -> Generator[None]:
    """Hold `path` the way a running program does: opened with share mode 0, so another
    process can neither read, rename nor delete it."""
    windll = ctypes.WinDLL("kernel32", use_last_error=True)  # type: ignore[attr-defined]
    windll.CreateFileW.restype = ctypes.c_void_p
    windll.CreateFileW.argtypes = [ctypes.c_wchar_p, ctypes.c_uint32, ctypes.c_uint32] + [
        ctypes.c_void_p,
        ctypes.c_uint32,
        ctypes.c_uint32,
        ctypes.c_void_p,
    ]
    handle = windll.CreateFileW(str(path), 0x80000000, 0, None, 3, 0, None)
    assert handle not in (None, ctypes.c_void_p(-1).value), "could not lock the file"
    try:
        yield
    finally:
        windll.CloseHandle.argtypes = [ctypes.c_void_p]
        windll.CloseHandle(handle)


needs_windows = pytest.mark.skipif(sys.platform != "win32", reason="needs Windows file locking")


def installed_runtime(rig: Rig) -> tuple[Path, list[Path]]:
    rig.install("runtimes", WHISPER_RUNTIME)
    rig.set_profile("cpu")
    folder = Path(rig.asset(WHISPER_RUNTIME)["path"])
    (folder / "sub").mkdir()
    (folder / "sub" / "extra.dll").write_bytes(b"dll")
    return folder, sorted(p for p in folder.rglob("*") if p.is_file())


@needs_windows
def test_deleting_a_runtime_with_a_locked_file_leaves_every_file_in_place(rig: Rig) -> None:
    folder, files = installed_runtime(rig)

    with exclusive_lock(files[-1]):
        reply = rig.client.delete(f"/api/runtimes/{WHISPER_RUNTIME}")

    assert reply.status_code == 409
    message = reply.json()["detail"]["message"]
    assert "locked by another program" in message and "Close the program" in message
    assert sorted(p for p in folder.rglob("*") if p.is_file()) == files
    assert rig.asset(WHISPER_RUNTIME)["installed"]


@needs_windows
def test_the_delete_works_once_the_lock_is_released(rig: Rig) -> None:
    folder, files = installed_runtime(rig)
    with exclusive_lock(files[-1]):
        assert rig.client.delete(f"/api/runtimes/{WHISPER_RUNTIME}").status_code == 409

    assert rig.client.delete(f"/api/runtimes/{WHISPER_RUNTIME}").status_code == 204

    assert not folder.exists()
    assert not list(folder.parent.glob(f"*{runtimes.TRASH_MARK}*"))


def test_a_trash_folder_left_by_a_delete_is_swept_at_the_next_start(
    rig: Rig, monkeypatch: pytest.MonkeyPatch
) -> None:
    folder, _ = installed_runtime(rig)
    monkeypatch.setattr(runtimes.shutil, "rmtree", lambda *args, **kwargs: None)  # type: ignore[misc]

    assert rig.client.delete(f"/api/runtimes/{WHISPER_RUNTIME}").status_code == 204
    monkeypatch.undo()

    leftovers = list(folder.parent.glob(f"*{runtimes.TRASH_MARK}*"))
    assert not folder.exists() and len(leftovers) == 1
    rig.start()
    assert not leftovers[0].exists()


@needs_windows
def test_verify_and_repair_on_a_locked_model_are_a_readable_conflict(rig: Rig) -> None:
    rig.install("models", VAD_MODEL)
    path = Path(rig.asset(VAD_MODEL)["path"])

    with exclusive_lock(path):
        verify = rig.client.post(f"/api/inventory/{VAD_MODEL}/verify")
        fix = rig.client.post(f"/api/inventory/{VAD_MODEL}/repair")

    for reply in (verify, fix):
        assert reply.status_code == 409
        assert "locked by another program" in reply.json()["detail"]["message"]
        assert str(path) in reply.json()["detail"]["message"]


def test_a_locked_file_on_move_names_the_path(rig: Rig, tmp_path: Path) -> None:
    rig.install("models", SILERO_GGML)
    rig.install("models", VAD_MODEL)
    target = tmp_path / "target"
    seen: list[Path] = []
    real = storage_move.MoveRunner._transfer  # pyright: ignore[reportPrivateUsage]

    def flaky(self: Any, src: Path, dest: Path) -> None:
        seen.append(src)
        if len(seen) == 2:
            raise locked(src, dest)
        real(self, src, dest)

    storage_move.MoveRunner._transfer = flaky  # pyright: ignore[reportPrivateUsage]
    try:
        rig.client.post("/api/storage/move", json={"target": str(target)})
        _wait_move(rig)
    finally:
        storage_move.MoveRunner._transfer = real  # pyright: ignore[reportPrivateUsage]

    error = rig.client.get("/api/storage/move").json()["error"]
    assert str(seen[1]) in error and "locked by another program" in error
    assert "PermissionError" not in error
