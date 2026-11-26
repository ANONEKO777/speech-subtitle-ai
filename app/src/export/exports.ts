import { type Backend, fetchSubtitleText, fetchSummary } from "../api/client";
import type { SourceLang } from "../api/sourceLang";
import type { Translate } from "../i18n";

export interface ExportItem {
  readonly id: string;
  /** The menu entry, in the language of the window. */
  readonly label: (t: Translate) => string;
  /** Suggested file name. */
  readonly file: string;
  readonly text: (b: Backend, projectId: string) => Promise<string>;
}

/** The language name that goes in a menu label, without the region in brackets. */
export const shortName = (nativeName: string) => nativeName.replace(/[（(].*$/, "").trim();

const stemOf = (videoPath: string) => {
  const name = videoPath.slice(Math.max(videoPath.lastIndexOf("\\"), videoPath.lastIndexOf("/")) + 1);
  const dot = name.lastIndexOf(".");
  return dot > 0 ? name.slice(0, dot) : name;
};

/** The summary export of a language that has no summary yet. */
export class NoSummary extends Error {}

/** What the export menu offers for the language shown: three SRT files, ASS, VTT and the summary. */
export function exportItems(videoPath: string, lang: string, label: string, source: SourceLang): ExportItem[] {
  const stem = stemOf(videoPath);
  const subs = (show: "en" | "zh" | "bilingual", format: "srt" | "vtt" | "ass") => (b: Backend, id: string) =>
    fetchSubtitleText(b, id, lang, { show, format });
  return [
    { id: "srt-en", label: (t) => t("export.srtOriginal"), file: `${stem}.${source.replace("+", "-")}.srt`, text: subs("en", "srt") },
    { id: "srt-zh", label: (t) => t("export.srtTarget", { name: label }), file: `${stem}.${lang}.srt`, text: subs("zh", "srt") },
    { id: "srt-bilingual", label: (t) => t("export.bilingual", { format: "SRT" }), file: `${stem}.bilingual.${lang}.srt`, text: subs("bilingual", "srt") },
    { id: "ass", label: (t) => t("export.bilingual", { format: "ASS" }), file: `${stem}.bilingual.${lang}.ass`, text: subs("bilingual", "ass") },
    { id: "vtt", label: (t) => t("export.bilingual", { format: "VTT" }), file: `${stem}.bilingual.${lang}.vtt`, text: subs("bilingual", "vtt") },
    {
      id: "summary",
      label: (t) => t("export.summary"),
      file: `${stem}.summary.${lang}.md`,
      text: async (b, id) => {
        const text = await fetchSummary(b, id, lang);
        if (text === null) throw new NoSummary();
        return text;
      },
    },
  ];
}
