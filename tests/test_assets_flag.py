import pytest
from conftest import REQUIRE_ENV, require


def test_a_missing_asset_skips_the_test_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(REQUIRE_ENV, raising=False)
    with pytest.raises(pytest.skip.Exception, match="no ffmpeg"):
        require(False, "no ffmpeg")


def test_a_missing_asset_fails_the_test_when_ci_requires_assets(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(REQUIRE_ENV, "1")
    with pytest.raises(pytest.fail.Exception, match="no ffmpeg"):
        require(False, "no ffmpeg")


def test_a_present_asset_passes_either_way(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(REQUIRE_ENV, "1")
    require(True, "unused")
