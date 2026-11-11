# Subtitle modes and list

While a video plays, the subtitle area under it shows the current cue in English, Chinese, or both. The list beside it shows every cue, jumps the video when clicked, and keeps the current cue in view. Size and color settings survive a restart.

## Sub-features

- `mode-toggle` switches 英文 / 中文 / 雙語. Each mode shows only its languages.
- `cue-jump` clicking cue N sets the video time to that cue's start.
- `autoscroll` the active list item stays inside the list's visible area during playback.
- `style-persist` font size, color, line height, language order and mode persist across restarts.
- `latency` the subtitle changes within one frame of the video clock reaching a cue's start.

## How to get to it (user POV)

- Import a video, then use the 英文 / 中文 / 雙語 buttons and the sliders in the top bar.
- Click any row in the right-hand list.

## Driving it with app/e2e

Preconditions: a player is showing a translated project with at least 200 cues.

- **Modes.** Click `mode-en`, `mode-zh`, `mode-both`. Read `subtitle p[data-lang]`: `["src"]`, `["zh"]`, `["zh","src"]`.
- **Jump.** Click `cue-200 button`. After 0.5 s `video.currentTime` is within 0.1 s of `cue-200`'s `data-start` / 1000. With the video paused the match is exact.
- **Autoscroll.** Play from cue 200 for 60 s, sampling each second. The `[data-active="true"]` row rectangle is inside the `cue-list` rectangle every time.
- **Persist.** Fill `font-size` and `font-color`, press `mode-zh`, close the window, relaunch, import the same video. Computed `fontSize` and `color` on `subtitle` match, and `mode-zh` has `aria-pressed=true`.
- **Latency.** A MutationObserver on `subtitle` records `video.currentTime` at each DOM change. Latency is that time minus the cue's start. This is a proxy for the screen-recording measure.

## Gotchas

- `video.play()` needs a prior user gesture. Click a cue first, and set `muted = true`.
- Audio-only files play in the `<video>` element as a black frame. Fine for list and subtitle checks, not for visual checks of the video.
- The latency proxy reads the same clock the app reads. It does not see display delay.
