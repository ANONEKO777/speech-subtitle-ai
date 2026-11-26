# W4a notes: no Chinese from the backend or the shell

Branch `pr/P60-i18n-w4a`, from `422a635` (head of `pr/P57-i18n-sweep`). Every Chinese sentence that the Python backend or the Rust shell wrote for the window is now an English sentence with a code. The window words the code from its catalog. `zh-TW` is the old text, character for character.

## The data shape

A notice is `{ code, params, message }`. `message` is the complete English sentence. A parameter is a string or a list of strings. No sentence takes a count, so there are no number parameters.

The brief's recommended shape sends one notice for one message. The backend does not send messages that way. It sends them whole, with a prefix (`asr: …`, `OptionsError: …`), and nested in other sentences. The self-test report quotes the Visual C++ sentence up to four times. So each text field stays one English string, and a second field lists the notices inside it, outermost first. The window replaces every copy of each notice's `message` with its own wording. One rule covers a whole, a prefixed and a nested sentence, and a wrapper needs no code of its own.

| Channel | Text | Notices |
|---|---|---|
| any HTTP refusal | `detail` or `detail.message` | `notices`, beside `detail` |
| job state and the `failed` event | `error` | `error_notices` |
| `queue.db` and `/api/queue` | `last_error` | `last_error_notices` (new column) |
| project file and `/api/projects/{id}` | `steps.*.error` | `error_notices` (written only when not empty) |
| burn export | `error` | `error_notices` |
| `selftest.json` and the self-test routes | `message`, `fallback.reason`, `stages[].detail` | `message_notices`, `reason_notices`, `detail_notices` |
| shell command rejection and `backend-failed` | `message` | `notices` |
| a backend that stops before it is ready | its stderr | `VST_NOTICE {json}` lines, which the shell takes out of the output |

How a notice gets into a field without new plumbing:

- `noticed(ErrorType, TEMPLATE(...))` raises the error that the caller already handles.
- `notices_of(exc, text)` follows `__cause__` and `__context__`. A wrapper such as `OptionsError(str(exc)) from exc` therefore keeps the notice. A notice whose `message` is not in `text` is left out.
- One FastAPI handler (`noticed_http_error`) adds `notices` to every `HTTPException ... from exc`.

In the window, `i18n/said.ts` keeps the text and its notices as they came (`Said`), and `i18n/notice.ts` words it at render. A change of language therefore re-words a message that is on the screen. The fields that carry a `Said` have that type, so `tsc` finds a display site that prints one without wording it.

## The registry, and what fails when a mapping is missing

- `backend/core/notices.py` holds the 12 backend sentences. `python scripts/export_notices.py` writes `app/src/i18n/notices.backend.json`. `tests/test_notices.py` fails while they differ.
- `app/src-tauri/src/notice.rs` holds the 14 shell sentences. The `templates!` macro lists each one in `ALL`. A cargo test fails while `app/src/i18n/notices.shell.json` differs from the table.
- `app/src/i18n/notice.test.ts` fails when a code has no entry in one of the four catalogs, when the English entry differs from the sender's template, when the placeholders differ, or when a `notice.*` key has no sender.
- `tests/test_notices.py` also fails when a backend file outside the translation data holds Chinese, Japanese, Korean, Thai or full-width text, or when a Rust source file does.

To add a sentence (this is the W4b recipe): add a `Template` in `notices.py`, raise it with `noticed`, run the export script, add `notice.<code>` to the four catalogs, and add a scenario to `tests/notice_scenarios.py`. A test fails until the scenario exists.

## Proof that the Chinese did not change

`tests/notice_scenarios.py` raises every backend sentence the way the app raises it (20 scenarios, all 12 codes). It was run on a clean export of `422a635`, and that output is the `before` field of `notices.wire.fixture.json`. The vitest words what the new backend sends in `zh-TW` and requires `before` back. The 15 old shell sentences were read out of the Rust source of `422a635` (`notices.shell.before.json`).

## Renders

