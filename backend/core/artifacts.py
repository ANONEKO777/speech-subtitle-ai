from __future__ import annotations

import json
from collections.abc import Sequence
from typing import cast

from backend.core.model import FormatError, Word
from backend.core.vad import Chunk

ARTIFACT_SCHEMA_VERSION = 1


def _load(text: str, name: str, key: str) -> list[dict[str, object]]:
    try:
        doc: object = json.loads(text)
    except ValueError as exc:
        raise FormatError(f"{name}: not valid JSON ({exc})") from exc
    if not isinstance(doc, dict):
        raise FormatError(f"{name} must be a JSON object")
    top = cast("dict[str, object]", doc)
    if top.get("schema_version") != ARTIFACT_SCHEMA_VERSION:
        raise FormatError(f"{name}: unsupported schema_version {top.get('schema_version')!r}")
    items = top.get(key)
    if not isinstance(items, list):
        raise FormatError(f"{name}: {key!r} must be a list")
    rows: list[dict[str, object]] = []
    for item in cast("list[object]", items):
        if not isinstance(item, dict):
            raise FormatError(f"{name}: every entry of {key!r} must be an object")
        rows.append(cast("dict[str, object]", item))
    return rows


def _int(row: dict[str, object], key: str, name: str) -> int:
    value = row.get(key)
    if type(value) is not int:
        raise FormatError(f"{name}: {key!r} must be an integer, got {value!r}")
    return value


def render_chunks(chunks: Sequence[Chunk]) -> str:
    rows = [{"start_ms": c.start_ms, "end_ms": c.end_ms} for c in chunks]
    return json.dumps({"schema_version": ARTIFACT_SCHEMA_VERSION, "chunks": rows}, indent=1) + "\n"


def parse_chunks(text: str) -> list[Chunk]:
    try:
        return [
            Chunk(_int(row, "start_ms", "chunks.json"), _int(row, "end_ms", "chunks.json"))
            for row in _load(text, "chunks.json", "chunks")
        ]
    except ValueError as exc:
        if isinstance(exc, FormatError):
            raise
        raise FormatError(f"chunks.json: {exc}") from exc


def render_words(engine_id: str, words: Sequence[Word]) -> str:
    """`segments.json`: the ASR result as one time-ordered word list and the engine id."""
    rows = [{"text": w.text, "start_ms": w.start_ms, "end_ms": w.end_ms} for w in words]
    doc = {"schema_version": ARTIFACT_SCHEMA_VERSION, "engine": engine_id, "words": rows}
    return json.dumps(doc, ensure_ascii=False, indent=1) + "\n"


def parse_words(text: str) -> list[Word]:
    try:
        rows = _load(text, "segments.json", "words")
        return [
            Word(
                str(row.get("text")),
                _int(row, "start_ms", "segments.json"),
                _int(row, "end_ms", "segments.json"),
            )
            for row in rows
        ]
    except ValueError as exc:
        if isinstance(exc, FormatError):
            raise
        raise FormatError(f"segments.json: {exc}") from exc
