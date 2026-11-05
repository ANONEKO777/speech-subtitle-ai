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

## Command line

```
uv run python -m backend.cli talk.mp4 --engine whispercpp --llm qwen3-8b-q4_k_m
```

This writes `talk.vst/` next to the video, with `en.srt`, `zh-TW.srt`, `bilingual.ass`, `bilingual.vtt`, `summary.md` and `project.json`. Run the same command again and every step is skipped. Change `--llm` and only translation, export and the summary run again. Press Ctrl+C during any step and run the command again to resume at that step. `--help` lists every option.
