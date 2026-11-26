import type { Locale } from "../i18n/locale";
import { shortName } from "../export/exports";

/**
 * A language as the window names it. The backend sends the language's own name and its English
 * name. Traditional Chinese and Japanese windows show the first, an English window the second,
 * without the region in brackets.
 */
export const languageLabel = (language: { readonly name: string; readonly nativeName: string }, locale: Locale): string =>
  shortName(locale === "en" ? language.name : language.nativeName);
