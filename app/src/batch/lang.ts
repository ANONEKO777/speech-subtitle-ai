import type { LanguageInfo } from "../api/client";
import type { Translate } from "../i18n";
import { languageName } from "../i18n/languageName";

/** The name of `code` in the language of the window, from the languages the backend listed. */
export const langName = (code: string, languages: readonly Pick<LanguageInfo, "code" | "nativeName">[], t: Translate): string =>
  languageName(t, code, languages.find((x) => x.code === code)?.nativeName);

export const isExperimental = (code: string, languages: readonly LanguageInfo[]): boolean =>
  languages.find((l) => l.code === code)?.quality === "experimental";
