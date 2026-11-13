"""Name the language of a video before it is imported, with the speech engine already installed.

Whisper large-v3 turbo names a language on every profile. On a GPU it takes about 3 s for the
`SAMPLE_COUNT` pieces, and the voice activity detector adds a fraction of a second. On a CPU a piece
costs about 10 s (measured), and fewer than `MIN_PIECES` say nothing, so a CPU profile is not asked:
the person's own choice stands."""

from __future__ import annotations

import threading
from collections.abc import Callable
from pathlib import Path

from backend.core import audio, vad
from backend.core.language_detect import Detection, detect
from backend.engines.base import EngineUnavailableError, ascii_temp_dir
from backend.engines.table import engine_paths
from backend.engines.whispercpp import ENGINE_ID, name_languages
from backend.manager.active import runs_on_cpu
from backend.manager.context import ManagerContext
from backend.manager.profiles import VAD_MODEL, Device

NAME_TIMEOUT_S = 40.0

Detector = Callable[[Path], Detection]
"""Names the language of a video file, or raises `Undetectable`, `audio.AudioError` or an
`EngineError`."""


class Undetectable(Exception):
    """This machine cannot name the language now, with the reason in words."""


def real_detector(ctx: ManagerContext, user_data: Path) -> Detector:
    one_at_a_time = threading.Lock()

    def run(video: Path) -> Detection:
        if runs_on_cpu(user_data, ctx.detect_hardware, ctx.registry):
            raise Undetectable("a CPU profile takes about 10 s for each piece of audio")
        found = engine_paths(ENGINE_ID, ctx.storage, registry=ctx.registry)
        if not (found.binary.is_file() and found.model.is_file()):
            raise EngineUnavailableError(f"{ENGINE_ID} is not installed")
        vad_model = ctx.storage.model_file(ctx.registry.models[VAD_MODEL])
        if not vad_model.is_file():
            raise EngineUnavailableError("the voice activity model is not installed")
        duration = audio.probe_duration_s(video)
        if duration is None:
            raise audio.AudioError(f"cannot read the length of {video.name}")
        with one_at_a_time, ascii_temp_dir() as work:
            return detect(
                duration,
                lambda starts, length: audio.cut_clips(video, starts, length, work),
                lambda wavs: name_languages(
                    found.binary, found.model, wavs, device=Device.CUDA, timeout_s=NAME_TIMEOUT_S
                ),
                lambda wavs: vad.speech_seconds(wavs, vad_model),
            )

    return run
