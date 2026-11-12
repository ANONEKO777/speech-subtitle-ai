"""Speech recognition for a talk spoken in Japanese and English, one short piece at a time.

Qwen3-ASR with `-l auto` picks one language for each piece of audio it is given and writes only
that language, so a piece that holds Japanese and its English interpretation comes back as Japanese
alone. The audio is therefore cut at every pause of 300 ms (`vad.split_at_pauses`), each piece is
recognised with `-l auto`, and two repairs follow. A piece whose text is neither Japanese nor
English (short pieces come back as Korean, Chinese, Polish or Italian) is recognised again with
`-l ja`. Speech the engine left without words at the end of a piece is recognised again as a piece
of its own. Then every word is tagged `ja` or `en` from its script. The stages are separate
functions so that `scripts/p23b_proto.py` can score each of them on its own.
"""

from __future__ import annotations

import re
import threading
from collections.abc import Sequence
from dataclasses import dataclass, replace
from pathlib import Path

from backend.core.model import Segment, Word
from backend.core.segmenter import merge_words
from backend.core.vad import Chunk
from backend.engines.base import ASREngine, ProgressCb, ascii_temp_dir, segment_of
from backend.engines.chunks import place, write_chunks

JAPANESE = "ja"
ENGLISH = "en"
AUTO = "auto"
FRAGMENT_MS = 1800
"""A piece this short has too little audio for the language to be told from the sound alone."""
TAIL_MS = 1500
"""Speech left without words at the end of a piece that is at least this long is recognised again."""
EN_RUN_WORDS = 3
"""A run of Latin words this long is an English sentence, not a name inside a Japanese one."""
_FIRST_PASS_SHARE = 0.9

_HANGUL = re.compile("[ᄀ-ᇿ㄰-㆏가-힯]")
_KANA = re.compile("[぀-ヿㇰ-ㇿｦ-ﾟ]")
_HAN = re.compile("[㐀-䶿一-鿿]")
_LATIN_WORD = re.compile(r"[A-Za-z0-9][A-Za-z0-9'’.,!?;:\-]*")
_SENTENCE_END = re.compile(r"[.?!…][\"')\]”]*\Z")


def is_japanese_text(text: str) -> bool:
    return bool(_KANA.search(text) or _HAN.search(text))


def _japanese_kanji_only(text: str) -> bool:
    """Whether every ideograph can be written in Shift JIS, which Simplified-only ones cannot."""
    for char in _HAN.findall(text):
        try:
            char.encode("cp932")
        except UnicodeEncodeError:
            return False
    return True


def is_plausible(text: str) -> bool:
    """Whether `text` can be what a person said in Japanese or in English: no Hangul, and no
    ideograph that Japanese does not write."""
    return not _HANGUL.search(text) and _japanese_kanji_only(text)


def _text(words: Sequence[Word]) -> str:
    return " ".join(word.text for word in words)


def _is_single_latin_word(words: Sequence[Word]) -> bool:
    return len(words) == 1 and not is_japanese_text(words[0].text)


@dataclass(frozen=True, slots=True)
class Piece:
    """The words of one stretch of the audio, with the chunk they came from."""

    chunk: Chunk
    words: tuple[Word, ...]


def first_pass(
    engine: ASREngine,
    wav: Path,
    chunks: Sequence[Chunk],
    progress_cb: ProgressCb | None = None,
    cancel: threading.Event | None = None,
) -> list[Piece]:
    """Each chunk recognised with `-l auto`."""
    with ascii_temp_dir() as work:
        paths = write_chunks(wav, chunks, work, cancel)
        results = engine.transcribe_many(paths, AUTO, progress_cb, cancel)
    return [
        Piece(chunk, tuple(place(chunk, segments)))
        for chunk, segments in zip(chunks, results, strict=True)
    ]


def _recognise(
    engine: ASREngine,
    wav: Path,
    spans: Sequence[Chunk],
    language: str,
    cancel: threading.Event | None,
) -> list[tuple[Word, ...]]:
    if not spans:
        return []
    with ascii_temp_dir() as work:
        paths = write_chunks(wav, spans, work, cancel)
        results = engine.transcribe_many(paths, language, None, cancel)
    return [tuple(place(span, segments)) for span, segments in zip(spans, results, strict=True)]


def needs_japanese(piece: Piece) -> bool:
    """A piece whose text cannot be Japanese or English, or a short one that is one Latin word
    (`sempre`, `Pierwszy`) where Japanese was said."""
    text = _text(piece.words)
    if not is_plausible(text):
        return True
    return piece.chunk.duration_ms < FRAGMENT_MS and _is_single_latin_word(piece.words)


