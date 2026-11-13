"""P31: the Mainland words the Japanese flow rewrites to Taiwan wording.
The sentences are invented."""

from __future__ import annotations

import pytest

from backend.core.languages import get as get_language
from backend.core.source_langs import JAPANESE_SOURCE


class TestMainlandWordingOfTheJapaneseFlow:
    @pytest.mark.parametrize(
        ("said", "written"),
        [
            ("這套硬件很便宜", "這套硬體很便宜"),
            ("請看演示。", "請看示範。"),
            ("我們進行演示", "我們進行示範"),
            ("五百万筆記錄", "五百萬筆記錄"),
            ("3万人", "3萬人"),
            ("當AI触碰資產", "當AI觸碰資產"),
            ("功能与工具", "功能與工具"),
            ("透過網頁訪問P4伺服器的介面", "透過網頁存取P4伺服器的介面"),
            ("就可以訪問P4的資訊", "就可以存取P4的資訊"),
            ("進行訪問，針對管理員則有P4-Admin", "進行存取，針對管理員則有P4-Admin"),
        ],
    )
    def test_the_mainland_word_becomes_the_taiwan_word(self, said: str, written: str) -> None:
        assert JAPANESE_SOURCE.clean(said) == written
        assert JAPANESE_SOURCE.clean(written) == written

    @pytest.mark.parametrize(
        "kept",
        [
            "他準備了演示文稿",
            "我訪問了Google總部",
            "進行訪問。目前狀態為技術預覽階段",
            "訪問京都的寺院",
            "硬體很便宜",
            "示範影片",
            "萬一失敗",
        ],
    )
    def test_a_sentence_without_the_mainland_sense_is_left_alone(self, kept: str) -> None:
        assert JAPANESE_SOURCE.clean(kept) == kept

    @pytest.mark.parametrize("text", ["這套硬件", "請看演示", "五百万筆", "訪問P4伺服器"])
    def test_the_english_flow_does_not_get_these_rules(self, text: str) -> None:
        assert get_language("zh-TW").terms_from("en", text) == text
