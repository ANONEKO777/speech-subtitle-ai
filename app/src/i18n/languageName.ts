import { shortName } from "../export/exports";
import { CATALOGS, type Key } from "./catalog";
import type { Locale } from "./locale";

/** A language as the backend describes it: its code, its English name and its own name. Only the code is sure. */
export interface NamedLanguage {
  readonly code: string;
  readonly name?: string;
  readonly nativeName?: string;
}

type LanguageKey = Extract<Key, `lang.${string}`>;

const keyOf = (code: string): LanguageKey | null => {
  const key = `lang.${code}`;
  return key in CATALOGS.en ? (key as LanguageKey) : null;
};

/**
 * The name of a language in the language of the window ("Japanese", 日本語). A window in Traditional Chinese
 * keeps the native names it always showed. A code the catalog does not know yet falls back to the backend's
 * names (without the country in brackets): its English `name` in an English window, its `nativeName` in the
 * others, then to the code. The window's own language picker is the one place that shows each language in
 * its own script instead.
 */
export function languageName(locale: Locale, language: NamedLanguage): string {
  const key = keyOf(language.code);
  if (key !== null) return CATALOGS[locale][key];
  const backendName = locale === "en" ? (language.name ?? language.nativeName) : language.nativeName;
  return backendName === undefined ? language.code : shortName(backendName);
}
