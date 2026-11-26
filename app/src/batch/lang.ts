import type { LanguageInfo } from "../api/client";
import { type Translate, t } from "../i18n";
import { languageName } from "../i18n/languageName";
import type { Locale } from "../i18n/locale";

/** The name of `code` in the language of the window, from the languages the backend listed. */
export function langName(code: string, languages: readonly Pick<LanguageInfo, "code" | "nativeName">[], locale: Locale): string {
  const translate: Translate = (key, ...args) => t(locale, key, ...args);
  return languageName(translate, code, languages.find((x) => x.code === code)?.nativeName);
}

export const isExperimental = (code: string, languages: readonly LanguageInfo[]): boolean =>
  languages.find((l) => l.code === code)?.quality === "experimental";
