# Plan: a multi-language user interface

Status: plan only, nothing is implemented. Written 2026-11-25.

## Goal

The app window, the setup wizard, the settings pages, the installer and the messages the person reads should come in English, Traditional Chinese, Simplified Chinese and Japanese (the four languages the README already has). A person on a Japanese or English Windows or macOS sees the app in their own language without finding a setting. A person can change the language in the settings page and the window follows at once, with no restart.

This is the user interface language. It is a different thing from the video's spoken language and from the subtitle language the app produces. Those two stay as they are: Japanese or English in, Traditional Chinese (and the other target languages) out.

## What exists today (measured on `main`, 2026-11-25)

| Place | State |
|---|---|
| React frontend, `app/src` | About 540 source lines that contain Chinese, in 48 files, all literal text in the code (JSX text, string literals, template strings with `${}`). No i18n library, no catalog. `<html lang="zh-Hant">` is fixed. The biggest files are `Wizard.tsx`, `HardwareSection.tsx`, `BatchPanel.tsx`, `ModelsSection.tsx`, `App.tsx`, `LlmSection.tsx`. |
| Frontend tests | 28 vitest files and 10 e2e driver files assert Chinese text. |
| Rust shell, `app/src-tauri/src` | 19 lines with Chinese in 3 files (the update messages in `updater.rs`, two in `sidecar.rs`, two in `lib.rs`). |
| Python backend | About 20 user-facing lines with Chinese in `fonts.py`, `runtimes.py`, `secrets.py`, `platforms.py`, `translate.py`, `render.py`, `vc_runtime.py`. Most other Chinese in `backend/` (`ja_terms.py`, `zh_tw.py`, `language_prompts.py`, `kana.py`) is linguistic data for translation, not interface text, and must not be touched. Many backend messages the window shows are English. The window shows the backend's text as it comes. |
| Installer | NSIS already has `TradChinese` and `English` (`installer/lang-*.nsh`). |
| Setting storage | `settings.json` in the user data folder, one typed model in `backend/manager/settings.py`. |
| Formatting | 7 places format numbers, sizes or durations by hand. |

Counting is by line, and a line can hold more than one string, so treat 540 as a floor for lines and expect roughly the same order for distinct strings.

## Decisions (my recommendation; say so if you want another)

1. **Languages.** `en`, `zh-TW`, `zh-CN`, `ja`. A setting `ui_language` with `auto` (follow the operating system, fall back to English) as the default, or one of the four. The picker lists only languages whose catalog is complete.
2. **Library.** A small typed catalog of our own, no dependency. About 80 lines: `t(key, params)`, a React context with `useT()`, `Intl` for numbers, sizes, dates and plural choice. The English catalog is the type: `type Key = keyof typeof en`, and every other language is declared `satisfies Record<Key, string>`, so a missing or extra key fails `tsc`. This is the cheapest way to make "a translation is missing" impossible to ship. Keys are flat and named by area (`wizard.start`), so moving to `i18next` or FormatJS later is a mechanical change. The alternative (Lingui or FormatJS) buys an extraction tool and ICU message syntax at the price of a build step and a dependency, which this size of project does not need. Some strings carry a count and a unit (`${n} 條`; not counted yet, the check script will count them); Chinese and Japanese have no plural forms and English needs two, handled by one `plural(key, n)` helper over `Intl.PluralRules`.
3. **Chinese stays exact.** The `zh-TW` catalog is the current text, character for character. Moving the strings out is a behavior-preserving change, proven by the method used for the macOS work: render the same screens before and after and compare text and PNG hashes. Existing tests and e2e drivers keep asserting Chinese and keep passing, because they run with `zh-TW` pinned.
4. **Translations.** English is written by hand from the Chinese by the owner of each wave. `zh-CN` and `ja` are produced by a model in one pass at the end, with a glossary file (`docs/i18n-glossary.md`: Taiwan terms for `zh-TW`, mainland terms for `zh-CN`, the Japanese terms for the same concepts), then read by you where you can, and marked in the picker as "machine translated" until a native speaker has read them. Nobody has verified quality in any language but `zh-TW` and a basic English.
5. **Where the language lives.** `ui_language` in `settings.json` is the source of truth. The frontend mirrors it in `localStorage` so the first paint, before the backend answers, is already in the right language.
6. **Backend and shell messages.** The text the person reads is chosen in one place, the frontend. The backend (and the Rust shell) send a stable `code` and `params` next to an English `message`. The frontend maps `code` to the catalog and shows the English `message` for an unknown code, so a missing mapping is ugly but never blank. Migrate the codes the window shows often first (wizard, models, hardware, update). Linguistic data files are out of scope.
7. **Guard in structure.** A check script (`scripts/check_ui_strings.mjs`, run in CI) fails when a user-facing literal appears in `app/src` outside `app/src/i18n/`. It also produces the inventory and a progress count, and is the first thing built.

