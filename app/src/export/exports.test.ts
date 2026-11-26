import { describe, expect, it } from "vitest";
import { tZhTW } from "../i18n";
import { type ExportItem, exportItems } from "./exports";

const shown = (item: ExportItem | undefined) => item && { label: item.label(tZhTW), file: item.file };

describe("exportItems", () => {
  it("names the source file after the video language and calls it 原文", () => {
    const ja = exportItems("D:/talks/cedec.mp4", "zh-TW", "繁體中文", "ja").find((i) => i.id === "srt-en");
    expect(shown(ja)).toEqual({ label: "SRT 原文", file: "cedec.ja.srt" });
    const en = exportItems("D:/talks/talk.mp4", "zh-TW", "繁體中文", "en").find((i) => i.id === "srt-en");
    expect(shown(en)).toEqual({ label: "SRT 原文", file: "talk.en.srt" });
  });

  it("names the source file of a mixed talk ja-en, with no plus sign in the name", () => {
    const items = exportItems("D:/talks/kirby.mp4", "zh-TW", "繁體中文", "ja+en");
    expect(shown(items.find((i) => i.id === "srt-en"))).toEqual({ label: "SRT 原文", file: "kirby.ja-en.srt" });
    expect(items.find((i) => i.id === "srt-bilingual")?.file).toBe("kirby.bilingual.zh-TW.srt");
  });
});
