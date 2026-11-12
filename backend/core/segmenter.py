from __future__ import annotations

import logging
import re
from collections.abc import Sequence
from dataclasses import dataclass
from itertools import accumulate

from backend.core import unspaced
from backend.core.model import DEFAULT_SOURCE, Cue, Segment, Word

log = logging.getLogger(__name__)

MAX_LINES = 2
_VIOLATION = 1_000_000.0
_DUP_TOLERANCE_MS = 100
_LOOKBACK = 64
_MAX_WORD_MS = 1500
_GLUE_GAP_MS = 250
_SENTENCE_END = ".?!…"
_CLOSERS = "\"'”’»)]}"
_CLAUSE_END = ",;:—"
_GLUED = re.compile(
    r"[,.;:!?)\]}%…、。，！？」』）〕】]+|['’](?:s|re|ll|ve|d|m|t)|n['’]t", re.IGNORECASE
)
_WEAK_END = frozenset(
    "a an the of to in on at for with from by and but or nor so as if that than into about "
    "is are was were be i you we they he she it my your our their his her its this these".split()
)
_WEAK_START = frozenset("and but or so because which who that when while where then".split())


@dataclass(frozen=True, slots=True)
class CueRules:
    """SPEC §5.1 limits for subtitles. Lines are always at most two. `max_line_chars` counts
    characters, or display columns when `unspaced` (Japanese, where a full-width character is two
    columns and words are not separated by spaces). `max_cps` is how many of them a second may
    show before a cue is penalised."""

    max_line_chars: int = 42
    unspaced: bool = False
    max_cps: float = 17.0
    min_cue_ms: int = 1000
    max_cue_ms: int = 7000
    min_gap_ms: int = 80
    split_gap_ms: int = 1500

    def __post_init__(self) -> None:
        if not 0 < self.min_cue_ms < self.max_cue_ms:
            raise ValueError("need 0 < min_cue_ms < max_cue_ms")
        if self.max_line_chars < 1 or self.min_gap_ms < 0 or self.split_gap_ms < 0:
            raise ValueError("limits must be positive")


def _norm(text: str) -> str:
    return re.sub(r"\W+", "", text.casefold())


def _overlap_ms(a: Word, b: Word) -> int:
    return min(a.end_ms, b.end_ms) - max(a.start_ms, b.start_ms)


def _is_duplicate(word: Word, earlier: Sequence[Word], taken: set[int]) -> bool:
    key = _norm(word.text)
    covered = 0
    for index in range(len(earlier) - 1, -1, -1):
        known = earlier[index]
        if known.end_ms + _DUP_TOLERANCE_MS < word.start_ms:
            break
        overlap = _overlap_ms(word, known)
        if overlap >= -_DUP_TOLERANCE_MS and _norm(known.text) == key:
            taken.add(index)
            return True
        if index not in taken:
            covered += max(0, overlap)
    return word.end_ms > word.start_ms and covered * 2 >= word.end_ms - word.start_ms


def _last_char(text: str) -> str:
    return (text.rstrip(_CLOSERS) or text)[-1]


def merge_words(segments: Sequence[Segment]) -> list[Word]:
    """One time-ordered word list from ASR segments that may overlap at chunk edges.

    Only a segment that starts before an earlier one ends is checked for duplicates. There
    a word is dropped when it repeats a nearby word of the same text, or lies mostly inside
    a word of the earlier segment that nothing else matched, so the first segment wins.
    Segments that only touch or follow each other, and words inside one segment, are never
    deduplicated, so a real repeat ("No. No.") survives. Punctuation and contractions that
    arrive as their own token are glued to the word before them, and they stretch it only
    when they follow within 250 ms. Starts never go backward, every word ends at or after
    its start, and a word longer than 1.5 s is shortened to its last 1.5 s, because an
    aligner stretches a word across the silence before it and the sound sits at the end.
    """
    kept: list[Word] = []
    clamped = 0
    reach = 0
    for index, segment in enumerate(segments):
        if segment.words is None:
            raise ValueError(
                f"segment {index} ({segment.start_ms} ms) has no word timestamps; align it first"
            )
        first = min([segment.start_ms, *(w.start_ms for w in segment.words)])
        earlier = kept[-_LOOKBACK:] if kept and first < reach else []
        taken: set[int] = set()
        reach = max([reach, segment.end_ms, *(w.end_ms for w in segment.words)])
        for word in segment.words:
            text = " ".join(word.text.split())
            if not text or _is_duplicate(Word(text, word.start_ms, word.end_ms), earlier, taken):
                continue
            start, end = max(word.start_ms, word.end_ms - _MAX_WORD_MS), word.end_ms
            if kept and start < kept[-1].start_ms:
                start, end, clamped = kept[-1].start_ms, max(end, kept[-1].start_ms), clamped + 1
            if kept and _GLUED.fullmatch(text):
                prev = kept[-1]
                joined = end if start - prev.end_ms <= _GLUE_GAP_MS else prev.end_ms
                kept[-1] = Word(prev.text + text, prev.start_ms, max(prev.end_ms, joined), prev.lang)
            else:
                kept.append(Word(text, start, end, word.lang))
    if clamped:
        log.warning("moved %d word start(s) forward to keep time order", clamped)
    return kept


