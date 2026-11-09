import type { LanguageInfo } from "../api/client";
import { shortName } from "../export/exports";

export const langName = (code: string, languages: readonly LanguageInfo[]): string => {
  const l = languages.find((x) => x.code === code);
  return l ? shortName(l.nativeName) : code;
};

export const isExperimental = (code: string, languages: readonly LanguageInfo[]): boolean =>
  languages.find((l) => l.code === code)?.quality === "experimental";
