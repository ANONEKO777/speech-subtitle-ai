"""P31: the Japanese term table (what it names, what it counts wrong), the glossary a user writes,
the Perforce spellings and the cache key. The sentences are invented."""

from __future__ import annotations

import json
import re
from collections.abc import Sequence
from dataclasses import replace

import pytest

from backend.core import pipeline, translate
from backend.core.ja_terms import JaTerm
from backend.core.languages import get as get_language
from backend.core.model import Cue
from backend.core.source_langs import JAPANESE_SOURCE, SourceLanguage
from scripts.p30_quality_check import glossary as table_score

CREATE_BRANCH = "ブランチを切る (create a branch)"


def ja(*texts: str) -> list[Cue]:
    return [Cue(i, i * 2000, i * 2000 + 1500, t, lang="ja") for i, t in enumerate(texts, 1)]


def spans(
    cues: list[Cue], source: SourceLanguage = JAPANESE_SOURCE, limit: int = 6
) -> list[tuple[int, int]]:
    return [(u.start, u.stop) for u in translate.sentence_units(cues, 0, len(cues), limit, source)]


def named_lines(text: str, glossary: Sequence[translate.GlossaryEntry] = ()) -> list[str]:
    cues = ja(text)
    batch = translate.Batch((translate.Unit(0, 1),))
    request = translate.build_request(cues, batch, glossary, 0, source=JAPANESE_SOURCE)
    prompt = request.messages[0]["content"]
    return [line for line in prompt.splitlines() if "must be translated as" in line]


def table_terms_in(text: str) -> list[str]:
    return [term.said for term in JAPANESE_SOURCE.terms if term.in_source(text)]


def term(said: str) -> JaTerm:
    return next(t for t in JAPANESE_SOURCE.terms if t.said == said)


class TestCodeTerm:
    @pytest.mark.parametrize(
        "text",
        [
            "コードを書きます",
            "このコードをレビューします",
            "コードレビューの基準",
            "Pythonのコードです",
        ],
    )
    def test_code_in_the_programming_sense_names_the_term(self, text: str) -> None:
        assert "コード" in table_terms_in(text)

    def test_source_code_names_its_own_term_and_not_the_plain_one(self) -> None:
        assert table_terms_in("ソースコードを読む") == ["ソースコード"]

    @pytest.mark.parametrize(
        "text",
        [
            "レコードを検索します",
            "バーコードを読む",
            "QRコードを出す",
            "エラーコードが出た",
            "ステータスコード200",
            "Visual Studioコードを開く",
            "Visual Studio コードを開く",
            "クロードコードを使う",
            "Claude コードを使う",
            "デコードします",
            "エンコードします",
            "電源コードを抜く",
            "コード進行を覚える",
            "コードネームは秘密です",
        ],
    )
    def test_code_inside_another_word_does_not_name_the_term(self, text: str) -> None:
        assert "コード" not in table_terms_in(text)

    def test_the_prompt_for_a_record_does_not_say_code(self) -> None:
        assert not any("コード" in line for line in named_lines("レコードが500万件あります"))

    def test_correct_output_for_an_error_code_is_not_counted_wrong(self) -> None:
        cue = Cue(1, 0, 1000, "エラーコードを確認します", "請確認錯誤碼", lang="ja")
        assert table_score([cue])["コード"] == (0, 0)

    @pytest.mark.parametrize("zh", ["錯誤碼", "QR 碼", "條碼", "編碼", "解碼", "驗證碼"])
    def test_a_taiwan_word_with_a_code_character_is_not_a_wrong_code(self, zh: str) -> None:
        assert term("コード").kept_in(f"程式碼和{zh}")

    @pytest.mark.parametrize("zh", ["這段代碼", "這段碼"])
    def test_the_wrong_code_words_still_fail(self, zh: str) -> None:
        assert not term("コード").kept_in(f"程式碼和{zh}")