## Architecture

```
app/src/i18n/
  index.ts            t(), plural(), the Key type, formatters (bytes, duration, count)
  I18nProvider.tsx    context, current locale, setLocale, sets <html lang>
  locale.ts           detect from settings, localStorage, navigator.language
  catalog/
    en/<area>.ts      source of the Key type (one file per area, merged in index)
    zh-TW/<area>.ts   the current text
    zh-CN/<area>.ts
    ja/<area>.ts
```

One catalog file per area (`wizard`, `models`, `hardware`, `player`, `batch`, `settings`, `errors`) so several waves can run in parallel without editing the same file. Code outside React that returns text today (`manage/parse.ts`, `rules.ts`, `api/importPlan.ts`, `sourceLabel`) returns a key and params instead, and the component translates. Language names (繁體中文, 日本語) come from `Intl.DisplayNames`, not hand tables. `<html lang>` follows the locale because the wrong `lang` makes the browser pick Chinese glyphs for Japanese text (the Han characters differ), so the CSS font stacks need a `lang`-aware CJK fallback for `ja` and `zh-CN`.

## Waves (each one is a PR with an independent verifier and a before/after render in `zh-TW`)

- **W0, the lever and the base.** `i18n/` module, provider, `ui_language` in the backend settings model and API, the picker in the settings page, `<html lang>`, the check script in CI, the Rust and Python code lists. No string moves except the picker's own. Test: `tsc` fails on a missing key (a deliberate mutant proves it).
- **W1, shell and settings.** `App.tsx`, `SettingsBar`, `HardwareSection`, `LlmSection`, `LicensesSection`, `UpdateSection`, toolbar, toasts. `zh-TW` and `en` complete.
- **W2, wizard and models.** `Wizard.tsx`, `ModelsSection`, `StorageCard`, the inventory and profile text, plus the backend codes they show.
- **W3, working screens.** Player, editor, batch, library, export, summary, help and shortcuts.
- **W4, backend and shell.** The remaining backend codes, the Rust update and sidecar messages (the shell asks the frontend for the language, or returns codes), notification texts, the macOS menu left to the system.
- **W5, translations and installer.** `zh-CN` and `ja` through the glossary, NSIS language files for Simplified Chinese and Japanese, README screenshots left as they are, then a layout pass.

Waves W1 to W3 can run side by side after W0 because each owns its catalog files. Longer English text is the real layout risk: every wave renders its screens at 960 and 1280 px in all complete languages (the Edge render harness from the macOS work, with stubbed Tauri and backend) and a person looks at the pictures before the merge.

## What I will not do

- Touch the subtitle languages or the translation prompts.
- Add a runtime dependency before W0 shows one is needed.
- Call a machine translation reviewed.

## Open risks

