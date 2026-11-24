# pyright: reportUnknownLambdaType=false, reportUnknownArgumentType=false
"""The backend's choices on a Mac, made with the platform faked on this Windows PC.

`as_mac` makes `sys.platform` and `platform.machine()` say an Apple-silicon Mac; no program is
started and no model is read. What only a real Mac can show is listed in docs/MACOS.md."""

from __future__ import annotations

import os
import shutil
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from backend.engines.table import engine_paths, spec_for
from backend.manager import registry as registry_module
from backend.manager.inventory import Inventory
from backend.manager.manifest import Manifest
from backend.manager.platforms import MACOS_ARM64, WIN_X64
from backend.manager.profiles import (
    ALL_PROFILES,
    Device,
    ProfileId,
    runtime_set,
)
from backend.manager.registry import Registry
from backend.manager.resolve import Request, SettingsError, resolve
from backend.manager.runtimes import (
    NotInstallable,
    delete_runtime,
    local_build_message,
    program_of,
    runtime_executable,
    runtime_plan,
)
from backend.manager.selftest import ProbeFailed, run_selftest
from backend.manager.selftest_store import SelfTestStore
from backend.manager.storage import Storage

MAC: Registry = registry_module.load(platform=MACOS_ARM64)
WHISPER = "whispercpp-b5454-macos-metal"
LLAMA = "llama.cpp-b12068-macos-metal"
CRISPASR = "crispasr-v0.8.49-macos-metal"
QWEN3_8B = "qwen3-8b-q4_k_m"
TURBO = "whisper-large-v3-turbo"
VAD = "silero-vad-onnx-v6.2.3"


