# W3b notes: the batch, the editor, export and the summary

Branch `pr/P56-i18n-w3b`, from `main` `2efa598` (W1 and W1b), with `main` `e4a2b12` (W3a) merged in. The batch queue (`app/src/batch/**`), the cue editor (`app/src/editor/**`), the export menu (`app/src/export/**`) and the summary view (`app/src/summary/**`) read the catalog. zh-TW is the old text, character for character. English is written by hand. `zh-CN` and `ja` are machine translations, marked in their file headers, hidden from the picker.

## What was built

- Catalog areas `batch`, `editor`, `export` and `summary` (`catalog/<locale>/<area>.ts`), 95 keys. The queue's step names reuse `progress.step.*` (the progress screen's words) and add `batch.step.translate`. The video and subtitle language labels reuse `import.source` and `import.targetAria`. Cancel and Close reuse `common.*`.
- Plural keys: `batch.countdown.sleepAfter` and `batch.countdown.shutdownAfter` ("in 1 second.", "in 42 seconds.").
- Text that a helper returns takes a translator: `validateDraft(..., t)` (zh-TW by default), `formatEta(..., t)`. `BACKEND_PROBLEM` maps the backend's cue problem codes to keys. `ExportItem.label` is `(t) => string`, so `Player.tsx` calls `exportItems` as before. A missing summary throws `NoSummary` and the menu words it.
- `batch/lang.ts` `langName(code, languages, locale)` is the one place the batch calls `languageName`. `TargetChoice` and the queue rows use it, so language names follow the window language.
- Deleted with their last caller: `SOURCE_NOTES` (`api/sourceLang.ts`). The experimental-language constants and `JOB_RUNNING` went after the merge (see "After merging `main`").
- English CSS: `:root:lang(en) .batch-lang` wraps, so the Batch tab in the 340 px side column does not overflow (the chip "Japanese + English Korean Experimental" pushed the row past the column).
- Guard: all 119 literals of the area left the baseline.
- Tests: `batch/w3b.screens.test.tsx` renders 16 scenes in zh-TW and en. zh-TW equals `w3b.screens.zh-TW.fixture.json`, written by the same test on `main` (regenerated in a clean `main` checkout: identical bytes). English holds no CJK or full-width character. More tests check the English wording, the safety text and the live language switch.

## Decisions

- **"Batch" for the processing queue.** 佇列 is "batch" in English on every screen W3b owns, and W1's toolbar chip and toasts now say "Batch 2/7", "View batch", "3 items added to the batch", "Batch finished: 3 done". W3a's library keeps "Play queue" (播放佇列). "Queue" next to "Play queue" reads as the same list; "Batch" never does, and it matches the toolbar button "Batch add". zh-TW is unchanged. The player's tab says "Batch" too.
- **The export menu.** Entries are "SRT (original)", "SRT (Traditional Chinese)", "SRT (bilingual)", "ASS (bilingual)", "VTT (bilingual)", "Summary (summary.md)". Format and file names are unchanged. With W3a merged the open menu measures 267 px wide, inside the side column at 960 (column 608 to 948, menu 672 to 939) and at 1280 (928 to 1268, menu 992 to 1259), and no entry is clipped.
- **Undo and refusal messages** are worded when they happen. A refusal on screen stays in the language it was written in until the next save or undo; the client-side checks (`validate`) follow a language switch at once.

## Safety text (English next to the Chinese, for the reviewer)

