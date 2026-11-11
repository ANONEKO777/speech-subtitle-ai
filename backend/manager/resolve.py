"""Turn what a user typed (CLI options, later an API body) into pipeline `Settings` and `Ports`.

This is the boundary: files are looked up and checked here, and what the pipeline keys on is
reduced to identity strings. The pipeline itself never sees a path to a model."""

from __future__ import annotations

import os
import threading
from collections.abc import Callable, Generator, Sequence
from contextlib import AbstractContextManager, contextmanager
from dataclasses import dataclass
from pathlib import Path

from backend.core import audio, vad
from backend.core.languages import DEFAULT_CODE, UnknownLanguage
from backend.core.languages import get as get_language
from backend.core.model import DEFAULT_SOURCE, Word
from backend.core.pipeline import LlmSession, Ports, ProgressCb, Settings
from backend.core.source_langs import UnknownSource, get_source
from backend.core.summarize import summary_chat
from backend.core.translate import BATCH_SIZE, GlossaryEntry, default_glossary
from backend.core.vad import Chunk
from backend.engines.chunks import transcribe_chunks
from backend.engines.crispasr import ENGINE_ID as CRISPASR_ID
from backend.engines.table import create_engine, engine_paths, spec_for
from backend.engines.whispercpp import ENGINE_ID as WHISPERCPP_ID
from backend.llm.ask import json_chat
from backend.llm.client import LLM_SEED, LlmConfig
from backend.llm.local_server import NO_THINK, LlamaServer
from backend.manager import registry as registry_module
from backend.manager.profiles import (
    LLAMA_CPU_RUNTIME,
    LLAMA_RUNTIME,
    QWEN3_8B,
    VAD_MODEL,
    WHISPER_CPU_RUNTIME,
    Device,
)
from backend.manager.registry import Model, Registry, Runtime
from backend.manager.runtimes import recover_runtimes
from backend.manager.storage import Storage, default_user_data

ENGINE_ALIASES = {"whispercpp": WHISPERCPP_ID, "crispasr": CRISPASR_ID}
DEFAULT_KEY_ENV = "VST_LLM_API_KEY"
LLM_CONTEXT = 8192


class SettingsError(ValueError):
    """An option names something that does not exist or cannot be used."""


@dataclass(frozen=True, slots=True)
class Request:
    engine: str = "whispercpp"
    asr_bin: Path | None = None
    asr_model: Path | None = None
    aligner: Path | None = None
    cpu: bool = False
    llm: str = QWEN3_8B
    llm_model: str | None = None
    llm_key_env: str = DEFAULT_KEY_ENV
    llm_key: str = ""
    """The key itself, when the caller holds it. The environment variable is the fallback."""
    llama_server: Path | None = None
    vad_model: Path | None = None
    ffmpeg_dir: Path | None = None
    user_data: Path | None = None
    glossary: tuple[GlossaryEntry, ...] = ()
    summary_en: bool = False
    batch_size: int = BATCH_SIZE
    target_lang: str = DEFAULT_CODE
    source_lang: str = DEFAULT_SOURCE


def _file_id(path: Path) -> str:
    return f"file:{path.name}:{path.stat().st_size}"


def _registry_id(model: Model, runtime: Runtime | None = None) -> str:
    text = f"{model.id}@{model.version}:{model.sha256[:16]}"
    return text if runtime is None else f"{text}|{runtime.id}"


def _need_file(path: Path, what: str) -> Path:
    if not path.is_file():
        raise SettingsError(f"{what} not found: {path}")
    return path


Transcribe = Callable[[Path, Sequence[Chunk], ProgressCb, threading.Event], list[Word]]


def _asr(request: Request, storage: Storage, registry: Registry) -> tuple[str, str, Transcribe]:
    engine_id = ENGINE_ALIASES.get(request.engine, request.engine)
    try:
        spec = spec_for(engine_id)
    except ValueError as exc:
        raise SettingsError(str(exc)) from exc
    cpu_runtime = WHISPER_CPU_RUNTIME if request.cpu and engine_id == WHISPERCPP_ID else None
    found = engine_paths(engine_id, storage, registry=registry, runtime_id=cpu_runtime)
    found_runtime = cpu_runtime or spec.runtime_id
    binary = _need_file(request.asr_bin or found.binary, f"{engine_id} program")
    model = _need_file(request.asr_model or found.model, f"{engine_id} model")
    aligner = request.aligner or found.aligner
    if spec.needs_aligner:
        aligner = _need_file(aligner or Path("aligner"), f"{engine_id} aligner model")
    runtime = registry.runtimes[found_runtime]
    model_entry = registry.models[spec.model_id]
    parts = [
        _file_id(request.asr_model) if request.asr_model else _registry_id(model_entry),
        _file_id(request.asr_bin) if request.asr_bin else f"runtime:{runtime.id}",
    ]
    if aligner is not None:
        aligner_entry = next(
            registry.models[n]
            for n in model_entry.needs
            if registry.models[n].kind is registry_module.ModelKind.ALIGNER
        )
        parts.append(_file_id(request.aligner) if request.aligner else _registry_id(aligner_entry))
    device = Device.CPU if request.cpu else Device.CUDA

    def transcribe(
        wav: Path, chunks: Sequence[Chunk], progress: ProgressCb, cancel: threading.Event
    ) -> list[Word]:
        engine = create_engine(engine_id, binary, model, aligner=aligner, device=device)
        return transcribe_chunks(engine, wav, chunks, request.source_lang, progress, cancel)

    return engine_id, "|".join(parts), transcribe


