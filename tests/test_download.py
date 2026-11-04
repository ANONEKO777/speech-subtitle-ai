from __future__ import annotations

import threading
import time
import zipfile
from pathlib import Path

import pytest
from download_support import (
    Origin,
    blob,
    disk_with,
    item_for,
    make_zip,
    runner,
    serve,
    settle,
    sha,
    wait_until,
)

from backend.manager import download
from backend.manager.download import (
    FailureKind,
    InstallState,
    Item,
    Job,
    JobState,
    Outcome,
    Plan,
    part_of,
    staging_of,
)

SIZE = 3 * 1024 * 1024 + 123


def plan_for(origin: Origin, path: str, dest: Path) -> Plan:
    return Plan(path, (item_for(origin, path, dest),))


def test_a_download_lands_verified_with_no_part_file(tmp_path: Path) -> None:
    with serve() as origin:
        origin.files["/m.bin"] = blob(SIZE)
        dest = tmp_path / "m" / "m.bin"

        final = settle(runner(), plan_for(origin, "/m.bin", dest))

    assert final.state is JobState.DONE
    assert final.outcome is Outcome.INSTALLED
    assert (final.bytes_done, final.bytes_total) == (SIZE, SIZE)
    assert sha(dest.read_bytes()) == sha(blob(SIZE))
    assert not part_of(dest).exists()


def test_a_dropped_connection_resumes_from_the_bytes_already_on_disk(tmp_path: Path) -> None:
    with serve() as origin:
        data = blob(SIZE)
        origin.files["/m.bin"] = data
        origin.cut_after, origin.cuts_left = 1_200_000, 1
        dest = tmp_path / "m.bin"

        final = settle(runner(), plan_for(origin, "/m.bin", dest))

    assert final.state is JobState.DONE
    assert final.retries == 1
    assert final.resumed_from == 1_200_000
    assert origin.ranges("/m.bin") == [None, "bytes=1200000-"]
    assert dest.read_bytes() == data


def test_a_part_file_left_by_an_earlier_run_is_continued_not_restarted(tmp_path: Path) -> None:
    with serve() as origin:
        data = blob(SIZE)
        origin.files["/m.bin"] = data
        dest = tmp_path / "m.bin"
        part_of(dest).write_bytes(data[:2_000_000])

        final = settle(runner(), plan_for(origin, "/m.bin", dest))

    assert final.state is JobState.DONE
    assert origin.ranges("/m.bin") == ["bytes=2000000-"]
    assert dest.read_bytes() == data


def test_a_server_that_ignores_range_still_converges(tmp_path: Path) -> None:
    with serve() as origin:
        data = blob(SIZE)
        origin.files["/m.bin"] = data
        origin.ignore_range = True
        dest = tmp_path / "m.bin"
        part_of(dest).write_bytes(data[:1_000_000])

        final = settle(runner(), plan_for(origin, "/m.bin", dest))

    assert final.state is JobState.DONE
    assert final.resumed_from == 0
    assert dest.read_bytes() == data


def test_a_complete_part_file_is_verified_and_renamed_without_a_request(tmp_path: Path) -> None:
    with serve() as origin:
        data = blob(SIZE)
        origin.files["/m.bin"] = data
        dest = tmp_path / "m.bin"
        part_of(dest).write_bytes(data)

        final = settle(runner(), plan_for(origin, "/m.bin", dest))

    assert final.state is JobState.DONE
    assert origin.requests == []
    assert dest.read_bytes() == data


def test_a_hash_mismatch_is_rejected_and_nothing_is_kept(tmp_path: Path) -> None:
    with serve() as origin:
        origin.files["/m.bin"] = blob(SIZE)
        dest = tmp_path / "m.bin"
        wrong = Item(origin.url("/m.bin"), dest, sha(b"something else"), SIZE)

        final = settle(runner(), Plan("m", (wrong,)))

    assert final.state is JobState.FAILED
    assert final.failure is not None
    assert final.failure.kind is FailureKind.HASH_MISMATCH
    assert not dest.exists()
    assert not part_of(dest).exists()


