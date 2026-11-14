"""P33: the stream and branch words the model gets wrong, mended from the Japanese, and the cache
key that reads them. The sentences are invented."""

from __future__ import annotations

import pytest
from test_japanese_followups import cues_of, translated

from backend.core import pipeline
from backend.core.ja_terms import SOURCE_FIXES, SourceFix, fix_from_source
from backend.core.source_langs import MIXED_SOURCE
from backend.core.translate import GlossaryEntry


class TestStreamIsNotSmooth:
    STREAM = "配信の話です。新しい配信ストリームの設定"

    @pytest.mark.parametrize(
        ("zh", "want"),
        [
            ("上面說的流暢或是別的選項", "上面說的串流或是別的選項"),
            ("與公告的流暢度不同", "與公告的串流不同"),
            ("上面說的流動或別的選項", "上面說的串流或別的選項"),
            ("流暢、流動和流暢度", "串流、流動和串流"),
            ("流動或別的選項", "串流或別的選項"),
            ("流暢", "串流"),
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
        zh = "與公告的流暢度不同，與流動不同"
        assert fix_from_source(zh, "ストリームです") != zh
        assert fix_from_source(zh, src) == zh

    def test_a_unit_without_the_stream_word_is_never_touched(self) -> None:
        zh = "與公告的流暢度不同，與流動不同"
        assert fix_from_source(zh, "操作がスムーズです") == zh
        assert fix_from_source(zh, "お願いします") == zh

    def test_the_stream_word_of_a_line_break_still_counts(self) -> None:
        assert fix_from_source("與流暢度不同", "分岐のスト\nリームです") == "與串流不同"

    def test_the_rewrite_is_idempotent(self) -> None:
        once = fix_from_source("與公告的流暢度不同", self.STREAM)
        assert fix_from_source(once, self.STREAM) == once

    @pytest.mark.parametrize("zh", ["藉由串流功能", "串流類型與串流機制", "分支串流"])
    def test_a_stream_already_written_with_the_right_word_is_unchanged(self, zh: str) -> None:
        assert fix_from_source(zh, self.STREAM) == zh

    def test_a_workflow_in_the_unit_does_not_hide_the_stream(self) -> None:
        src = "ワークフローのストリームです"
        assert fix_from_source("與流暢不同", src) == "與串流不同"

    def test_a_translation_that_is_right_is_unchanged(self) -> None:
        assert fix_from_source("與公告的串流不同", self.STREAM) == "與公告的串流不同"

    def test_a_cue_the_model_put_the_word_in_is_mended_by_its_unit(self) -> None:
        cues = cues_of("新しい", "配信ストリームの", "設定を見ます")
        zh = "[[1]]上面說的[[2]]流暢[[3]]或是別的選項。"
        assert translated(cues, [zh]) == ["上面說的", "串流", "或是別的選項。"]

    def test_a_smooth_adverb_that_starts_a_cue_stays(self) -> None:
        cues = cues_of("新しい", "配信ストリームの", "設定を見ます")
        zh = "[[1]]上面說的[[2]]流暢地[[3]]或是別的選項。"
        assert translated(cues, [zh]) == ["上面說的", "流暢地", "或是別的選項。"]

    def test_a_unit_that_says_smooth_in_another_cue_keeps_the_word(self) -> None:
        cues = cues_of("ストリームが", "スムーズに", "動きます")
        zh = "[[1]]串流[[2]]很流暢[[3]]地運作。"
        assert translated(cues, [zh])[1] == "很流暢"

    def test_the_english_cues_of_a_mixed_talk_are_not_rewritten(self) -> None:
        cues = cues_of("The stream is smooth.", lang="en")
        assert translated(cues, ["串流很流暢。"], source=MIXED_SOURCE) == ["串流很流暢。"]


class TestAStreamNounStandsAfterAParticleOrAlone:
    SRC = "ストリームの話です"

    @pytest.mark.parametrize("particle", list("的與和及跟或之"))
    def test_a_smooth_noun_after_a_particle_is_mended(self, particle: str) -> None:
        assert fix_from_source(f"{particle}流暢度", self.SRC) == f"{particle}串流"
        assert fix_from_source(f"{particle}流動", self.SRC) == f"{particle}串流"

    @pytest.mark.parametrize(
        "after", ["", "，", "。", "、", ",", "；", "！", "？", " 和", "或", "與", "和", "及", "跟"]
    )
    def test_a_smooth_noun_that_is_a_whole_cue_or_ends_one_is_mended(self, after: str) -> None:
        assert fix_from_source(f"流暢{after}", self.SRC) == f"串流{after}"
        assert fix_from_source(f"流動{after}", self.SRC) == f"串流{after}"

    @pytest.mark.parametrize("after", ["的", "地", "得", "很", "情況", "性"])
    def test_a_smooth_word_that_goes_on_in_a_cue_start_stays(self, after: str) -> None:
        assert fix_from_source(f"流暢{after}運作", self.SRC) == f"流暢{after}運作"
        assert fix_from_source(f"流動{after}運作", self.SRC) == f"流動{after}運作"

    @pytest.mark.parametrize("word", list("主上下分合對逆水氣電暖寒潮洪河溪回交熱激金物人"))
    def test_each_word_that_ends_in_flow_is_not_a_stream(self, word: str) -> None:
        assert fix_from_source(f"{word}流功能", self.SRC) == f"{word}流功能"
        assert fix_from_source(f"{word}流串起來", self.SRC) == f"{word}流串起來"

    @pytest.mark.parametrize(
        "word",
        [
            "現金流",
            "資金流",
            "物流",
            "人流",
            "氣流",
            "電流",
            "水流",
            "暖流",
            "逆流",
            "分流",
            "主流",
            "合流",
        ],
    )
    @pytest.mark.parametrize("after", ["功能", "類型", "機制"])
    def test_a_common_word_that_ends_in_flow_stays_before_a_noun(
        self, word: str, after: str
    ) -> None:
        for before in ("", "的", "與", "新"):
            assert fix_from_source(f"{before}{word}{after}", self.SRC) == f"{before}{word}{after}"

    def test_a_cash_flow_feature_is_not_a_stream_feature(self) -> None:
        assert fix_from_source("現金流功能", "配信ストリームの機能です") == "現金流功能"
        assert (
            fix_from_source("資金流類型與物流機制", "配信ストリームの機能です")
            == "資金流類型與物流機制"
        )

    @pytest.mark.parametrize("after", list("接聯連"))
    def test_a_flow_word_with_a_chain_after_it_is_not_a_misspelt_stream(self, after: str) -> None:
        assert fix_from_source(f"與公告的流串{after}起來", self.SRC) == f"與公告的流串{after}起來"
        assert fix_from_source("與公告的流串或別的選項", self.SRC) == "與公告的串流或別的選項"

    @pytest.mark.parametrize("after", list("性作態畫向量速"))
    def test_a_flowing_word_that_goes_on_is_another_word(self, after: str) -> None:
        zh = f"與公告的流動{after}不同"
        assert fix_from_source(zh, self.SRC) == zh
        assert fix_from_source(f"流動{after}", self.SRC) == f"流動{after}"

    @pytest.mark.parametrize("after", list("地性"))
    def test_a_smooth_word_that_goes_on_is_another_word(self, after: str) -> None:
        zh = f"與公告的流暢{after}不同"
        assert fix_from_source(zh, self.SRC) == zh
        assert fix_from_source(f"流暢度{after}", self.SRC) == f"流暢度{after}"

    @pytest.mark.parametrize("word", ["音楽", "娯楽", "快楽"])
    def test_a_word_with_music_or_pleasure_in_it_is_not_easy(self, word: str) -> None:
        assert (
            fix_from_source("與公告的流暢度不同", f"{word}のストリームです") == "與公告的串流不同"
        )

    @pytest.mark.parametrize("after", list("しむ器曲譜団園天"))
    def test_a_word_that_starts_with_the_easy_character_is_not_easy(self, after: str) -> None:
        src = f"ストリームの楽{after}です"
        assert fix_from_source("與公告的流暢度不同", src) == "與公告的串流不同"

    @pytest.mark.parametrize(
        "src", ["ストリームは楽です", "ストリームが楽に動きます", "楽なストリーム"]
    )
    def test_the_easy_word_keeps_the_smooth_word(self, src: str) -> None:
        assert fix_from_source("與公告的流暢度不同", src) == "與公告的流暢度不同"

    @pytest.mark.parametrize(
        "src", ["ストリームが流します", "ストリームを流す", "ストリームへ流さない"]
    )
    def test_sending_changes_down_a_stream_keeps_the_flow_word(self, src: str) -> None:
        assert fix_from_source("與公告的流動不同", src) == "與公告的流動不同"


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

    @pytest.mark.parametrize("zh", ["稀疏流程很快", "稀疏串流很快", "稀疏流動作", "稀疏流動態"])
    def test_a_longer_word_or_the_right_word_is_unchanged(self, zh: str) -> None:
        assert fix_from_source(zh, self.SPARSE) == zh

    @pytest.mark.parametrize("after", list("程動暢量向性速派行通水氓"))
    def test_a_sparse_flow_word_that_goes_on_is_another_word(self, after: str) -> None:
        for zh in (f"稀疏流{after}", f"這是稀疏流{after}很好", f"與稀疏流{after}"):
            assert fix_from_source(zh, self.SPARSE) == zh

    @pytest.mark.parametrize(
        ("zh", "want"),
        [
            ("稀疏流暢", "稀疏流暢"),
            ("稀疏流量", "稀疏流量"),
            ("稀疏流向", "稀疏流向"),
            ("稀疏流與稀疏流", "稀疏串流與稀疏串流"),
            ("稀疏流，稀疏流。", "稀疏串流，稀疏串流。"),
        ],
    )
    def test_the_flow_words_of_a_sparse_unit_are_not_split_by_the_rewrite(
        self, zh: str, want: str
    ) -> None:
        assert fix_from_source(zh, self.SPARSE) == want

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
            ("每個workflow", "每個工作流程"),
            ("建立 workflow 並執行 workflows。", "建立工作流程並執行工作流程。"),
            ("`workflow` 和 workflow", "`workflow` 和工作流程"),
        ],
    )
    def test_a_workflow_written_in_latin_is_written_in_chinese(self, zh: str, want: str) -> None:
        assert fix_from_source(zh, self.WORKFLOW) == want

    @pytest.mark.parametrize(
        "zh",
        [
            "寫在 workflow.yml，放在 .github/workflows 裡。",
            "設定 GITHUB_WORKFLOW 和 my_workflow",
            "執行 `workflow` 指令",
            "執行 `gh run workflow now` 指令，再看 workflow",
            "Windows Workflow Foundation",
            "GitHub Workflows 的頁面",
            "Workflow Studio",
            "workflow-based 的做法",
            "workflow2 和 workflow/steps 與 a/workflow",
            "WORKFLOWS",
            "the workflow engine",
        ],
    )
    def test_a_file_a_path_a_variable_code_or_a_title_is_not_a_word(self, zh: str) -> None:
        src = "ワークフローは workflow.yml に書いて、.github/workflows に置きます"
        want = zh.replace("再看 workflow", "再看工作流程")
        assert fix_from_source(zh, src) == want

    @pytest.mark.parametrize(
        "zh",
        [
            "a.workflow",
            "my-workflow",
            "2workflow",
            "C:\\workflow\\x",
            "workflow\\run",
            "workflows/a",
        ],
    )
    def test_a_word_next_to_a_path_or_a_dot_is_not_a_word(self, zh: str) -> None:
        assert fix_from_source(zh, self.WORKFLOW) == zh

    @pytest.mark.parametrize("zh", ["GitHubWorkflows", "workflowy", "myworkflow"])
    def test_a_longer_latin_word_is_unchanged(self, zh: str) -> None:
        assert fix_from_source(zh, self.WORKFLOW) == zh

    def test_without_the_japanese_word_a_latin_workflow_stays(self) -> None:
        assert fix_from_source("GitHub workflow", "GitHubのworkflowです") == "GitHub workflow"


