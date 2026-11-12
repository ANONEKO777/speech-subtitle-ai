# Subtitle modes and list

While a video plays, the subtitle area under it shows the current cue in the original language (English, Japanese, or both in a mixed talk), in Traditional Chinese, or both. The list beside it shows every cue, jumps the video when clicked, and keeps the current cue in view. Size and color settings survive a restart.

## Sub-features

- `mode-toggle` switches 原文 / 繁體中文 / 雙語. Each mode shows only its languages.
- `cue-jump` clicking cue N sets the video time to that cue's start.
- `autoscroll` the active list item stays inside the list's visible area during playback.
- `style-persist` font size, color, line height, language order and mode persist across restarts.
- `latency` the subtitle changes within one frame of the video clock reaching a cue's start.
- `cue-lang` in a `ja+en` project each cue shows its own language. The cue list and the editor put a 日 or 英 mark (`lang-mark`, `data-cue-lang`) beside the original line, the original line in the subtitle area carries `data-cue-lang` and `lang`, and no mark shows in an English or Japanese project. Editing never merges two neighbouring cues of different languages.

## How to get to it (user POV)

- Import a video, then use the 原文 / 繁體中文 / 雙語 buttons and the sliders in the top bar.
- Click any row in the right-hand list.

## Driving it with app/e2e

Preconditions: a player is showing a translated project with at least 200 cues.

- **Modes.** Click `mode-en`, `mode-zh`, `mode-both`. Read `subtitle p[data-lang]`: `["src"]`, `["zh"]`, `["zh","src"]`.
- **Cue language (mixed project only).** Read `subtitle p[data-lang=src]` and check its `data-cue-lang` is `ja` or `en` and matches the `lang` attribute. In `cue-list`, every `cue-<n> .src` has `data-cue-lang`, and `lang-mark` has the same value and the text 日 or 英. In an English or Japanese project `lang-mark` does not exist. Open the editor on a cue: `edit-source` carries `data-cue-lang` and its own `lang-mark`.
- **Jump.** Click `cue-200 button`. After 0.5 s `video.currentTime` is within 0.1 s of `cue-200`'s `data-start` / 1000. With the video paused the match is exact.
- **Autoscroll.** Play from cue 200 for 60 s, sampling each second. The `[data-active="true"]` row rectangle is inside the `cue-list` rectangle every time.
- **Persist.** Fill `font-size` and `font-color`, press `mode-zh`, close the window, relaunch, import the same video. Computed `fontSize` and `color` on `subtitle` match, and `mode-zh` has `aria-pressed=true`.
- **Latency.** A MutationObserver on `subtitle` records `video.currentTime` at each DOM change. Latency is that time minus the cue's start. This is a proxy for the screen-recording measure.

## Gotchas

- `video.play()` needs a prior user gesture. Click a cue first, and set `muted = true`.
- Audio-only files play in the `<video>` element as a black frame. Fine for list and subtitle checks, not for visual checks of the video.
- The latency proxy reads the same clock the app reads. It does not see display delay.
