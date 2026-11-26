# W3a notes: the player

Branch `pr/P55-i18n-w3a`. The player (`app/src/player/**`) reads the catalog. zh-TW is the old text, character for character. English is written by hand. `zh-CN` and `ja` are machine translations, marked in their file headers, hidden from the picker.

## What was built

- `catalog/<locale>/player.ts`, 116 keys named `player.*`: the control bar and its tooltips, the speed, offset and more menus, the help overlay and its 18 shortcut descriptions, the on-screen lines (volume, speed, frame, A-B loop, subtitle timing, jump to subtitle), the toasts, the burn-in card and its two menu entries, the side column (tabs, undo, language row, failure note, footer), the cue list, the add-a-language menu and the library (home screen and side tab).
- Plural keys: `player.foot.edited` and `player.failedNote`. `everyPluralHasBothForms` covers them.
- `shortcuts.ts`: a row is `{ keys, what }` where `what` is a catalog key (`PlainKey`). The key caps (Space, Ctrl, Shift, arrows) are not translated.
- `failures.ts`: `failureSummary` and `failureTitle` take the translator last and default to zh-TW, as in W1.
- `useTransport` calls `useT()` itself, so its on-screen lines follow the window language. `useIdle` and its tests are untouched.
- `player/langName.ts` (`languageLabel`): an English window shows the backend's English language name (`name`, region in brackets removed), the other languages show `nativeName`. It is used by the side column, the add-a-language menu, the export labels' language and, with one line in `App.tsx`, the library's language chips. It falls back to the code. W1b works on language names in the toolbar and the progress screen: the root should keep one helper (this one or W1b's) and point both at it.
- English CSS in `styles.css`, all scoped `:root:lang(en)`: the side column's tabs get a row of their own with undo and export under them (the four English tab names plus the two tools are wider than the 340 px column), the folder row of the more menu gets room for its path, and the library title of the one-column list leaves room for the add-to-queue button.
- Guard: `check:strings` 388 to 256 (all 132 player literals gone, baseline lowered in the same commit).
- Tests: `player/w3a.screens.test.tsx` renders the player in 11 scenes in both languages (control bar and menus, options, help, on-screen lines, toasts, burn-in, burn card, unplayable video, side column, other tabs, library). zh-TW equals `w3a.screens.zh-TW.fixture.json`, written by running the same test on `main`. English must hold no CJK or full-width character. Two more tests check English wording and the live language switch.

## Decisions

- **Keyboard modifiers.** The app has no platform source for the web layer (`isMac` exists only for the hardware profile). The player handles `Ctrl+Left/Right` only with Ctrl (`keyAction` rejects Meta), and `Ctrl+Z` or `Cmd+Z` both undo. The tooltips and the help overlay say Ctrl, which is correct on every platform, so nothing became platform-aware.
- **Numbers and times.** The player formats `m:ss`, `+0.1 s` and a percent by hand, with a dot as decimal separator, which every released and hidden locale uses. No `Intl` call was needed.
- **"Subtitle", never "line".** The Chinese counters 句, 則 and 條 become "subtitle" (`Subtitle 12`, `2 subtitles failed`). See the glossary section W3a.
- **"Play queue" and "queue".** 播放佇列 is "play queue" (library), 佇列 is "Queue" (the tab of the processing queue). The library button reads "Add all to play queue".
- `EXPERIMENTAL` and `EXPERIMENTAL_HINT` (`api/targets.ts`) stay: `batch/TargetChoice.tsx` and `batch/AddDialog.tsx` (W3b) still read them. The player now reads `t("targets.experimental")` and `t("targets.experimentalHint")`. W3b deletes the constants with its last caller.
- The failure note keeps the Chinese structure but its pieces are separate keys (`player.failedEmpty`, `player.failedEnglish`, `player.failedJoin`) so that a language with another word order only changes text.

## Backend, shell or other-wave text on the player screens (not translated here)

- Backend: the error of a failed screenshot, burn-in export or folder open (`e.message`, shown after "Screenshot failed:" and the like), the burn-in `error`, language names (`nativeName` in zh-TW, `name` in English), library titles (file names), the `notice` after an import (W1, from the catalog), `addBlocked` (W1 text).
- Browser or shell: the message of a refused picture-in-picture, full-screen or folder dialog.
- Subtitle text, the summary text and the cue text are data.
- W3b components inside the player: the Export menu button and its items (`export/ExportMenu.tsx`, `export/exports.ts` labels such as "SRT 原文"), the cue editor (`editor/CueEditor.tsx`), the summary view chrome (`summary/SummaryView.tsx`), the queue tab (`batch/*`). They stay Chinese in an English window until W3b merges. The screens test leaves only the Export button out of its harvest, because nothing else of W3b renders there.

## Open points

- `lib-card` in the one-column list has the add-to-queue button over the end of a long title in zh-TW too (main shows it). It is fixed for English only, to keep zh-TW pixels. The same two lines would fix zh-TW if the root wants it.
- The toolbar path field above the player shrinks to a few letters in English ("Full pat"), the W1 note about the width. It is W1b's.
