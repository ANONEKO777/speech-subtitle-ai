from __future__ import annotations

from backend.core.languages import get
from backend.core.model import Cue
from backend.core.subtitle_io import render_ass
from scripts.check_wrap import count


def counts(code: str, zh: str) -> dict[str, int]:
    cues = [Cue(1, 0, 4000, "english words here", zh)]
    return count(render_ass(cues, get(code).wrap))


def test_breaks_between_han_and_kana_are_by_design_and_are_not_counted() -> None:
    ja = counts("ja", "これはとても長い日本語の字幕でありここで折り返しが必要になるほどです。" * 2)
    zh = counts(
        "zh-TW", "這是一段很長的中文字幕，需要在這裡換行才能放進畫面裡，所以我們寫長一點。" * 2
    )
    assert ja["breaks"] > 0 and ja["in_word"] == 0
    assert zh["breaks"] > 0 and zh["in_word"] == 0
