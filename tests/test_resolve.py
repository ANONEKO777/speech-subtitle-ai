from __future__ import annotations

from pathlib import Path

import pytest

from backend.core.artifacts import parse_chunks, parse_words, render_chunks, render_words
from backend.core.model import FormatError, Word
from backend.core.vad import Chunk
from backend.manager import registry as registry_module
from backend.manager.profiles import LLAMA_RUNTIME, QWEN3_8B, VAD_MODEL, WHISPER_RUNTIME
from backend.manager.registry import Registry
from backend.manager.resolve import Request, SettingsError, resolve
from backend.manager.storage import Storage

REGISTRY: Registry = registry_module.load()


def install(user_data: Path) -> Storage:
    storage = Storage(user_data)
    for model_id in (REGISTRY.models["whisper-large-v3-turbo"].id, VAD_MODEL, QWEN3_8B):
        path = storage.model_file(REGISTRY.models[model_id])
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"model")
    for runtime_id in (WHISPER_RUNTIME, LLAMA_RUNTIME):
        runtime = REGISTRY.runtimes[runtime_id]
        path = storage.runtime_dir(runtime) / (runtime.executable or "")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"exe")
    return storage


def test_registry_files_become_identities_with_the_registry_version_and_hash(
    tmp_path: Path,
) -> None:
    install(tmp_path)
    settings, _ = resolve(Request(user_data=tmp_path), tmp_path / "p")
    turbo = REGISTRY.models["whisper-large-v3-turbo"]
    assert turbo.sha256[:16] in settings.asr_identity
    assert REGISTRY.runtimes[WHISPER_RUNTIME].version in settings.asr_identity
    assert REGISTRY.models[QWEN3_8B].sha256[:16] in settings.llm_identity
    assert REGISTRY.models[VAD_MODEL].sha256[:16] in settings.vad_identity
    assert not any(str(tmp_path) in text for text in (
        settings.asr_identity, settings.llm_identity, settings.vad_identity))  # fmt: skip


def test_a_gguf_path_is_identified_by_name_and_size(tmp_path: Path) -> None:
    install(tmp_path)
    gguf = tmp_path / "mine.gguf"
    gguf.write_bytes(b"12345")
    settings, _ = resolve(Request(user_data=tmp_path, llm=str(gguf)), tmp_path / "p")
    assert "file:mine.gguf:5" in settings.llm_identity
    gguf.write_bytes(b"123456")
    again, _ = resolve(Request(user_data=tmp_path, llm=str(gguf)), tmp_path / "p")
    assert again.llm_identity != settings.llm_identity


def test_a_url_llm_is_identified_by_url_and_model(tmp_path: Path) -> None:
    install(tmp_path)
    request = Request(user_data=tmp_path, llm="http://127.0.0.1:11434/v1/", llm_model="qwen3:8b")
    settings, _ = resolve(request, tmp_path / "p")
    assert settings.llm_identity == "remote:http://127.0.0.1:11434/v1#qwen3:8b"