class _Widths:
    """The width of any run of words `i..j` as it is laid out on a line."""

    def __init__(self, words: Sequence[Word], r: CueRules) -> None:
        if r.unspaced:
            sizes = [unspaced.columns(w.text) for w in words]
            joints = [
                unspaced.joint(a.text, b.text) for a, b in zip(words, words[1:], strict=False)
            ]
        else:
            sizes = [len(w.text) for w in words]
            joints = [1] * max(0, len(words) - 1)
        self._words = list(accumulate(sizes, initial=0))
        self._joints = list(accumulate(joints, initial=0))

    def span(self, i: int, j: int) -> int:
        return self._words[j + 1] - self._words[i] + self._joints[j] - self._joints[i]


def _display_end(words: Sequence[Word], i: int, j: int, follow_ms: int | None, r: CueRules) -> int:
    end = max(words[j].end_ms, words[i].start_ms + r.min_cue_ms)
    if follow_ms is not None:
        end = min(end, follow_ms - r.min_gap_ms)
    return end


def _fits_two_lines(widths: _Widths, i: int, j: int, limit: int) -> bool:
    if widths.span(i, j) <= limit:
        return True
    first = i
    while first < j and widths.span(i, first + 1) <= limit:
        first += 1
    head = widths.span(i, first)
    rest = widths.span(first + 1, j) if first < j else 0
    return head <= limit and rest <= limit


def _break_cost(words: Sequence[Word], j: int, follow: Word | None) -> float:
    last = _last_char(words[j].text)
    cost = 0.0 if last in _SENTENCE_END else 1.5 if last in _CLAUSE_END else 4.0
    if last not in _SENTENCE_END + _CLAUSE_END and _norm(words[j].text) in _WEAK_END:
        cost += 3.0
    if follow is not None:
        cost = _pause_cost(cost, follow.start_ms - words[j].end_ms)
        if _norm(follow.text) in _WEAK_START and last not in _SENTENCE_END:
            cost -= 0.5
    return cost


def _pause_cost(cost: float, pause_ms: int) -> float:
    return min(cost, 0.3 if pause_ms >= 700 else 1.0 if pause_ms >= 300 else cost)


@dataclass(frozen=True, slots=True)
class _Run:
    """The words of one run with what `_split_run` asks about them again and again."""

    words: Sequence[Word]
    follow: Word | None
    widths: _Widths
    rules: CueRules
    breaks: Sequence[float] | None
    """For unspaced text, what it costs to end a cue after each word, from the script alone."""

    def break_cost(self, j: int, follow: Word | None) -> float:
        if self.breaks is None:
            return _break_cost(self.words, j, follow)
        cost = self.breaks[j]
        return cost if follow is None else _pause_cost(cost, follow.start_ms - self.words[j].end_ms)

    def wrap_cost(self, i: int, j: int) -> float:
        """What the second line of a two-line unspaced cue costs: the cheapest cut that keeps both
        lines within the limit, which a cue that fits one line does not pay."""
        limit = self.rules.max_line_chars
        if self.breaks is None or self.widths.span(i, j) <= limit:
            return 0.0
        scores = [
            self.breaks[cut]
            + abs(self.widths.span(i, cut) - self.widths.span(cut + 1, j)) / unspaced.LINE_BALANCE
            for cut in range(i, j)
            if self.widths.span(i, cut) <= limit and self.widths.span(cut + 1, j) <= limit
        ]
        return min(scores, default=0.0)

    def sentence_ends(self, i: int, j: int) -> int:
        end = unspaced.is_sentence_end if self.rules.unspaced else _ends_a_sentence
        return sum(1 for k in range(i, j) if end(self.words[k].text))


def _ends_a_sentence(text: str) -> bool:
    return _last_char(text) in _SENTENCE_END


def _cue_cost(run: _Run, i: int, j: int, follow: Word | None) -> float:
    r, words = run.rules, run.words
    cost = 2.0
    start = words[i].start_ms
    duration = _display_end(words, i, j, follow.start_ms if follow else None, r) - start
    if not _fits_two_lines(run.widths, i, j, r.max_line_chars):
        cost += _VIOLATION
    if duration > r.max_cue_ms or duration < r.min_cue_ms:
        cost += _VIOLATION
    spoken = max(words[j].end_ms - start, r.min_cue_ms)
    chars = run.widths.span(i, j)
    cost += max(0.0, chars * 1000 / spoken - r.max_cps) * 0.5
    if spoken < 1500:
        cost += 2.0
    cost += 6.0 * run.sentence_ends(i, j)
    return cost + run.break_cost(j, follow) + run.wrap_cost(i, j)


