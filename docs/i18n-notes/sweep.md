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

**An earlier version of these notes said the English toolbar was fixed, with 91 px at 960 and 161.7 px at 1280. That held for Korean subtitles only**, the one language the harness played. With Traditional Chinese, the usual choice, the toolbar still wrapped at 1280 and left the box 25.3 px at 960. A Traditional Chinese window had the same failure with Indonesian, Portuguese and Vietnamese. The box's width depends on the length of the playing language's name, which the toolbar shows twice.

### How it works now

- The player's header cannot wrap.
- The path box has a floor of 66 px, or 130 px in a window over 1150 px wide.
- When the row is short, the import bar gives up its spare width first. The two sliders and the name inside "{name} on top" follow, and the name on the middle button is last.
- A shortened name ends in an ellipsis and keeps at least 3.5em. "on top" (在上) always stays whole.
- The middle button gets a tooltip with the full name while it is shortened. The switch's tooltip already held the whole sentence. Both accessible names are the same as before.
- No rule names a language, so a name of any length works. The matrix includes an invented language with a 50-character name.
- While the name fits, the switch's words are one plain text, as before. Only a shortened name is laid out in pieces. A screen reader would read the pieces with a gap in `在上`, so the switch then carries its whole sentence as `aria-label`.

### The Traditional Chinese floor

The layout lane in `.claude/skills/verify/SKILL.md` asks for 66 and 130 px. In the headless render, the Traditional Chinese window that plays Chinese reads 64.6 and 127.6 px, on `main` too. The cause is the render, not the stylesheet. The P26b build (`4ddc208`), which the app's own window measured at 67.2 and 130.6 px (`.work/p26b/fix2/layout-run.txt`), reads 64.6 and 127.6 px in the same headless render at pixel ratios 1, 1.25 and 1.5. So a Traditional Chinese window has floors of 64.5 and 127.5 px, which leaves that toolbar where it was. Every Traditional Chinese player toolbar is therefore at least as wide in the box as that one. English floors are 66 and 130 px in the headless render. The lane itself needs the real window and was not run.

### Path box in the player, with the batch chip showing, in px

An asterisk marks a shortened name. "2 rows" means that the toolbar wrapped.

| Playing | en 960: `422a635`, now | en 1280: `422a635`, now | zh-TW 960: `422a635`, now | zh-TW 1280: `422a635`, now |
|---|---|---|---|---|
| zh-TW | 25.3, 66* | 2 rows, 130* | 64.6, 64.6 | 127.6, 127.6 |
| zh-CN | 28.2, 66* | 2 rows, 130* | 64.6, 64.6 | 127.6, 127.6 |
| en | 90.4, 90.4 | 160.5, 160.5 | 75.4, 75.4 | 149.2, 149.2 |
| ja | 79.6, 79.6 | 138.9, 138.9 | 77.1, 77.1 | 152.6, 152.6 |
| ko | 91, 91 | 161.7, 161.7 | 77.1, 77.1 | 152.6, 152.6 |
| es | 86.8, 86.8 | 153.2, 153.2 | 71.8, 71.8 | 142.1, 142.1 |
| fr | 92.7, 92.7 | 165, 165 | 70.2, 70.2 | 138.9, 138.9 |
| de | 85.9, 85.9 | 151.5, 151.5 | 69.8, 69.8 | 138.1, 138.1 |
| pt | 67.3, 67.3 | 114.2, 130 | 58.8, 64.5* | 116, 127.5 |
| it | 96.2, 96.2 | 172, 172 | 73.8, 73.8 | 146.1, 146.1 |
| ru | 88, 88 | 155.6, 155.6 | 69.3, 69.3 | 136.9, 136.9 |
| vi | 65.4, 66* | 110.6, 130 | 59, 64.5* | 116.5, 127.5 |
| th | 106.6, 106.6 | 192.8, 192.8 | 92, 92 | 182.4, 182.4 |
| id | 69.1, 69.1 | 117.9, 130 | 19.2, 64.5* | 2 rows, 127.5* |
| invented, 50 characters | 2 rows, 604.5, 66* | 2 rows, 130* | 2 rows, 600, 64.5* | 2 rows, 127.5* |

### The layout proof

`matrix.mjs` in `.work/p57-fix-scratch/h/` renders every combination below in headless Edge with a stubbed Tauri and a stubbed backend, and exits 1 on any failure. It is not the Tauri window, and it is not in CI. `e2e/toolbar-css.test.mjs` is in CI and only pins the rules by their text.

