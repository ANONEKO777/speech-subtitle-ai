# Desktop app verification map

This directory is the maintained source for verifying what a user does in the Video Subtitle Translator window. Read this index, then use the matching feature file as the recipe.

## Baseline preconditions

- The release exe is built (`cd app && npx tauri build --no-bundle`) and `.venv` exists at the repo root.
- Use a disposable projects folder per run. To skip the GPU during the run, build a seed once with `uv run python scripts/make_verify_seed.py` (GPU free, `VST_USER_DATA` or `--user-data` pointing at a folder that has the models). It cuts a 60 s clip of `.work/audio/talk38.wav` onto a colour background, runs the real CLI on it, and is safe to rerun. Copy the printed `project folder` into the disposable projects folder and import the printed `import this video` path. The seed lives under `.work/verify-seed`, so no moved scratch folder breaks it.
- A first import of a new video needs the GPU free: `tasklist | grep -iE "whisper-cli|crispasr|llama-server"` exits 1.
- Never drive a window this run did not start.

## Driving conventions

- Drive through `app/e2e/lib.mjs` (`launch`) over WebView2's DevTools port. Selectors are `data-testid`.
- The file dialog is native and not driveable. Type the absolute path into `video-path`.
- Read measurements with `page.evaluate`. A screenshot alone does not prove a position or a time.

## Proof and skip reporting

- Capture the action and the resulting state. Include a screenshot per lane.
- After every run, `strayProcesses()` must be empty.
- Report an unreachable path with the attempted step and the unmet precondition. Do not report it as verified another way.

## Features

- [Import and play](./import-and-play.md) covers the import form, the SSE progress bar, the player with subtitles below the video, and shutdown.
- [Subtitle modes and list](./subtitles-and-list.md) covers English, Chinese and bilingual modes, jump to a cue, auto-scroll, and the style settings that persist.
- [Window size and formats](./window-and-formats.md) covers the 1280x720 window and the MKV notice.
