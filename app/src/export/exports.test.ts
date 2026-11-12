import { describe, expect, it } from "vitest";
import { exportItems } from "./exports";

describe("exportItems", () => {
  it("names the source file after the video language and calls it 原文", () => {
    const ja = exportItems("D:/talks/cedec.mp4", "zh-TW", "繁體中文", "ja").find((i) => i.id === "srt-en");
    expect(ja).toMatchObject({ label: "SRT 原文", file: "cedec.ja.srt" });
    const en = exportItems("D:/talks/talk.mp4", "zh-TW", "繁體中文", "en").find((i) => i.id === "srt-en");
    expect(en).toMatchObject({ label: "SRT 原文", file: "talk.en.srt" });
  });

  it("names the source file of a mixed talk ja-en, with no plus sign in the name", () => {
    const items = exportItems("D:/talks/kirby.mp4", "zh-TW", "繁體中文", "ja+en");
    expect(items.find((i) => i.id === "srt-en")).toMatchObject({ label: "SRT 原文", file: "kirby.ja-en.srt" });
    expect(items.find((i) => i.id === "srt-bilingual")?.file).toBe("kirby.bilingual.zh-TW.srt");
  });
});
