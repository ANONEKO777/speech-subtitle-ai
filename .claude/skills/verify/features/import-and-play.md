# Import and play

A user pastes a video path, presses 匯入, watches a progress bar with the current step name, and then sees the video with the subtitles below it and a cue list beside it.

## Sub-features

- `import-form` accepts a typed path and enables 匯入 only with a non-empty path.
- `import-progress` shows a bar that follows the job's server-sent events and names the step (擷取音訊, 偵測語音, 語音辨識, 斷句, 翻譯成繁體中文, 輸出字幕, 重點摘要).
- `import-cached` goes straight to the player when the project is already translated.
- `play-below` puts the subtitle area under the video, not over it.
- `shutdown` kills the backend and its ASR children when the window closes.

## How to get to it (user POV)

- Launch the app, wait for 後端已就緒, type the path, press 匯入.
- 選擇檔案 opens the native picker and fills the same field.

## Driving it with app/e2e

Preconditions: release exe built, projects folder prepared (see README), GPU free for a new video.

- **Import.** `node app/e2e/import-play.mjs <projects> <video> <shots>`. Fills `video-path`, clicks `import`. `importing` appears for a new video with `step-name` and `percent` rising. Then `video` and `cue-list` appear.
- **Below the video.** The script reads the rectangles. `subtitle` top is at or below `video` bottom. Output line starts with PASS.
- **Progress samples.** `lanes.mjs` samples `step-name` and `percent` every 0.5 s into `progress-samples.json`. At least four distinct step names and a non-decreasing percent.
- **Shutdown.** The script closes the window with `CloseMainWindow`, waits 1.5 s, then `strayProcesses()` is empty.

## Gotchas

- A new video runs the full pipeline (about 6 minutes for 38 minutes of audio on an RTX 4090). Use a copied projects folder for quick checks.
- A project is keyed by the hash of the video path, so a copy of a video at another path is a new project.
- The cached path shows no progress bar, so it cannot prove `import-progress`.
- Another agent's `llama-server` can be running. It is not ours. Check its command line before calling it a leak.