These are renders in headless Edge with a stubbed Tauri and a stubbed backend. They are not the Tauri window. The script is `.work/p60-shots/shots.mjs`. It renders 16 screens where a backend or shell sentence appears, at 960 and 1280: the wizard's self-test result, the fallback banner and the self-test panel on the hardware page, the import error screen, two batch rows, the screenshot and export toasts, two burn cards, two `backend-failed` screens, two update errors, the LLM save error and the delete dialog.

- Branch, `zh-TW` and English (64 renders): no element off screen, no clipped or cut text, no unreachable button, and no other script in an English message box.
- `422a635`, fed the old Chinese strings, against this branch, fed English with notices (32 `zh-TW` renders): all 32 PNG hashes are equal.

The self-test's own wrapper sentences are still English in both languages (item 2 of the list below). In English a nested sentence ends in `.;` or `..`, as the Chinese wrapper did with `。;` and `。.`.

## The real window

`.work/p60-verify/drive.mjs` drives a release build over CDP with disposable data. No model runs: the models and runtimes are one-byte files, and `VST_SIMULATE_NO_VCRUNTIME` stops the self-test before any program starts. It covers what the Edge stubs cannot: the shell's `backend-failed` payload, a rejection of a real update command, the argument names of the two file dialog commands, and a real backend's notices after a change of language. The native file dialog itself was not opened. All 13 checks passed. The operator's app was running during the run, and its processes were the same before and after.

## Checks

- `tsc` clean, vitest 755 passed in 73 files, `check:strings` 0 of 660.
- ruff and `ruff format --check` clean, pyright 0 errors, full pytest at Idle: 3175 passed, 8 skipped.
- `cargo test --locked` with `CARGO_TARGET_DIR` under `.work/p60-target`: 38 passed, 1 failed. The failure is `a_binary_built_in_this_crate_is_a_developer_build`, which requires the test binary to be under the crate's own `target` folder. CI builds there.
- `cargo clippy --all-targets -- -D warnings` is clean with two lints allowed, `enum_variant_names` and `items_after_test_module`. Both point at code this branch does not change. CI does not run clippy.
- 21 mutants (9 Python, 10 frontend, 2 Rust), all killed. Each check passes on the unchanged tree.

## Decisions

- **Language parameters** travel as codes. The font messages used the native name (`한국어`, `Русский`), and `lang.ko` and `lang.ru` in `zh-TW` hold the same text. English says "Korean".
- **Lists** (the fonts that were tried) travel as lists. `zh-TW` joins them with `、` and English with `, ` (`common.listSeparator`).
- **The file dialog's filter name** is not a message. The window passes it to `pick_video` and `pick_videos` (`filterName`). The dialog still runs in the shell, so a page script cannot forge a pick.
- **The command line** (`python -m backend.cli`) printed these sentences in Chinese and now prints them in English. The CLI has no language setting.
- **Downgrade.** An earlier build refuses a `project.json` step with a key it does not know. Only a step that failed with a notice has `error_notices`, so only such a project fails to open in an earlier build, until the step runs again. `queue.db` and `selftest.json` are read by earlier builds, which ignore the new column and keys.
- A queue that an earlier build wrote to after this one can hold notices of an older error beside a newer one. They do nothing, because a notice only replaces its own `message`.
- **Not translated:** the window title in `index.html` and `tauri.conf.json` (`字幕翻譯`) is static and shows until the page loads. Update notes from the manifest, file names, subtitle and summary text, and the output of other programs are data.

## English backend and shell messages the window can show (input to W4b)

A Chinese window shows these in English today. The order is by priority: how often a person is likely to see one. **The order is a judgment from reading the code, not a measurement.** "Ready" means the channel already carries notices, so W4b only adds codes. "Needs a field" means the sender of that field must also send a `_notices` list, and the parser must read it.

