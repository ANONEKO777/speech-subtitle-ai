"""Which language a video is spoken in, guessed from a few short pieces of its audio.

Whisper names the language of an audio piece before it transcribes (`whisper-cli -dl`), with a
probability. The video is sampled, not read through: `SAMPLE_COUNT` pieces of `SAMPLE_S` seconds
spread over its length, so the answer arrives in a few seconds however long the talk is. The pieces
are short on purpose. A talk that changes language every few seconds (a speaker and an
interpreter) puts both languages in one 30 s piece and Whisper names only one of them, so 5 s
pieces are what make a Japanese and English talk show both. `scripts/p24c_detect_table.py` measures
the choices below on real videos; the numbers are in `docs/SPEC.md` section 5.0.

The module only turns the pieces' tags into an answer. Cutting the audio and running Whisper are
passed in, so a test can give it fake ones.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path

from backend.core.source_langs import MIXED_SOURCE

SAMPLE_COUNT = 24
SAMPLE_S = 5.0
MIN_PROBABILITY = 0.5
"""A piece whose language Whisper names with less probability than this holds no speech worth
counting (music, silence, a few words)."""
MIN_PIECES = 3
"""Fewer pieces than this with a clear language is too little to say anything. A 15 s video has
three."""
MIN_MIXED_PIECES = 12
"""A talk is called mixed only from this many clear pieces, so that one stray piece of a short
video cannot do it."""
MIXED_SHARE = 0.15
"""The smaller language holds at least this share of the clear pieces: the talk uses both."""
SURE_SHARE = 0.9
"""The larger language holds at least this share of the clear pieces: one language, and sure."""

LANGUAGES = tuple(member.code for member in MIXED_SOURCE.members)
"""The two languages that can be told apart: the members of the mixed source, in its order."""


@dataclass(frozen=True, slots=True)
class Heard:
    """What Whisper named for one piece of audio: a language code and how probable it found it."""

    code: str
    probability: float


@dataclass(frozen=True, slots=True)
class Sample:
    start_s: float
    heard: Heard

    @property
    def clear(self) -> bool:
        return self.heard.code in LANGUAGES and self.heard.probability >= MIN_PROBABILITY


@dataclass(frozen=True, slots=True)
class Detection:
    """The answer: `code` is a source language code (`en`, `ja`, `ja+en`) or None when the video
    holds too little speech to say. `confidence` is the share of clear pieces in the language
    that spoke most, and `shares` the share of each of the two languages."""

    code: str | None
    confidence: float
    shares: tuple[tuple[str, float], ...]
    clear: int
    samples: tuple[Sample, ...]

    @property
    def sure(self) -> bool:
        """Whether a person who chose another language should be told. A talk in both languages
        is called mixed from `MIXED_SHARE`, so it is always sure."""
        return self.code is not None and (
            self.code == MIXED_SOURCE.code or self.confidence >= SURE_SHARE
        )


def sample_starts(
    duration_s: float, count: int = SAMPLE_COUNT, length_s: float = SAMPLE_S
) -> list[float]:
    """Where each piece starts: the centres are spaced evenly over the video. A video shorter than
    `count` pieces gets as many whole pieces as fit, and one shorter than a piece gets one at 0."""
    pieces = min(count, int(duration_s // length_s))
    if pieces <= 0:
        return [0.0]
    return [
        max(0.0, min((index + 0.5) / pieces * duration_s - length_s / 2, duration_s - length_s))
        for index in range(pieces)
    ]


def decide(samples: Sequence[Sample]) -> Detection:
    """One language when nearly every clear piece is in it, both when the smaller one holds
    `MIXED_SHARE` or more of at least `MIN_MIXED_PIECES`, and None when fewer than `MIN_PIECES`
    are clear."""
    clear = [sample.heard.code for sample in samples if sample.clear]
    kept = tuple(samples)
    if len(clear) < MIN_PIECES:
        return Detection(None, 0.0, (), len(clear), kept)
    shares = tuple((code, clear.count(code) / len(clear)) for code in LANGUAGES)
    main, share = max(shares, key=lambda item: item[1])
    if len(clear) >= MIN_MIXED_PIECES and min(value for _, value in shares) >= MIXED_SHARE:
        return Detection(MIXED_SOURCE.code, share, shares, len(clear), kept)
    return Detection(main, share, shares, len(clear), kept)


Cut = Callable[[Sequence[float], float], list[Path]]
"""Cuts the pieces that start at the given seconds and last the given seconds, as wav files."""
Name = Callable[[Sequence[Path]], list[Heard]]
"""Names the language of each wav file, in order."""


def detect(duration_s: float, cut: Cut, name: Name) -> Detection:
    starts = sample_starts(duration_s)
    heard = name(cut(starts, SAMPLE_S))
    if len(heard) != len(starts):
        raise ValueError(f"{len(heard)} languages named for {len(starts)} pieces")
    return decide([Sample(start, tag) for start, tag in zip(starts, heard, strict=True)])
