# Final sweep notes: layout, wording and test follow-ups

Branch `pr/P57-i18n-sweep`, from `main` `4e94a55` (all interface strings already in the catalog).

All renders are headless Edge with a stubbed Tauri and a stubbed backend. They are not the Tauri window. The scripts are `batch.mjs` and `player.mjs` in `.work/p57-shots/` (copies of the W3b and W3a harnesses), `cmp.mjs` (which PNGs differ, and the box that holds the changed pixels) and `nums.py` (side column rectangles). `main/` holds the PNGs of `main`, `final/` those of this branch.

## Intended Traditional Chinese pixel changes

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

## English toolbar in the player

The minimum is the one the layout lane in `.claude/skills/verify/SKILL.md` states: 130 px at 1280 and 66 px at 960. English missed it at both widths.

| Path box width | 960 | 1280 |
|---|---|---|
| English, `main` | 41 | 87.7 |
| English, this branch | 91 | 161.7 |
| zh-TW, both | 77.1 | 152.6 |

In English only: the segmented control and the two import buttons have 7 px of side padding, the header's column gap at 1280 is 12 px (as it already was at 960), and both path placeholders start "Video path, e.g." instead of "Full path to the video, e.g.". The example path still shows that a full path is wanted. The header stays 51 px high. The lane itself needs the real window and was not run.

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

Not translated here. From reading the source and the earlier wave reports:

- The native file dialog's filter name `影片與音訊` (`app/src-tauri/src/lib.rs`), which "Choose files" opens in an English window.
- `FOUND_ELSEWHERE_MESSAGE` and `LOCAL_BUILD_MESSAGE` in `backend/manager/runtimes.py`.
- Backend errors shown as toasts after batch actions, a row's `last_error`, and the reasons for skipped files.
- Backend English that says "queue" beside UI that says "batch": `already in the queue as {id} ({state})` (`backend/core/queue_store.py`) and `the queue crashed`.

## Open points

- A refusal note in the models table's Actions cell is not capped. A long registry URL can widen the column by about 30 px at 960 (measured in the W2 verification).

## Final checks and renders

- `tsc` exit 0, vitest 656 passed in 71 files, `check:strings` 0 of 660, ruff and `ruff format --check` clean, pyright 0 errors. Full pytest once at Idle: 3147 passed, 8 skipped (run before a one-line type annotation fix in `tests/test_engines.py`; that file passed again after it, 48 tests).
- Nine mutants against the pinned behaviour, all killed (`.work/p57-mutate.py`).
- zh-TW, 152 renders at 960 and 1280: 36 PNGs equal `main`, 116 differ. For every one except `pip`, the box holding the changed pixels is inside the side column. `pip` also differs when `main` is rendered twice. Against the render taken after change 1, only `library-queue` (change 3) and `pip` differ. A control render with the three zh-TW rules removed was not run.
- The layout audit reports no new kind of finding in zh-TW, and no new batch-harness finding in English. The new English player findings are the play queue's long titles ending in an ellipsis; the player harness's English findings fell from 613 to 109.
- The Chinese and Japanese left in the English player renders is subtitle data in the cue editor.
- The wizard, models and settings screens were not re-rendered. The new CSS selects the side column, the library, the narrow batch row and the English toolbar (the app's only `header`).
