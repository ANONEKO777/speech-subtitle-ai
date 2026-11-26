# W1b: finishing and repairing W1

Branch `pr/P53-i18n-w1b`, from `main` `ab9b41d`. The operator switched the picker to English and found the progress screen broken and Chinese left in the toolbar. This round fixes those and sweeps the W1 screens again.

## What was built

- **Progress screen overflow.** Cause: `.steps` had `grid-template-columns: repeat(7, minmax(max-content, 1fr))`. Each column is at least as wide as its label, so seven English labels (about 650 px with gaps) cannot fit a 640 px card, and the grid track of `.progress` (an `auto` track) grew to the content width, which pushed the percent out too. On `main` zh-TW fits (labels are about 48 px, the longest 80 px), so the screen did not overflow in zh-TW with the languages in the stub. By the same arithmetic it overflows in zh-TW for a Latin-script target (`翻譯成Español` is about 105 px wide; inferred from the column sizes, not rendered on `main`), a latent defect that the same fix covers. The fix has four parts. `.progress` has one `minmax(0, 1fr)` column so nothing can widen it. `.steps li` has `max-width: 112px` and `overflow-wrap: anywhere`, which caps each column's `max-content` contribution, so a long label wraps instead of stretching the grid. `.step-name` can shrink and wrap, and `.percent` does not. The English card is `min(780px, 94%)` wide (`:root:lang(en) .importing`). zh-TW pixels are unchanged for every screen of the sweep (hashes below).
- **Language names.** `lang.<code>` in a new catalog area `languages` for the 14 target languages of `backend/core/languages.py` (zh-TW, zh-CN, en, ja, ko, es, fr, de, pt, it, ru, vi, th, id). `languageName(t, code, nativeName?)` in `app/src/i18n/languageName.ts` reads it, then falls back to the backend's `nativeName` (country in brackets cut off), then to the code. zh-TW values are the native names the window always showed (`繁體中文`, `日本語`, `한국어`...), so zh-TW is unchanged. English says "Traditional Chinese", "Japanese" and so on. The interface-language picker keeps the native names (`Intl.DisplayNames`). Used by the import header's subtitle-language picker, the toolbar's subtitle bar (`playingName`), the progress screen's target, and the `names` map that `App` passes to the library (so the library chips follow the window language as soon as W3 keeps using `names`).
- **Window and page title.** `app.title` (`Video Subtitle Translator` / `字幕翻譯`). `I18nProvider` sets `document.title` and calls `getCurrentWindow().setTitle` (`i18n/windowTitle.ts`, a failure outside the shell is ignored). `capabilities/default.json` now grants `core:window:allow-set-title`; the default `core:default` set does not include it. No Rust change, so no `cargo test` was needed (see "Not run"). The static title in `index.html` and `tauri.conf.json` stays `字幕翻譯`, so an English window shows the Chinese name for the moment between the window opening and the page loading. `queue.notifyTitle` already said `Video Subtitle Translator: queue finished` on `main`.
- **`.nav-item` (F4).** Back to the old zh-TW rule; the two-line rule (`height: auto`, `min-height: 36px`, `white-space: normal`, vertical padding) is `:root:lang(en) .nav-item`.
- **Platform examples.** The shell reports its path separator to the page (`sep()` from `@tauri-apps/api/path`, set by the Rust side), so `app/src/platform.ts` `isMacShell()` needs no backend call and no user-agent test. Outside the shell it returns false, which is today's Windows text. The import box has `import.pathPlaceholderMac` (`/Users/me/Movies/talk.mp4`). The licenses page said "The installer ships with FFmpeg ... ffmpeg.exe and DLLs", which is false on a Mac (the Mac build does not pack FFmpeg, it uses the Homebrew one, `docs/MACOS.md`), so a Mac gets `lic.ffmpegMac.*` with a link to `https://ffmpeg.org/legal.html`. The hardware page already branches on the platform (`isMac(hw)`).
- **English wording.** `hw.useActive` "Current profile" (the chip beside it says "In use"), `lic.hint` "model and runtime", `app.switchLanguageFailed` "Couldn't switch the subtitle language". The other verifier suggestions were already on `main` (`7e4ce27`) or are left on purpose: "Both" stays (glossary), "Japanese and English mixed" stays (it reads better inside "was processed earlier as ..."), "24 GB GPU" stays (a spec name).
- **English select widths.** The target picker is 152 px (190 px for an experimental language) in English; the old 104 px cut "Traditional Chinese".

## Backend or shell text still shown on W1 screens (not translated here, W4)

From W1: the hardware page shows the backend's recommendation reason, self-test messages, stage details and fallback reasons, the profile-switch warnings and the download failure message. The LLM page shows the settings problem, the connection-test detail and the save error. The update page shows the shell's failure sentences. The import header shows the backend's error when an import fails (`ApiError.message`) and the failed job's error.

Added by W1b (the W1 verifier's F2):

1. The backend-failed screen, `App.tsx` `status.message` (the shell's startup failure text, a `<pre>`).
2. The update notes, `UpdateSection.tsx` `available.notes` (from the update manifest).
3. The licenses fetch error, `LicensesSection.tsx` `error`.
4. `e.message` on the hardware page (`HardwareSection.tsx`, load, switch, download, self-test failures) and in the `App` notices (`switchLanguageFailed`, `addTargetFailed`, `playedDirectly` error branch): the text after the colon is the backend's.

Also not translated: `document.title` before the page loads and the window title in `tauri.conf.json` (`字幕翻譯`).

## Sweep: what belongs to other waves

Chinese still on the English render of the screens W1b rendered, all outside W1: the home screen's queue panel (`加入`, `暫停佇列`, the disconnect notice, the empty text, `只通知我（預設）`), the library cards (`最近開啟`, `所有影片`, `日文影片`, `全部加入佇列`) and the library chip tooltips (W3 batch and library); the playing screen's side panel, tabs, export button, player controls and notices (`字幕`, `摘要`, `媒體庫`, `佇列`, `匯出`, the proxy notice, the sample cues are stub data) (W3 player); the whole Models page and its storage card (W2), whose folder box says `例如 E:\vst-models` (`models-page/StorageCard.tsx:107`, W2: make it platform-aware with `isMacShell()` and an English text); the wizard (W2: the hardware lines `顯示記憶體`, `驅動`, `統一記憶體`, `記憶體`, `磁碟可用` in `Wizard.tsx:272-276`). Not rendered in Edge (no stub path reaches them): the batch Add dialog, the countdown modal, the editor, the export dialog, the summary tab.

W3 sites that still print `shortName(nativeName)` and must call `languageName(t, code, nativeName)` (`app/src/i18n/languageName.ts`): `batch/lang.ts:6`, `batch/TargetChoice.tsx:17,92`, `player/AddTarget.tsx:60`, `player/Player.tsx:130`, `player/SidePanel.tsx:56,110`. W3 can also use `isMacShell()`.

## Not checked by a render

The queue chip, toasts, the edits notice and the opened-video notice were checked in jsdom (`w1.screens.test.tsx`, English has no CJK). The Edge harness has no screen that raises them. The chip is an icon button with a numeric badge, so only its tooltip text depends on the language. Native tooltips (`title`) cannot be rendered in headless Edge.

## Open points

- `index.html` and `tauri.conf.json` keep the Chinese initial title. Making the initial title English would change zh-TW's first frame; a native title that follows the saved language before the page loads is W4.
- `core:window:allow-set-title` was checked against the permission names in `tauri-2.12.5`; the full Tauri build (which validates capabilities) was not run.