SWITCH_SENTENCES = {
    "切り替え": "ブランチを切ってから切り替えます",
    "切替": "ブランチを切って切替えます",
    "切り換え": "ブランチを切ってから切り換えます",
    "切換え": "ブランチを切って切換えます",
    "切りかえ": "ブランチを切って切りかえます",
    "乗り換え": "ブランチを切って乗り換えます",
    "乗換": "ブランチを切って乗換えます",
    "乗りかえ": "ブランチを切って乗りかえます",
    "スイッチ": "ブランチを切ってスイッチします",
    "チェックアウト": "ブランチを切ってチェックアウトします",
    "移動": "ブランチを切って、そこに移動します",
    "移る": "ブランチを切って別の枝に移る",
    "移り": "ブランチを切って別の枝に移ります",
    "移っ": "ブランチを切って別の枝に移ったあと",
    "移す": "ブランチを切って作業を移す",
    "移し": "ブランチを切って作業を移します",
    "移行": "ブランチを切って移行を始めます",
    "遷移": "ブランチを切って遷移を確かめます",
    "変更": "ブランチを切ってから設定を変更します",
    "変え": "ブランチを切って作業を変えます",
    "戻る": "ブランチを切ったあと元に戻る",
    "戻り": "ブランチを切ったあと元に戻ります",
    "戻っ": "ブランチを切ったあと元に戻ったら",
    "戻す": "ブランチを切って設定を戻す",
    "戻し": "ブランチを切って設定を戻します",
    "行く": "ブランチを切ってそっちへ行く",
    "行き": "ブランチを切ってそっちへ行きます",
    "行っ": "ブランチを切ってそっちへ行ったら",
    "入る": "ブランチを切って作業に入る",
    "入り": "ブランチを切って作業に入ります",
    "入っ": "ブランチを切って作業に入ったら",
    "使い分け": "ブランチを切って使い分けます",
    "入れ替え": "ブランチを切って入れ替えます",
    "そのブランチ": "ブランチを切って、そのブランチで作業します",
    "別のブランチ": "ブランチを切って、別のブランチで試します",
    "他のブランチ": "ブランチを切って、他のブランチを見ます",
    "元のブランチ": "ブランチを切って、元のブランチと比べます",
    "ブランチ間": "ブランチを切って、ブランチ間の差を見ます",
}


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
            ("大家各自切換分支，隨時切換分支", "大家各自建立分支，隨時建立分支"),
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

    @pytest.mark.parametrize("src", list(SWITCH_SENTENCES.values()), ids=list(SWITCH_SENTENCES))
    def test_a_unit_with_a_switching_word_keeps_the_switch(self, src: str) -> None:
        assert fix_from_source("建立分支並切換分支", src) == "建立分支並切換分支"

    @pytest.mark.parametrize(
        "src",
        [
            "ブランチを切ります",
            "新しいブランチを切って作業します",
            "ブランチを2本切ります",
            "ブランチを切って機能を入れます",
            "ブランチを切って入力します",
            "ブランチを切ってからテストを書きます",
            "ブランチを切って作業に取りかかります",
        ],
    )
    def test_a_unit_that_only_creates_still_mends_a_switch(self, src: str) -> None:
        assert fix_from_source("建立分支並切換分支", src) == "建立分支並建立分支"

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