def guard_pass(
    engine: ASREngine,
    wav: Path,
    pieces: Sequence[Piece],
    cancel: threading.Event | None = None,
) -> list[Piece]:
    """Recognise again with `-l ja` the pieces `needs_japanese` names. The new words replace the
    old ones when the old text was not plausible, and when it was one Latin word only if the
    Japanese is Japanese."""
    wanted = [i for i, piece in enumerate(pieces) if needs_japanese(piece)]
    redone = _recognise(engine, wav, [pieces[i].chunk for i in wanted], JAPANESE, cancel)
    out = list(pieces)
    for index, words in zip(wanted, redone, strict=True):
        old = pieces[index]
        if is_plausible(_text(old.words)) or is_japanese_text(_text(words)):
            out[index] = Piece(old.chunk, words)
    return out


def tail_chunk(piece: Piece) -> Chunk | None:
    """The end of the piece that no word covers, when it is long enough to hold speech."""
    chunk = piece.chunk
    spoken_to = max((w.end_ms for w in piece.words), default=chunk.start_ms)
    if chunk.end_ms - spoken_to < TAIL_MS:
        return None
    return Chunk(spoken_to, chunk.end_ms)


def tail_pass(
    engine: ASREngine,
    wav: Path,
    pieces: Sequence[Piece],
    cancel: threading.Event | None = None,
) -> list[Piece]:
    """Recognise the uncovered end of each piece as a piece of its own, and keep what it says
    when that is plausible. This is how English that follows Japanese without a pause is found."""
    tails = [(i, tail) for i, piece in enumerate(pieces) if (tail := tail_chunk(piece))]
    redone = _recognise(engine, wav, [tail for _, tail in tails], AUTO, cancel)
    out = list(pieces)
    for (index, _), words in zip(tails, redone, strict=True):
        if words and is_plausible(_text(words)):
            out[index] = Piece(pieces[index].chunk, (*pieces[index].words, *words))
    return out


def tag_words(words: Sequence[Word]) -> list[Word]:
    """Give each word the language of its script. Kana and ideographs are Japanese. A run of
    Latin words is English when the piece has no Japanese in it, when it has three words or more,
    or when it ends a sentence after Japanese; a shorter run inside Japanese (a product name) goes
    with the Japanese around it. Punctuation and digits go with the word before."""
    kinds: list[str | None] = [
        JAPANESE if is_japanese_text(w.text) else ENGLISH if _LATIN_WORD.match(w.text) else None
        for w in words
    ]
    has_japanese = JAPANESE in kinds
    index = 0
    while index < len(words):
        if kinds[index] != ENGLISH:
            index += 1
            continue
        stop = index
        while stop < len(words) and kinds[stop] in (ENGLISH, None):
            stop += 1
        run = [i for i in range(index, stop) if kinds[i] == ENGLISH]
        ends_sentence = bool(_SENTENCE_END.search(words[stop - 1].text))
        inside = index > 0 and stop < len(words)
        as_english = (
            not has_japanese
            or len(run) >= EN_RUN_WORDS
            or (ends_sentence and not inside)
            or (ends_sentence and len(run) >= 2)
        )
        for i in range(index, stop):
            kinds[i] = ENGLISH if as_english else JAPANESE
        index = stop
    tagged: list[Word] = []
    previous = ENGLISH if not has_japanese else JAPANESE
    for word, kind in zip(words, kinds, strict=True):
        previous = kind or previous
        tagged.append(replace(word, lang=previous))
    return tagged


def tag_pieces(pieces: Sequence[Piece]) -> list[Word]:
    """One time-ordered word list with a language on every word."""
    segments: list[Segment] = []
    for piece in pieces:
        words = tag_words(piece.words)
        if words:
            segments.append(segment_of(words, words[0].start_ms, 0))
    return merge_words(segments)


def transcribe_mixed(
    engine: ASREngine,
    wav: Path,
    chunks: Sequence[Chunk],
    progress_cb: ProgressCb | None = None,
    cancel: threading.Event | None = None,
) -> list[Word]:
    def first_progress(fraction: float) -> None:
        if progress_cb is not None:
            progress_cb(fraction * _FIRST_PASS_SHARE)

    pieces = first_pass(engine, wav, chunks, first_progress, cancel)
    pieces = guard_pass(engine, wav, pieces, cancel)
    pieces = tail_pass(engine, wav, pieces, cancel)
    return tag_pieces(pieces)
