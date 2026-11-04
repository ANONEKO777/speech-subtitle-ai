import os
import shutil
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

REQUIRE_ENV = "VST_REQUIRE_ASSETS"
MODEL_ENV = "VST_SILERO_MODEL"
DEFAULT_MODEL = Path(__file__).parents[1] / "models" / "silero-vad" / "silero_vad.onnx"


def require(present: bool, reason: str) -> None:
    """Skip a test that needs a local asset, or fail it when CI sets VST_REQUIRE_ASSETS=1."""
    if present:
        return
    if os.environ.get(REQUIRE_ENV) == "1":
        pytest.fail(f"{reason} ({REQUIRE_ENV}=1 forbids skipping)", pytrace=False)
    pytest.skip(reason)


@pytest.fixture
def silero_model() -> Path:
    env = os.environ.get(MODEL_ENV)
    for candidate in (Path(env) if env else DEFAULT_MODEL, DEFAULT_MODEL):
        if candidate.is_file():
            return candidate
    require(False, f"run scripts/fetch_silero_vad.py or set {MODEL_ENV}")
    return DEFAULT_MODEL


@pytest.fixture(scope="session")
def ffmpeg_tools() -> None:
    present = shutil.which("ffmpeg") is not None and shutil.which("ffprobe") is not None
    require(present, "ffmpeg and ffprobe are not on PATH")