class TestBranchIdiom:
    @pytest.mark.parametrize(
        "text",
        [
            "ブランチを切る",
            "新しいブランチを切って",
            "ブランチを切った",
            "ブランチを1本切ります",
            "ブランチを切りました",
            "ブランチを切り出す",
            "ブランチを切り、作業する",
            "ブランチが切られる",
        ],
    )
    def test_creating_a_branch_names_the_idiom(self, text: str) -> None:
        assert CREATE_BRANCH in table_terms_in(text)

    @pytest.mark.parametrize(
        "text",
        [
            "ブランチを切り替える",
            "ブランチを切り替えます",
            "ブランチを切り替えて確認",
            "ブランチを切り離す",
            "ブランチを切り戻す",
            "ブランチ切替の方法",
        ],
    )
    def test_switching_a_branch_does_not_name_the_create_idiom(self, text: str) -> None:
        names = table_terms_in(text)
        assert CREATE_BRANCH not in names
        assert "ブランチ" in names

    def test_the_prompt_for_a_switch_never_says_create(self) -> None:
        assert not any("建立分支" in line for line in named_lines("ブランチを切り替えます"))


class TestWordsInsideLongerWords:
    @pytest.mark.parametrize(
        ("text", "name"),
        [
            ("マージンを取る", "マージ"),
            ("マージャンをする", "マージ"),
            ("プロファイルを開く", "ファイル"),
            ("メタデータを読む", "データ"),
            ("ビッグデータの話", "データ"),
            ("デッドロックが起きる", "ロック"),
            ("ロックダウンの話", "ロック"),
            ("ブロックを置く", "ロック"),
            ("交通アクセスの案内", "アクセス"),
        ],
    )
    def test_a_longer_word_does_not_name_the_term(self, text: str, name: str) -> None:
        assert name not in table_terms_in(text)

    @pytest.mark.parametrize(
        ("text", "name"),
        [
            ("ブランチをマージします", "マージ"),
            ("ファイルを開く", "ファイル"),
            ("データを読む", "データ"),
            ("メタデータを読む", "メタデータ"),
            ("ロックします", "ロック"),
            ("APIにアクセスします", "アクセス"),
        ],
    )
    def test_the_word_itself_names_the_term(self, text: str, name: str) -> None:
        assert name in table_terms_in(text)


def homing() -> JaTerm:
    return next(t for t in JAPANESE_SOURCE.terms if t.zh == "自動鎖定")


class TestHomingTerm:
    """P35: speech recognition hears ホーミング as フォーミング. The sentences are invented."""

    @pytest.mark.parametrize(
        "text",
        [
            "近い敵をフォーミングで狙います",
            "強いホーミングで補います",
            "フォーミング性能を上げる",
            "二段階フォーミングにする",
            "ホーミングミサイルを撃つ",
            "ちゃんと外れるフォーミングにします",
        ],
    )
    def test_homing_and_its_garble_name_the_term(self, text: str) -> None:
        assert homing().said in table_terms_in(text)

    @pytest.mark.parametrize(
        "text",
        [
            "トランスフォーミングします",
            "パフォーミングアートの話",
            "リフォーミングの相談",
            "ウォーミングアップをする",
            "ホミングする",
            "ホームページを見る",
            "フォームに入力する",
        ],
    )
    def test_a_longer_word_or_another_word_does_not_name_the_term(self, text: str) -> None:
        assert homing().said not in table_terms_in(text)

    def test_the_prompt_for_a_garbled_unit_says_what_to_write(self) -> None:
        lines = named_lines("敵が空中にいても、フォーミングして当たります")
        assert [line for line in lines if '"自動鎖定"' in line and "ホーミング" in line]

    def test_the_prompt_for_an_unrelated_unit_does_not_say_it(self) -> None:
        assert not any("自動鎖定" in line for line in named_lines("フォームに入力して送信します"))

    def test_a_user_term_for_the_word_replaces_the_line(self) -> None:
        user = (translate.GlossaryEntry("フォーミング", "追尾"),)
        lines = named_lines("フォーミングを使います", user)
        assert not any("自動鎖定" in line for line in lines)

    @pytest.mark.parametrize("zh", ["自動鎖定", "強力的自動鎖定", "追蹤", "自動追蹤", "自動瞄準"])
    def test_a_taiwan_form_is_right(self, zh: str) -> None:
        assert homing().kept_in(zh)

    @pytest.mark.parametrize("wrong", ["組裝", "成型", "形成", "形狀"])
    def test_a_garbled_rendering_is_wrong_even_beside_the_right_form(self, wrong: str) -> None:
        assert not homing().kept_in(wrong)
        assert not homing().kept_in(f"自動鎖定與{wrong}")

    def test_the_prompt_line_names_both_spellings_and_the_garble(self) -> None:
        (line,) = named_lines("フォーミングを二段階にします")
        assert line.startswith('- "フォーミング / ホーミング')
        assert "speech recognition" in line

    def test_the_check_counts_a_right_and_a_wrong_cue(self) -> None:
        cues = [
            Cue(1, 0, 1000, "強いフォーミングで補います", "以強力的自動鎖定補足", lang="ja"),
            Cue(2, 0, 1000, "フォーミング性能を高くします", "將成型效能提高", lang="ja"),
        ]
        assert table_score(cues)[homing().said] == (1, 2)


