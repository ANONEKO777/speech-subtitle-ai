# Final sweep notes: layout, wording and test follow-ups

Branch `pr/P57-i18n-sweep`, from `main` `4e94a55` (all interface strings already in the catalog).

All renders are headless Edge with a stubbed Tauri and a stubbed backend. They are not the Tauri window. The scripts are `batch.mjs` and `player.mjs` in `.work/p57-shots/` (copies of the W3b and W3a harnesses), `cmp.mjs` (which PNGs differ, and the box that holds the changed pixels) and `nums.py` (side column rectangles). `main/` holds the PNGs of `main`, `final/` those of this branch.

## Intended Traditional Chinese pixel changes of the first round, against `main`

There are three. The first two fix defects that `main` has only in zh-TW; the third fixes one `main` has in both languages.

### 1. Side column head

`:root:lang(zh-Hant) .tabs button` has 6 px of side padding instead of 10.

| Export button, column edge | `main` | this branch |
|---|---|---|
| 960 (edge 948) | 883..967 | 855..939 |
| 1280 (edge 1268) | 1203..1287 | 1175..1259 |

### 2. Batch rows in the side column

The three one-column row rules lost their `:root:lang(en)` scope, so the language chip has its own line in every language.

| Narrowest file name, 960 and 1280 | `main` | this branch |
|---|---|---|
| 8 rows | 8 px | 174 px |
| 24 rows | 0 px | 148.6 px |

After both, no element is outside the column and the column does not scroll sideways (`main`: 4 outside on the Batch tab, 16 with the export menu open).

### 3. Library tab with a filled play queue

| `.side-body` scroll width in a 328 px column | `main` | this branch |
|---|---|---|
| zh-TW, 960 and 1280 | 671 | 328 |
| English, 960 and 1280 | 699 | 328 |

Root cause: `.library` and `.queue` are grids with an implicit `auto` column. The column grew to the width of the longest title in the play queue, which does not wrap, and every library card stretched with it. Both grids now use `minmax(0, 1fr)`, so the title's own ellipsis works.

## The toolbar in the player

Two earlier rounds failed verification here. The first measured Korean subtitles only. The second forbade the header to wrap and chose floors at fixed window widths. It measured 960 and 1280 px, and between 1151 and 1210 px the row was wider than the window. Both assumed that values picked at breakpoints can always keep the toolbar on one row. They cannot, because the room the row needs depends on what is in it: the language's name, the window language and the queue chip.

### How it works now

- Both blocks of the header, the import bar and the subtitle settings, give their least width as their flex basis. When the two leasts do not fit on one line, the browser moves the settings to a second row, where the names are whole. So the player toolbar cannot push the page sideways, whatever the names are.
- Every cell rendered at 960 px and wider is one row. The second row appears only below the app's minimum width.
- When the row is short, these give way in order: the path box down to its floor, the two sliders down to 34 px, the name in the switch's words, and last the name on the middle button.
- A name up to 5 em wide is never shortened (繁體中文, English, 日本語, Japanese, Português). A longer one keeps at least 3.5 em. "on top" (在上) stays whole.
- The path box floor is 66 px, and 130 px from a 1280 px window, in both window languages. The Traditional Chinese floors of 64.5 and 127.5 px are gone. The headless render needs 1.4 to 2.4 px for this from the sliders. The app's own window measured the usual toolbar above both floors, so it should not move there (not measured again).
- With the queue chip showing, the toolbar uses the narrow window's spacing (12 px between blocks, 8 px between the two settings groups, 6 px inside a control) in a window of any width.
- A shortened name ends in an ellipsis. The tooltips and accessible names keep the whole name, as before.

### What still depends on a pixel breakpoint

| Breakpoint | What it changes | If the content does not fit |
|---|---|---|
| 1150 px and under (from `main`) | the toolbar's words become tooltips, narrower spacing, shorter sliders | names shorten, then the settings wrap |
| 1280 px and over | the path box floor goes from 66 to 130 px | names shorten, then the settings wrap |
| control row narrower than 640 px (container query) | less space around the volume slider | not covered by the wrap |

