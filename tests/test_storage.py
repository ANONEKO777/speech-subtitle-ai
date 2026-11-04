from __future__ import annotations

from pathlib import Path

import pytest

from backend.manager import registry
from backend.manager.storage import (
    Storage,
    StorageConfig,
    StorageError,
    default_user_data,
    parse_config,
)

REGISTRY = registry.load()


def test_the_default_user_folder_is_under_local_app_data_unless_overridden() -> None:
    assert (
        default_user_data({"LOCALAPPDATA": r"C:\Users\x\AppData\Local"})
        == Path(r"C:\Users\x\AppData\Local") / "video-subtitle-translator"
    )
    assert default_user_data({"VST_USER_DATA": r"D:\vst", "LOCALAPPDATA": "C:/a"}) == Path(
        r"D:\vst"
    )


def test_models_live_under_the_user_folder_until_a_custom_folder_is_set(tmp_path: Path) -> None:
    storage = Storage(tmp_path)
    model = REGISTRY.models["whisper-large-v3-turbo"]

    assert storage.model_file(model) == tmp_path / "models" / model.id / model.file
    storage.update(StorageConfig(models_dir=tmp_path / "big" / "disk"))
    assert storage.model_file(model) == tmp_path / "big" / "disk" / model.id / model.file
    assert storage.runtimes_root == tmp_path / "runtimes"


def test_the_settings_are_read_back_by_a_new_instance(tmp_path: Path) -> None:
    Storage(tmp_path).update(
        parse_config({"models_dir": str(tmp_path / "m"), "mirrors": {"https://a/": "http://b/"}})
    )

    again = Storage(tmp_path)

    assert again.models_root == tmp_path / "m"
    assert again.resolve_url("https://a/x/y.bin") == "http://b/x/y.bin"


def test_the_longest_matching_mirror_prefix_wins_and_other_urls_are_untouched(
    tmp_path: Path,
) -> None:
    storage = Storage(tmp_path)
    storage.update(
        parse_config(
            {
                "mirrors": {
                    "https://huggingface.co/": "https://hf-mirror.example/",
                    "https://huggingface.co/ggerganov/": "https://other.example/g/",
                }
            }
        )
    )

    assert storage.resolve_url("https://huggingface.co/ggerganov/w.bin") == (
        "https://other.example/g/w.bin"
    )
    assert storage.resolve_url("https://huggingface.co/Qwen/q.gguf") == (
        "https://hf-mirror.example/Qwen/q.gguf"
    )
    assert storage.resolve_url("https://github.com/a/b") == "https://github.com/a/b"


@pytest.mark.parametrize(
    "raw",
    [
        [],
        {"models_dir": "relative"},
        {"models_dir": 5},
        {"mirrors": []},
        {"mirrors": {"http://a/": "https://b/"}},
        {"mirrors": {"https://a/": "file:///c/"}},
        {"mirrors": {"https://a/": 1}},
        {"extra": 1},
    ],
)
def test_bad_settings_are_refused(raw: object) -> None:
    with pytest.raises(StorageError):
        parse_config(raw)


def test_a_corrupt_settings_file_is_reported_not_ignored(tmp_path: Path) -> None:
    (tmp_path / "storage.json").write_text("{nope", encoding="utf-8")

    with pytest.raises(StorageError):
        Storage(tmp_path)
