import json
import random
from pathlib import Path

import pytest

from backend.core.model import Cue, Segment, Word
from backend.core.segmenter import CueRules, merge_words, to_cues, violations
from backend.core.subtitle_io import parse_srt, render_srt

RULES = CueRules()
FIXTURE_WORDS = Path(__file__).parent / "fixtures" / "en_15s.words.json"


def seg(*words: tuple[str, int, int]) -> Segment:
    made = tuple(Word(text, start, end) for text, start, end in words)
    return Segment(" ".join(w.text for w in made), made[0].start_ms, made[-1].end_ms, made)


def timed(text: str, start: int, per_word: int = 300, gap: int = 0) -> Segment:
    t = start
    out: list[tuple[str, int, int]] = []
    for token in text.split():
        out.append((token, t, t + per_word))
        t += per_word + gap
    return seg(*out)


def texts(cues: list[Cue]) -> list[str]:
    return [c.en.replace("\n", " / ") for c in cues]


def test_fixture_words_make_compliant_cues() -> None:
    raw = json.loads(FIXTURE_WORDS.read_text(encoding="utf-8"))
    segments = [
        Segment("", 0, 1, tuple(Word(w["text"], w["start_ms"], w["end_ms"]) for w in s["words"]))
        for s in raw
    ]
    cues = to_cues(segments)
    assert violations(cues) == []
    assert " ".join(c.en.replace("\n", " ") for c in cues).startswith("Recordings are in the")
    assert len(cues) >= 2


def test_empty_input_gives_no_cues() -> None:
    assert to_cues([]) == []


def test_a_short_sentence_is_one_one_line_cue() -> None:
    cues = to_cues([timed("Good morning, everyone.", 1000)])
    assert [(c.id, c.start_ms, c.en) for c in cues] == [(1, 1000, "Good morning, everyone.")]
    assert cues[0].end_ms - cues[0].start_ms >= RULES.min_cue_ms


def test_a_long_sentence_wraps_to_two_lines_of_at_most_42_characters() -> None:
    text = "Today I want to talk about three ideas that changed my work."
    (cue,) = to_cues([timed(text, 0, per_word=250)])
    lines = cue.en.split("\n")
    assert len(lines) == 2 and all(len(line) <= 42 for line in lines)
    assert " ".join(lines) == text


def test_wrap_prefers_a_comma_over_a_perfectly_even_split() -> None:
    text = "When we started this project, nobody thought it would ever work at all"
    (cue,) = to_cues([timed(text, 0, per_word=300)])
    assert cue.en.split("\n")[0].endswith("project,")


def test_wrap_prefers_a_pause_between_words() -> None:
    words = "I shipped two thousand pull requests to production last month".split()
    t = 0
    spec: list[tuple[str, int, int]] = []
    for index, word in enumerate(words):
        spec.append((word, t, t + 250))
        t += 250 + (400 if index == 3 else 0)
    (cue,) = to_cues([seg(*spec)])
    assert cue.en.split("\n")[0].endswith("thousand")


def test_text_too_long_for_two_lines_becomes_several_cues() -> None:
    sentence = "the quick brown fox jumps over the lazy dog and keeps running"
    words = " ".join([sentence] * 3)
    cues = to_cues([timed(words, 0, per_word=200)])
    assert len(cues) >= 2
    assert violations(cues) == []
    assert " ".join(c.en.replace("\n", " ") for c in cues) == words


def test_a_cue_never_runs_past_seven_seconds() -> None:
    cues = to_cues([timed("word " * 100, 0, per_word=400)])
    assert violations(cues) == []
    assert max(c.end_ms - c.start_ms for c in cues) <= 7000
    assert len(cues) >= 6


def test_a_short_cue_is_held_on_screen_for_one_second_when_there_is_room() -> None:
    cues = to_cues([seg(("Yes.", 1000, 1300)), timed("Now the next idea begins here.", 6000)])
    assert (cues[0].start_ms, cues[0].end_ms) == (1000, 2000)
    assert violations(cues) == []


def test_a_short_cue_with_no_room_merges_into_its_neighbour() -> None:
    cues = to_cues([seg(("Yes.", 1000, 1300)), timed("Now the next idea begins here.", 1300)])
    assert len(cues) == 1
    assert cues[0].en.startswith("Yes. Now")
    assert violations(cues) == []


def test_a_held_cue_may_end_exactly_80_ms_before_the_next_one() -> None:
    cues = to_cues([seg(("Yes.", 1000, 1300)), timed("Now the next idea begins here.", 2080)])
    assert [c.end_ms for c in cues][:1] == [2000]
    assert len(cues) == 2 and violations(cues) == []
    merged = to_cues([seg(("Yes.", 1000, 1300)), timed("Now the next idea begins here.", 2079)])
    assert len(merged) == 1


