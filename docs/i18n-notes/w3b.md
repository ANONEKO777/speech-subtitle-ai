# W3b notes: the batch, the editor, export and the summary

Branch `pr/P56-i18n-w3b`, from `main` `2efa598` (W1 and W1b). The batch queue (`app/src/batch/**`), the cue editor (`app/src/editor/**`), the export menu (`app/src/export/**`) and the summary view (`app/src/summary/**`) read the catalog. zh-TW is the old text, character for character. English is written by hand. `zh-CN` and `ja` are machine translations, marked in their file headers, hidden from the picker.

## What was built

- Catalog areas `batch`, `editor`, `export` and `summary` (`catalog/<locale>/<area>.ts`), 95 keys. The queue's step names reuse `progress.step.*` (the progress screen's words) and add `batch.step.translate`. The video and subtitle language labels reuse `import.source` and `import.targetAria`. Cancel and Close reuse `common.*`.
- Plural keys: `batch.countdown.sleepAfter` and `batch.countdown.shutdownAfter` ("in 1 second.", "in 42 seconds.").
- Text that a helper returns takes a translator: `validateDraft(..., t)` (zh-TW by default), `formatEta(..., t)`. `BACKEND_PROBLEM` maps the backend's cue problem codes to keys. `ExportItem.label` is `(t) => string`, so `Player.tsx` calls `exportItems` as before. A missing summary throws `NoSummary` and the menu words it.
- `batch/lang.ts` `langName(code, languages, locale)` is the one place the batch calls `languageName`. `TargetChoice` and the queue rows use it, so language names follow the window language.
- Deleted with their last caller: `SOURCE_NOTES` (`api/sourceLang.ts`). `EXPERIMENTAL` and `EXPERIMENTAL_HINT` (`api/targets.ts`) are no longer read by W3b, but `player/AddTarget.tsx` and `player/SidePanel.tsx` (W3a) still read them on `main`, so they go after both merges (see "After the merge").
- English CSS: `:root:lang(en) .batch-lang` wraps, so the Batch tab in the 340 px side column does not overflow (the chip "Japanese + English Korean Experimental" pushed the row past the column).
- Guard: `check:strings` 388 to 269 (all 119 literals of the area).
- Tests: `batch/w3b.screens.test.tsx` renders 16 scenes in zh-TW and en. zh-TW equals `w3b.screens.zh-TW.fixture.json`, written by the same test on `main` (regenerated in a clean `main` checkout: identical bytes). English holds no CJK or full-width character. More tests check the English wording, the safety text and the live language switch.

## Decisions

- **"Batch" for the processing queue.** 佇列 is "batch" in English on every screen W3b owns, and W1's toolbar chip and toasts now say "Batch 2/7", "View batch", "3 items added to the batch", "Batch finished: 3 done". W3a's library keeps "Play queue" (播放佇列). "Queue" next to "Play queue" reads as the same list; "Batch" never does, and it matches the toolbar button "Batch add". zh-TW is unchanged. The player's tab key `player.tab.queue` is W3a's and must say "Batch" after the merge.
- **The export menu.** Entries are "SRT (original)", "SRT (Traditional Chinese)", "SRT (bilingual)", "ASS (bilingual)", "VTT (bilingual)", "Summary (summary.md)". Format and file names are unchanged. In a merge of W3a and W3b the open menu measures 267 px wide, inside the side column at 960 (column 608 to 948, menu 672 to 939) and at 1280 (928 to 1268, menu 992 to 1259), and no entry is clipped.
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

## After the merge (the root, when W3a and W3b are both on `main`)

`.work/p56-post-merge.patch` (made on a scratch merge of `main`, P55 `dfa29c0` and P56, where `tsc` passes and 566 vitest tests pass):

1. `batch/lang.ts` calls W3a's `languageName(locale, language)` (one line), and passes `name` so English can fall back to the backend's English name.
2. `EXPERIMENTAL` and `EXPERIMENTAL_HINT` are deleted from `api/targets.ts`, and the three tests that read `EXPERIMENTAL_HINT` read `tZhTW("targets.experimentalHint")`.
3. `player.tab.queue` in `catalog/en/player.ts` says "Batch".

The merge itself conflicts only at the shared edges: the four `catalog/<locale>/index.ts` (keep both spreads), `app/i18n-baseline.json` (take `main`'s and run `npm run check:strings -- --update`: 137 after both), and `docs/i18n-glossary.md` (keep both sections).

## Open points

- At 960 px the queue row's file name is short in the side column in both languages (zh-TW on `main` too). It ellipsizes and the full path is in its tooltip.
- In the Edge renders the modal screens (countdown, batch dialog) differ from run to run by a few pixels of value 1 under the backdrop blur, on `main` as well.