class TestWrongFormLists:
    @pytest.mark.parametrize("zh", ["新的串流功能", "串流類型", "串流機制", "稀疏串流"])
    def test_a_stream_word_with_the_right_form_in_it_is_right(self, zh: str) -> None:
        assert term("ストリーム").kept_in(zh)

    @pytest.mark.parametrize("zh", ["串流和流功能", "分支流與串流", "串流和流類型"])
    def test_a_bare_wrong_form_still_fails(self, zh: str) -> None:
        assert not term("ストリーム").kept_in(zh)

    def test_an_administrator_is_not_a_table_term(self) -> None:
        assert table_terms_in("管理者向けのツール") == ["ツール"]

    @pytest.mark.parametrize("zh", ["程式碼審查", "程式碼審閱", "程式碼檢閱"])
    def test_a_review_in_any_taiwan_form_is_right(self, zh: str) -> None:
        assert term("コードレビュー").kept_in(zh)
        assert term("レビュー").kept_in(zh.replace("程式碼", ""))

    def test_a_checklist_is_right_as_a_verification_list_too(self) -> None:
        assert term("チェックリスト").kept_in("核對清單")

    def test_source_code_as_the_long_taiwan_form_is_right(self) -> None:
        assert term("ソースコード").kept_in("原始程式碼")
        assert not term("ソースコード").kept_in("源碼")

    @pytest.mark.parametrize("zh", ["預設關閉", "預設是關閉的", "預設停用"])
    def test_disabled_by_default_in_taiwan_forms_is_right(self, zh: str) -> None:
        assert term("デフォルトで無効 (disabled by default)").kept_in(zh)

    @pytest.mark.parametrize("zh", ["預設開啟", "預設是開啟的", "預設啟用"])
    def test_enabled_by_default_in_taiwan_forms_is_right(self, zh: str) -> None:
        assert term("デフォルトで有効 (enabled by default)").kept_in(zh)

    def test_a_plugin_is_one_word_and_the_long_form_is_wrong(self) -> None:
        plugin = term("プラグイン")
        assert plugin.zh == "外掛"
        assert plugin.kept_in("外掛")
        assert not plugin.kept_in("外掛程式")
        assert not plugin.kept_in("插件")

    def test_the_word_file_next_to_documentation_is_not_a_wrong_form(self) -> None:
        assert term("ファイル").kept_in("開啟檔案並閱讀說明文件")
        assert not term("ファイル").kept_in("開啟檔案和文件")

    def test_a_file_written_with_the_short_form_is_right(self) -> None:
        assert term("ファイル").kept_in("腳本檔和設定檔")

    def test_no_wrong_form_matches_the_taiwan_form_of_any_term(self) -> None:
        for one in JAPANESE_SOURCE.terms:
            for bad in one.avoid:
                for other in JAPANESE_SOURCE.terms:
                    for good in (other.zh, *other.also):
                        assert not re.search(bad, good), (one.said, bad, good)

    def test_access_prefers_the_taiwan_word_over_visit(self) -> None:
        access = term("アクセス")
        assert access.zh == "存取"
        assert access.kept_in("存取資料庫")
        assert not access.kept_in("存取和訪問")