def test_touching_words_still_leave_an_80_ms_gap_between_cues() -> None:
    first = "This is the first long sentence of the talk and it keeps going on."
    second = "Here comes a second sentence that follows it without any pause."
    cues = to_cues([timed(first + " " + second, 0, per_word=300)])
    assert len(cues) >= 2
    for before, after in zip(cues, cues[1:], strict=False):
        assert after.start_ms - before.end_ms >= RULES.min_gap_ms
    assert violations(cues) == []


def test_breaks_land_on_sentence_ends_when_the_limits_allow() -> None:
    text = "We tried a new approach. It worked well. Then everything changed completely."
    cues = to_cues([timed(text, 0, per_word=500)])
    for cue in cues[:-1]:
        assert cue.en.rstrip()[-1] in ".?!"


def test_a_comma_is_a_better_place_to_break_than_a_random_word() -> None:
    text = (
        "When we first looked at the numbers last year, "
        "we found something that nobody on the team had expected to see"
    )
    cues = to_cues([timed(text, 0, per_word=330)])
    assert len(cues) == 2
    assert cues[0].en.endswith("last year,")


def test_cues_end_at_sentence_ends_when_the_limits_allow_it() -> None:
    text = "We shipped it. Then we tested it. Nobody complained about the result."
    assert [c.en for c in to_cues([timed(text, 0, per_word=500)])] == [
        "We shipped it.",
        "Then we tested it.",
        "Nobody complained about the result.",
    ]


def test_a_long_pause_always_starts_a_new_cue() -> None:
    cues = to_cues([timed("one two three", 0), timed("four five six", 5000)])
    assert [c.en for c in cues] == ["one two three", "four five six"]


def test_punctuation_and_contraction_tokens_glue_to_the_word_before() -> None:
    merged = merge_words(
        [seg(("Hello", 0, 300), (",", 300, 300), ("it", 400, 500), ("'s", 500, 600))]
    )
    assert [(w.text, w.start_ms, w.end_ms) for w in merged] == [
        ("Hello,", 0, 300),
        ("it's", 400, 600),
    ]


def test_blank_tokens_and_inner_whitespace_are_cleaned() -> None:
    merged = merge_words([seg((" Hi\n", 0, 100), ("  ", 100, 200), (" there ", 200, 300))])
    assert [w.text for w in merged] == ["Hi", "there"]


def test_overlap_duplicates_from_neighbouring_chunks_appear_once() -> None:
    chunk_a = timed("we think the quick brown fox", 25_000, per_word=400)
    chunk_b = timed("the quick brown fox jumps over it", 26_200, per_word=400)
    merged = merge_words([chunk_a, chunk_b])
    assert [w.text for w in merged] == "we think the quick brown fox jumps over it".split()
    assert [w.start_ms for w in merged] == sorted(w.start_ms for w in merged)


def test_duplicates_are_found_despite_timestamp_jitter() -> None:
    chunk_a = seg(("alpha", 0, 400), ("beta", 450, 800), ("gamma", 850, 1200))
    chunk_b = seg(("beta", 500, 820), ("gamma", 910, 1190), ("delta", 1250, 1600))
    assert [w.text for w in merge_words([chunk_a, chunk_b])] == ["alpha", "beta", "gamma", "delta"]


def test_a_duplicate_whose_timestamps_drifted_50_ms_apart_is_still_one_word() -> None:
    chunk_a = seg(("alpha", 0, 400), ("beta", 450, 800), ("gamma", 850, 1200))
    chunk_b = seg(("beta", 500, 800), ("gamma", 1250, 1500), ("delta", 1550, 1800))
    assert [w.text for w in merge_words([chunk_a, chunk_b])] == ["alpha", "beta", "gamma", "delta"]


def test_the_earlier_chunk_wins_when_the_overlap_text_differs() -> None:
    chunk_a = seg(("see", 0, 400), ("the", 450, 700), ("fox", 750, 1100))
    chunk_b = seg(("the", 450, 700), ("box", 760, 1100), ("jumps", 1150, 1500))
    assert [w.text for w in merge_words([chunk_a, chunk_b])] == ["see", "the", "fox", "jumps"]