The home and settings toolbar has no such fallback inside the import bar, because its pickers take the width of their label. The sweeps below show that it fits for every input they render, the invented 50-character name included. A much longer picker label is not covered.

### The layout proof

`sweep.mjs` in `.work/p57-fix2/h/` renders in chromium-headless-shell with a stubbed Tauri and a stubbed backend. It is not the Tauri window, and it is not in CI. It resizes one live page, narrowing for one language and widening for the next, and `report.mjs` exits 1 on any failing cell and 2 on any missing one.

A player cell fails on: a sideways scroll; anything outside the window or the header's padding; a clipped, wrapped, squeezed or overlapping control; a second row; a path box under its floor; a short name that is shortened; a name that is shortened while the path box, a slider or the settings block still has room; a shortened name with a wrong tooltip or accessible name; and a Traditional Chinese window with Traditional Chinese subtitles that is not whole between 1151 and 1279 px.

| Cells | Inputs | `422a635` | `3fbf455` | now |
|---|---|---|---|---|
| 8820 | every width 960 to 1400; both window languages; zh-TW, id, en, ja and the invented name; chip off and on | 4058 fail | 2465 fail | 0 |
| 1350 | all 14 languages and the invented one; 15 widths 960 to 2560; chip none, 5 items, `118/120` | 483 fail | 363 fail | 0 |
| 10584 | home screen, every width 960 to 1400; chip and experimental labels off and on | not run | not run | 0 |
| 4320 | home and settings, every video language and subtitle target, 15 widths | not run | not run | 0 |
| 1764 | control row, every width 960 to 1400; speeds 0.75 and 1.25; 10:12:03, -60.0 s, A-B loop | not run | not run | 0 |
| 120 | stress, 760 to 940 px: the settings must wrap when one row cannot hold them, and nothing may overflow | not run | not run | 0 |

Of the 8820 cells, 694 of `3fbf455` scroll sideways, up to 1210 px with the chip on. `422a635` takes two or three rows instead.

Where a name is shortened now, in px of window width (every-width cells; the invented name is left out):

| Window / subtitles | chip off | chip on |
|---|---|---|
| zh-TW / zh-TW, en, ja | never | never |
| zh-TW / id | 960-962, 1151-1209 | 960-998, 1151-1187 |
| English / zh-TW | 1151-1215 | 960-992, 1151-1217, 1280-1281 |
| English / id, en, ja | never | never |

`other.mjs` checks the library cards and the licenses table: none of 48 cells fails at 960, 1100, 1151, 1181, 1280 and 1920 px.

### Mutants

| Mutant | Killed by |
|---|---|
| `CutName` never measures again when the name changes | vitest |
| a name short by up to 12 px is not treated as shortened | vitest |
| every name may shrink, short ones too | vitest |
| the words around a name are not kept | vitest |
| the Traditional Chinese floor goes back under 66 px | vitest (CSS text) |
| the 130 px floor starts at 1151 px again | vitest (CSS text), matrix |
| a name takes its whole width even when it may shrink | vitest (CSS text) |
| a later, stronger rule removes the path box floor | matrix, 59 of 100 cells. vitest does not see it |
| a later, stronger rule forbids the toolbar to wrap | stress matrix, 96 of 120 cells. vitest does not see it |
| a later rule makes the toolbar wrap while there is room | matrix, 59 of 100 |
| a later rule makes the settings wrap inside | matrix, 59 of 100 |
| the import bar gives up its room last | matrix, 40 of 100 |
| the chip's spacing is removed | matrix, 8 of 100 |

The unmutated page passes the same 100 cells.

### Other layout defects fixed in the second round

- **Pickers.** On the home and settings screens, the fixed width of the subtitle language picker cut "Bahasa Indonesia" in a Traditional Chinese window, "Traditional Chinese (experimental)" in an English one, and most experimental names in Chinese. The old widths are now minimums (`field-sizing: content`).
- **Control row at 960.** The button row was 9 to 23 px wider than its box at every speed, in both languages. The controls grid grew with it, so the total time and the last button left the picture at some speeds. Only the volume slider gives way now; its narrowest in the matrix is 49 px.
- **Library titles.** The 28 px that keeps a title clear of the add button was English only.
- **Licenses table.** The links cell was a flex box, so its divider sat up to 20 px above the others, in both window languages.