def _split_run(words: Sequence[Word], follow: Word | None, r: CueRules) -> list[tuple[int, int]]:
    run = _Run(
        words, follow, _Widths(words, r), r, unspaced.break_costs(words) if r.unspaced else None
    )
    n = len(words)
    best = [0.0] + [float("inf")] * n
    back = [0] * (n + 1)
    max_chars = 2 * r.max_line_chars + 1
    for i in range(n):
        for j in range(i, n):
            if j > i and (
                run.widths.span(i, j) > max_chars
                or words[j].end_ms - words[i].start_ms > r.max_cue_ms
            ):
                break
            nxt = words[j + 1] if j + 1 < n else follow
            total = best[i] + _cue_cost(run, i, j, nxt)
            if total < best[j + 1]:
                best[j + 1], back[j + 1] = total, i
    spans: list[tuple[int, int]] = []
    end = n
    while end > 0:
        spans.append((back[end], end - 1))
        end = back[end]
    return spans[::-1]


def _wrap(words: Sequence[Word], limit: int) -> str:
    texts = [w.text for w in words]
    whole = " ".join(texts)
    if len(whole) <= limit:
        return whole
    best: tuple[float, int] | None = None
    for cut in range(1, len(texts)):
        left, right = " ".join(texts[:cut]), " ".join(texts[cut:])
        if len(left) > limit or len(right) > limit:
            continue
        score = abs(len(left) - len(right)) * 0.5
        score -= 8.0 if _last_char(left) in _SENTENCE_END + _CLAUSE_END else 0.0
        score -= min(words[cut].start_ms - words[cut - 1].end_ms, 400) / 50
        score += 6.0 if _norm(texts[cut - 1]) in _WEAK_END else 0.0
        score -= 3.0 if _norm(texts[cut]) in _WEAK_START else 0.0
        if best is None or score < best[0]:
            best = (score, cut)
    if best is None:
        return whole
    return " ".join(texts[: best[1]]) + "\n" + " ".join(texts[best[1] :])


def to_cues(
    segments: Sequence[Segment], rules: CueRules | None = None, lang: str = DEFAULT_SOURCE
) -> list[Cue]:
    """Turn ASR word timestamps into subtitle cues that follow SPEC §5.1.

    Cues break at sentence ends, then clause punctuation and pauses, then anywhere that
    keeps the other limits. A cue that would be under the minimum is held on screen
    longer when the next cue is far enough away, and merged into its neighbor otherwise.
    A word wider than a line cannot be wrapped, and `violations` reports it.
    """
    r = rules or CueRules()
    words = merge_words(segments)
    cues: list[Cue] = []
    begin = 0
    for index in range(1, len(words) + 1):
        if index < len(words) and words[index].start_ms - words[index - 1].end_ms < r.split_gap_ms:
            continue
        run = words[begin:index]
        follow = words[index] if index < len(words) else None
        breaks = unspaced.break_costs(run) if r.unspaced else None
        for i, j in _split_run(run, follow, r):
            start = run[i].start_ms
            nxt = run[j + 1] if j + 1 < len(run) else follow
            end = max(start, _display_end(run, i, j, nxt.start_ms if nxt else None, r))
            if breaks is None:
                text = _wrap(run[i : j + 1], r.max_line_chars)
            else:
                text = unspaced.wrap(run[i : j + 1], r.max_line_chars, breaks[i:j])
            cues.append(Cue(len(cues) + 1, start, end, text, lang=lang))
        begin = index
    return cues


def violations(cues: Sequence[Cue], rules: CueRules | None = None) -> list[str]:
    r = rules or CueRules()
    problems: list[str] = []
    for index, cue in enumerate(cues):
        where = f"cue {cue.id} ({cue.start_ms} ms)"
        lines = cue.src.split("\n")
        size = unspaced.columns if r.unspaced else len
        unit = "columns" if r.unspaced else "characters"
        if len(lines) > MAX_LINES:
            problems.append(f"{where}: {len(lines)} lines")
        problems += [
            f"{where}: line of {size(line)} {unit}"
            for line in lines
            if size(line) > r.max_line_chars
        ]
        duration = cue.end_ms - cue.start_ms
        if not r.min_cue_ms <= duration <= r.max_cue_ms:
            problems.append(f"{where}: lasts {duration} ms")
        if index and cue.start_ms < cues[index - 1].end_ms + r.min_gap_ms:
            gap = cue.start_ms - cues[index - 1].end_ms
            problems.append(f"{where}: {gap} ms after the previous cue")
        if index and cue.id <= cues[index - 1].id:
            problems.append(f"{where}: id does not increase")
    return problems