def test_a_corrupt_part_file_fails_the_hash_check_and_is_deleted(tmp_path: Path) -> None:
    with serve() as origin:
        data = blob(SIZE)
        origin.files["/m.bin"] = data
        dest = tmp_path / "m.bin"
        part_of(dest).write_bytes(b"\0" * 1000)

        final = settle(runner(), plan_for(origin, "/m.bin", dest))
        retry = settle(runner(), plan_for(origin, "/m.bin", dest))

    assert final.failure is not None
    assert final.failure.kind is FailureKind.HASH_MISMATCH
    assert retry.state is JobState.DONE
    assert dest.read_bytes() == data


def test_too_little_free_space_fails_before_any_request_and_says_how_much(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(download.shutil, "disk_usage", disk_with(1000))
    with serve() as origin:
        origin.files["/m.bin"] = blob(SIZE)

        final = settle(runner(), plan_for(origin, "/m.bin", tmp_path / "m.bin"))

    assert final.state is JobState.FAILED
    assert final.failure is not None
    assert final.failure.kind is FailureKind.INSUFFICIENT_SPACE
    assert (final.failure.needed_bytes, final.failure.available_bytes) == (SIZE, 1000)
    assert "3.0 MiB" in final.failure.message
    assert origin.requests == []


def test_space_needed_counts_only_the_bytes_not_yet_downloaded(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    with serve() as origin:
        data = blob(SIZE)
        origin.files["/m.bin"] = data
        dest = tmp_path / "m.bin"
        part_of(dest).write_bytes(data[: SIZE - 5000])
        monkeypatch.setattr(download.shutil, "disk_usage", disk_with(6000))

        final = settle(runner(), plan_for(origin, "/m.bin", dest))

    assert final.state is JobState.DONE


def test_cancel_keeps_the_part_file_and_a_rerun_resumes_it(tmp_path: Path) -> None:
    with serve() as origin:
        data = blob(8 * 1024 * 1024)
        origin.files["/m.bin"] = data
        origin.pause_per_piece = 0.02
        dest = tmp_path / "m.bin"
        jobs = runner()
        job = jobs.submit(plan_for(origin, "/m.bin", dest))
        wait_until(lambda: (jobs.status(job.id) or job).bytes_done >= 1024 * 1024)

        cancelled = jobs.cancel(job.id)
        assert cancelled is not None
        final = jobs.wait(job.id, 10)
        assert final is not None
        origin.pause_per_piece = 0
        held = part_of(dest).stat().st_size
        again = settle(jobs, plan_for(origin, "/m.bin", dest))

    assert final.state is JobState.CANCELLED
    assert 0 < held < len(data)
    assert origin.ranges("/m.bin")[-1] == f"bytes={held}-"
    assert again.state is JobState.DONE
    assert dest.read_bytes() == data


def test_a_cancelled_job_leaves_only_the_part_file(tmp_path: Path) -> None:
    with serve() as origin:
        origin.files["/m.bin"] = blob(8 * 1024 * 1024)
        origin.pause_per_piece = 0.02
        dest = tmp_path / "m" / "m.bin"
        jobs = runner()
        job = jobs.submit(plan_for(origin, "/m.bin", dest))
        wait_until(lambda: (jobs.status(job.id) or job).bytes_done > 0)

        jobs.cancel(job.id)
        final = jobs.wait(job.id, 10)

    assert final is not None
    assert final.state is JobState.CANCELLED
    assert sorted(p.name for p in dest.parent.iterdir()) == ["m.bin.part"]


def test_a_queued_job_cancels_at_once_and_never_runs(tmp_path: Path) -> None:
    with serve() as origin:
        origin.files["/a.bin"] = blob(8 * 1024 * 1024)
        origin.files["/b.bin"] = blob(SIZE, seed=2)
        origin.pause_per_piece = 0.02
        jobs = runner()
        first = jobs.submit(plan_for(origin, "/a.bin", tmp_path / "a.bin"))
        queued = jobs.submit(plan_for(origin, "/b.bin", tmp_path / "b.bin"))

        assert queued.state is JobState.QUEUED
        cancelled = jobs.cancel(queued.id)
        jobs.cancel(first.id)
        jobs.wait(first.id, 10)

    assert cancelled is not None
    assert cancelled.state is JobState.CANCELLED
    assert all(p != "/b.bin" for p, _ in origin.requests)


def test_downloading_the_same_thing_twice_reports_it_already_exists(tmp_path: Path) -> None:
    with serve() as origin:
        origin.files["/m.bin"] = blob(SIZE)
        plan = plan_for(origin, "/m.bin", tmp_path / "m.bin")
        jobs = runner()

        first = settle(jobs, plan)
        second = settle(jobs, plan)

    assert first.outcome is Outcome.INSTALLED
    assert (second.state, second.outcome) == (JobState.DONE, Outcome.ALREADY_PRESENT)
    assert len(origin.requests) == 1


def test_submitting_while_a_job_runs_returns_that_job(tmp_path: Path) -> None:
    with serve() as origin:
        origin.files["/m.bin"] = blob(4 * 1024 * 1024)
        origin.pause_per_piece = 0.01
        plan = plan_for(origin, "/m.bin", tmp_path / "m.bin")
        jobs = runner()

        first = jobs.submit(plan)
        second = jobs.submit(plan)
        jobs.wait(first.id, 20)

    assert second.id == first.id
    assert len(origin.requests) == 1


def test_a_file_of_the_wrong_size_is_replaced(tmp_path: Path) -> None:
    with serve() as origin:
        data = blob(SIZE)
        origin.files["/m.bin"] = data
        dest = tmp_path / "m.bin"
        dest.write_bytes(b"truncated")

        final = settle(runner(), plan_for(origin, "/m.bin", dest))

    assert final.outcome is Outcome.INSTALLED
    assert dest.read_bytes() == data


def test_a_missing_file_fails_at_once_without_retrying(tmp_path: Path) -> None:
    with serve() as origin:
        item = Item(origin.url("/nope.bin"), tmp_path / "x.bin", sha(b"x"), 10)

        final = settle(runner(), Plan("x", (item,)))

    assert final.failure is not None
    assert final.failure.kind is FailureKind.HTTP
    assert len(origin.requests) == 1


def test_a_server_error_is_retried_until_it_recovers(tmp_path: Path) -> None:
    with serve() as origin:
        origin.files["/m.bin"] = blob(SIZE)
        origin.statuses = [503, 503]

        final = settle(runner(), plan_for(origin, "/m.bin", tmp_path / "m.bin"))

    assert final.state is JobState.DONE
    assert final.retries == 2


def test_an_outage_that_outlasts_the_retries_fails_but_keeps_the_part(tmp_path: Path) -> None:
    with serve() as origin:
        data = blob(SIZE)
        origin.files["/m.bin"] = data
        origin.cut_after, origin.cuts_left = 0, 99
        dest = tmp_path / "m.bin"
        part_of(dest).write_bytes(data[:1_000_000])

        final = settle(runner(), plan_for(origin, "/m.bin", dest))
        origin.cuts_left = 0
        recovered = settle(runner(), plan_for(origin, "/m.bin", dest))

    assert final.failure is not None
    assert final.failure.kind is FailureKind.NETWORK
    assert recovered.state is JobState.DONE
    assert dest.read_bytes() == data


def test_a_server_sending_the_wrong_length_is_refused(tmp_path: Path) -> None:
    with serve() as origin:
        origin.files["/m.bin"] = blob(SIZE)
        item = Item(origin.url("/m.bin"), tmp_path / "m.bin", sha(blob(SIZE)), SIZE + 1)

        final = settle(runner(), Plan("m", (item,)))

    assert final.failure is not None
    assert final.failure.kind is FailureKind.SIZE_MISMATCH


def test_a_bundle_downloads_every_item_and_skips_the_ones_already_there(tmp_path: Path) -> None:
    with serve() as origin:
        origin.files["/a.bin"] = blob(SIZE, seed=3)
        origin.files["/b.bin"] = blob(SIZE, seed=4)
        a, b = tmp_path / "a.bin", tmp_path / "b.bin"
        a.write_bytes(origin.files["/a.bin"])
        plan = Plan("bundle", (item_for(origin, "/a.bin", a), item_for(origin, "/b.bin", b)))

        final = settle(runner(), plan)

    assert final.state is JobState.DONE
    assert final.bytes_total == 2 * SIZE
    assert [p for p, _ in origin.requests] == ["/b.bin"]
    assert b.read_bytes() == origin.files["/b.bin"]


def test_the_install_state_follows_the_files_on_disk(tmp_path: Path) -> None:
    with serve() as origin:
        origin.files["/m.bin"] = blob(SIZE)
        dest = tmp_path / "m.bin"
        plan = plan_for(origin, "/m.bin", dest)
        jobs = runner()

        assert jobs.state(plan) is InstallState.NOT_INSTALLED
        part_of(dest).write_bytes(blob(SIZE)[:3])
        assert jobs.state(plan) is InstallState.PARTIAL
        settle(jobs, plan)
        assert jobs.state(plan) is InstallState.INSTALLED
        dest.unlink()
        assert jobs.state(plan) is InstallState.NOT_INSTALLED


def test_a_job_can_only_move_along_the_state_machine() -> None:
    job = Job(Plan("x", ()))

    with pytest.raises(AssertionError):
        job.move(JobState.VERIFYING)
    job.move(JobState.DONE)
    for later in JobState:
        if later is not JobState.DONE:
            with pytest.raises(AssertionError):
                job.move(later)


def test_the_job_passes_through_verifying_then_extracting(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    with serve() as origin:
        plan = runtime_plan(origin, tmp_path, {"bin/run.exe": b"MZ"})
        jobs = runner()
        seen: list[JobState] = []
        real_replace = download.os.replace

        def spy(src: Path, dst: Path) -> None:
            seen.append(jobs.jobs()[-1].state)
            real_replace(src, dst)

        monkeypatch.setattr(download.os, "replace", spy)

        final = settle(jobs, plan)

    assert final.state is JobState.DONE
    assert seen == [JobState.VERIFYING, JobState.EXTRACTING]


def runtime_plan(
    origin: Origin,
    tmp_path: Path,
    entries: dict[str, bytes],
    raw_names: dict[str, str] | None = None,
) -> Plan:
    origin.files["/rt.zip"] = make_zip(tmp_path / "src.zip", entries, raw_names)
    return Plan(
        "rt",
        (item_for(origin, "/rt.zip", tmp_path / "data" / "_archives" / "rt.zip"),),
        unpack_to=tmp_path / "data" / "rt",
        entry_point="bin/run.exe",
    )


def test_a_runtime_archive_is_unpacked_into_its_folder_and_the_archive_removed(
    tmp_path: Path,
) -> None:
    with serve() as origin:
        plan = runtime_plan(origin, tmp_path, {"bin/run.exe": b"MZ", "bin/lib.dll": b"dll"})

        final = settle(runner(), plan)

    folder = tmp_path / "data" / "rt"
    assert final.state is JobState.DONE
    assert (folder / "bin" / "run.exe").read_bytes() == b"MZ"
    assert not (tmp_path / "data" / "_archives" / "rt.zip").exists()
    assert not staging_of(folder).exists()
    assert runner().state(plan) is InstallState.INSTALLED
    assert settle(runner(), plan).outcome is Outcome.ALREADY_PRESENT


def test_an_archive_without_the_expected_executable_is_not_installed(tmp_path: Path) -> None:
    with serve() as origin:
        plan = runtime_plan(origin, tmp_path, {"bin/other.exe": b"MZ"})

        final = settle(runner(), plan)

    assert final.failure is not None
    assert final.failure.kind is FailureKind.ARCHIVE
    assert not (tmp_path / "data" / "rt").exists()
    assert not staging_of(tmp_path / "data" / "rt").exists()


EVIL_NAMES = [
    "../evil.txt",
    "bin/../../evil.txt",
    "/abs/evil.txt",
    "C:/evil.txt",
    "C:evil.txt",
    "..\\evil.txt",
    "bin\\..\\..\\evil.txt",
    "\\evil.txt",
    ".. /evil.txt",
    "bin/run.exe:stream",
]


@pytest.mark.parametrize("name", EVIL_NAMES)
def test_zip_slip_entries_are_refused_and_nothing_is_written_outside(
    tmp_path: Path, name: str
) -> None:
    with serve() as origin:
        plan = runtime_plan(
            origin,
            tmp_path,
            {"bin/run.exe": b"MZ", "evil": b"pwned"},
            raw_names={"evil": name},
        )

        final = settle(runner(), plan)

    assert final.failure is not None
    assert final.failure.kind is FailureKind.ARCHIVE
    assert "unsafe path" in final.failure.message
    assert not (tmp_path / "evil.txt").exists()
    assert not (tmp_path / "data" / "evil.txt").exists()
    assert not (tmp_path / "data" / "rt").exists()
    assert [p.name for p in tmp_path.rglob("evil*")] == []


def test_a_symlink_entry_in_an_archive_is_refused(tmp_path: Path) -> None:
    archive = tmp_path / "x.zip"
    with zipfile.ZipFile(archive, "w") as z:
        info = zipfile.ZipInfo("link")
        info.external_attr = 0o120777 << 16
        z.writestr(info, "/etc/passwd")
    with zipfile.ZipFile(archive) as z, pytest.raises(download.DownloadError) as caught:
        download.safe_members(z, tmp_path / "out")

    assert caught.value.failure.kind is FailureKind.ARCHIVE


def test_unpacking_needs_room_for_the_uncompressed_files(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    archive = tmp_path / "data" / "_archives" / "rt.zip"
    with serve() as origin:
        plan = runtime_plan(origin, tmp_path, {"bin/run.exe": b"MZ" * 10_000})
        monkeypatch.setattr(
            download.shutil,
            "disk_usage",
            disk_with(lambda: 100 if archive.exists() else 10**12),
        )

        final = settle(runner(), plan)

    assert final.failure is not None
    assert final.failure.kind is FailureKind.INSUFFICIENT_SPACE
    assert (final.failure.needed_bytes, final.failure.available_bytes) == (20_000, 100)
    assert archive.exists()
    assert not (tmp_path / "data" / "rt").exists()


def test_progress_read_from_another_thread_stays_within_the_total(tmp_path: Path) -> None:
    with serve() as origin:
        origin.files["/m.bin"] = blob(4 * 1024 * 1024)
        origin.pause_per_piece = 0.005
        jobs = runner()
        job = jobs.submit(plan_for(origin, "/m.bin", tmp_path / "m.bin"))
        seen: set[JobState] = set()
        bad: list[int] = []
        stop = threading.Event()

        def poll() -> None:
            while not stop.is_set():
                status = jobs.status(job.id)
                assert status is not None
                seen.add(status.state)
                if not 0 <= status.bytes_done <= status.bytes_total:
                    bad.append(status.bytes_done)
                time.sleep(0.001)

        thread = threading.Thread(target=poll)
        thread.start()
        final = jobs.wait(job.id, 20)
        stop.set()
        thread.join()

    assert final is not None
    assert final.state is JobState.DONE
    assert JobState.DOWNLOADING in seen
    assert bad == []
