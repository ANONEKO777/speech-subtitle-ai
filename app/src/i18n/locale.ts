import { readStored, writeStored } from "../storage";
export const LOCALES = ["en", "zh-TW", "zh-CN", "ja"] as const;
export type Locale = (typeof LOCALES)[number];

/** What the setting holds: a locale, or `auto` to follow the operating system. */
export const UI_LANGUAGES = ["auto", ...LOCALES] as const;
export type UiLanguage = (typeof UI_LANGUAGES)[number];

/**
 * What a fresh install shows until the whole window has an English catalog (W5 flips it to `auto`).
 * `tests/test_ui_language.py` keeps it equal to the backend default in `backend/manager/settings.py`.
 */
export const DEFAULT_UI_LANGUAGE: UiLanguage = "zh-TW";

/** The locales a person can pick. zh-CN and ja stay hidden until their catalogs are complete (W5). */
export const RELEASED_LOCALES: readonly Locale[] = ["zh-TW", "en"];

/** The locales whose catalogs a model wrote and no native speaker has read. The picker says so. */
export const MACHINE_TRANSLATED: readonly Locale[] = ["zh-CN", "ja"];

/** What `useT()` speaks outside an `I18nProvider`, so a bare render keeps the Traditional Chinese text. */
export const UNMANAGED_LOCALE: Locale = "zh-TW";
const FALLBACK_LOCALE: Locale = "en";

/** The `lang` attribute of the page. It picks the Han glyph forms, so it must follow the locale. */
export const HTML_LANG: Record<Locale, string> = { en: "en", "zh-TW": "zh-Hant", "zh-CN": "zh-Hans", ja: "ja" };

export const MIRROR_KEY = "vst.ui_language";

export const isUiLanguage = (value: unknown): value is UiLanguage => UI_LANGUAGES.some((l) => l === value);

/** The locale a browser language tag asks for, or null when no catalog speaks it. */
export function localeFromTag(tag: string): Locale | null {
  const parts = tag.toLowerCase().split("-");
  switch (parts[0]) {
    case "en":
      return "en";
    case "ja":
      return "ja";
    case "zh":
      if (parts.includes("hant")) return "zh-TW";
      if (parts.includes("hans")) return "zh-CN";
      return parts.some((p) => p === "tw" || p === "hk" || p === "mo") ? "zh-TW" : "zh-CN";
    default:
      return null;
  }
}

/**
 * The locale to show. A released locale chosen by hand wins. Otherwise the first browser language
 * a released catalog speaks wins, and English is the fallback.
 */
export function resolveLocale(setting: UiLanguage, browserLanguages: readonly string[], released: readonly Locale[] = RELEASED_LOCALES): Locale {
  if (setting !== "auto" && released.includes(setting)) return setting;
  for (const tag of browserLanguages) {
    const locale = localeFromTag(tag);
    if (locale !== null && released.includes(locale)) return locale;
  }
  return FALLBACK_LOCALE;
}

/** The mirror in localStorage, so the first paint before the backend answers is already right. */
export function readMirror(): UiLanguage {
  const value = readStored(MIRROR_KEY);
  return isUiLanguage(value) ? value : DEFAULT_UI_LANGUAGE;
}

export function writeMirror(value: UiLanguage): void {
  writeStored(MIRROR_KEY, value);
}
