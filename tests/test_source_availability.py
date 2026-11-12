"""GET /api/languages tells the window which source languages this machine can process, so the
picker can say so before a job starts instead of after the backend refuses it."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from test_api import GUARD, Client, Rig, open_client

from backend.core.source_langs import MIXED_SOURCE
from backend.engines.table import engine_paths, missing_files
from backend.main import AppConfig, create_app
from backend.manager.context import ManagerContext, build_context
from backend.manager.hardware import Hardware
from backend.manager.registry import load as load_registry

BIG_GPU = Hardware("NVIDIA GeForce RTX", 24564, "596.36", 65536, 500_000)
NO_GPU = Hardware(None, None, None, 32768, 100_000)
ENGINE = MIXED_SOURCE.asr_engine


def open_app(data: Path, hardware: Hardware) -> tuple[Client, ManagerContext]:
    context = build_context(data, detect_hardware=lambda: hardware)
    app = create_app(AppConfig(data, GUARD, Rig().resolve, manager=context))
    return open_client(app), context


def sources(client: Client) -> dict[str, dict[str, Any]]:
    return {s["code"]: s for s in client.get("/api/languages").json()["sources"]}


def install_engine(context: ManagerContext) -> None:
    assert ENGINE is not None
    for path in missing_files(ENGINE, context.storage, registry=load_registry()):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"x")


def test_a_mixed_talk_is_offered_only_when_the_qwen3_files_are_installed(tmp_path: Path) -> None:
    client, context = open_app(tmp_path / "data", BIG_GPU)
    with client:
        found = sources(client)
        assert list(found) == ["en", "ja", "ja+en"]
        assert found["ja+en"]["available"] is False
        assert found["ja+en"]["reason"] == "missing_files"
        assert found["ja+en"]["native_name"] == "日本語と英語"
        assert found["en"]["available"] and found["ja"]["available"]
        install_engine(context)
        assert sources(client)["ja+en"]["available"] is True
        assert sources(client)["ja+en"]["reason"] is None


def test_a_mixed_talk_is_refused_while_jobs_run_on_the_cpu(tmp_path: Path) -> None:
    client, context = open_app(tmp_path / "data", NO_GPU)
    with client:
        install_engine(context)
        found = sources(client)
        assert found["ja+en"]["available"] is False
        assert found["ja+en"]["reason"] == "cpu"
        assert found["en"]["available"] is True


@pytest.mark.parametrize("missing", [0, 1, 2])
def test_one_missing_file_is_enough_to_refuse(tmp_path: Path, missing: int) -> None:
    client, context = open_app(tmp_path / "data", BIG_GPU)
    with client:
        install_engine(context)
        assert ENGINE is not None
        found = engine_paths(ENGINE, context.storage, registry=load_registry())
        victim = [found.binary, found.model, found.aligner][missing]
        assert victim is not None
        victim.unlink()
        assert sources(client)["ja+en"]["reason"] == "missing_files"
