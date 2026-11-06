# Promo media

The screenshots, `demo.mp4` and `poster.png` that the root READMEs use. Everything here was captured from the real window with real speech recognition and translation, on an RTX 4090.

## Source clip

The clip is minutes 1:14 to 7:07 of the 2023 "State of NASA" address by NASA Administrator Bill Nelson (9 March 2023, 5 min 53 s, 1280x720 H.264/AAC). NASA media is generally not subject to copyright in the United States ([usage guidelines](https://www.nasa.gov/nasa-brand-center/images-and-media/)).

- Source: https://images.nasa.gov/details/2023%20%E2%80%98State%20of%20NASA%E2%80%99%20Address%20from%20Administrator%20Bill%20Nelson
- File used: the `~medium.mp4` rendition from `https://images-assets.nasa.gov/video/2023%20%E2%80%98State%20of%20NASA%E2%80%99%20Address%20from%20Administrator%20Bill%20Nelson/`
- Cut with `ffmpeg -ss 74 -to 427 -c:v libx264 -crf 22 -c:a aac`

The clip is not in the repository.

## Files

| File | What it is |
| --- | --- |
| `hero.png`, `mode-en.png`, `mode-zh.png`, `mode-both.png` | The player in bilingual, English-only, Chinese-only and both modes |
| `import-progress.png` | The import screen during translation |
| `edit-error.png`, `edit-saved.png` | A refused edit and a saved one |
| `summary.png`, `export-menu.png`, `languages.png` | The summary tab, the export menu, the same talk in Japanese |
| `demo.mp4`, `poster.png` | The one-minute walkthrough (H.264, no audio) and a still for it |

Screenshots are 1600x900 PNG, taken from a 1280x720 viewport at 1.25x.

## Regenerating

Run from the repository root with a built app (`cd app && npx tauri build --no-bundle`), the models under `VST_USER_DATA`, and the GPU free. Set `WEBVIEW2_USER_DATA_FOLDER` to a folder of your own so the window does not join another running copy of the app. Each script uses its own DevTools port.

1. `node docs/media/tools/record-import.mjs <projects> <video> <out>` imports the clip in the window and records the progress.
2. `uv run python -m backend.cli <video> -o <projects>/<id> --lang ja` adds the second language.
3. `node docs/media/tools/shots.mjs <projects-copy> <video> <out> <hero-cue> <edit-cue>` takes the screenshots. It edits the project, so use a copy.
4. `node docs/media/tools/record-tour.mjs <projects-copy> <video> <out>/tour <edit-cue> "<new text>"` records the tour. Set `VST_EXPORT_DIR` first to a neutral folder such as `D:\talks\exports`, because the footer shows its path in the video, and the native save dialog cannot be driven.
5. `node docs/media/tools/build-demo.mjs <out> <work> <dest> <hero.png>` builds the captioned video and the poster.
6. `python docs/media/tools/optimize-png.py <src> <dest> --size 1600x900` optimizes the PNGs.
7. `node docs/media/tools/check-readmes.mjs` checks the four READMEs.

`.gitignore` lets `docs/media/*.mp4` through, so `git add docs/media/demo.mp4` is enough.
