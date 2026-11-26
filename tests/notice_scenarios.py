"""Every notice, raised the way the app raises it, as the window receives it.

`app/src/i18n/notices.wire.fixture.json` holds, for each scenario, the text and notices this module
produces now (`tests/test_notices.py` keeps them equal) and `before`: the text the same call gave
at commit 422a635, before the sentences became notices. `before` was written by running this module
on that commit, so it only calls what both versions have. The window's tests word each scenario in
Traditional Chinese and require `before` back, character for character.

Paths are written with `/`, so the fixture is the same on every system.
"""

# pyright: reportUnknownLambdaType=false, reportUnknownArgumentType=false

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from collections.abc import Callable
from dataclasses import asdict
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

import pytest

from backend.core import render, vc_runtime
from backend.core.fonts import burn_font, target_font
from backend.core.languages import LANGUAGES
from backend.core.model import Cue
from backend.manager import maintain, platforms, selftest
from backend.manager import registry as registry_module
from backend.manager.profiles import ProfileId, profiles_for
from backend.manager.runtimes import runtime_plan
from backend.manager.secrets import UnavailableSecretStore
from backend.manager.selftest_store import SelfTestStore
from backend.manager.storage import Storage

MAC = registry_module.load(platform=platforms.MACOS_ARM64)
WHISPER = "whispercpp-b5454-macos-metal"
DATA = Path("/vst-data")


def _slashes(value: Any) -> Any:
    if isinstance(value, str):
        return value.replace("\\", "/")
    if isinstance(value, dict):
        entries = cast("dict[str, object]", value)
        return {key: _slashes(item) for key, item in entries.items()}
    if isinstance(value, (list, tuple)):
        return [_slashes(item) for item in cast("list[object]", value)]
    return value


def _notices(exc: BaseException) -> list[dict[str, Any]]:
    try:
        from backend.core.notices import notices_of, to_json
    except ImportError:
        return []
    return to_json(notices_of(exc))


def _raised(call: Callable[[], object]) -> dict[str, Any]:
    try:
        call()
    except Exception as exc:
        return {"text": str(exc), "notices": _notices(exc)}
    raise AssertionError("nothing was raised")


def _cues(text: str, zh: str = "x", lang: str = "ja") -> list[Cue]:
    return [Cue(1, 0, 1000, text, zh, lang)]


def _no_font(_chars: object) -> Callable[[str], None]:
    return lambda _family: None


def _lacking(*lacks: str) -> Callable[[object], Callable[[str], tuple[Path, set[str]]]]:
    return lambda _chars: lambda _family: (Path("font.ttf"), set(lacks))


def _encoder(system: str) -> dict[str, Any]:
    render._video_encoder.cache_clear()  # pyright: ignore[reportPrivateUsage]
    return _raised(lambda: render._video_encoder("ffmpeg", system))  # pyright: ignore[reportPrivateUsage]


def _no_encoder(command: list[str], **_kwargs: Any) -> subprocess.CompletedProcess[Any]:
    return subprocess.CompletedProcess(command, 1, stdout="" if "-encoders" in command else b"")


def _selftest(profile_id: ProfileId, tmp: Path, mp: pytest.MonkeyPatch) -> dict[str, Any]:
    registry = registry_module.load(platform=platforms.WIN_X64)
    storage = Storage(tmp)
    profile = next(p for p in profiles_for(platforms.WIN_X64) if p.id is profile_id)
    program = tmp / "program.exe"
    program.write_bytes(b"x")
    mp.setattr(selftest, "runtime_executable", lambda *_a: program)
    mp.setattr(Storage, "model_file", lambda *_a: program)
    report = selftest.run_selftest(profile, registry, storage, SelfTestStore(tmp))
    raw = asdict(report)
    return {"report": raw}


def collect(tmp: Path) -> dict[str, dict[str, Any]]:
    found: dict[str, dict[str, Any]] = {}
    with pytest.MonkeyPatch.context() as mp:
        mp.setenv("VST_SIMULATE_NO_VCRUNTIME", "1")
        found["vc"] = _raised(lambda: vc_runtime.require(RuntimeError))
        gpu = _selftest(ProfileId.GPU_24GB, tmp, mp)["report"]
        cpu = _selftest(ProfileId.CPU, tmp, mp)["report"]
        for name, report in (("selftest.gpu", gpu), ("selftest.cpu", cpu)):
            found[f"{name}.message"] = {
                "text": report["message"],
                "notices": report.get("message_notices", []),
            }
            first = report["stages"][0]
            found[f"{name}.stage"] = {
                "text": first["detail"],
                "notices": first.get("detail_notices", []),
            }
        found["selftest.gpu.fallback"] = {
            "text": gpu["fallback"]["reason"],
            "notices": gpu["fallback"].get("reason_notices", []),
        }
    with pytest.MonkeyPatch.context() as mp:
        for system, name in (("win32", "Windows"), ("darwin", "Mac")):
            mp.setattr(sys, "platform", system)
            found[f"font.japanese{name}"] = _raised(
                lambda: burn_font(_cues("日本語です"), _no_font)
            )
    found["font.glyphs"] = _raised(lambda: burn_font(_cues("日本"), _lacking("本", "日")))
    for code, language in LANGUAGES.items():
        if language.fonts == LANGUAGES["zh-TW"].fonts:
            continue
        word = _cues("x", "Приветы 안녕")
        found[f"font.{code}.none"] = _raised(
            lambda lang=language, w=word: target_font(w, lang, _no_font)
        )
        found[f"font.{code}.glyphs"] = _raised(
            lambda lang=language, w=word: target_font(w, lang, _lacking("녕"))
        )
    with pytest.MonkeyPatch.context() as mp:
        mp.delenv("VST_SIMULATE_NO_H264", raising=False)
        mp.setattr(render.subprocess, "run", _no_encoder)
        found["encoder.windows"] = _encoder("win32")
        found["encoder.mac"] = _encoder("darwin")
        render._video_encoder.cache_clear()  # pyright: ignore[reportPrivateUsage]
    found["platform.linux"] = _raised(lambda: platforms.detect_platform("linux", "x86_64"))
    found["platform.intelMac"] = _raised(lambda: platforms.detect_platform("darwin", "x86_64"))
    found["localBuild"] = _raised(lambda: runtime_plan(WHISPER, MAC, Storage(DATA)))
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(shutil, "which", lambda *_a, **_k: "/opt/homebrew/bin/whisper-cli")
        context: Any = SimpleNamespace(registry=MAC, storage=Storage(DATA))
        found["foundElsewhere"] = _raised(
            lambda: maintain.delete_asset(context, WHISPER, False, "")
        )
    found["cloudKey"] = _raised(lambda: UnavailableSecretStore().set("llm", "key"))
    return {name: _slashes(entry) for name, entry in found.items()}


FIXTURE = Path(__file__).resolve().parents[1] / "app/src/i18n/notices.wire.fixture.json"

if __name__ == "__main__":
    import json
    import tempfile

    with tempfile.TemporaryDirectory(dir=os.environ.get("VST_SCRATCH")) as folder:
        found = json.dumps(collect(Path(folder)), ensure_ascii=False, indent=2)
        sys.stdout.buffer.write(found.encode("utf-8"))