class TestStreamGuard:
    """What the model writes for a smooth or easy stream, and the loanwords with ストリーム."""

    @pytest.mark.parametrize(
        "src",
        [
            "ストリームを使うと作業が楽になります",
            "ストリームの運用が円滑です",
            "ストリームは快適です",
            "ストリームが軽快に動きます",
            "ストリームでサクサク進みます",
            "ストリームは使いやすいです",
            "ストリームが安定しています",
            "ストリームに変更を流します",
            "親ストリームへ流す",
            "メインストリームの機能とストリーム",
            "ダウンストリームのストリーム",
            "アップストリームとストリーム",
            "ストリームラインです",
        ],
    )
    def test_a_unit_about_smoothness_or_a_loanword_keeps_its_words(self, src: str) -> None:
        zh = "與公告的流暢度不同，與流動，主流功能，下流機制，上流功能"
        assert fix_from_source(zh, src) == zh

    @pytest.mark.parametrize(
        "src",
        [
            "快適な環境をつくるために、これからいろいろな機能を紹介します。ストリームの話です",
            "ストリームの話です。これからいろいろな機能を紹介します。サクサク動きます",
            "安定性を高める機能が、さらに便利になる形で提供されていて、ストリーム機能と呼びます",
            "ストリームの安定性を見ます",
        ],
    )
    def test_an_easy_word_far_from_the_stream_word_does_not_block(self, src: str) -> None:
        assert fix_from_source("與公告的流暢度不同", src) == "與公告的串流不同"

    @pytest.mark.parametrize("src", ["このストリームは安定度で決めます", "音楽のストリームです"])
    def test_a_word_that_only_looks_like_a_guard_does_not_block(self, src: str) -> None:
        assert fix_from_source("與公告的流暢度不同", src) == "與公告的串流不同"

    @pytest.mark.parametrize(
        "zh", ["主流功能", "下流機制", "上流功能", "分流功能", "合流類型", "對流機制"]
    )
    def test_a_word_that_ends_in_flow_is_not_a_stream(self, zh: str) -> None:
        assert fix_from_source(zh, "ストリームの話です") == zh

    @pytest.mark.parametrize(
        ("zh", "want"),
        [
            ("分支流功能", "分支串流功能"),
            ("父流類型", "父串流類型"),
            ("藉由流機制", "藉由串流機制"),
            ("另外流功能中", "另外串流功能中"),
            ("除此之外流類型", "除此之外串流類型"),
        ],
    )
    def test_a_bare_stream_noun_is_mended(self, zh: str, want: str) -> None:
        assert fix_from_source(zh, "ストリームの話です") == want

    @pytest.mark.parametrize(
        "zh",
        ["作業更流暢", "運作很流暢", "流暢地運作", "不流暢", "整體變得流暢", "更新的流暢地執行"],
    )
    def test_a_smooth_adjective_is_not_a_stream(self, zh: str) -> None:
        assert fix_from_source(zh, "ストリームを使います") == zh

    @pytest.mark.parametrize(
        "zh",
        ["串流動作", "串流動態", "串流動畫", "串流動向", "串流暢通", "串流串接", "稀疏串流動作"],
    )
    def test_a_right_stream_with_more_after_it_is_unchanged(self, zh: str) -> None:
        assert fix_from_source(zh, "スパースストリームとストリームです") == zh

    @pytest.mark.parametrize("zh", ["的流動性", "的流動作業", "與流動態", "的流動畫面", "或流動向"])
    def test_a_flow_word_that_goes_on_as_another_word_is_not_a_stream(self, zh: str) -> None:
        assert fix_from_source(zh, "ストリームの話です") == zh


