from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

import pytest

from backend.manager import registry
from backend.manager.hardware import Hardware
from backend.manager.profiles import PROFILES, Device, ProfileId, Stage, describe, select
from backend.manager.registry import ModelKind, RegistryError

REGISTRY = registry.load()
RAW: dict[str, Any] = json.loads(registry.REGISTRY_PATH.read_text(encoding="utf-8"))


def stages() -> list[tuple[str, Stage, ModelKind]]:
    out: list[tuple[str, Stage, ModelKind]] = []
    for profile in PROFILES.values():
        out.append((f"{profile.id} asr", profile.asr, ModelKind.ASR))
        if profile.asr_fallback:
            out.append((f"{profile.id} asr_fallback", profile.asr_fallback, ModelKind.ASR))
        out.append((f"{profile.id} llm", profile.llm, ModelKind.LLM))
    return out


def test_there_are_exactly_three_profiles_and_cpu_is_the_only_one_without_a_vram_floor() -> None:
    assert set(PROFILES) == set(ProfileId)
    assert [p.id for p in PROFILES.values() if p.min_vram_mib is None] == [ProfileId.CPU]


@pytest.mark.parametrize(("label", "stage", "kind"), stages(), ids=[s[0] for s in stages()])
def test_every_profile_stage_names_a_registry_model_and_a_runtime_that_runs_it(
    label: str, stage: Stage, kind: ModelKind
) -> None:
    model = REGISTRY.models[stage.model]
    runtime = REGISTRY.runtimes[stage.runtime]

    assert model.kind is kind, label
    assert runtime.engine == model.engine, label
    assert runtime.executable is not None, label


def test_the_default_asr_is_whisper_cpp_and_crispasr_is_only_a_24gb_fallback() -> None:
    default = PROFILES[ProfileId.GPU_24GB]

    assert REGISTRY.runtimes[default.asr.runtime].engine == "whispercpp"
    assert default.asr_fallback is not None
    assert REGISTRY.runtimes[default.asr_fallback.runtime].engine == "crispasr"
    assert all(p.asr_fallback is None for p in PROFILES.values() if p.id is not ProfileId.GPU_24GB)


def test_only_the_cpu_profile_runs_on_the_cpu_and_recommends_cloud() -> None:
    for profile in PROFILES.values():
        on_cpu = profile.id is ProfileId.CPU
        assert (profile.asr.device is Device.CPU) is on_cpu
        assert (profile.llm.device is Device.CPU) is on_cpu
        assert profile.recommend_cloud is on_cpu


def test_the_local_llm_size_comes_from_the_registry() -> None:
    assert {REGISTRY.models[p.llm.model].params_b for p in PROFILES.values()} == {8}


def test_crispasr_declares_its_aligner_and_vad_model_and_ascii_path_limit() -> None:
    qwen = REGISTRY.models["qwen3-asr-1.7b-q8_0"]

    assert {REGISTRY.models[n].kind for n in qwen.needs} == {ModelKind.ALIGNER, ModelKind.VAD}
    assert REGISTRY.runtimes["crispasr-v0.8.49-win-cuda"].ascii_paths_only
    assert not REGISTRY.runtimes["whispercpp-b5454-win-cuda12.4"].ascii_paths_only


def test_every_registry_entry_has_a_hash_license_version_and_size() -> None:
    for entry in (*REGISTRY.models.values(), *REGISTRY.runtimes.values()):
        assert len(entry.sha256) == 64, entry.id
        assert entry.license and entry.version and entry.size_bytes > 0, entry.id


REMOVE = object()


def with_field(section: str, key: str, value: object) -> dict[str, Any]:
    raw = copy.deepcopy(RAW)
    entry: dict[str, Any] = raw[section][0]
    if value is REMOVE:
        del entry[key]
    else:
        entry[key] = value
    return raw


@pytest.mark.parametrize(
    ("section", "key", "value", "message"),
    [
        ("models", "sha256", "ABC", "sha256"),
        ("models", "sha256", "G" * 64, "sha256"),
        ("models", "url", "http://example.com/x", "https"),
        ("models", "file", "dir/x.bin", "bare file name"),
        ("models", "size_bytes", 0, "size_bytes"),
        ("models", "size_bytes", True, "size_bytes"),
        ("models", "kind", "tts", "kind"),
        ("models", "license", "", "license"),
        ("models", "needs", ["nope"], "unknown id"),
        ("models", "needs", ["a", "a"], "distinct"),
        ("models", "extra", 1, "unexpected keys"),
        ("models", "license", REMOVE, "missing keys"),
        ("runtimes", "min_driver", "551", "min_driver"),
        ("runtimes", "ascii_paths_only", "yes", "ascii_paths_only"),
        ("runtimes", "executable", r"Release\x.exe", "executable"),
    ],
)
def test_a_malformed_registry_entry_is_refused_with_the_reason(
    section: str, key: str, value: object, message: str
) -> None:
    with pytest.raises(RegistryError, match=message):
        registry.parse(with_field(section, key, value))