The English toolbar keeps 7 px of side padding on the segmented control and the import buttons, a 12 px column gap, and path placeholders that start "Video path, e.g.".

### Traditional Chinese pixel changes, against `422a635`

No catalog file changed, and the visible text of the 194 screens that save it is the same as on `422a635`. The screen harnesses render 268 PNGs, all in chromium-headless-shell (`run-px.ps1`, `pxsum.py`). Two renders of `422a635` differ on 70 of them: 66 specks of 64 px or less at anti-aliased corners, and the picture-in-picture and self-test spinner frames. A difference above that is counted as real.

| Compared | Real differences |
|---|---|
| `422a635` with itself | 0 |
| head with `422a635` | 61 |
| head with `3fbf455` (the third round alone) | 14 |
| control: head with the third round's three rules reverted (chip spacing, 34 px slider, no 64.5 and 127.5 px floors), with `3fbf455` | 0 |
| control: head with the second round's four fixes reverted (control row, library titles, licenses table, pickers), with `422a635` | the same 14 toolbar screens, and `home-960` at 67 px |

`home-960` in the last row is anti-aliasing at corners (no pixel off by more than 15 of 255).

| PNGs | Screens | Cause |
|---|---|---|
| 14 | player toolbar with Traditional Chinese subtitles: the batch harness's side column screens (queue chip showing) and `playing` | third round: floors of 66 and 130 px, and the chip's spacing |
| 33 | screens that show the player at 960 | control row |
| 2 | library in the side column at 1280 | library titles |
| 4 | licenses, Windows and Mac wording | licenses table |
| 8 | home and importing with a Korean or Indonesian picker | pickers |

The second round's separate toolbar-only render set was not repeated. The matrix covers those toolbars.

## Wording

| Key | New English | zh-TW (unchanged) |
|---|---|---|
| `batch.warn.sleep.body` | When the batch finishes, the computer first counts down 60 seconds, and you can press Cancel to stop the countdown. If you don't cancel, the computer goes to sleep, and nothing is processed while it sleeps. | 佇列跑完後，電腦會先倒數 60 秒，可以按「取消」阻止；沒有取消就會進入睡眠，睡眠期間不會有任何處理。 |
| `batch.warn.shutdown.body` | When the batch finishes, the computer first counts down 60 seconds, and you can press Cancel to stop the countdown. If you don't cancel, the computer shuts down, and any unsaved work is lost. | 佇列跑完後，電腦會先倒數 60 秒，可以按「取消」阻止；沒有取消就會關機，未儲存的資料會遺失。 |
| `batch.etaLater` | Time left appears after the first item finishes | unchanged |
| `editor.busy` | A job is using this project, so your change can't be saved right now ({reason}) | unchanged |
| `editor.tooLong` (optional item) | {seconds} s is over the 7-second limit | unchanged |

Not taken: the optional `app.batch` and `app.batchTitle` rewording ("Add to batch"). `app.batch` sits in the toolbar's icon row, and this sweep needed that row narrower.

## Tests

- The English armed text, warning, consent and countdown cancel button are each pinned for sleep and for shutdown.
- A table pins all seven cue problem codes of the backend to their message in both languages.
- A refused action's note in the models table must not carry `job-failure`, the class that stops a long note widening the Actions column.
- The five screens tests share `app/src/i18n/notEnglish.ts`, which refuses Thai, Hangul, kana, Han and full-width characters. `notEnglish.test.ts` holds it to that.
- `test_timeout_kills_the_child_and_says_so`: the 0.5 s also covered the fake child's startup. The test now returns from `Popen` only after the child has written its pid file. The engine sets its deadline after `Popen`, so the 0.5 s and every assertion are unchanged.
- `test_a_batch_runs_in_order_one_at_a_time_and_each_item_ends_done`: the runner could start the first item before the add reply was built. The test pauses while adding, then resumes, and still asserts all three are `queued`.

