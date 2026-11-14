"""P33: the table lines for 間口が広い, コースクリア型 and the Perforce word シェルブ. The sentences
are invented."""

from __future__ import annotations

import pytest
from test_japanese_terms import named_lines, table_terms_in, term

from backend.core import translate
from backend.core.languages import get as get_language
from backend.core.source_langs import JAPANESE_SOURCE

EASY_TO_GET_INTO = "間口が広い (easy to get into)"
EASY_AND_DEEP = "間口が広く奥深い (easy to get into and deep)"
STAGES = "コースクリア型 (a game of stages)"


class TestWideEntrance:
    @pytest.mark.parametrize(
        "text",
        [
            "間口が広い店です",
            "間口が広く奥深い遊びです",
            "間口の広い設計にしました",
            "間口は広いままです",
            "間口広いです",
            "マグチが広く奥深い遊びです",
        ],
    )
    def test_the_idiom_names_the_term(self, text: str) -> None:
        assert EASY_TO_GET_INTO in table_terms_in(text)

    @pytest.mark.parametrize("text", ["間口を測ります", "入口が広い", "間口の狭い家です"])
    def test_other_words_do_not(self, text: str) -> None:
        assert EASY_TO_GET_INTO not in table_terms_in(text)

    def test_a_request_gives_the_taiwan_phrase(self) -> None:
        lines = named_lines("間口が広い遊びです")
        assert f'- "{EASY_TO_GET_INTO}" must be translated as "容易入門"' in lines

    @pytest.mark.parametrize(
        "zh",
        [
            "容易入門又深奧的遊戲",
            "入門簡單但深不可測",
            "入門門檻低的模式",
            "入門容易的主題公園",
            "好上手也耐玩",
            "容易上手的設計",
            "易於入門",
            "門檻低的主題公園",
        ],
    )
    def test_a_natural_taiwan_phrase_is_right(self, zh: str) -> None:
        assert term(EASY_TO_GET_INTO).kept_in(zh)

    @pytest.mark.parametrize(
        "zh",
        [
            "就是入口低且深不可測，容易入門",
            "入口門檻低的主題公園，容易入門",
            "廣開入口的模式，容易入門",
            "寬廣的入口，容易入門",
            "開闊的入口，容易入門",
            "入口寬，容易入門",
            "廣泛且深奧的遊戲，容易入門",
            "廣泛而深奧，容易入門",
            "廣泛深奧，容易入門",
        ],
    )
    def test_a_literal_wide_entrance_is_wrong_even_beside_a_right_phrase(self, zh: str) -> None:
        assert not term(EASY_TO_GET_INTO).kept_in(zh)

    def test_a_plain_word_for_entrance_is_not_wrong_by_itself(self) -> None:
        assert term(EASY_TO_GET_INTO).kept_in("從入口進去，容易入門")

    def test_the_static_prompt_no_longer_glosses_the_idiom(self) -> None:
        text = translate.system_prompt_template(get_language("zh-TW"), JAPANESE_SOURCE)
        assert "間口" not in text
        assert "barrier to entry" not in text


class TestWideEntranceAndDeep:
    def test_the_two_idioms_are_two_lines_and_a_request_has_both(self) -> None:
        lines = named_lines("間口が広く奥深い遊びです")
        assert f'- "{EASY_AND_DEEP}" must be translated as "容易入門又深奧"' in lines
        assert f'- "{EASY_TO_GET_INTO}" must be translated as "容易入門"' in lines

    @pytest.mark.parametrize("text", ["間口が広く奥深い", "マグチが広く奥深い", "間口の広く奥深い"])
    def test_the_pair_names_the_longer_term(self, text: str) -> None:
        assert EASY_AND_DEEP in table_terms_in(text)

    def test_the_plain_idiom_does_not_name_the_longer_term(self) -> None:
        assert EASY_AND_DEEP not in table_terms_in("間口が広い遊びです")

    @pytest.mark.parametrize("zh", ["容易入門又深奧", "入門簡單但深不可測", "好上手又耐玩"])
    def test_a_natural_phrase_is_right(self, zh: str) -> None:
        assert term(EASY_AND_DEEP).kept_in(zh)

    @pytest.mark.parametrize(
        "zh",
        [
            "就是入口低且深不可測",
            "入口門檻低而深",
            "入口寬又深",
            "入口廣又深",
            "廣開入口又深",
            "開闊的入口",
            "寬廣入口",
            "廣泛且深奧",
            "廣泛而深奧",
            "廣泛深奧",
        ],
    )
    def test_a_literal_phrase_is_wrong_even_beside_the_right_one(self, zh: str) -> None:
        assert term(EASY_AND_DEEP).kept_in("容易入門又深奧")
        assert not term(EASY_AND_DEEP).kept_in(f"容易入門又深奧，{zh}")


class TestCourseClearGames:
    @pytest.mark.parametrize(
        "text", ["コースクリア型のゲームです", "ステージクリア式の遊び", "ステージクリア型"]
    )
    def test_a_game_of_stages_names_the_term(self, text: str) -> None:
        assert STAGES in table_terms_in(text)

    @pytest.mark.parametrize(
        "text",
        [
            "クリア後に開きます",
            "キャッシュをクリアします",
            "コースを選びます",
            "ステージクリアの条件",
        ],
    )
    def test_clearing_something_else_does_not(self, text: str) -> None:
        assert STAGES not in table_terms_in(text)

    @pytest.mark.parametrize("zh", ["關卡制的遊戲", "過關型遊戲", "關卡式的設計"])
    def test_a_natural_form_is_right(self, zh: str) -> None:
        assert term(STAGES).kept_in(zh)

    @pytest.mark.parametrize(
        "zh", ["賽道清除類的遊戲，關卡制", "關卡清除類，關卡制", "賽程清除，關卡制"]
    )
    def test_a_literal_form_is_wrong(self, zh: str) -> None:
        assert not term(STAGES).kept_in(zh)


class TestShelve:
    @pytest.mark.parametrize(
        "text", ["変更をシェルブします", "シェルブの際に確認", "シェルブしてから出します"]
    )
    def test_the_perforce_word_names_the_term(self, text: str) -> None:
        assert "シェルブ" in table_terms_in(text)

    def test_a_request_gives_the_taiwan_form(self) -> None:
        assert '- "シェルブ" must be translated as "擱置"' in named_lines("シェルブしておく")

    @pytest.mark.parametrize("zh", ["先擱置再提交", "用 shelve 暫存", "Shelve 的變更"])
    def test_the_taiwan_form_or_the_english_word_is_right(self, zh: str) -> None:
        assert term("シェルブ").kept_in(zh)

    @pytest.mark.parametrize(
        "zh", ["而非Shell，擱置", "shelb 後擱置", "在 Shell 上擱置", "SHELL擱置"]
    )
    def test_a_shell_or_a_garble_is_wrong_even_beside_the_right_form(self, zh: str) -> None:
        assert not term("シェルブ").kept_in(zh)

    def test_the_word_is_not_the_shell_of_a_computer(self) -> None:
        assert "シェルブ" not in table_terms_in("シェルを開きます")


class TestWorkflowTerm:
    @pytest.mark.parametrize(
        "zh", ["不同分支的 workflows", "工作流程 workflow", "Work Flow 的設計"]
    )
    def test_a_workflow_in_latin_letters_is_wrong(self, zh: str) -> None:
        assert not term("ワークフロー").kept_in(f"工作流程，{zh}")

    def test_the_chinese_word_is_right(self) -> None:
        assert term("ワークフロー").kept_in("不同分支的工作流程")