def test_a_real_repeat_is_kept_inside_a_segment_and_across_separate_chunks() -> None:
    inside = seg(("that", 0, 200), ("that", 250, 450), ("works", 500, 900))
    assert [w.text for w in merge_words([inside])] == ["that", "that", "works"]
    chunk_a = seg(("I", 0, 100), ("think", 150, 500), ("that", 550, 800))
    chunk_b = seg(("that", 1200, 1400), ("works", 1450, 1800))
    assert [w.text for w in merge_words([chunk_a, chunk_b])] == [
        "I",
        "think",
        "that",
        "that",
        "works",
    ]


def test_duplicate_zero_length_words_in_the_overlap_are_dropped() -> None:
    chunk_a = seg(("ok", 0, 400), ("so", 500, 500))
    chunk_b = Segment("", 400, 900, (Word("so", 500, 500), Word("then", 600, 900)))
    assert [w.text for w in merge_words([chunk_a, chunk_b])] == ["ok", "so", "then"]


def test_a_zero_length_word_inside_another_word_is_not_a_duplicate() -> None:
    chunk_a = seg(("going", 0, 500))
    chunk_b = Segment("", 200, 900, (Word("to", 300, 300), Word("go", 520, 900)))
    assert [w.text for w in merge_words([chunk_a, chunk_b])] == ["going", "to", "go"]


def test_a_short_word_pushed_into_a_neighbour_by_jitter_is_kept() -> None:
    chunk_a = seg(("that", 0, 400))
    chunk_b = seg(("that", 20, 380), ("I", 350, 450), ("built", 500, 800))
    assert [w.text for w in merge_words([chunk_a, chunk_b])] == ["that", "I", "built"]


def test_repeats_across_adjacent_segments_are_kept() -> None:
    no = [seg(("No.", 0, 300)), seg(("No.", 350, 650)), seg(("No.", 700, 1000))]
    assert [w.text for w in merge_words(no)] == ["No.", "No.", "No."]
    touching = [seg(("No.", 0, 300)), seg(("No.", 300, 600))]
    assert [w.text for w in merge_words(touching)] == ["No.", "No."]
    sentences = [
        seg(("It's", 0, 200), ("not", 250, 450), ("that.", 500, 800)),
        seg(("That", 820, 1000), ("matters.", 1050, 1500)),
    ]
    assert [w.text for w in merge_words(sentences)] == ["It's", "not", "that.", "That", "matters."]
    stutter = [
        seg(("so", 900, 1000), ("the", 1450, 1550)),
        seg(("the", 1600, 1700), ("model", 1750, 2100)),
    ]
    assert [w.text for w in merge_words(stutter)] == ["so", "the", "the", "model"]


def test_every_overlap_duplicate_is_removed_once_under_jitter() -> None:
    raw = json.loads(FIXTURE_WORDS.read_text(encoding="utf-8"))
    words = [Word(w["text"], w["start_ms"], w["end_ms"]) for s in raw for w in s["words"]]
    rng = random.Random(9)

    def jittered(w: Word) -> Word:
        start = max(0, w.start_ms + rng.randint(-60, 60))
        return Word(w.text, start, max(start, w.end_ms + rng.randint(-60, 60)))

    removed = 0
    for _ in range(100):
        cut = rng.randint(words[3].start_ms, words[-4].end_ms)
        first = [w for w in words if w.start_ms < cut + 250]
        second = [jittered(w) for w in words if w.end_ms > cut - 250]
        removed += len(first) + len(second) - len(words)
        merged = merge_words(
            [
                Segment("", first[0].start_ms, first[-1].end_ms, tuple(first)),
                Segment("", second[0].start_ms, second[-1].end_ms, tuple(second)),
            ]
        )
        assert [w.text for w in merged] == [w.text for w in words]
    assert removed > 100


def test_duplicates_collapse_in_the_final_cues() -> None:
    chunk_a = timed("and that is why the result matters so much", 0, per_word=300)
    chunk_b = timed("the result matters so much to everyone here", 1500, per_word=300)
    cues = to_cues([chunk_a, chunk_b])
    joined = " ".join(c.en.replace("\n", " ") for c in cues)
    assert joined == "and that is why the result matters so much to everyone here"
    assert violations(cues) == []


def test_a_word_that_goes_back_in_time_is_moved_forward_not_reordered() -> None:
    merged = merge_words([seg(("a", 1000, 1200), ("b", 1300, 1500)), seg(("c", 900, 950))])
    assert [w.text for w in merged] == ["a", "b", "c"]
    assert all(x.start_ms <= y.start_ms for x, y in zip(merged, merged[1:], strict=False))
    assert all(w.end_ms >= w.start_ms for w in merged)


