import { type Backend, fetchSubtitleText, fetchSummary } from "../api/client";
import type { SourceLang } from "../api/sourceLang";

export interface ExportItem {
  readonly id: string;
  readonly label: string;
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

/** What the export menu offers for the language shown: three SRT files, ASS, VTT and the summary. */
export function exportItems(videoPath: string, lang: string, label: string, source: SourceLang): ExportItem[] {
  const stem = stemOf(videoPath);
  const subs = (show: "en" | "zh" | "bilingual", format: "srt" | "vtt" | "ass") => (b: Backend, id: string) =>
    fetchSubtitleText(b, id, lang, { show, format });
  return [
    { id: "srt-en", label: "SRT 原文", file: `${stem}.${source}.srt`, text: subs("en", "srt") },
    { id: "srt-zh", label: `SRT ${label}`, file: `${stem}.${lang}.srt`, text: subs("zh", "srt") },
    { id: "srt-bilingual", label: "SRT 雙語", file: `${stem}.bilingual.${lang}.srt`, text: subs("bilingual", "srt") },
    { id: "ass", label: "ASS 雙語", file: `${stem}.bilingual.${lang}.ass`, text: subs("bilingual", "ass") },
    { id: "vtt", label: "VTT 雙語", file: `${stem}.bilingual.${lang}.vtt`, text: subs("bilingual", "vtt") },
    {
      id: "summary",
      label: "摘要 summary.md",
      file: `${stem}.summary.${lang}.md`,
      text: async (b, id) => {
        const text = await fetchSummary(b, id, lang);
        if (text === null) throw new Error("這個語言還沒有摘要");
        return text;
      },
    },
  ];
}
