from __future__ import annotations

import argparse
import socket
from pathlib import Path

import uvicorn
from fastapi import FastAPI

from backend.api import downloads, models, runtimes
from backend.manager import registry
from backend.manager.context import build_context
from backend.manager.storage import default_user_data


def build_app(user_data: Path, registry_path: Path) -> FastAPI:
    app = FastAPI(title="video-subtitle-translator downloads (dev)")
    app.state.manager = build_context(user_data, registry.load(registry_path))
    for module in (downloads, models, runtimes):
        app.include_router(module.router)
    return app


def main() -> None:
    parser = argparse.ArgumentParser(description="Serve the download API on 127.0.0.1 for dev.")
    parser.add_argument("--data", type=Path, default=default_user_data())
    parser.add_argument("--registry", type=Path, default=registry.REGISTRY_PATH)
    parser.add_argument("--port", type=int, default=0)
    args = parser.parse_args()
    listener = socket.socket()
    listener.bind(("127.0.0.1", args.port))
    app = build_app(args.data, args.registry)
    print(f"READY port={listener.getsockname()[1]} data={args.data}", flush=True)
    uvicorn.Server(uvicorn.Config(app, log_level="warning")).run(sockets=[listener])


if __name__ == "__main__":
    main()