| zh-TW | English |
|---|---|
| 佇列全部完成後 | When the batch finishes |
| 只通知我（預設） / 讓電腦睡眠 / 關機 | Just notify me (default) / Put the computer to sleep / Shut down |
| 已啟用：全部完成後會讓電腦睡眠，之前有 60 秒倒數可以取消。 | On: when everything is done, the computer goes to sleep after a 60-second countdown you can cancel. |
| 已啟用：全部完成後會關機，之前有 60 秒倒數可以取消。 | On: when everything is done, the computer shuts down after a 60-second countdown you can cancel. |
| 睡眠會中斷電腦上的其他工作。 | Sleep interrupts everything else running on the computer. |
| 關機會中斷電腦上的其他工作。 | Shutting down interrupts everything else running on the computer. |
| 佇列跑完後，電腦會先倒數 60 秒，可以按「取消」阻止；沒有取消就會進入睡眠，睡眠期間不會有任何處理。 | When the batch finishes, the computer first counts down 60 seconds, and you can press Cancel to stop it. If you don't, it goes to sleep, and nothing is processed while it sleeps. |
| 佇列跑完後，電腦會先倒數 60 秒，可以按「取消」阻止；沒有取消就會關機，未儲存的資料會遺失。 | When the batch finishes, the computer first counts down 60 seconds, and you can press Cancel to stop it. If you don't, it shuts down, and any unsaved work is lost. |
| 我了解，並同意佇列完成後睡眠 / 關機 | I understand, and I agree to put the computer to sleep / shut down the computer when the batch finishes |
| 啟用 | Turn on |
| 佇列已全部完成 | Batch finished |
| 電腦將在 42 秒後進入睡眠。 / 關機。 | The computer will go to sleep in 42 seconds. / The computer will shut down in 42 seconds. |
| 取消，不要睡眠 / 取消，不要關機 | Cancel, don't sleep / Cancel, don't shut down |

The English body of the warning starts with a space (`batch.warn.*.body`), because the bold sentence before it is a separate element and zh-TW has no space there.

## Backend or other text on W3b screens (not translated here)

- A queue item's `last_error` (the processing error), the backend's reason for a skipped file in the batch dialog, and the error when adding to the batch fails.
- The text after "Export failed:" (the shell's save error), the backend's message for a cue problem code the frontend does not know, the text in brackets after "Can't reach the backend (...)" and "A job is using this project ... (...)".
- File names and paths, the subtitle text, the summary text and its chapter titles (data).
- A language the catalog has no `lang.*` key for falls back to the backend's name.

## After merging `main` (W3a)

Done on this branch after W3a reached `main` (`e4a2b12`).

- `batch/lang.ts` `langName` calls `languageName(locale, language)` with the whole record, so English falls back to the backend's English name.
- `EXPERIMENTAL`, `EXPERIMENTAL_HINT` and `JOB_RUNNING` are deleted. Their tests read the catalog.
- `player.tab.queue` says "Batch".
- Guard: `check:strings` 137 of 660. All 137 are in `models-page` and `wizard` (W2).
- Tests added: the add-a-language menu and the batch target list say "Spanish" (and fall back to the backend's English name), the four player tabs read "Subtitles", "Summary", "Library", "Batch", and the English check also refuses Thai and Hangul jamo.

## English layout fixes on the merged head

All scoped to `:root:lang(en)`. The zh-TW PNGs equal `main`'s on every rendered screen.

- In the one-column queue row (the side column), the language chip took the file name's width: the name was 0 px wide on the rows with a video language tag. In English the chip now has its own line, and the name is at least 164 px.
- In the same column the "When the batch finishes" label wrapped and squeezed its select. In English the select now goes under the label.
- In the wide row (the home panel), "Processing" plus "Recognizing speech (3/7)" did not fit the 150 px status column. In English the step now has its own line under the state.

## Renders

Edge with a stubbed Tauri and backend, not the Tauri window. The script is `.work/p56-shots/shots.mjs` and the PNGs are in `.work/p56-shots/final/`. The script turns the backdrop blur off, because the blur changed pixel values by 1 from run to run.

## Open points

- `main` has a zh-TW layout defect that this branch does not change, because zh-TW pixels must stay equal to `main`'s: in the side column the 匯出 button reaches past the column's right edge (967 px against 948 px at 960, 1287 px against 1268 px at 1280). The English side column has nothing outside its rectangle.
- In zh-TW the file name of a running mixed-language row is about one character wide in the side column. `main` has the same. The full path is in the tooltip.
- Long file names ellipsize in both languages. The full path is in the tooltip.