EVERYTHING = (
    "スパースストリームとストリームのワークフローで、ブランチを切ってファイルをチェックアウトします"
)
RIGHT_IN_CONTEXT = [
    prefix + right + suffix
    for right in ("串流", "稀疏串流", "工作流程", "建立", "檔案", "簽出")
    for prefix in ("", "的", "與", "稀疏", "分支", "和")
    for suffix in (
        "",
        "動作",
        "動態",
        "動畫",
        "動向",
        "暢通",
        "串接",
        "程",
        "圖",
        "功能",
        "類型",
        "機制",
        "地",
        "度",
        "分支",
        "新的分支",
        "夾",
        "出現",
        "，",
    )
]
WRONG_AND_RIGHT_TEXT = [
    "與公告的流暢度不同，流暢，流動，流串，流功能，分支流類型",
    "稀疏流和稀疏流動",
    "建立 workflow，GITHUB_WORKFLOW，`workflow`，Workflow",
    "切換分支，切換一個分支，切換新的分支",
    "技術文件，這個文件，文件夾，檢查出問題，檢查出分支",
    *RIGHT_IN_CONTEXT,
]


class TestEveryRewriteLeavesItsOwnResultAlone:
    def test_correct_chinese_with_the_right_word_in_it_is_unchanged(self) -> None:
        changed = [zh for zh in RIGHT_IN_CONTEXT if fix_from_source(zh, EVERYTHING) != zh]
        assert changed == []

    def test_a_rewritten_text_is_not_rewritten_again(self) -> None:
        for zh in WRONG_AND_RIGHT_TEXT:
            once = fix_from_source(zh, EVERYTHING)
            assert fix_from_source(once, EVERYTHING) == once, zh

    @pytest.mark.parametrize("fix", SOURCE_FIXES, ids=lambda fix: fix.right)
    def test_no_rewrite_matches_inside_its_own_right_word(self, fix: SourceFix) -> None:
        for prefix in ("", "的", "與", "稀疏", "分支", "和"):
            for suffix in ("", "動作", "動態", "動畫", "暢通", "串接", "程", "圖", "功能", "度"):
                text = prefix + fix.right + suffix
                assert not fix.wrong.search(text), text


