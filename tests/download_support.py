from __future__ import annotations

import hashlib
import random
import threading
import time
import zipfile
from collections.abc import Callable, Generator
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from types import SimpleNamespace

from backend.manager.download import Item, JobRunner, JobStatus, Plan, RetryPolicy

FAST = RetryPolicy(max_failures=3, backoff_s=0.01, max_backoff_s=0.02, timeout_s=5)
PIECE = 64 * 1024


def blob(size: int, seed: int = 1) -> bytes:
    return random.Random(seed).randbytes(size)


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


class Origin:
    def __init__(self) -> None:
        self.files: dict[str, bytes] = {}
        self.requests: list[tuple[str, str | None]] = []
        self.cut_after: int | None = None
        self.cuts_left = 0
        self.ignore_range = False
        self.pause_per_piece = 0.0
        self.statuses: list[int] = []
        self.port = 0

    def url(self, path: str) -> str:
        return f"http://127.0.0.1:{self.port}{path}"

    def ranges(self, path: str) -> list[str | None]:
        return [r for p, r in self.requests if p == path]


@contextmanager
def serve() -> Generator[Origin]:
    origin = Origin()

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: object) -> None:
            return

        def do_GET(self) -> None:
            header = self.headers.get("Range")
            origin.requests.append((self.path, header))
            if origin.statuses:
                self.send_error(origin.statuses.pop(0))
                return
            data = origin.files.get(self.path)
            if data is None:
                self.send_error(404)
                return
            start = 0
            if header and not origin.ignore_range:
                start = int(header.removeprefix("bytes=").rstrip("-"))
                if start >= len(data):
                    self.send_error(416)
                    return
            body = data[start:]
            self.send_response(206 if start else 200)
            if start:
                self.send_header("Content-Range", f"bytes {start}-{len(data) - 1}/{len(data)}")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            limit = len(body)
            if origin.cuts_left and origin.cut_after is not None:
                origin.cuts_left -= 1
                limit = min(limit, origin.cut_after)
            try:
                for offset in range(0, limit, PIECE):
                    self.wfile.write(body[offset : min(offset + PIECE, limit)])
                    if origin.pause_per_piece:
                        time.sleep(origin.pause_per_piece)
            except OSError:
                pass
            self.close_connection = True

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    origin.port = server.server_address[1]
    threading.Thread(
        target=server.serve_forever, kwargs={"poll_interval": 0.02}, daemon=True
    ).start()
    try:
        yield origin
    finally:
        server.shutdown()
        server.server_close()


def item_for(origin: Origin, path: str, dest: Path, data: bytes | None = None) -> Item:
    data = origin.files[path] if data is None else data
    return Item(origin.url(path), dest, sha(data), len(data))


def runner(policy: RetryPolicy = FAST, resolve: Callable[[str], str] | None = None) -> JobRunner:
    return JobRunner(resolve or (lambda url: url), policy)


def settle(jobs: JobRunner, plan: Plan, timeout: float = 20) -> JobStatus:
    submitted = jobs.submit(plan)
    final = jobs.wait(submitted.id, timeout)
    assert final is not None
    return final


def wait_until(check: Callable[[], bool], timeout: float = 10) -> None:
    end = time.monotonic() + timeout
    while not check():
        assert time.monotonic() < end, "condition not met in time"
        time.sleep(0.01)


def make_zip(
    path: Path, entries: dict[str, bytes], raw_names: dict[str, str] | None = None
) -> bytes:
    with zipfile.ZipFile(path, "w") as archive:
        for name, data in entries.items():
            info = zipfile.ZipInfo(name)
            if raw_names and name in raw_names:
                info.filename = raw_names[name]
            archive.writestr(info, data)
    return path.read_bytes()


def disk_with(free: Callable[[], int] | int) -> Callable[[Path], SimpleNamespace]:
    def usage(_path: Path) -> SimpleNamespace:
        return SimpleNamespace(free=free() if callable(free) else free)

    return usage
