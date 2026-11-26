import { shortName } from "../export/exports";
import type { Key, Translate } from ".";
import { CATALOGS } from "./catalog";

type LanguageKey = Extract<Key, `lang.${string}`>;

const keyOf = (code: string): LanguageKey | null => {
  const key = `lang.${code}`;
  return key in CATALOGS.en ? (key as LanguageKey) : null;
};

/**
 * The name of a language in the language of the window ("Japanese", 日本語). A window in Traditional Chinese
 * keeps the native names it always showed. A code the catalog does not know falls back to the backend's own
 * `nativeName` (without its country in brackets), then to the code. The window's own language picker is
 * the one place that shows each language in its own script instead.
 */
export function languageName(t: Translate, code: string, nativeName?: string): string {
  const key = keyOf(code);
  if (key !== null) return (t as (key: LanguageKey) => string)(key);
  return nativeName === undefined ? code : shortName(nativeName);
}
