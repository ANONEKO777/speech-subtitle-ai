# Window size and formats

The app stays usable in a 1280x720 window, and a video the built-in player cannot decode gets a clear notice that asks for a proxy.

## Sub-features

- `small-window` video, subtitle area and the list are fully visible at 1280x720.
- `mkv` an MKV plays, or the `unplayable` notice asks for an H.264/AAC MP4 proxy.

## How to get to it (user POV)

- Resize the window, or maximize and restore.
- Import a `.mkv` file.

## Driving it with app/e2e

Preconditions: player showing a project.

- **Resize.** `Browser.setWindowBounds` over a CDP session to 1280x720. Then every rectangle of `video` and `subtitle` is inside the viewport (`innerWidth` x `innerHeight`) and the video is at least 250 px tall.
- **MKV.** `node app/e2e/lanes.mjs <projects> <video.mp4> <shots> <video.mkv>`. After the import, either `video.readyState >= 2`, or `[data-testid="unplayable"]` is on screen.

## Gotchas

- The viewport reported at "1280x720" depends on the window frame and DPI scale. Record both numbers.
- An MKV import runs the pipeline for that path, so use a short clip to keep the GPU job small.
