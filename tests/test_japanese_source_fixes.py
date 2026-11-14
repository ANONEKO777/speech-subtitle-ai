"""P33: the stream and branch words the model gets wrong, mended from the Japanese, and the cache
key that reads them. The sentences are invented."""

from __future__ import annotations

import pytest
from test_japanese_followups import cues_of, translated

from backend.core import pipeline
from backend.core.ja_terms import SOURCE_FIXES, fix_from_source
from backend.core.source_langs import MIXED_SOURCE


class TestStreamIsNotSmooth:
    STREAM = "配信の話です。新しい配信ストリームの設定"

    @pytest.mark.parametrize(
        ("zh", "want"),
        [
            ("上面說的流暢或是別的選項", "上面說的串流或是別的選項"),
            ("與公告的流暢度不同", "與公告的串流不同"),
            ("上面說的流動或別的選項", "上面說的串流或別的選項"),
            ("流暢、流動和流暢度", "串流、串流和串流"),
            ("與公告的流串或別的選項", "與公告的串流或別的選項"),
            ("藉由流功能", "藉由串流功能"),
            ("這種流類型與流機制", "這種串流類型與串流機制"),
        ],
    )
    def test_a_stream_written_as_smooth_or_flowing_is_a_stream(self, zh: str, want: str) -> None:
        assert fix_from_source(zh, self.STREAM) == want

    @pytest.mark.parametrize(
        "src",
        [
            "ストリームの動きがスムーズです",
            "ストリームはスムースに切れます",
            "ストリームが流暢に動きます",
            "ストリームは滑らかです",
            "ストリームがなめらかです",
            "ストリームの流れを見ます",
            "ストリームのフローです",
        ],
    )
    def test_a_unit_that_says_smooth_or_flow_keeps_its_word(self, src: str) -> None:
        zh = "流暢地運作，流動情況，流暢度"
        assert fix_from_source(zh, src) == zh

    def test_a_unit_without_the_stream_word_is_never_touched(self) -> None:
        zh = "流暢的操作，流動情況"
        assert fix_from_source(zh, "操作がスムーズです") == zh
        assert fix_from_source(zh, "お願いします") == zh

    def test_the_stream_word_of_a_line_break_still_counts(self) -> None:
        assert fix_from_source("流暢的分支", "分岐のスト\nリームです") == "串流的分支"

    def test_the_rewrite_is_idempotent(self) -> None:
        once = fix_from_source("與公告的流暢度不同", self.STREAM)
        assert fix_from_source(once, self.STREAM) == once

    @pytest.mark.parametrize("zh", ["藉由串流功能", "串流類型與串流機制", "分支串流"])
    def test_a_stream_already_written_with_the_right_word_is_unchanged(self, zh: str) -> None:
        assert fix_from_source(zh, self.STREAM) == zh

    def test_a_workflow_in_the_unit_does_not_hide_the_stream(self) -> None:
        src = "ワークフローのストリームです"
        assert fix_from_source("流暢", src) == "串流"

    def test_a_translation_that_is_right_is_unchanged(self) -> None:
        assert fix_from_source("與公告的串流不同", self.STREAM) == "與公告的串流不同"

    def test_a_cue_the_model_put_the_word_in_is_mended_by_its_unit(self) -> None:
        cues = cues_of("新しい", "配信ストリームの", "設定を見ます")
        zh = "[[1]]上面說的[[2]]流暢[[3]]或是別的選項。"
        assert translated(cues, [zh]) == ["上面說的", "串流", "或是別的選項。"]

    def test_a_unit_that_says_smooth_in_another_cue_keeps_the_word(self) -> None:
        cues = cues_of("ストリームが", "スムーズに", "動きます")
        zh = "[[1]]串流[[2]]很流暢[[3]]地運作。"
        assert translated(cues, [zh])[1] == "很流暢"

    def test_the_english_cues_of_a_mixed_talk_are_not_rewritten(self) -> None:
        cues = cues_of("The stream is smooth.", lang="en")
        assert translated(cues, ["串流很流暢。"], source=MIXED_SOURCE) == ["串流很流暢。"]


class TestSparseStream:
    SPARSE = "スパースストリームの話です"

    @pytest.mark.parametrize(
        ("zh", "want"),
        [
            ("這就是稀疏流", "這就是稀疏串流"),
            ("稀疏流和稀疏流", "稀疏串流和稀疏串流"),
            ("稀疏流功能", "稀疏串流功能"),
        ],
    )
    def test_a_sparse_stream_is_a_sparse_stream(self, zh: str, want: str) -> None:
        assert fix_from_source(zh, self.SPARSE) == want

    @pytest.mark.parametrize("zh", ["稀疏流程很快", "稀疏串流很快"])
    def test_a_longer_word_or_the_right_word_is_unchanged(self, zh: str) -> None:
        assert fix_from_source(zh, self.SPARSE) == zh

    def test_the_plain_stream_word_does_not_name_the_rule(self) -> None:
        assert fix_from_source("稀疏流", "ストリームの話です") == "稀疏流"

    def test_a_unit_that_says_smooth_still_mends_it(self) -> None:
        assert fix_from_source("稀疏流很順", "スパースストリームがスムーズです") == "稀疏串流很順"


