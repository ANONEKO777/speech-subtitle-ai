"""The local service the app talks to: `python -m backend.main`.

It listens on 127.0.0.1 on a port the system picks, makes a token that only this start knows, and
prints `READY port=<n> token=<t>` once it can answer. Every request must carry the token (see
`backend.api.auth`).
"""

from __future__ import annotations

import argparse
import asyncio
import socket
import sys
from collections.abc import AsyncGenerator, Callable, Sequence
from contextlib import asynccontextmanager
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import uvicorn
from fastapi import FastAPI

from backend.api import downloads, jobs, languages, models, projects, runtimes
from backend.api.auth import APP_ORIGINS, Guard, GuardConfig, local_hosts, new_token
from backend.api.deps import Context
from backend.core.jobs import JobBook, JobOptions, OptionsError, Resolver
from backend.core.pipeline import Ports, Settings
from backend.core.projects import ProjectStore
from backend.manager.context import ManagerContext, build_context
from backend.manager.storage import default_user_data

GRACEFUL_SHUTDOWN_S = 5


@dataclass(frozen=True, slots=True)
class AppConfig:
    user_data: Path
    guard: GuardConfig
    resolver: Resolver
    on_ready: Callable[[], None] | None = None
    manager: ManagerContext | None = field(default=None)
    projects_dir: Path | None = None


def default_resolver(user_data: Path) -> Resolver:
    """Turn options into settings and ports with the real engines. `backend.manager.resolve` is
    imported on first use because it loads onnxruntime, which takes seconds the service should not
    spend before it says READY."""

    def resolve_options(options: JobOptions, folder: Path) -> tuple[Settings, Ports]:
        from backend.manager import resolve as r

        request = r.Request(
            engine=options.engine,
            cpu=options.cpu,
            llm=options.llm,
            llm_model=options.llm_model,
            user_data=user_data,
            glossary=options.glossary,
            summary_en=options.summary_en,
            batch_size=options.batch_size,
            target_lang=options.target_lang,
        )
        try:
            return r.resolve(request, folder)
        except (r.SettingsError, ValueError) as exc:
            raise OptionsError(str(exc)) from exc

    return resolve_options


def create_app(config: AppConfig) -> FastAPI:
    jobs_book = JobBook()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
        if config.on_ready:
            config.on_ready()
        yield
        await asyncio.to_thread(jobs_book.shutdown)

    app = FastAPI(
        title="video-subtitle-translator",
        lifespan=lifespan,
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )
    app.state.manager = config.manager or build_context(config.user_data)
    app.state.projects = ProjectStore(config.projects_dir or config.user_data / "projects")
    app.state.jobs = jobs_book
    app.state.resolver = config.resolver
    for module in (downloads, models, runtimes, projects, jobs, languages):
        app.include_router(module.router)

    @app.get("/api/health")
    def health() -> dict[str, str]:  # pyright: ignore[reportUnusedFunction]
        return {"status": "ok"}

    @app.get("/api/hardware")
    def hardware(ctx: Context) -> dict[str, Any]:  # pyright: ignore[reportUnusedFunction]
        return asdict(ctx.detect_hardware())

    app.add_middleware(Guard, config=config.guard)
    return app


def serve(user_data: Path, projects_dir: Path | None, extra_origins: Sequence[str]) -> None:
    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    listener.listen(128)
    port: int = listener.getsockname()[1]
    token = new_token()
    guard = GuardConfig(token, local_hosts(port), APP_ORIGINS | frozenset(extra_origins))

    def ready() -> None:
        print(f"READY port={port} token={token}", flush=True)

    app = create_app(
        AppConfig(user_data, guard, default_resolver(user_data), ready, projects_dir=projects_dir)
    )
    server = uvicorn.Server(
        uvicorn.Config(app, log_level="warning", timeout_graceful_shutdown=GRACEFUL_SHUTDOWN_S)
    )
    server.run(sockets=[listener])


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m backend.main",
        description="Serve the local API on 127.0.0.1 and print READY port=<n> token=<t>.",
    )
    parser.add_argument(
        "--user-data",
        type=Path,
        metavar="DIR",
        help="folder for projects, runtimes and models "
        "(default: $VST_USER_DATA or %%LOCALAPPDATA%%/video-subtitle-translator)",
    )
    parser.add_argument(
        "--projects",
        type=Path,
        metavar="DIR",
        help="folder for project folders (default: projects inside the user data folder)",
    )
    parser.add_argument(
        "--origin",
        action="append",
        default=[],
        metavar="ORIGIN",
        help="one more page origin allowed to call the service, such as a dev server",
    )
    args = parser.parse_args(argv)
    serve(args.user_data or default_user_data(), args.projects, args.origin)
    return 0


if __name__ == "__main__":
    sys.exit(main())