- English and Japanese strings are longer or shorter than the Chinese the layout was tuned on (toolbar, wizard, profile cards).
- Backend messages that are English today will show in English inside a Chinese window until their code is mapped. That is today's behavior, not a regression, and the waves shrink it.
- 28 vitest files and 10 e2e drivers must be run under the pinned `zh-TW` locale and need a small change each in W0.
- The effort is large in lines touched and small in design risk. My guess, not a measurement, is 4 to 6 agent rounds per wave for W1 to W3, counting verification.

## What I need from you

Nothing blocks W0. If you do not answer, W0 starts with the four languages, `auto` by operating system with English fallback, the in-house catalog, and the machine-translation flag. Tell me in your own words if you want a different language set, a different default (for example, keep Traditional Chinese as the default for everyone), or a library instead of the in-house catalog.

## W0 as built (2026-11-25)

W0 is in `app/src/i18n/`, `app/src/settings/LanguageSection.tsx`, `scripts/check_ui_strings.mjs` and `ui_language` in `backend/manager/settings.py`. Where the build differs from the plan above, this section wins.

- **Catalog.** One file per area under `catalog/<locale>/`. The English area file is the type of its area, and each other locale's area file is `satisfies Record<keyof typeof en-area, string>`, so a wave edits only its own area files. A locale's merge in `catalog/<locale>/index.ts` is checked against the full `Key`, so a missing area also fails `tsc`.
- **API.** `t(locale, key, params)` and `plural(locale, base, n, params)` are pure functions. Components use `useT()`, which binds the locale: `const { t, plural } = useT()`. The params of a key are read off its English text (`{name}`), so a missing or misnamed param fails `tsc`. A key without a placeholder takes no params. `plural` looks up `base.one` or `base.other` by `Intl.PluralRules`, and every locale defines both, so a language without plurals repeats its text.
- **Outside the provider.** `useT()` speaks `zh-TW`, and `useI18n()` is `null`. `I18nProvider` is mounted in `main.tsx` only, so no existing test needed a change.
- **Hidden locales.** `RELEASED_LOCALES` is `zh-TW` and `en`. A setting that names an unreleased locale, or an `auto` that would pick one, falls back to the next released browser language and then English. W5 adds `zh-CN` and `ja` to the constant.
- **Language names** come from `Intl.DisplayNames`. Edge draws Traditional Chinese as `中文（繁體）`, Node as `繁體中文`. The picker shows what the browser gives.
- **Settings page.** The picker is a sixth section, `section-language`, so the settings navigation has one more entry than before. Pictures of the Models and Hardware pages are therefore taken of `.settings-body`, not of the whole page.
- **First paint.** The `localStorage` mirror holds the setting (`auto` or a locale), not the resolved locale. The backend value replaces it once the backend answers (`useUiLanguageSync`).
- **Fonts.** `:root:lang(ja)` and `:root:lang(zh-Hans)` redefine `--font-sans` and `--font-display` with their own CJK fonts before the Traditional Chinese ones. `zh-Hant` matches neither rule.
- **Guard.** From `app`, `npm run check:strings` compares the literals left in the code with `app/i18n-baseline.json` (660 literals in 48 files on `main`). It fails when a file gains a literal, when a new file has one, and when the baseline is higher than the code. `npm run check:strings -- --update` lowers the baseline and never raises it; each wave runs it, and the committed `initial` number stays fixed so waves do not conflict on it. `-- --list` prints the inventory. It counts string and template literals with CJK or full-width text, and JSX text or `title`, `aria-label`, `placeholder` and `alt` with a Latin phrase (not one identifier-like word). A single Latin word is not counted. The command is not yet in `.github/workflows/ci.yml`.
- **A default to decide.** `auto` is the default. After W0, a person whose system language is not Traditional Chinese sees the language entry and its page in English, and everything else in Traditional Chinese until W1 to W3 move it. Once those waves land, a person with Traditional Chinese on an English Windows sees English. If that is not wanted, change the default to `zh-TW` in `backend/manager/settings.py` before W1.