def test_a_word_stretched_across_silence_keeps_its_last_1500_ms() -> None:
    cues = to_cues([seg(("this.", 0, 500), ("Let's", 500, 8000), ("make", 8100, 8300))])
    assert violations(cues) == []
    assert [(c.start_ms, c.en) for c in cues] == [(0, "this."), (6500, "Let's make")]
    assert merge_words([seg(("Let's", 500, 8000))]) == [Word("Let's", 6500, 8000)]


def test_a_word_of_up_to_1500_ms_is_left_alone() -> None:
    assert merge_words([seg(("verification.", 1000, 2500))]) == [Word("verification.", 1000, 2500)]


def test_a_punctuation_token_long_after_the_word_does_not_stretch_it() -> None:
    (word,) = merge_words([seg(("end", 0, 300), (".", 5000, 5100))])
    assert (word.text, word.start_ms, word.end_ms) == ("end.", 0, 300)


@pytest.mark.parametrize("ending", ['"Stop."', "(Stop.)", "Stop."])
def test_a_closing_quote_or_bracket_after_a_period_ends_the_sentence(ending: str) -> None:
    text = f"one two three four five six seven eight nine ten {ending} We kept going on fell"
    first, second = (c.en for c in to_cues([timed(text, 0, per_word=600)]))
    assert first.endswith(ending)
    assert second == "We kept going on fell"


def test_a_segment_without_word_timestamps_is_refused() -> None:
    with pytest.raises(ValueError, match="no word timestamps"):
        to_cues([Segment("hello", 0, 1000)])


def test_violations_name_each_broken_rule() -> None:
    cues = [
        Cue(1, 0, 500, "short"),
        Cue(2, 520, 9000, "x" * 50),
        Cue(3, 9010, 11_000, "a\nb\nc"),
        Cue(4, 11_080, 12_500, "fine"),
    ]
    found = violations(cues)
    assert any("cue 1" in p and "500 ms" in p for p in found)
    assert any("cue 2" in p and "50 characters" in p for p in found)
    assert any("cue 2" in p and "8480 ms" in p for p in found)
    assert any("cue 2" in p and "20 ms after" in p for p in found)
    assert any("cue 3" in p and "3 lines" in p for p in found)
    assert not any("cue 4" in p for p in found)


def test_violations_flag_ids_that_do_not_increase() -> None:
    cues = [Cue(2, 0, 1500, "one"), Cue(2, 1600, 3100, "two"), Cue(1, 3200, 4700, "three")]
    found = violations(cues)
    assert any("cue 2 (1600 ms)" in p and "id" in p for p in found)
    assert any("cue 1 (3200 ms)" in p and "id" in p for p in found)


def test_violations_flag_a_word_that_cannot_fit_a_line() -> None:
    cues = to_cues([seg(("x" * 60, 0, 1500))])
    assert any("60 characters" in p for p in violations(cues))


def test_cues_survive_an_srt_round_trip() -> None:
    cues = to_cues([timed("Today I want to talk about three ideas that changed my work.", 500)])
    assert parse_srt(render_srt(cues, "en"), "en") == cues


def test_rules_reject_nonsense() -> None:
    with pytest.raises(ValueError):
        CueRules(min_cue_ms=8000)
    with pytest.raises(ValueError):
        CueRules(max_line_chars=0)


VOCAB = (
    "the of and to a in that is was it we you I think really about people because going "
    "know want work agent code build make just like very thing time model pull request "
    "production environment infrastructure responsibility extraordinarily"
).split()


def random_talk(rng: random.Random) -> list[Segment]:
    t = rng.randint(0, 5000)
    segments: list[Segment] = []
    for _ in range(rng.randint(1, 12)):
        spec: list[tuple[str, int, int]] = []
        for _ in range(rng.randint(1, 60)):
            word = rng.choice(VOCAB)
            if rng.random() < 0.08:
                word += rng.choice([",", ".", "?", "!"])
            length = rng.choice([0, rng.randint(40, 300), rng.randint(100, 900)])
            spec.append((word, t, t + length))
            t += length + rng.choice([0, 0, 0, rng.randint(1, 250), rng.randint(250, 2500)])
        segments.append(seg(*spec))
        t += rng.choice([0, 0, rng.randint(1000, 4000)])
    return segments


@pytest.mark.parametrize("seed", range(60))
def test_random_talks_always_satisfy_every_rule(seed: int) -> None:
    segments = random_talk(random.Random(seed))
    cues = to_cues(segments)
    assert cues
    assert violations(cues) == []
    spoken = [w.text for w in merge_words(segments)]
    assert " ".join(c.en.replace("\n", " ") for c in cues).split() == spoken
    assert [c.id for c in cues] == list(range(1, len(cues) + 1))
