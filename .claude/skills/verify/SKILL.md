---
name: verify
description: Drive the Video Subtitle Translator desktop window (Tauri 2 + React, Python backend sidecar) the way a user does, to import a video, watch the progress bar, play it with subtitles under the video, and save screenshots. Use to prove any change in app/** or backend/api/** works in the real window.
---

# Verify the desktop app

Surface: the Tauri window in `app/`. A user types or picks a video path, presses 匯入, watches a progress bar, then sees the video with subtitles below it and a clickable cue list on the right. The window starts the Python backend (`python -m backend.main`) as a child and kills it when the window closes. Read `features/README.md` first, then the matching feature file.

## Launch

Needs Rust (`~/.cargo/bin` on PATH), node, and `uv sync` run once at the repo root (the app starts `.venv/Scripts/python.exe`).

```
export PATH="$HOME/.cargo/bin:$PATH"
npm --prefix app install            # once
(cd app && npx tauri build --no-bundle)   # release exe with the frontend embedded, about 1.5 to 4 min
```

The drivers start the exe themselves with a disposable projects folder and WebView2's DevTools port (`WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS=--remote-debugging-port=9222`), then attach with `playwright-core` over CDP. Ready means the page shows `[data-testid="ready"]` (the backend printed its READY line). Do not start a second window while another one holds port 9222. Pass a new port to `launch()` to run side by side.

Models and runtimes: a first import needs the whisper and llama runtimes and models, which the backend looks for under `VST_USER_DATA` (default `%LOCALAPPDATA%\video-subtitle-translator`, with `runtimes/` and `models/` inside). Without them the window shows "whispercpp-large-v3-turbo program not found". On a machine that has no default folder, `export VST_USER_DATA=D:/WebProject/speech-subtitle-ai/.work/p08-ud` before starting a driver (the app passes its environment to the backend). The cached-project route below needs none of this.

GPU rule: a first import runs whisper and llama on the GPU. Before one, run in Git Bash `tasklist | grep -iE "whisper-cli|crispasr|llama-server"`. Exit 1 means free. Wait if another job runs. To avoid the GPU, point `--projects` at a copy of an already processed project folder and import the same video path (`project.json` stores it), and the window goes straight to the player.

## Doctor

Read only. Run before driving when anything looks off.

```
ls app/src-tauri/target/release/video-subtitle-translator.exe     # built
ls .venv/Scripts/python.exe                                       # backend environment
powershell -NoProfile -Command "Get-NetTCPConnection -LocalPort 9222 -ErrorAction SilentlyContinue"   # empty = DevTools port free
node -e "import('./app/e2e/lib.mjs').then(m=>console.log(m.strayProcesses()))"   # backend/ASR processes now, expect []
```

## Drive

Helpers, all in `app/e2e/` (run from the repo root, they import `playwright-core` from `app/node_modules`):

- `node app/e2e/import-play.mjs <projects-dir> <video> <shots-dir> [png-name]` is lane 1: import, wait for the player, click cue 3, check the subtitle is below the video, save the screenshot, close the window, check no backend is left. Exit 0 is a pass.
- `node app/e2e/lanes.mjs <projects-dir> <video> <shots-dir> [<video.mkv>]` runs lanes 1 to 9 (progress, below-video layout, three modes, jump to cue 200, 60 s autoscroll, latency probe, style persistence across restart, 1280x720 window, shutdown, MKV). It restarts the app once.
- `app/e2e/lib.mjs` exports `launch({projects, shots})` returning `{page, shot(name), closeWindow(), coldStartMs, pageStartMs, readyMarkMs}`, and `strayProcesses()`.

Stable handles (`data-testid`): `video-path`, `import`, `ready`, `importing`, `step-name`, `percent`, `video`, `subtitle` (children `p[data-lang=en|zh]`), `cue-list`, `cue-<n>` (1-based, `data-start` in ms, `data-active`), `mode-en|zh|both`, `font-size`, `font-color`, `unplayable`, `error`, `backend-failed`. Use them, not coordinates. The native file dialog cannot be driven, so type the path into `video-path`.

## Evidence

Save screenshots into the shots folder you pass. For a UI claim capture the action and the state after it, and read the numbers with `page.evaluate` (video `currentTime`, element rectangles), not only the picture. Check side effects: the project folder under the projects dir holds `project.json`, `zh-TW.srt`, `summary.md`. Closing the window must leave no `python.exe ... backend.main`, `whisper-cli`, `crispasr` or `llama-server` of ours (`strayProcesses()`). `llama-server` from another agent's job is not ours, tell them apart by the command line and parent. Cold start is `coldStartMs` printed by the drivers (spawn to the ready hint, rule 4 s). Never invoke Tauri commands or backend routes directly to fake a result.

## Cleanup

The drivers close the window with `CloseMainWindow`, which is the user path, and exit. If a run died, stop only what you started: `Stop-Process -Id <pid>` for the app pid the driver printed or `strayProcesses()` listed, never by name. Delete the disposable projects folder if you made one. Screenshots are the proof, leave them.
