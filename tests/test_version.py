"""scripts/version.py: every copy of the app version agrees with tauri.conf.json, and a release tag
names that version."""

from __future__ import annotations

import json
import shutil
import tomllib
from pathlib import Path

import pytest

from scripts import version

ROOT = version.ROOT


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    for path in {c.path for c in version.COPIES}:
        (tmp_path / path).parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / path, tmp_path / path)
    return tmp_path


def _toml(path: Path) -> dict[str, object]:
    return tomllib.loads(path.read_text(encoding="utf-8"))


def test_this_repository_has_one_version() -> None:
    assert version.problems(ROOT) == []


def test_set_writes_every_copy_and_the_manifests_still_parse(repo: Path) -> None:
    version.set_version(repo, "7.8.9")
    assert version.problems(repo, "v7.8.9") == []
    assert (
        json.loads((repo / "app/src-tauri/tauri.conf.json").read_text("utf-8"))["version"]
        == "7.8.9"
    )
    lock = json.loads((repo / "app/package-lock.json").read_text("utf-8"))
    assert (lock["version"], lock["packages"][""]["version"]) == ("7.8.9", "7.8.9")
    assert _toml(repo / "app/src-tauri/Cargo.toml")["package"] == {
        **_toml(ROOT / "app/src-tauri/Cargo.toml")["package"],  # type: ignore[dict-item]
        "version": "7.8.9",
    }
    assert _toml(repo / "pyproject.toml")["project"]["version"] == "7.8.9"  # type: ignore[index]


def test_set_leaves_dependency_versions_alone(repo: Path) -> None:
    before = (repo / "app/package-lock.json").read_text("utf-8")
    version.set_version(repo, "7.8.9")
    after = (repo / "app/package-lock.json").read_text("utf-8")
    changed = [
        (a, b) for a, b in zip(before.splitlines(), after.splitlines(), strict=True) if a != b
    ]
    assert len(changed) == 2


def test_a_copy_that_drifts_is_named(repo: Path) -> None:
    package = repo / "app/package.json"
    package.write_text(
        package.read_text("utf-8").replace('"version": "', '"version": "9', 1), "utf-8"
    )
    [problem] = version.problems(repo)
    assert problem.startswith("app/package.json: 9")


def test_a_tag_must_name_the_version(repo: Path) -> None:
    current = version.found(repo)[0][1]
    assert version.problems(repo, f"v{current}") == []
    assert version.problems(repo, current) != []
    assert version.problems(repo, "v9.9.9") != []


def test_set_refuses_a_version_that_is_not_x_y_z(repo: Path) -> None:
    with pytest.raises(ValueError):
        version.set_version(repo, "0.2.0-rc.1")


def test_set_writes_nothing_when_a_copy_cannot_be_found(repo: Path) -> None:
    uv_lock = repo / "uv.lock"
    renamed = uv_lock.read_text("utf-8").replace('name = "video', 'name = "renamed')
    uv_lock.write_text(renamed, "utf-8")
    with pytest.raises(ValueError, match="uv.lock"):
        version.set_version(repo, "7.8.9")
    assert version.found(repo)[0][1] != "7.8.9"
