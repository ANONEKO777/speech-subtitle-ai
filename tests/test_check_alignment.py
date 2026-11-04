from __future__ import annotations

import json
from collections.abc import Callable, Sequence

import pytest

from backend.core.model import Cue
from backend.llm.client import LlmConfig, Message
from scripts import check_alignment
from scripts.check_alignment import check, content_words, score

CUES = [
    Cue(
        1,
        0,
        1000,
        "So last month I shipped two thousand pull requests",
        "所以上個月我送出兩千個合併請求",
    ),
    Cue(2, 1000, 2000, "to production and everything stayed stable", "到正式環境而且一切保持穩定"),
    Cue(
        3, 2000, 3000, "because verification caught every regression", "因為驗證抓到了每個迴歸問題"
    ),
]
CONFIG = LlmConfig("http://127.0.0.1:1/v1", "m")


def fake_chat(back: dict[str, str], judged: dict[str, str]) -> Callable[..., str]:
    def chat(
        config: LlmConfig,
        messages: Sequence[Message],
        *,
        temperature: float = 0.0,
        json_mode: bool = False,
    ) -> str:
        user = messages[1]["content"]
        if json_mode:
            zh = user.rsplit("Chinese: ", 1)[1]
            return json.dumps({"answer": judged[zh]})
        return back[user]

    return chat


def test_content_words_drop_filler_and_endings() -> None:
    assert content_words("So we shipped the requests, and you know it") == {"shipp", "request"}
    assert content_words("Requests shipped") == content_words("requests shipp")


def test_score_splits_shared_words_from_words_only_a_neighbour_has() -> None:
    own, prev, nxt = score(
        "to production and everything stayed stable",
        "I shipped pull requests",
        "to production and everything stayed stable",
        "because verification caught regressions",
    )
    assert (own, prev, nxt) == (1.0, 0.0, 0.0)
    own, prev, nxt = score(
        "verification caught every regression",
        "so last month I shipped requests",
        "to production and everything stayed stable",
        "because verification caught every regression",
    )
    assert own == 0.0 and prev == 0.0 and nxt == 1.0


@pytest.mark.parametrize(
    ("answer", "back", "misaligned"),
    [
        ("B", "to production and everything stayed stable", False),
        ("C", "because verification caught every regression", True),
        ("B", "to production, because verification caught every regression", True),
    ],
)
def test_a_cue_is_misaligned_when_the_judge_or_the_leak_says_so(
    monkeypatch: pytest.MonkeyPatch, answer: str, back: str, misaligned: bool
) -> None:
    middle = CUES[1].zh
    monkeypatch.setattr(
        check_alignment.client,
        "chat",
        fake_chat({middle: back}, {middle: answer}),
    )
    (result,) = check(CONFIG, CUES, [2])
    assert result.misaligned is misaligned
