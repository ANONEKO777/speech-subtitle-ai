from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import pytest
from test_pipeline import SETTINGS, Fakes, talk_words

from backend.core import cue_edits
from backend.core.languages import get
from backend.core.model import Cue
from backend.core.pipeline import run, save_edited_cues
from backend.core.subtitle_io import parse_subs, read_text_file, render_subs, write_text_file
from backend.core.translate import GlossaryEntry

LANG = get("zh-TW")
CURRENT = [
    Cue(0, 0, 2000, "one", "一"),
    Cue(1, 2000, 4000, "two", "二"),
    Cue(2, 4500, 6000, "three", "三"),
]


def codes(proposed: list[Cue]) -> list[tuple[int, str]]:
    return [(p.id, p.code) for p in cue_edits.check(CURRENT, proposed)]


def edit(index: int, **changes: object) -> list[Cue]:
    return [replace(c, **changes) if i == index else c for i, c in enumerate(CURRENT)]  # type: ignore[arg-type]


def test_an_unchanged_list_and_a_text_edit_pass() -> None:
    assert codes(list(CURRENT)) == []
    assert codes(edit(1, zh="改")) == []
    assert codes(edit(1, end_ms=4400)) == []


def test_an_end_that_reaches_the_next_start_is_an_overlap_blamed_on_the_edited_cue() -> None:
    assert codes(edit(0, end_ms=2001)) == [(0, "overlap")]
    assert codes(edit(1, start_ms=1999)) == [(1, "overlap")]
    assert codes(edit(1, end_ms=4600)) == [(1, "overlap")]


def test_touching_cues_are_fine_and_an_early_start_is_out_of_order() -> None:
    assert codes(edit(1, end_ms=4500)) == []
    assert (2, "out_of_order") in codes(edit(2, start_ms=1000, end_ms=1500))


def test_a_cue_over_seven_seconds_is_too_long_but_an_old_long_cue_is_left_alone() -> None:
    assert codes(edit(2, end_ms=11_501)) == [(2, "too_long")]
    long_ = [Cue(0, 0, 9000, "a", "甲"), Cue(1, 9000, 10_000, "b", "乙")]
    assert cue_edits.check(long_, [long_[0], replace(long_[1], zh="丙")]) == []


def test_empty_text_and_a_changed_english_line_are_refused() -> None:
    assert codes(edit(0, zh="")) == [(0, "empty")]
    assert codes(edit(0, src="uno")) == [(0, "english_changed")]


def put_state(tmp_path: Path, mark: str = "譯") -> tuple[Path, Path, Fakes]:
    video = tmp_path / "talk.mp4"
    video.write_bytes(b"x")
    folder = tmp_path / "p"
    fakes = Fakes(mark=mark, words=talk_words(8))
    run(video, folder, SETTINGS, fakes.ports())
    return video, folder, fakes


def save(folder: Path, edited: dict[int, str]) -> list[Cue]:
    current = parse_subs(read_text_file(folder / LANG.files.subs))
    proposed = [replace(c, zh=edited.get(c.id, c.zh)) for c in current]
    assert cue_edits.check(current, proposed) == []
    cue_edits.record(folder, LANG, current, proposed)
    save_edited_cues(folder, proposed, LANG)
    return proposed


def test_a_rerun_that_retranslates_keeps_every_edit_and_reports_how_many(tmp_path: Path) -> None:
    video, folder, _ = put_state(tmp_path)
    save(folder, {1: "人工第一句", 4: "人工第四句"})
    glossary = (GlossaryEntry("talk", "對談"),)
    changed = replace(SETTINGS, glossary=glossary)
    report = run(video, folder, changed, Fakes(mark="改", words=talk_words(8)).ports())
    assert report.edits_kept == 2 and report.edits_unmatched == 0
    after = {c.id: c for c in parse_subs(read_text_file(folder / LANG.files.subs))}
    assert after[1].zh == "人工第一句" and after[4].zh == "人工第四句"
    assert "改" in after[2].zh and "譯" not in after[2].zh
    assert "人工第一句" in (folder / LANG.files.srt).read_text(encoding="utf-8")
    assert json.loads((folder / "edits.zh-TW.json").read_text(encoding="utf-8"))["edited"]["cues"]


def test_an_edit_whose_english_line_is_gone_is_reported_and_stays_on_disk(tmp_path: Path) -> None:
    video, folder, _ = put_state(tmp_path)
    save(folder, {2: "人工"})
    other = Fakes(mark="改", words=talk_words(8)[: len(talk_words(8)) // 2])
    changed = replace(SETTINGS, asr_identity="whisper@2")
    report = run(video, folder, changed, other.ports())
    kept = [c.id for c in cue_edits.edited(folder, LANG)]
    assert report.edits_kept + report.edits_unmatched == len(kept) == 1


def test_a_rerun_with_nothing_changed_does_not_touch_the_edits(tmp_path: Path) -> None:
    video, folder, fakes = put_state(tmp_path)
    save(folder, {1: "人工"})
    report = run(video, folder, SETTINGS, fakes.ports())
    assert report.ran == () and report.edits_kept == 0
    assert parse_subs(read_text_file(folder / LANG.files.subs))[0].zh == "人工"


@pytest.mark.parametrize("name", ["edits.zh-TW.json"])
def test_the_edit_record_is_a_known_file_name(name: str) -> None:
    assert cue_edits.edits_file(LANG) == name


def test_putting_a_cue_back_to_the_translators_text_removes_its_mark(tmp_path: Path) -> None:
    _, folder, _ = put_state(tmp_path)
    original = parse_subs(read_text_file(folder / LANG.files.subs))
    save(folder, {2: "人工"})
    assert [c.id for c in cue_edits.edited(folder, LANG)] == [2]
    save(folder, {2: "再改"})
    assert [c.zh for c in cue_edits.edited(folder, LANG)] == ["再改"]
    save(folder, {2: original[1].zh})
    assert cue_edits.edited(folder, LANG) == []


def test_an_edit_whose_english_line_changed_is_kept_but_not_listed_as_applied(
    tmp_path: Path,
) -> None:
    _, folder, _ = put_state(tmp_path)
    save(folder, {2: "人工", 3: "人工三"})
    cues = parse_subs(read_text_file(folder / LANG.files.subs))
    moved = [replace(c, src="Another line.") if c.id == 2 else c for c in cues]
    write_text_file(folder / LANG.files.subs, render_subs(moved))
    assert [c.id for c in cue_edits.edited(folder, LANG)] == [2, 3]
    assert [c.id for c in cue_edits.applied(folder, LANG)] == [3]