class TestAUserGlossaryEntryKeepsItsWord:
    def test_a_workflow_the_user_keeps_in_latin_letters_is_not_translated(self) -> None:
        cues = cues_of("ワークフローを", "建立します")
        zh = "[[1]]建立 workflow[[2]]很方便。"
        glossary = [GlossaryEntry("ワークフロー", "workflow")]
        assert translated(cues, [zh], glossary) == ["建立 workflow", "很方便。"]
        assert translated(cues, [zh]) == ["建立工作流程", "很方便。"]

    def test_a_user_stream_word_keeps_the_users_noun(self) -> None:
        cues = cues_of("ストリームの", "機能です")
        zh = "[[1]]建立流功能[[2]]很方便。"
        glossary = [GlossaryEntry("ストリーム", "流")]
        assert translated(cues, [zh], glossary) == ["建立流功能", "很方便。"]
        assert translated(cues, [zh]) == ["建立串流功能", "很方便。"]

    def test_a_user_sparse_stream_word_keeps_the_users_noun(self) -> None:
        cues = cues_of("スパースストリームです")
        glossary = [GlossaryEntry("スパースストリーム", "稀疏流")]
        assert translated(cues, ["這是稀疏流"], glossary) == ["這是稀疏流"]
        assert translated(cues, ["這是稀疏流"]) == ["這是稀疏串流"]

    def test_the_entry_switches_off_only_its_own_rewrite(self) -> None:
        src = "スパースストリームとワークフロー"
        zh = "稀疏流與 workflow"
        assert fix_from_source(zh, src, {"ワークフロー"}) == "稀疏串流與 workflow"
        assert fix_from_source(zh, src, {"スパースストリーム"}) == "稀疏流與工作流程"
        assert fix_from_source(zh, src, {"プロジェクト"}) == "稀疏串流與工作流程"

    @pytest.mark.parametrize(
        ("zh", "src", "term"),
        [
            ("這個文件", "ファイルです", "ファイル"),
            ("檢查出分支", "チェックアウトします", "チェックアウト"),
        ],
    )
    def test_an_entry_for_the_file_or_check_out_word_keeps_the_users_word(
        self, zh: str, src: str, term: str
    ) -> None:
        assert fix_from_source(zh, src, {term}) == zh
        assert fix_from_source(zh, src) != zh

    def test_an_entry_for_the_branch_word_alone_does_not_switch_off_the_create_rule(self) -> None:
        assert fix_from_source("切換分支", "ブランチを切ります", {"ブランチ"}) == "建立分支"
        assert fix_from_source("切換分支", "ブランチを切ります", {"ブランチを切る"}) == "切換分支"