| # | Message | Sender | Where it shows | How often | Channel |
|---|---|---|---|---|---|
| 1 | Why this profile was chosen (a block of `Profile:`, `Why:`, `ASR:` lines and 8 reason sentences) | `manager/profiles.py` `describe`, `_REASON_TEXT` | Hardware page, "why" box | every visit that opens the box | needs a field (`recommended.why`) |
| 2 | Self-test wrapper sentences ("Self-test passed on CUDA.", "Self-test failed: …", "The GPU backend failed: … The CPU backend is used instead.", "GPU failed and the CPU runtime is not installed. …") and stage notes ("transcribed one second of silence", "llama-server starts", "exited with code N", "did not finish") | `manager/selftest.py` | Wizard result, hardware page, fallback banner | every first run | ready. The wrappers need a parameter that quotes a nested sentence; outermost-first replacement already handles it |
| 3 | Update check summary and each model's state ("Everything installed matches…", "installed, but its version was not recorded; …") | `manager/updates.py` | Models page, update line and tooltips | each update check | needs a field |
| 4 | Download failures and retry notes (network, HTTP status, SHA256, disk space, locked file) | `manager/download.py` `Failure.message`, `note`, `readable_os_error` | Wizard error, job rows, models table | whenever a download fails | needs a field on `Failure` |
| 5 | Processing errors: speech engine, translation, ffmpeg and llama-server failures ("… not found", "cue N could not be translated…", "llama-server exited with code…") | `engines/`, `llm/`, `core/translate.py`, `core/audio.py`, `core/pipeline.py`, `core/queue_runner.py` ("the video is gone", "the queue crashed") | Import error screen, batch row | when a run fails | ready |
| 6 | Refusals before a run ("a job is already running", "the video is gone", "… talks need the Qwen3-ASR engine", missing model or program) | `api/jobs.py`, `manager/resolve.py` | Import error screen, notices, batch row | when a start is refused | ready |
| 7 | Batch refusals and skipped files ("already in the queue as …", "not a media file extension", "cannot retry an item that is …"). The backend says "queue" where the English window says "batch" | `core/queue_store.py`, `core/queue_runner.py`, `api/queue.py` | Toasts; skipped list of the batch dialog | now and then | toasts ready; `skipped[].reason` needs a field |
| 8 | Delete and repair refusals, blockers, "a job is running; wait for it…", repair action and reason | `manager/maintain.py`, `manager/inventory.py`, `api/runtimes.py`, `api/deps.py`, `api/inventory.py` | Delete dialog, models table notes and tooltips | when managing models | refusal message ready; `blockers[]` and repair `reason` need a field |
| 9 | LLM page: connection test result, settings problem, save errors ("an API key is required…", URL rules) | `manager/llm_check.py`, `manager/settings.py`, `api/settings.py` | LLM settings page | when a cloud or Ollama source is set up | save error and test detail ready; `problem` needs a field |
| 10 | Models folder: warnings ("N installed model(s) … stay in …", which also names an API route), move errors, "target must be an absolute path" | `api/downloads.py`, `manager/storage_move.py`, `manager/storage.py` | Storage card | when the folder changes | refusals ready; `warnings[]` and move `error` need a field |
| 11 | Profile switch warnings ("This machine has … MiB…") | `manager/switch.py` | Hardware page | when a profile that does not fit is picked | needs a field |
| 12 | Player: screenshot, thumbnail, burn and folder errors ("cannot use the folder…", "another burn-in export is running", ffmpeg tails) | `api/player.py`, `core/render.py` | Toast, burn card | rare | ready |
| 13 | Cue save problems with a code the window does not know, "nothing to correct yet", "no summary yet" | `core/cue_edits.py`, `core/projects.py`, `api/projects.py` | Cue editor, export menu | rare (the known cue codes are already worded) | ready |
| 14 | Shell command errors ("… is not a video or audio file", "cannot read …", "cannot write …", "… is not in a folder this app writes to", link refusals). Some quote an OS message in the OS language | `src-tauri/src/lib.rs`, `links.rs`, `folders.rs` | Import error screen, export menu, folder toast | rare | the commands still return `String`; return `Said` |
| 15 | Names from the registry: asset kinds (`asr`, `llm`), profile ids in "Used by", license names, profile `label` | `manager/registry.json`, `manager/inventory.py` | Models table, wizard, licenses | always, but they are names | not sentences |