- Header, 3040 cells: both window languages; 960 and 1280 px; the batch chip absent, with 5 items, paused, at `0/120` and at `118/120`; experimental targets off and on. For each: the home and settings screens with every video language and every target it offers (the 14 languages and the invented one, without the video's own), a very long path in the box, the player with each of those 15, and the player of a mixed Japanese and English video.
- Control row, 336 cells: both window languages; 960 and 1280 px; all seven speeds; videos of 2:10, 1:02:03 and 10:12:03; offsets of `+0.0 s` and `-60.0 s`; with and without an A-B loop.
- Checks: one row, the header height, the path box floor, no clipped, wrapped or squeezed control, no cut picker label, nothing overlapping or outside its block or the window, a tooltip and whole accessible names for a shortened name, and no two languages that shorten to the same letters.

| Failing cells | `422a635` | now |
|---|---|---|
| Header | 840 of 3040 | 0 |
| Control row | 168 of 336 | 0 |

Both columns come from the same script and the same floors. With 66 and 130 px for the Traditional Chinese window too, `422a635` fails 900 header cells.

`other.mjs` checks the library cards and the licenses table the same way: 8 of 16 cells failed on `422a635`, and none fails now.

### Other layout defects fixed in the same round

- **Pickers.** On the home and settings screens, the fixed width of the subtitle language picker cut "Bahasa Indonesia" in a Traditional Chinese window, "Traditional Chinese (experimental)" in an English one, and most experimental names in Chinese. The old widths are now minimums (`field-sizing: content`).
- **Control row at 960.** The button row was 9 to 23 px wider than its box at every speed, in both languages. The controls grid grew with it, so the total time and the last button left the picture at some speeds. Only the volume slider gives way now; its narrowest in the matrix is 49 px.
- **Library titles.** The 28 px that keeps a title clear of the add button was English only.
- **Licenses table.** The links cell was a flex box, so its divider sat up to 20 px above the others, in both window languages.

The English toolbar keeps 7 px of side padding on the segmented control and the import buttons, a 12 px column gap, and path placeholders that start "Video path, e.g.".

### Traditional Chinese pixel changes of the fix round, against `422a635`

No catalog file changed. `pixels.sh` renders every screen harness (268 PNGs) and `tbpx.mjs` renders the toolbar alone for every target (584 PNGs). `control.py` reverses a fix's commit on top of the head and renders again.

Screen harnesses: 209 PNGs equal `422a635` and 59 differ.

| PNGs | Screens | Rule |
|---|---|---|
| 37 | screens that show the player at 960 | control row |
| 3 | library in the side column at 960 | control row and library titles together |
| 3 | library in the side column at 1280 | library titles |
| 4 | licenses, Windows and Mac wording | licenses table |
| 8 | home and importing with a Korean (experimental) or Indonesian picker | pickers |
| 4 | `pip` and the wizard's self-test spinner | none: these change between two renders of one build |

With those four rules reversed together, 266 of 268 PNGs return to the old hash. The other two are one `pip` and one spinner PNG. With one rule reversed at a time, the PNGs of each row that names a rule return under that rule, except the three screens that show two.

Toolbar alone: 312 PNGs equal `422a635` and 272 differ.

- **Player, 32 PNGs:** only the toolbars that were broken: Indonesian, Portuguese, Vietnamese and the invented language. The toolbar with every other target, the usual one included, is byte for byte the same.
- **Home and settings, 240 PNGs:** only pickers that grew. Not experimental: Indonesian (92 to 125 px) and the invented language. Experimental: every language but Thai (128 px to between 130 and 188 px, and 359 px for the invented one).
- By the browser's own measure all of those lacked room. With Japanese, Korean (130 px), English (132 px) and Italian (133 px) only the blank half of the closing full-width bracket was lost, so those four looked whole before. The others lost ink.
- With the pickers and the toolbar rules reversed, all 584 return to the old hash. With only the pickers reversed, exactly the 32 player PNGs still differ.

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

- The Traditional Chinese player floors (64.5 and 127.5 px) rest on the headless render reading 2.6 to 3 px under the real window. That was measured on the P26b build. It was not measured again in the real window on this branch.
- `field-sizing` was not tried on macOS. An engine without it makes the subtitle language picker as wide as its longest option.

- A refusal note in the models table's Actions cell is not capped. A long registry URL can widen the column by about 30 px at 960 (measured in the W2 verification).

## Final checks and renders

### Fix round

- `tsc` exit 0, vitest 671 passed in 73 files, `check:strings` 0 of 660. No Python file changed, and no test in `tests/` reads a changed file, so ruff, pyright and pytest were not run again.
- Twelve mutants against the new guard tests, all killed (`.work/p57-fix-scratch/h/mutate.py`). They include removing the whole player toolbar CSS block, and removing the English toolbar block, the mutant that survived the first round's verification.
- Not run: the real Tauri window, so no `app/e2e` window lane (`layout` and `p24b-chip` among them), macOS, WKWebView, widths other than 960 and 1280, CI.

### First round

- `tsc` exit 0, vitest 656 passed in 71 files, `check:strings` 0 of 660, ruff and `ruff format --check` clean, pyright 0 errors. Full pytest once at Idle: 3147 passed, 8 skipped (run before a one-line type annotation fix in `tests/test_engines.py`; that file passed again after it, 48 tests).
- Nine mutants against the pinned behaviour, all killed (`.work/p57-mutate.py`).
- zh-TW, 152 renders at 960 and 1280: 36 PNGs equal `main`, 116 differ. For every one except `pip`, the box holding the changed pixels is inside the side column. `pip` also differs when `main` is rendered twice. Against the render taken after change 1, only `library-queue` (change 3) and `pip` differ. A control render with the three zh-TW rules removed was not run.
- The layout audit reports no new kind of finding in zh-TW, and no new batch-harness finding in English. The new English player findings are the play queue's long titles ending in an ellipsis; the player harness's English findings fell from 613 to 109.
- The Chinese and Japanese left in the English player renders is subtitle data in the cue editor.
- The wizard, models and settings screens were not re-rendered. The new CSS selects the side column, the library, the narrow batch row and the English toolbar (the app's only `header`).
