import { type PlainKey, type Translate, tZhTW } from "../i18n";

/** The language spoken in a video. Matches the backend's source table (`backend/core/source_langs.py`). `ja+en` is a talk that changes between Japanese and English. */
export type SourceLang = "en" | "ja" | "ja+en";

export const DEFAULT_SOURCE: SourceLang = "en";
export const MIXED: SourceLang = "ja+en";

export const SOURCE_LANGS: ReadonlyArray<{ readonly code: SourceLang; readonly label: PlainKey; readonly tag: PlainKey }> = [
  { code: "en", label: "source.label.en", tag: "source.tag.en" },
  { code: "ja", label: "source.label.ja", tag: "source.tag.ja" },
  { code: "ja+en", label: "source.label.mixed", tag: "source.tag.mixed" },
];

const NOTE_KEYS: Readonly<Partial<Record<SourceLang, PlainKey>>> = { ja: "source.note.ja", "ja+en": "source.note.mixed" };

/** What a person is told after picking a language whose subtitles come out in a few languages only. */
export const sourceNote = (code: SourceLang, t: Translate): string | undefined => {
  const key = NOTE_KEYS[code];
  return key === undefined ? undefined : t(key);
};

export const parseSourceLang = (value: unknown): SourceLang =>
  SOURCE_LANGS.find((l) => l.code === value)?.code ?? DEFAULT_SOURCE;

export const sourceLabel = (code: string, t: Translate = tZhTW): string => {
  const found = SOURCE_LANGS.find((l) => l.code === code);
  return found ? t(found.label) : code;
};

/** The small tag that says which language a video is in, such as 日文影片 or 日英混合. */
export const sourceTag = (code: string, t: Translate = tZhTW): string => {
  const found = SOURCE_LANGS.find((l) => l.code === code);
  return found ? t(found.tag) : t("source.tag.unknown", { code });
};

/** Why this machine cannot process a source language, by the code the backend gives. */
const UNAVAILABLE_KEYS: Readonly<Record<string, PlainKey>> = {
  missing_files: "source.unavailable.missingFiles",
  cpu: "source.unavailable.cpu",
};

/** The source languages this machine cannot process, each with the reason in words. A language that is not listed can be picked. */
export type Unavailable = Readonly<Partial<Record<SourceLang, string>>>;

export function parseUnavailable(sources: unknown, t: Translate = tZhTW): Unavailable {
  if (!Array.isArray(sources)) return {};
  const out: Partial<Record<SourceLang, string>> = {};
  for (const item of sources as unknown[]) {
    if (typeof item !== "object" || item === null) continue;
    const s = item as Record<string, unknown>;
    const code = SOURCE_LANGS.find((l) => l.code === s["code"])?.code;
    if (code === undefined || s["available"] !== false) continue;
    out[code] = t(UNAVAILABLE_KEYS[String(s["reason"])] ?? "source.unavailable.unknown");
  }
  return out;
}

/** The language to keep selected: the one picked, or the default when this machine can no longer process it. */
export const usableSource = (picked: SourceLang, unavailable: Unavailable): SourceLang =>
  unavailable[picked] === undefined ? picked : DEFAULT_SOURCE;

/** The two cue languages the window marks in a mixed talk: the short mark and the full name. */
export const cueMark = (lang: string, t: Translate = tZhTW): { readonly mark: string; readonly name: string } => {
  if (lang === "ja") return { mark: t("source.cue.ja.mark"), name: t("source.cue.ja.name") };
  if (lang === "en") return { mark: t("source.cue.en.mark"), name: t("source.cue.en.name") };
  return { mark: lang, name: lang };
};
