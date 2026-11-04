from __future__ import annotations

import logging
import re
import threading
import wave
from collections.abc import Sequence
from dataclasses import replace
from pathlib import Path

from backend.core.audio import SAMPLE_RATE, wav_duration_ms
from backend.core.model import Segment, Word
from backend.core.segmenter import merge_words
from backend.core.vad import Chunk
from backend.engines.base import (
    ASREngine,
    EngineCancelled,
    EngineError,
    ProgressCb,
    ascii_temp_dir,
    segment_of,
)

SENTENCE_PAUSE_GAP_MS = 150
_SENTENCE_END = ".?!…"
_CLOSERS = "\"'”’»)]}"
_NON_WORD = re.compile(r"\W+")
_PRONOUN_I = re.compile(r"I(['’].*)?")
_LOWER_I = re.compile(r"i(?=['’]|\W|$)")
_FILLERS = frozenset("um uh er ah hm hmm mm".split())
_CANNOT_END_A_SENTENCE = _FILLERS | frozenset(
    "a an the of to in on at for with from by and but or nor if than into about".split()
)

log = logging.getLogger(__name__)


def transcribe_chunks(
    engine: ASREngine,
    wav: Path,
    chunks: Sequence[Chunk],
    language: str = "en",
    progress_cb: ProgressCb | None = None,
    cancel: threading.Event | None = None,
) -> list[Word]:
    if not engine.supports_word_timestamps:
        raise EngineError(f"{engine.id} gives no word timestamps; align its output first")
    total_ms = wav_duration_ms(wav)
    for chunk in chunks:
        if chunk.end_ms > total_ms + 1000:
            raise ValueError(
                f"chunk {chunk.start_ms}..{chunk.end_ms} ms is past the {total_ms} ms wav"
            )
    with ascii_temp_dir() as work:
        paths = write_chunks(wav, chunks, work, cancel)
        results = engine.transcribe_many(paths, language, progress_cb, cancel)
    per_chunk = [_place(chunk, segments) for chunk, segments in zip(chunks, results, strict=True)]
    trimmed = trim_overlaps(chunks, per_chunk)
    repaired = [capitalize_pronoun_i(words) for words in repair_boundaries(chunks, trimmed)]
    return merge_words([segment_of(words, words[0].start_ms, 0) for words in repaired if words])


def write_chunks(
    wav: Path, chunks: Sequence[Chunk], work: Path, cancel: threading.Event | None
) -> list[Path]:
    paths: list[Path] = []
    with wave.open(str(wav), "rb") as reader:
        for index, chunk in enumerate(chunks):
            if cancel is not None and cancel.is_set():
                raise EngineCancelled("chunk extraction was cancelled")
            first = chunk.start_ms * SAMPLE_RATE // 1000
            reader.setpos(first)
            frames = reader.readframes(chunk.end_ms * SAMPLE_RATE // 1000 - first)
            path = work / f"c{index:05d}.wav"
            with wave.open(str(path), "wb") as writer:
                writer.setnchannels(1)
                writer.setsampwidth(2)
                writer.setframerate(SAMPLE_RATE)
                writer.writeframes(frames)
            paths.append(path)
    return paths


def _place(chunk: Chunk, segments: Sequence[Segment]) -> list[Word]:
    return [
        Word(w.text, w.start_ms + chunk.start_ms, w.end_ms + chunk.start_ms)
        for segment in segments
        for w in segment.words or ()
    ]


def trim_overlaps(chunks: Sequence[Chunk], per_chunk: Sequence[list[Word]]) -> list[list[Word]]:
    kept = [list(words) for words in per_chunk]
    for index in range(len(chunks) - 1):
        left, right = chunks[index], chunks[index + 1]
        if left.end_ms <= right.start_ms:
            continue
        twice_mid = left.end_ms + right.start_ms
        kept[index] = [w for w in kept[index] if w.start_ms + w.end_ms < twice_mid]
        kept[index + 1] = [w for w in kept[index + 1] if w.start_ms + w.end_ms >= twice_mid]
    return kept


def _ends_sentence(text: str) -> bool:
    return (text.rstrip(_CLOSERS) or text)[-1] in _SENTENCE_END


def _norm(text: str) -> str:
    return _NON_WORD.sub("", text.casefold())


def _mid_sentence_capitals(chunks: Sequence[Sequence[Word]]) -> set[str]:
    names: set[str] = set()
    for words in chunks:
        for before, word in zip(words, words[1:], strict=False):
            if word.text[0].isupper() and not _ends_sentence(before.text):
                names.add(_norm(word.text))
    return names


def _capital_i(text: str) -> str:
    return _LOWER_I.sub("I", text, count=1) if text[:1] == "i" else text


def _lowered(text: str, names: set[str]) -> str:
    plain = text[0].isupper() and text[1:] == text[1:].lower()
    if not plain or _PRONOUN_I.fullmatch(text) or _norm(text) in names or _norm(text) in _FILLERS:
        return text
    return text[0].lower() + text[1:]


def _is_false_period(tail: Word, head: Word, gap_ms: int) -> bool:
    if len(tail.text) < 2 or not tail.text.endswith(".") or tail.text.endswith(".."):
        return False
    continues = head.text[0].islower() and _norm(head.text) not in _FILLERS
    return gap_ms < SENTENCE_PAUSE_GAP_MS or continues or _norm(tail.text) in _CANNOT_END_A_SENTENCE


def repair_boundaries(
    chunks: Sequence[Chunk], per_chunk: Sequence[Sequence[Word]]
) -> list[list[Word]]:
    out = [list(words) for words in per_chunk]
    names = _mid_sentence_capitals(out)
    last: int | None = None
    removed = 0
    for index, words in enumerate(out):
        if not words:
            continue
        if last is not None:
            tail, head = out[last][-1], words[0]
            gap_ms = chunks[index].start_ms - chunks[last].end_ms
            if _is_false_period(tail, head, gap_ms):
                out[last][-1] = replace(tail, text=tail.text[:-1])
                if gap_ms < SENTENCE_PAUSE_GAP_MS:
                    words[0] = replace(head, text=_lowered(head.text, names))
                removed += 1
        last = index
    if removed:
        log.info("removed %d period(s) at chunk edges", removed)
    return out


def capitalize_pronoun_i(words: Sequence[Word]) -> list[Word]:
    return [replace(w, text=_capital_i(w.text)) for w in words]
