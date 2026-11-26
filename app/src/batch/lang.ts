import type { LanguageInfo } from "../api/client";
import { languageName } from "../i18n/languageName";
import type { Locale } from "../i18n/locale";

/** The name of `code` in the language of the window, from the languages the backend listed. */
export function langName(code: string, languages: readonly Pick<LanguageInfo, "code" | "name" | "nativeName">[], locale: Locale): string {
  return languageName(locale, languages.find((x) => x.code === code) ?? { code });
}

export const isExperimental = (code: string, languages: readonly LanguageInfo[]): boolean =>
  languages.find((l) => l.code === code)?.quality === "experimental";
