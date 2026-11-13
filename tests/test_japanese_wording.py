"""P31, P32: the Mainland words the Japanese flow rewrites to Taiwan wording.
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
            ("三十万張照片", "三十萬張照片"),
            ("3万人", "3萬人"),
            ("當AI触碰資產", "當AI觸碰資產"),
            ("貓与狗", "貓與狗"),
            ("透過網頁訪問P4伺服器的介面", "透過網頁存取P4伺服器的介面"),
            ("就可以訪問P4的資訊", "就可以存取P4的資訊"),
            ("進行訪問，針對訪客則有REST說明", "進行存取，針對訪客則有REST說明"),
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
            "進行訪問。下週開始營業",
            "訪問京都的寺院",
            "硬體很便宜",
            "示範影片",
            "萬一失敗",
        ],
    )
    def test_a_sentence_without_the_mainland_sense_is_left_alone(self, kept: str) -> None:
        assert JAPANESE_SOURCE.clean(kept) == kept

    @pytest.mark.parametrize(
        "visit",
        [
            "前往訪問Apple的總部，順便試用Git",
            "他訪問NHK的節目，談Git",
            "他們訪問Apple的團隊，談API",
            "我們前往訪問Tokyo的朋友，聊AI",
            "進行訪問Apple時使用了Git",
            "親自訪問OpenAI公司，討論MCP",
        ],
    )
    def test_a_visit_to_a_company_a_place_or_a_broadcaster_stays_a_visit(self, visit: str) -> None:
        assert JAPANESE_SOURCE.clean(visit) == visit

    @pytest.mark.parametrize(
        ("said", "written"),
        [
            ("訪問Perforce Server的API", "存取Perforce Server的API"),
            ("同時訪問GitHub上的資料", "同時存取GitHub上的資料"),
            ("透過App訪問Docker", "透過App存取Docker"),
            ("進行訪問時用Apps與Git", "進行存取時用Apps與Git"),
        ],
    )
    def test_a_software_cue_that_is_not_a_visit_still_changes(
        self, said: str, written: str
    ) -> None:
        assert JAPANESE_SOURCE.clean(said) == written

    def test_a_name_that_only_contains_a_software_word_is_not_a_software_word(self) -> None:
        for kept in (
            "他訪問Apple的新品發表會",
            "他進行訪問，Appleton先生答應了",
            "我訪問Capital公司",
        ):
            assert JAPANESE_SOURCE.clean(kept) == kept

    @pytest.mark.parametrize("text", ["這套硬件", "請看演示", "五百万筆", "訪問P4伺服器"])
    def test_the_english_flow_does_not_get_these_rules(self, text: str) -> None:
        assert get_language("zh-TW").terms_from("en", text) == text

    @pytest.mark.parametrize("said", ["外掛程式", "插件程式", "這個外掛程式很好用"])
    def test_a_plug_in_is_written_with_one_word_in_the_japanese_flow(self, said: str) -> None:
        from backend.core.zh_tw import taiwan_terms

        assert "外掛程式" not in JAPANESE_SOURCE.clean(taiwan_terms(said))
        assert "外掛" in JAPANESE_SOURCE.clean(taiwan_terms(said))
