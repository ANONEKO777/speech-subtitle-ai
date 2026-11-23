/** The language spoken in a video. Matches the backend's source table (`backend/core/source_langs.py`). `ja+en` is a talk that changes between Japanese and English. */
export type SourceLang = "en" | "ja" | "ja+en";

export const DEFAULT_SOURCE: SourceLang = "en";
export const MIXED: SourceLang = "ja+en";

export const SOURCE_LANGS: ReadonlyArray<{ readonly code: SourceLang; readonly label: string; readonly tag: string }> = [
  { code: "en", label: "英文", tag: "英文影片" },
  { code: "ja", label: "日文", tag: "日文影片" },
  { code: "ja+en", label: "日文與英文混合", tag: "日英混合" },
];

/** What a person is told after picking a language whose subtitles come out in a few languages only. */
export const SOURCE_NOTES: Readonly<Partial<Record<SourceLang, string>>> = {
  ja: "日文影片可以同時有幾種字幕語言，之後再加一種只會重新翻譯，不會重跑語音辨識。",
  "ja+en": "日英混合影片目前只輸出繁體中文字幕，需要 Qwen3 模型檔（24 GB 的模型組會安裝）。",
};

export const parseSourceLang = (value: unknown): SourceLang =>
  SOURCE_LANGS.find((l) => l.code === value)?.code ?? DEFAULT_SOURCE;

export const sourceLabel = (code: string): string => SOURCE_LANGS.find((l) => l.code === code)?.label ?? code;

/** The small tag that says which language a video is in, such as 日文影片 or 日英混合. */
export const sourceTag = (code: string): string => SOURCE_LANGS.find((l) => l.code === code)?.tag ?? `${code}影片`;

/** Why this machine cannot process a source language, by the code the backend gives. */
const UNAVAILABLE_TEXT: Readonly<Record<string, string>> = {
  missing_files: "這台電腦沒有安裝混合語言所需的模型",
  cpu: "混合語言需要顯示卡，這台電腦目前以 CPU 執行",
};

/** The source languages this machine cannot process, each with the reason in words. A language that is not listed can be picked. */
export type Unavailable = Readonly<Partial<Record<SourceLang, string>>>;

export function parseUnavailable(sources: unknown): Unavailable {
  if (!Array.isArray(sources)) return {};
  const out: Partial<Record<SourceLang, string>> = {};
  for (const item of sources as unknown[]) {
    if (typeof item !== "object" || item === null) continue;
    const s = item as Record<string, unknown>;
    const code = SOURCE_LANGS.find((l) => l.code === s["code"])?.code;
    if (code === undefined || s["available"] !== false) continue;
    out[code] = UNAVAILABLE_TEXT[String(s["reason"])] ?? "這台電腦目前無法處理這種影片";
  }
  return out;
}

/** The language to keep selected: the one picked, or the default when this machine can no longer process it. */
export const usableSource = (picked: SourceLang, unavailable: Unavailable): SourceLang =>
  unavailable[picked] === undefined ? picked : DEFAULT_SOURCE;

/** The two cue languages the window marks in a mixed talk: the one letter and the full name. */
const CUE_MARKS: Readonly<Record<string, { readonly mark: string; readonly name: string }>> = {
  ja: { mark: "日", name: "日文" },
  en: { mark: "英", name: "英文" },
};

export const cueMark = (lang: string): { readonly mark: string; readonly name: string } =>
  CUE_MARKS[lang] ?? { mark: lang, name: lang };
