"""Which language a video is spoken in, guessed from a few short pieces of its audio.

Whisper names the language of an audio piece before it transcribes (`whisper-cli -dl`), with a
probability. The video is sampled, not read through: `SAMPLE_COUNT` pieces of `SAMPLE_S` seconds
spread over its length, so the answer arrives in a few seconds however long the talk is. The pieces
are short on purpose. A talk that changes language every few seconds (a speaker and an
interpreter) puts both languages in one 30 s piece and Whisper names only one of them, so 5 s
pieces are what make a Japanese and English talk show both. `scripts/p24c_detect_table.py` measures
the choices below on real videos; the numbers are in `docs/SPEC.md` section 5.0.

Whisper names a language for any sound, so a piece counts only when the voice activity detector
also finds speech in it: chord music and noise are named English at 0.7 and the detector hears no
speech in them.

The module only turns the pieces' tags into an answer. Cutting the audio, running Whisper and
measuring the speech are passed in, so a test can give it fake ones.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path

from backend.core.source_langs import MIXED_SOURCE

SAMPLE_COUNT = 24
SAMPLE_S = 5.0
MIN_PROBABILITY = 0.5
"""A piece whose language Whisper names with less probability than this is left out. This filters
silence (Whisper names it English at 0.37) and a piece it cannot place, not music or noise."""
MIN_SPEECH_S = 0.5
"""A piece counts only when at least this many seconds of it is speech (Silero VAD). Measured on
5 s pieces that Whisper names with 0.5 or more: chord music and pink noise hold 0 s of speech, ring
tones at most 0.3 s, and a pause inside a real talk 0 s, while the sparsest spoken piece of a real
talk held 0.4 s."""
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
    speech_s: float

    @property
    def clear(self) -> bool:
        return (
            self.heard.code in LANGUAGES
            and self.heard.probability >= MIN_PROBABILITY
            and self.speech_s >= MIN_SPEECH_S
        )


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
    are clear (a piece is clear when it holds speech and Whisper names its language)."""
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
Measure = Callable[[Sequence[Path]], list[float]]
"""Measures the seconds of speech in each wav file, in order."""


def detect(duration_s: float, cut: Cut, name: Name, measure: Measure) -> Detection:
    starts = sample_starts(duration_s)
    wavs = cut(starts, SAMPLE_S)
    heard = name(wavs)
    speech = measure(wavs)
    if not len(heard) == len(speech) == len(starts):
        raise ValueError(
            f"{len(heard)} languages and {len(speech)} speech lengths for {len(starts)} pieces"
        )
    pieces = zip(starts, heard, speech, strict=True)
    return decide([Sample(start, tag, seconds) for start, tag, seconds in pieces])
