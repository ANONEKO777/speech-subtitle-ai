from __future__ import annotations

from typing import Any

from scripts.p23b_score import build_rows, render


def manifest(*ids: str) -> dict[str, Any]:
    return {
        "segments": [
            {"id": i, "stratum": "s", "start_s": n, "duration_s": 3.0} for n, i in enumerate(ids)
        ]
    }


def verdict(ids: list[str], labels: dict[str, str], tags: dict[str, str]) -> str:
    rows, unlabelled, unclear = build_rows(
        manifest(*ids), {k: {"label": v} for k, v in labels.items()}, tags
    )
    return render(rows, unlabelled, unclear, len(ids)).splitlines()[-1]


def test_a_complete_perfect_sample_passes() -> None:
    assert verdict(["a", "b"], {"a": "ja", "b": "en"}, {"a": "ja", "b": "en"}).endswith(
        "PASS on this sample"
    )


def test_an_unlabelled_segment_makes_the_verdict_partial_even_when_the_rest_is_right() -> None:
    last = verdict(["a", "b"], {"a": "ja"}, {"a": "ja", "b": "en"})
    assert "PARTIAL" in last and "PASS" not in last


def test_lost_english_fails_even_at_high_accuracy() -> None:
    ids = [f"s{i}" for i in range(60)]
    labels = {i: "ja" for i in ids[:-1]} | {ids[-1]: "en"}
    tags = {i: "ja" for i in ids}
    assert verdict(ids, labels, tags).endswith("FAIL")
