# video-subtitle-translator

Desktop app that turns English talk videos with no subtitles into English and Traditional Chinese (Taiwan) bilingual subtitles and a summary.

Design and decisions are in `docs/SPEC.md`. Licensed under AGPL-3.0-or-later (see `LICENSE`).

## Develop

```
uv sync
uv run pytest
uv run ruff check .
uv run ruff format --check .
uv run pyright
```