Both races were forced (a 0.005 s timeout, and a 0.4 s sleep after `queue.add`): `main`'s tests both fail, the new ones both pass. They passed 20 of 20 runs, and once with 32 busy loops on 16 threads.

## Backend and shell text still in Chinese or in the wrong words (W4)

**This list is superseded.** It was incomplete, and W4a has since translated the Chinese text. The current list is "English backend and shell messages the window can show" in `docs/i18n-notes/w4a.md` (branch `pr/P60-i18n-w4a`). The old list stays below as a record.

Not translated here. From reading the source and the earlier wave reports:

- The native file dialog's filter name `影片與音訊` (`app/src-tauri/src/lib.rs`), which "Choose files" opens in an English window.
- `FOUND_ELSEWHERE_MESSAGE` and `LOCAL_BUILD_MESSAGE` in `backend/manager/runtimes.py`.
- Backend errors shown as toasts after batch actions, a row's `last_error`, and the reasons for skipped files.
- Backend English that says "queue" beside UI that says "batch": `already in the queue as {id} ({state})` (`backend/core/queue_store.py`) and `the queue crashed`.

## Open points

- The Traditional Chinese floors now rest on the app's own window reading the usual toolbar 2.6 to 3 px wider than the headless render (67.2 and 130.6 px). The verifier measured that on `3fbf455` at a device pixel ratio of 1.1458. The real window was not run on this head, and not at another ratio.
- The chip's narrower spacing applies at every width. The sweep needs it only just above 1150 px: in a coarse run without it, and with 36 px sliders, the chip-on toolbar took a second row at 1151 and 1152 px, and none at its next widths from 1181 px up. (That run also had second rows at 960 px, where the spacing is narrow already. The 34 px slider closed those.) From 1280 px it moves Traditional Chinese pixels that did not have to move, and gives long names and the path box more room.
- At 960 px the path box shows about "Video path," or 影片的完整, and the switch's words are in its tooltip only, as before this round.
- `field-sizing` was not tried on macOS. An engine without it makes the subtitle language picker as wide as its longest option.

- A refusal note in the models table's Actions cell is not capped. A long registry URL can widen the column by about 30 px at 960 (measured in the W2 verification).

## Final checks and renders

### Third round

- `tsc` exit 0, vitest 679 passed in 73 files, `check:strings` 0 of 660. No Python or Rust file changed, so ruff, pyright, pytest and cargo tests were not run.
- Renders ran only through `gdi-run.ps1`, with the ledger in `.work/p57-fix2/runs`.
- Not run: the real Tauri window and so no `app/e2e` window lane, `/verify` (it drives that window), macOS, WKWebView, CI, a device pixel ratio other than 1, keyboard focus order.

### Second round

- `tsc` exit 0, vitest 671 passed in 73 files, `check:strings` 0 of 660. Its renders used installed Edge, at 960 and 1280 px only.

### First round

- `tsc` exit 0, vitest 656 passed in 71 files, `check:strings` 0 of 660, ruff and `ruff format --check` clean, pyright 0 errors. Full pytest once at Idle: 3147 passed, 8 skipped (run before a one-line type annotation fix in `tests/test_engines.py`; that file passed again after it, 48 tests).
- Nine mutants against the pinned behaviour, all killed (`.work/p57-mutate.py`).
- zh-TW, 152 renders at 960 and 1280: 36 PNGs equal `main`, 116 differ. For every one except `pip`, the box holding the changed pixels is inside the side column. `pip` also differs when `main` is rendered twice. Against the render taken after change 1, only `library-queue` (change 3) and `pip` differ. A control render with the three zh-TW rules removed was not run.
- The layout audit reports no new kind of finding in zh-TW, and no new batch-harness finding in English. The new English player findings are the play queue's long titles ending in an ellipsis; the player harness's English findings fell from 613 to 109.
- The Chinese and Japanese left in the English player renders is subtitle data in the cue editor.
- The wizard, models and settings screens were not re-rendered. The new CSS selects the side column, the library, the narrow batch row and the English toolbar (the app's only `header`).