class TestUserGlossaryOverridesTheTable:
    def test_a_user_term_replaces_the_table_line_for_the_same_word(self) -> None:
        lines = named_lines("ファイルを保存します", (translate.GlossaryEntry("ファイル", "文件"),))
        assert not any('"檔案"' in line for line in lines)

    def test_a_user_term_that_contains_a_table_word_replaces_its_line(self) -> None:
        user = (translate.GlossaryEntry("ファイルサーバー", "檔案伺服器"),)
        lines = named_lines("ファイルサーバーを使う", user)
        assert not any('"ファイル" must' in line for line in lines)

    def test_a_user_term_inside_an_idiom_replaces_the_idiom_line(self) -> None:
        lines = named_lines("ブランチを切ります", (translate.GlossaryEntry("ブランチ", "分枝"),))
        assert not any("建立分支" in line or '"分支"' in line for line in lines)

    def test_the_table_line_stays_for_a_word_the_user_term_does_not_touch(self) -> None:
        lines = named_lines("ファイルとブランチ", (translate.GlossaryEntry("ファイル", "文件"),))
        assert '- "ブランチ" must be translated as "分支"' in lines

    def test_the_table_line_stays_for_another_occurrence_of_the_word(self) -> None:
        user = (translate.GlossaryEntry("ファイルサーバー", "檔案伺服器"),)
        lines = named_lines("ファイルサーバーのファイルを開く", user)
        assert '- "ファイル" must be translated as "檔案"' in lines

    def test_a_user_term_in_another_case_still_overrides(self) -> None:
        user = (translate.GlossaryEntry("チャットgpt", "ChatGPT"),)
        lines = named_lines("チャットGPTを使う", user)
        assert sum('"ChatGPT"' in line for line in lines) == 1

    def test_a_term_with_no_user_entry_keeps_its_line(self) -> None:
        assert '- "ファイル" must be translated as "檔案"' in named_lines("ファイルを開く")


class TestPerforceAliases:
    @pytest.mark.parametrize(
        "alias",
        [
            "パフォース",
            "パワーフォース",
            "パワフォース",
            "パワーホース",
            "PowerForce",
            "Powerforce",
            "PowerHorse",
        ],
    )
    def test_each_garbled_product_name_is_a_glossary_entry(self, alias: str) -> None:
        for source in ("ja", "ja+en"):
            entries = {e.term: e.zh for e in translate.default_glossary(source)}
            assert entries[alias] == "Perforce"
        assert alias not in {e.term for e in translate.default_glossary("en")}

    def test_the_prompt_names_the_new_spellings(self) -> None:
        text = translate.system_prompt_template(get_language("zh-TW"), JAPANESE_SOURCE)
        for alias in ("パワーフォース", "パワフォース", "パワーホース"):
            assert alias in text

    @pytest.mark.parametrize("copied", ["パワフォース", "PowerForce", "Powerforce", "PowerHorse"])
    def test_a_copied_alias_is_mended_to_the_product_name(self, copied: str) -> None:
        cues = [Cue(1, 0, 1000, "パワフォースのサーバーです", lang="ja")]
        reply = json.dumps({"translations": [{"id": 1, "zh": f"這是{copied}的伺服器。"}]})
        done = translate.run(
            cues,
            lambda messages, temperature: reply,
            batch_size=1,
            max_retries=0,
            sleep=lambda _: None,
            glossary=translate.default_glossary("ja"),
            keep_english=True,
            source=JAPANESE_SOURCE,
        )
        assert "Perforce" in done[0].zh and copied not in done[0].zh


class TestTermTableIsInTheCacheKey:
    @staticmethod
    def digest(terms: tuple[JaTerm, ...], monkeypatch: pytest.MonkeyPatch) -> str:
        digest_of = pipeline._translate_prompt_digest  # pyright: ignore[reportPrivateUsage]
        changed = replace(JAPANESE_SOURCE, terms=terms)
        monkeypatch.setattr(pipeline, "get_source", lambda code: changed)  # pyright: ignore[reportUnknownLambdaType, reportUnknownArgumentType]
        digest_of.cache_clear()
        try:
            return digest_of("zh-TW", "ja")
        finally:
            digest_of.cache_clear()

    def test_changing_a_taiwan_form_changes_the_translate_digest(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        table = JAPANESE_SOURCE.terms
        edited = (replace(table[0], zh="文件"), *table[1:])
        assert self.digest(table, monkeypatch) != self.digest(edited, monkeypatch)

    def test_removing_a_term_changes_the_translate_digest(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        table = JAPANESE_SOURCE.terms
        assert self.digest(table, monkeypatch) != self.digest(table[1:], monkeypatch)

    def test_the_homing_line_is_in_the_translate_digest(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        table = JAPANESE_SOURCE.terms
        without = tuple(t for t in table if t.zh != "自動鎖定")
        assert len(without) == len(table) - 1
        assert self.digest(table, monkeypatch) != self.digest(without, monkeypatch)

    def test_the_same_table_gives_the_same_digest(self, monkeypatch: pytest.MonkeyPatch) -> None:
        table = JAPANESE_SOURCE.terms
        assert self.digest(table, monkeypatch) == self.digest(table, monkeypatch)