def _vad_model(request: Request, storage: Storage, registry: Registry) -> tuple[Path, str]:
    if request.vad_model:
        return _need_file(request.vad_model, "VAD model"), _file_id(request.vad_model)
    model = registry.models[VAD_MODEL]
    path = _need_file(storage.model_file(model), "VAD model (see --vad-model)")
    return path, _registry_id(model)


def _remote_config(request: Request) -> LlmConfig:
    if not request.llm_model:
        raise SettingsError("--llm-model is required when --llm is a URL")
    key = request.llm_key or os.environ.get(request.llm_key_env, "")
    try:
        return LlmConfig(
            request.llm.rstrip("/"), request.llm_model, key, extra_body={"seed": LLM_SEED}
        )
    except ValueError as exc:
        raise SettingsError(str(exc)) from exc


def _local_llm(request: Request, storage: Storage, registry: Registry) -> tuple[Path, Path, str]:
    runtime = registry.runtimes[LLAMA_CPU_RUNTIME if request.cpu else LLAMA_RUNTIME]
    server = request.llama_server or storage.runtime_dir(runtime) / (runtime.executable or "")
    server = _need_file(server, "llama-server program (see --llama-server)")
    as_path = Path(request.llm)
    if as_path.suffix.lower() == ".gguf" or as_path.is_file():
        gguf = _need_file(as_path, "LLM model file")
        model_id = _file_id(gguf)
    else:
        model = registry.models.get(request.llm)
        if model is None or model.kind is not registry_module.ModelKind.LLM:
            known = sorted(m.id for m in registry.models.values() if m.kind.value == "llm")
            raise SettingsError(
                f"--llm {request.llm!r} is not a URL, a .gguf file or a known LLM {known}"
            )
        gguf = _need_file(storage.model_file(model), f"LLM model {model.id}")
        model_id = _registry_id(model)
    runtime_id = _file_id(request.llama_server) if request.llama_server else runtime.id
    return server, gguf, f"{model_id}|{runtime_id}"


def resolve(request: Request, folder: Path) -> tuple[Settings, Ports]:
    storage = Storage(request.user_data or default_user_data())
    registry = registry_module.load()
    recover_runtimes(registry, storage)
    engine_id, asr_identity, transcribe = _asr(request, storage, registry)
    vad_path, vad_identity = _vad_model(request, storage, registry)
    ffmpeg_dir = request.ffmpeg_dir

    def extract_audio(video: Path, wav: Path, cancel: threading.Event) -> None:
        audio.extract(video, wav, tool_dir=ffmpeg_dir, cancel=cancel)

    def split_vad(wav: Path) -> list[Chunk]:
        return vad.split(wav, vad_path)

    opener: Callable[[threading.Event], AbstractContextManager[LlmSession]]
    if request.llm.startswith(("http://", "https://")):
        config = _remote_config(request)
        llm_identity = f"remote:{config.base_url}#{config.model}"

        @contextmanager
        def open_remote(cancel: threading.Event) -> Generator[LlmSession]:
            yield LlmSession(json_chat(config), summary_chat(config))

        opener = open_remote
    else:
        server, gguf, llm_identity = _local_llm(request, storage, registry)

        @contextmanager
        def open_local(cancel: threading.Event) -> Generator[LlmSession]:
            log_path = folder / "llama-server.log"
            with LlamaServer(
                server, gguf, log_path=log_path, ctx=LLM_CONTEXT, cancel=cancel
            ) as running:
                config = LlmConfig(
                    running.base_url, "local", extra_body={**NO_THINK, "seed": LLM_SEED}
                )
                yield LlmSession(json_chat(config), summary_chat(config))

        opener = open_local
    try:
        target = get_language(request.target_lang)
        source = get_source(request.source_lang)
        settings = Settings(
            asr_engine=engine_id,
            asr_identity=asr_identity,
            vad_identity=vad_identity,
            llm_identity=llm_identity,
            source_lang=source.code,
            glossary=(*default_glossary(source.code), *request.glossary),
            target_lang=target.code,
            summary_en=request.summary_en,
            batch_size=request.batch_size,
        )
    except (UnknownLanguage, UnknownSource, ValueError) as exc:
        raise SettingsError(str(exc)) from exc
    return settings, Ports(extract_audio, split_vad, transcribe, opener)
