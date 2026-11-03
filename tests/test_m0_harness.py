from pathlib import Path

from scripts.m0.harness import ascii_stem


def test_chinese_video_name_becomes_ascii_and_keeps_its_ascii_words(tmp_path: Path) -> None:
    video = tmp_path / "上個月向生產環境提交 2500 個 PR 的方法-lauren @poteto X.mp4"

    stem = ascii_stem(video)

    assert stem.isascii()
    assert stem.startswith("2500-PR-lauren-poteto-X-")
    assert stem == ascii_stem(video)


def test_same_name_in_different_folders_gets_different_stems(tmp_path: Path) -> None:
    a = ascii_stem(tmp_path / "一" / "演講.mp4")
    b = ascii_stem(tmp_path / "二" / "演講.mp4")

    assert a.isascii() and b.isascii()
    assert a != b