class TestWorkflowStaysChinese:
    WORKFLOW = "ワークフローの話です"

    @pytest.mark.parametrize(
        ("zh", "want"),
        [
            ("不同店家的 workflows。", "不同店家的工作流程。"),
            ("最佳化出貨的 workflow。", "最佳化出貨的工作流程。"),
            ("Workflow 很重要", "工作流程很重要"),
            ("WORKFLOWS", "工作流程"),
            ("每個workflow", "每個工作流程"),
        ],
    )
    def test_a_workflow_written_in_latin_is_written_in_chinese(self, zh: str, want: str) -> None:
        assert fix_from_source(zh, self.WORKFLOW) == want

    @pytest.mark.parametrize("zh", ["GitHubWorkflows", "workflowy", "myworkflow"])
    def test_a_longer_latin_word_is_unchanged(self, zh: str) -> None:
        assert fix_from_source(zh, self.WORKFLOW) == zh

    def test_without_the_japanese_word_a_latin_workflow_stays(self) -> None:
        assert fix_from_source("GitHub workflow", "GitHubのworkflowです") == "GitHub workflow"


class TestBranchIsCreatedNotSwitched:
    CREATE = "新しいブランチを3本切ります"

    @pytest.mark.parametrize(
        ("zh", "want"),
        [
            ("只要切換一個分支", "只要建立一個分支"),
            ("只要切換1個分支就好", "只要建立1個分支就好"),
            ("只要切換兩個分支", "只要建立兩個分支"),
            ("切換分支時", "建立分支時"),
            ("切換新的分支", "建立新的分支"),
            ("輕鬆地切換分支，各自切換分支", "輕鬆地建立分支，各自建立分支"),
        ],
    )
    def test_a_branch_made_is_not_a_branch_switched(self, zh: str, want: str) -> None:
        assert fix_from_source(zh, self.CREATE) == want

    @pytest.mark.parametrize(
        "src",
        [
            "ブランチを切って、ブランチを切り替えます",
            "ブランチを切ったあと切替えます",
            "ブランチを切ってスイッチします",
        ],
    )
    def test_a_unit_that_also_switches_keeps_its_word(self, src: str) -> None:
        assert fix_from_source("切換分支", src) == "切換分支"

    @pytest.mark.parametrize("src", ["ブランチを切り替えます", "ブランチを見ます", "お願いします"])
    def test_a_unit_without_a_branch_made_is_never_touched(self, src: str) -> None:
        assert fix_from_source("切換分支", src) == "切換分支"

    @pytest.mark.parametrize("zh", ["切換到舊的串流", "切換環境", "切換模式與分支名稱"])
    def test_a_switch_of_something_else_stays(self, zh: str) -> None:
        assert fix_from_source(zh, self.CREATE) == zh

    def test_a_cue_the_model_put_the_word_in_is_mended_by_its_unit(self) -> None:
        cues = cues_of("ブランチを", "1本", "切るだけです")
        zh = "[[1]]只要[[2]]切換一個分支[[3]]就好。"
        assert translated(cues, [zh]) == ["只要", "建立一個分支", "就好。"]


class TestTheFixesAreInTheCacheKey:
    def test_the_digest_reads_the_source_fixes(self, monkeypatch: pytest.MonkeyPatch) -> None:
        digest_of = pipeline._translate_prompt_digest  # pyright: ignore[reportPrivateUsage]
        digest_of.cache_clear()
        before = digest_of("zh-TW", "ja")
        monkeypatch.setattr(pipeline, "SOURCE_FIXES", SOURCE_FIXES[:-1])
        digest_of.cache_clear()
        try:
            assert digest_of("zh-TW", "ja") != before
        finally:
            digest_of.cache_clear()

    def test_the_english_digest_does_not_read_them(self, monkeypatch: pytest.MonkeyPatch) -> None:
        digest_of = pipeline._translate_prompt_digest  # pyright: ignore[reportPrivateUsage]
        digest_of.cache_clear()
        before = digest_of("zh-TW", "en")
        monkeypatch.setattr(pipeline, "SOURCE_FIXES", SOURCE_FIXES[:-1])
        digest_of.cache_clear()
        try:
            assert digest_of("zh-TW", "en") == before
        finally:
            digest_of.cache_clear()