@pytest.fixture
def as_mac(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("sys.platform", "darwin")
    monkeypatch.setattr("platform.machine", lambda: "arm64")


@pytest.fixture
def no_path(monkeypatch: pytest.MonkeyPatch) -> None:
    """No `whisper-cli` on PATH or in the Homebrew folders, whatever this PC has."""
    real = shutil.which

    def which(name: str, mode: int = os.F_OK | os.X_OK, path: str | None = None) -> str | None:
        return None if name == "whisper-cli" else real(name, mode, path)

    monkeypatch.setattr(shutil, "which", which)


def put(path: Path, data: bytes = b"x") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return path


def install_mac(user_data: Path, *, whisper: bool = True) -> Storage:
    storage = Storage(user_data)
    for model_id in (TURBO, VAD, QWEN3_8B):
        put(storage.model_file(MAC.models[model_id]), b"model")
    for rid in (WHISPER, LLAMA, CRISPASR):
        runtime = MAC.runtimes[rid]
        if rid == WHISPER and not whisper:
            continue
        put(storage.runtime_dir(runtime) / (runtime.executable or ""), b"exe")
    return storage


# --- the runtime that is built on the machine -------------------------------------------------


def test_the_whisper_program_is_found_in_the_runtimes_folder(tmp_path: Path, no_path: None) -> None:
    storage = Storage(tmp_path)
    whisper = MAC.runtimes[WHISPER]
    assert runtime_executable(WHISPER, MAC, storage) is None

    built = put(storage.runtime_dir(whisper) / "whisper-cli")

    assert runtime_executable(WHISPER, MAC, storage) == built
    assert program_of(whisper, storage) == built


def test_the_whisper_program_is_found_on_path_when_it_is_not_in_the_folder(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    elsewhere = put(tmp_path / "bin" / "whisper-cli")
    monkeypatch.setattr(
        shutil, "which", lambda name, mode=0, path=None: str(elsewhere) if path is None else None
    )

    assert runtime_executable(WHISPER, MAC, Storage(tmp_path / "ud")) == elsewhere


def test_the_whisper_program_is_found_in_the_homebrew_folder_when_path_has_no_homebrew(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def which(name: str, mode: int = 0, path: str | None = None) -> str | None:
        if path is not None and "/opt/homebrew/bin" in path:
            return "/opt/homebrew/bin/whisper-cli"
        return None

    monkeypatch.setattr(shutil, "which", which)

    found = runtime_executable(WHISPER, MAC, Storage(tmp_path))

    assert found == Path("/opt/homebrew/bin/whisper-cli")


def test_the_folder_wins_over_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    storage = Storage(tmp_path)
    built = put(storage.runtime_dir(MAC.runtimes[WHISPER]) / "whisper-cli")
    monkeypatch.setattr(shutil, "which", lambda *a, **k: "/usr/bin/whisper-cli")

    assert runtime_executable(WHISPER, MAC, storage) == built


def test_the_missing_whisper_message_names_the_one_script_and_the_doc(
    tmp_path: Path,
) -> None:
    message = local_build_message(MAC.runtimes[WHISPER], Storage(tmp_path))

    assert "scripts/mac/build_whisper_cli.sh" in message
    assert "docs/MACOS.md" in message
    assert "whisper-cli" in message
    assert str(Storage(tmp_path).runtime_dir(MAC.runtimes[WHISPER])) in message


def test_a_runtime_built_on_the_machine_cannot_be_installed_and_says_how_to_build_it(
    tmp_path: Path,
) -> None:
    with pytest.raises(NotInstallable, match="build_whisper_cli.sh"):
        runtime_plan(WHISPER, MAC, Storage(tmp_path))


def test_the_other_mac_runtimes_install_from_a_tarball_into_their_own_folder(
    tmp_path: Path,
) -> None:
    storage = Storage(tmp_path)

    plan = runtime_plan(LLAMA, MAC, storage)

    assert [i.dest.name for i in plan.items] == ["llama-b12068-bin-macos-arm64.tar.gz"]
    assert plan.unpack_to == storage.runtime_dir(MAC.runtimes[LLAMA])
    assert plan.entry_point == "llama-b12068/llama-server"


def test_deleting_the_built_whisper_removes_its_folder_and_nothing_else(tmp_path: Path) -> None:
    storage = Storage(tmp_path)
    folder = storage.runtime_dir(MAC.runtimes[WHISPER])
    put(folder / "whisper-cli")
    neighbour = put(storage.runtime_dir(MAC.runtimes[LLAMA]) / "llama-b12068" / "llama-server")

    delete_runtime(WHISPER, MAC, storage)

    assert not folder.exists()
    assert neighbour.is_file()


def test_deleting_a_whisper_that_is_only_on_path_is_a_no_op(tmp_path: Path) -> None:
    delete_runtime(WHISPER, MAC, Storage(tmp_path))


def test_the_engine_finds_whisper_where_the_runtime_helper_does(
    tmp_path: Path, as_mac: None, no_path: None
) -> None:
    storage = Storage(tmp_path)
    built = put(storage.runtime_dir(MAC.runtimes[WHISPER]) / "whisper-cli")

    assert engine_paths("whispercpp-large-v3-turbo", storage, registry=MAC).binary == built


def test_the_engine_table_names_this_platforms_runtimes(as_mac: None) -> None:
    assert spec_for("whispercpp-large-v3-turbo").runtime_id == WHISPER
    assert spec_for("crispasr-qwen3-asr-1.7b").runtime_id == CRISPASR


def test_the_engine_table_on_windows_names_the_windows_runtimes() -> None:
    assert spec_for("whispercpp-large-v3-turbo").runtime_id == "whispercpp-b5454-win-cuda12.4"
    assert spec_for("crispasr-qwen3-asr-1.7b").runtime_id == "crispasr-v0.8.49-win-cuda"


# --- resolve, the step before a run ----------------------------------------------------------


def test_a_run_without_whisper_stops_with_the_message_that_names_the_script(
    tmp_path: Path, as_mac: None, no_path: None
) -> None:
    install_mac(tmp_path, whisper=False)

    with pytest.raises(SettingsError) as caught:
        resolve(Request(user_data=tmp_path), tmp_path / "p")

    text = str(caught.value)
    assert "scripts/mac/build_whisper_cli.sh" in text
    assert "Traceback" not in text


def test_a_run_with_the_built_whisper_resolves_on_a_mac(
    tmp_path: Path, as_mac: None, no_path: None
) -> None:
    install_mac(tmp_path)

    settings, _ports = resolve(Request(user_data=tmp_path), tmp_path / "p")

    assert WHISPER in settings.asr_identity
    assert LLAMA in settings.llm_identity


def test_an_explicit_program_beats_the_missing_build_message(
    tmp_path: Path, as_mac: None, no_path: None
) -> None:
    install_mac(tmp_path, whisper=False)
    mine = put(tmp_path / "mine" / "whisper-cli")

    settings, _ = resolve(Request(user_data=tmp_path, asr_bin=mine), tmp_path / "p")

    assert "file:whisper-cli" in settings.asr_identity


class FakeServer:
    seen: list[dict[str, Any]] = []

    def __init__(self, exe: Path, gguf: Path, **kwargs: Any) -> None:
        FakeServer.seen.append({"exe": exe, **kwargs})
        self.base_url = "http://127.0.0.1:1/v1"

    def __enter__(self) -> FakeServer:
        return self

    def __exit__(self, *_: object) -> None:
        return None


def llama_layers(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, *, cpu: bool) -> int:
    import threading

    FakeServer.seen = []
    monkeypatch.setattr("backend.manager.resolve.LlamaServer", FakeServer)
    _settings, ports = resolve(Request(user_data=tmp_path, cpu=cpu), tmp_path / "p")
    with ports.open_llm(threading.Event()):
        pass
    return FakeServer.seen[-1]["gpu_layers"]


def test_the_cpu_switch_on_a_mac_keeps_every_layer_off_the_gpu(
    tmp_path: Path, as_mac: None, no_path: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    install_mac(tmp_path)

    assert llama_layers(tmp_path, monkeypatch, cpu=True) == 0
    assert llama_layers(tmp_path, monkeypatch, cpu=False) == 99


def test_the_cpu_switch_on_windows_passes_the_layers_it_always_did(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    windows = registry_module.load(platform=WIN_X64)
    storage = Storage(tmp_path)
    for model_id in (TURBO, VAD, QWEN3_8B):
        put(storage.model_file(windows.models[model_id]), b"model")
    for rid in ("whispercpp-b5454-win-cpu", "llama.cpp-b12068-win-cpu"):
        runtime = windows.runtimes[rid]
        put(storage.runtime_dir(runtime) / (runtime.executable or ""), b"exe")

    assert llama_layers(tmp_path, monkeypatch, cpu=True) == 99


# --- the self-test and its fall back ---------------------------------------------------------


def probe_that(fails_on: Device | None, calls: list[tuple[str, Device]]) -> Callable[..., str]:
    def probe(stage: str, program: Path, model: Path, device: Device, timeout_s: float) -> str:
        calls.append((stage, device))
        if device is fails_on:
            raise ProbeFailed("Metal is not available")
        return "ok"

    return probe


def test_the_self_test_runs_the_mac_runtimes_on_metal(
    tmp_path: Path, as_mac: None, no_path: None
) -> None:
    storage = install_mac(tmp_path)
    calls: list[tuple[str, Device]] = []

    report = run_selftest(
        ALL_PROFILES[ProfileId.METAL_32GB],
        MAC,
        storage,
        SelfTestStore(tmp_path),
        probe_that(None, calls),
    )

    assert report.ok and report.device is Device.METAL and report.fallback is None
    assert calls == [("asr", Device.METAL), ("llm", Device.METAL)]
    assert [s.runtime_id for s in report.stages] == [WHISPER, LLAMA]
    assert report.message == "Self-test passed on METAL."


def test_a_metal_failure_falls_back_to_the_same_programs_on_the_cpu(
    tmp_path: Path, as_mac: None, no_path: None
) -> None:
    storage = install_mac(tmp_path)
    calls: list[tuple[str, Device]] = []

    report = run_selftest(
        ALL_PROFILES[ProfileId.METAL_32GB],
        MAC,
        storage,
        SelfTestStore(tmp_path),
        probe_that(Device.METAL, calls),
    )

    assert report.ok and report.device is Device.CPU and report.fallback is not None
    assert calls == [
        ("asr", Device.METAL),
        ("llm", Device.METAL),
        ("asr", Device.CPU),
        ("llm", Device.CPU),
    ]
    assert [s.runtime_id for s in report.stages] == [WHISPER, LLAMA]


def test_the_cpu_profile_on_a_mac_has_no_gpu_to_fall_back_from(
    tmp_path: Path, as_mac: None, no_path: None
) -> None:
    storage = install_mac(tmp_path)
    calls: list[tuple[str, Device]] = []

    report = run_selftest(
        ALL_PROFILES[ProfileId.APPLE_CPU],
        MAC,
        storage,
        SelfTestStore(tmp_path),
        probe_that(None, calls),
    )

    assert report.ok and report.device is Device.CPU
    assert {d for _, d in calls} == {Device.CPU}


def test_a_missing_whisper_is_reported_as_not_installed_and_not_as_a_metal_failure(
    tmp_path: Path, as_mac: None, no_path: None
) -> None:
    storage = install_mac(tmp_path, whisper=False)

    report = run_selftest(
        ALL_PROFILES[ProfileId.METAL_32GB],
        MAC,
        storage,
        SelfTestStore(tmp_path),
        probe_that(None, []),
    )

    asr = report.stages[0]
    assert not asr.installed and "not installed" in asr.detail
    assert report.fallback is None


# --- the inventory page ----------------------------------------------------------------------


def test_the_built_whisper_shows_in_the_inventory_with_its_real_path_and_size(
    tmp_path: Path, as_mac: None, no_path: None
) -> None:
    storage = install_mac(tmp_path)
    inventory = Inventory(MAC, storage, Manifest(tmp_path))

    from backend.manager.download import InstallState

    entry = inventory.entry(WHISPER, frozenset(), InstallState.NOT_INSTALLED)

    assert entry.installed
    assert entry.path == str(storage.runtime_dir(MAC.runtimes[WHISPER]) / "whisper-cli")
    assert entry.size_on_disk == 3
    assert ProfileId.METAL_32GB in entry.used_by_profiles
    assert ProfileId.GPU_24GB not in entry.used_by_profiles


def test_an_uninstalled_built_runtime_is_listed_as_not_installed(
    tmp_path: Path, as_mac: None, no_path: None
) -> None:
    storage = install_mac(tmp_path, whisper=False)
    inventory = Inventory(MAC, storage, Manifest(tmp_path))

    assert not inventory.is_installed(WHISPER)
    assert inventory.is_installed(LLAMA)


def test_the_license_page_gives_the_source_of_a_built_runtime_and_not_an_empty_url() -> None:
    from backend.manager.licenses import license_entries

    entries = {e.id: e for e in license_entries(MAC)}

    assert entries[WHISPER].source_url == "https://github.com/ggml-org/whisper.cpp"
    assert entries[LLAMA].source_url.endswith("llama-b12068-bin-macos-arm64.tar.gz")


# --- keys, data folder, power ----------------------------------------------------------------


def test_saving_a_cloud_key_on_a_mac_is_a_plain_refusal_in_traditional_chinese(
    tmp_path: Path,
) -> None:
    from backend.manager.secrets import (
        KEY_NOT_AVAILABLE_MESSAGE,
        LLM_KEY,
        SecretError,
        UnavailableSecretStore,
        default_secret_store,
    )

    store = default_secret_store(tmp_path, MACOS_ARM64)

    assert isinstance(store, UnavailableSecretStore)
    assert store.get(LLM_KEY) is None
    store.clear(LLM_KEY)
    with pytest.raises(SecretError) as caught:
        store.set(LLM_KEY, "sk-secret")
    assert str(caught.value) == KEY_NOT_AVAILABLE_MESSAGE
    assert "sk-secret" not in str(caught.value)
    assert "Mac" in KEY_NOT_AVAILABLE_MESSAGE and "金鑰" in KEY_NOT_AVAILABLE_MESSAGE
    assert not (tmp_path / "secrets").exists()


def test_windows_still_gets_the_dpapi_store(tmp_path: Path) -> None:
    from backend.manager.secrets import DpapiSecretStore, default_secret_store

    assert isinstance(default_secret_store(tmp_path, WIN_X64), DpapiSecretStore)
    assert isinstance(default_secret_store(tmp_path), DpapiSecretStore)


def test_the_data_folder_on_a_mac_is_in_application_support(tmp_path: Path) -> None:
    from backend.manager.storage import default_user_data

    home = tmp_path / "me"

    assert default_user_data({}, "darwin", home) == (
        home / "Library" / "Application Support" / "video-subtitle-translator"
    )


def test_the_environment_variable_still_comes_first_on_a_mac(tmp_path: Path) -> None:
    from backend.manager.storage import default_user_data

    assert default_user_data({"VST_USER_DATA": str(tmp_path / "d")}, "darwin", tmp_path) == (
        tmp_path / "d"
    )


def test_the_data_folder_on_windows_is_the_one_it_was(tmp_path: Path) -> None:
    from backend.manager.storage import default_user_data

    assert default_user_data({"LOCALAPPDATA": r"C:\Users\x\AppData\Local"}, "win32", tmp_path) == (
        Path(r"C:\Users\x\AppData\Local") / "video-subtitle-translator"
    )
    assert default_user_data({}, "linux", tmp_path) == (
        tmp_path / ".local" / "share" / "video-subtitle-translator"
    )


def test_sleep_and_shutdown_on_a_mac_are_two_named_commands() -> None:
    from backend.core.power import PowerAction, system_power

    ran: list[tuple[str, ...]] = []
    system_power(PowerAction.SLEEP, "darwin", lambda c: ran.append(c) or 0)
    system_power(PowerAction.SHUTDOWN, "darwin", lambda c: ran.append(c) or 0)

    assert ran[0] == ("pmset", "sleepnow")
    assert ran[1][0] == "osascript" and "shut down" in ran[1][-1]
    assert "sudo" not in " ".join(ran[0] + ran[1])


def test_sleep_and_shutdown_on_windows_are_the_commands_they_were() -> None:
    from backend.core.power import PowerAction, system_power

    ran: list[tuple[str, ...]] = []
    system_power(PowerAction.SLEEP, "win32", lambda c: ran.append(c) or 0)
    system_power(PowerAction.SHUTDOWN, "win32", lambda c: ran.append(c) or 0)

    assert ran == [
        ("rundll32.exe", "powrprof.dll,SetSuspendState", "0,1,0"),
        ("shutdown", "/s", "/t", "0"),
    ]


def test_a_failed_power_command_is_logged_and_never_raises(
    caplog: pytest.LogCaptureFixture,
) -> None:
    from backend.core.power import PowerAction, system_power

    with caplog.at_level("WARNING"):
        system_power(PowerAction.SHUTDOWN, "darwin", lambda c: 1)

    assert "did not succeed" in caplog.text


def test_a_platform_with_no_power_command_does_nothing_and_says_so(
    caplog: pytest.LogCaptureFixture,
) -> None:
    from backend.core.power import PowerAction, system_power

    ran: list[tuple[str, ...]] = []
    with caplog.at_level("WARNING"):
        system_power(PowerAction.SLEEP, "linux", lambda c: ran.append(c) or 0)

    assert ran == [] and "no sleep command" in caplog.text


def test_the_mac_whisper_runtime_ids_and_the_selftest_twin_are_the_same_row() -> None:
    twins = runtime_set(MACOS_ARM64)

    assert twins.whisper == twins.whisper_cpu == WHISPER