def test_a_duplicate_id_is_refused() -> None:
    raw = copy.deepcopy(RAW)
    raw["runtimes"].append(copy.deepcopy(raw["runtimes"][0]))

    with pytest.raises(RegistryError, match="duplicate"):
        registry.parse(raw)


@pytest.mark.parametrize(("key", "value"), [("schema_version", 2), ("models", {})])
def test_a_malformed_registry_top_level_is_refused(key: str, value: object) -> None:
    with pytest.raises(RegistryError):
        registry.parse({**RAW, key: value})


def test_a_registry_that_is_not_json_is_refused(tmp_path: Path) -> None:
    broken = tmp_path / "registry.json"
    broken.write_text("{", encoding="utf-8")

    with pytest.raises(RegistryError, match="cannot read"):
        registry.load(broken)


def test_the_8gb_profile_runs_asr_then_llm_with_a_capped_context() -> None:
    small = PROFILES[ProfileId.GPU_8GB]

    assert small.concurrent_stages is False
    assert small.llm_ctx == 8192
    assert all(p.concurrent_stages for p in PROFILES.values() if p is not small)
    assert all(p.llm_ctx is None for p in PROFILES.values() if p is not small)


def test_describing_the_8gb_profile_says_the_stages_are_sequential_and_the_context_capped() -> None:
    text = describe(select(Hardware("GPU", 8192, "596.36", 32768, 1), REGISTRY), REGISTRY)

    assert "run one after the other" in text
    assert "capped at 8192 tokens" in text
    assert "run one after the other" not in describe(
        select(Hardware("GPU", 24564, "596.36", 32768, 1), REGISTRY), REGISTRY
    )


def test_licenses_list_what_each_archive_bundles() -> None:
    def licenses(runtime_id: str) -> set[str]:
        return set(REGISTRY.runtimes[runtime_id].license.split(" AND "))

    assert licenses("whispercpp-b5454-win-cuda12.4") == {
        "MIT",
        "Zlib",
        "LicenseRef-NVIDIA-CUDA-EULA",
    }
    assert licenses("crispasr-v0.8.49-win-cuda") == {
        "MIT",
        "BSD-3-Clause",
        "Apache-2.0",
        "MIT-0",
        "LicenseRef-NVIDIA-CUDA-EULA",
    }


@pytest.mark.parametrize(
    "executable",
    [
        "/abs/x.exe",
        "C:/Windows/x.exe",
        "C:x.exe",
        "../evil.exe",
        "a/../../evil.exe",
        "./x.exe",
        "a//b.exe",
        "a/",
        "",
        5,
    ],
)
def test_an_executable_that_could_escape_the_runtime_folder_is_refused(executable: object) -> None:
    with pytest.raises(RegistryError, match="executable"):
        registry.parse(with_field("runtimes", "executable", executable))


@pytest.mark.parametrize("file", ["..", ".", "C:x.zip", "a/b.zip", "/x.zip"])
def test_a_file_name_that_is_not_a_plain_name_is_refused(file: str) -> None:
    with pytest.raises(RegistryError, match="file"):
        registry.parse(with_field("models", "file", file))


@pytest.mark.parametrize(
    ("section", "key", "value", "message"),
    [
        ("models", "id", "has space", "id"),
        ("models", "id", "-leading", "id"),
        ("runtimes", "id", "", "id"),
        ("runtimes", "platform", "linux-x64", "platform"),
        ("runtimes", "backend", "vulkan", "backend"),
        ("runtimes", "needs", ["bad id"], "needs"),
        ("models", "size_bytes", 1.0, "size_bytes"),
    ],
)
def test_ids_platform_backend_and_size_types_are_checked(
    section: str, key: str, value: object, message: str
) -> None:
    with pytest.raises(RegistryError, match=message):
        registry.parse(with_field(section, key, value))


@pytest.mark.parametrize("section", ["models", "runtimes"])
def test_an_empty_models_or_runtimes_list_is_refused(section: str) -> None:
    with pytest.raises(RegistryError, match="empty"):
        registry.parse({**RAW, section: []})


def test_a_model_may_not_need_a_runtime_id() -> None:
    runtime_id = RAW["runtimes"][0]["id"]

    with pytest.raises(RegistryError, match="unknown id"):
        registry.parse(with_field("models", "needs", [runtime_id]))
