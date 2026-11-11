/** The language spoken in a video. Matches the backend's source table (`backend/core/source_langs.py`). */
export type SourceLang = "en" | "ja";

export const DEFAULT_SOURCE: SourceLang = "en";

export const SOURCE_LANGS: ReadonlyArray<{ readonly code: SourceLang; readonly label: string }> = [
  { code: "en", label: "英文" },
  { code: "ja", label: "日文" },
];

/** What a person is told after picking a language whose subtitles come out in one language only. */
export const SOURCE_NOTES: Readonly<Partial<Record<SourceLang, string>>> = {
  ja: "日文影片目前只輸出繁體中文字幕。",
};

/** The target languages a source language can be translated into for now, or null for all of them. Mirrors `targets` of the backend's source table. */
export const SOURCE_TARGETS: Readonly<Partial<Record<SourceLang, readonly string[]>>> = {
  ja: ["zh-TW"],
};

export const canTarget = (source: SourceLang, target: string): boolean => SOURCE_TARGETS[source]?.includes(target) ?? true;

export const parseSourceLang = (value: unknown): SourceLang => (value === "ja" ? "ja" : DEFAULT_SOURCE);

export const sourceLabel = (code: string): string => SOURCE_LANGS.find((l) => l.code === code)?.label ?? code;

/** The small tag that says which language a video is in, such as 日文影片. */
export const sourceTag = (code: string): string => `${sourceLabel(code)}影片`;