def test_the_api_key_is_read_from_the_environment_and_never_enters_a_key(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    install(tmp_path)
    monkeypatch.setenv("MY_KEY", "sk-secret-value")
    request = Request(
        user_data=tmp_path, llm="https://api.example.com/v1", llm_model="m", llm_key_env="MY_KEY"
    )
    settings, _ = resolve(request, tmp_path / "p")
    assert "sk-secret-value" not in repr(settings)


def test_default_product_names_come_first_and_user_terms_follow(tmp_path: Path) -> None:
    install(tmp_path)
    from backend.core.translate import GlossaryEntry

    request = Request(user_data=tmp_path, glossary=(GlossaryEntry("Acme", "艾克米"),))
    settings, _ = resolve(request, tmp_path / "p")
    terms = [entry.term for entry in settings.glossary]
    assert terms[0] == "Cursor"
    assert terms[-1] == "Acme"
    assert "Claude Code" in terms


def test_the_english_summary_is_opt_in(tmp_path: Path) -> None:
    install(tmp_path)
    assert resolve(Request(user_data=tmp_path), tmp_path)[0].summary_langs == ("zh-TW",)
    both = resolve(Request(user_data=tmp_path, summary_en=True), tmp_path)[0]
    assert both.summary_langs == ("zh-TW", "en")


def test_a_missing_runtime_names_the_path(tmp_path: Path) -> None:
    with pytest.raises(SettingsError, match=r"program not found: .*whisper-cli"):
        resolve(Request(user_data=tmp_path), tmp_path / "p")


def test_an_unknown_llm_lists_the_known_ones(tmp_path: Path) -> None:
    install(tmp_path)
    with pytest.raises(SettingsError, match=QWEN3_8B):
        resolve(Request(user_data=tmp_path, llm="gpt-nonsense"), tmp_path / "p")


def test_chunks_and_words_round_trip() -> None:
    chunks = [Chunk(0, 25_000), Chunk(24_600, 50_000)]
    assert parse_chunks(render_chunks(chunks)) == chunks
    words = [Word("Hello,", 10, 400), Word("世界", 400, 900)]
    assert parse_words(render_words("engine", words)) == words


@pytest.mark.parametrize(
    "text", ["", "[]", '{"schema_version": 2, "words": []}', '{"schema_version": 1}']
)
def test_bad_artifacts_are_format_errors(text: str) -> None:
    with pytest.raises(FormatError):
        parse_words(text)
    with pytest.raises(FormatError):
        parse_chunks(text)


def test_the_cpu_build_of_a_runtime_has_its_own_identity(tmp_path: Path) -> None:
    from backend.manager.profiles import LLAMA_CPU_RUNTIME, WHISPER_CPU_RUNTIME

    storage = install(tmp_path)
    for runtime_id in (WHISPER_CPU_RUNTIME, LLAMA_CPU_RUNTIME):
        runtime = REGISTRY.runtimes[runtime_id]
        path = storage.runtime_dir(runtime) / (runtime.executable or "")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"exe")
    gpu, _ = resolve(Request(user_data=tmp_path), tmp_path / "p")
    cpu, _ = resolve(Request(user_data=tmp_path, cpu=True), tmp_path / "p")
    assert gpu.asr_identity != cpu.asr_identity
    assert gpu.llm_identity != cpu.llm_identity


def test_crispasr_identity_carries_the_model_runtime_and_aligner_versions(tmp_path: Path) -> None:
    from backend.manager.profiles import CRISPASR_RUNTIME, QWEN3_ASR

    storage = install(tmp_path)
    runtime = REGISTRY.runtimes[CRISPASR_RUNTIME]
    exe = storage.runtime_dir(runtime) / (runtime.executable or "")
    exe.parent.mkdir(parents=True, exist_ok=True)
    exe.write_bytes(b"exe")
    model = REGISTRY.models[QWEN3_ASR]
    for entry in (model, *(REGISTRY.models[n] for n in model.needs)):
        path = storage.model_file(entry)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"m")
    settings, _ = resolve(Request(user_data=tmp_path, engine="crispasr"), tmp_path / "p")
    aligner = REGISTRY.models[model.needs[0]]
    assert model.sha256[:16] in settings.asr_identity
    assert aligner.sha256[:16] in settings.asr_identity
    assert CRISPASR_RUNTIME in settings.asr_identity


def test_resolving_restores_a_llama_runtime_that_a_kill_left_as_old(tmp_path: Path) -> None:
    storage = install(tmp_path)
    folder = storage.runtime_dir(REGISTRY.runtimes[LLAMA_RUNTIME])
    folder.rename(folder.with_name(folder.name + ".old"))

    _, ports = resolve(Request(user_data=tmp_path), tmp_path / "p")

    assert ports is not None
    assert (folder / (REGISTRY.runtimes[LLAMA_RUNTIME].executable or "")).is_file()
