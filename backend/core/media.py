"""Which files count as media input. The CLI, the project API and the queue all ask this one set."""

from __future__ import annotations

from pathlib import Path

VIDEO_EXTENSIONS = frozenset(
    {
        ".mp4",
        ".mkv",
        ".mov",
        ".avi",
        ".webm",
        ".m4v",
        ".flv",
        ".wmv",
        ".ts",
        ".mpg",
        ".mpeg",
        ".3gp",
        ".mts",
        ".m2ts",
        ".ogv",
    }
)
AUDIO_EXTENSIONS = frozenset(
    {".wav", ".mp3", ".m4a", ".flac", ".ogg", ".aac", ".opus", ".wma", ".aiff", ".aif"}
)
MEDIA_EXTENSIONS = VIDEO_EXTENSIONS | AUDIO_EXTENSIONS


def accepted_extensions() -> str:
    return " ".join(sorted(MEDIA_EXTENSIONS))


def is_media(path: Path | str) -> bool:
    return Path(path).suffix.lower() in MEDIA_EXTENSIONS
