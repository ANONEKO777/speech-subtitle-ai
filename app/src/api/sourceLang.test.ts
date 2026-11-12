import { describe, expect, it } from "vitest";
import { SOURCE_NOTES, canTarget, cueMark, parseSourceLang, parseUnavailable, sourceLabel, sourceTag, usableSource } from "./sourceLang";

describe("the mixed Japanese and English choice", () => {
  it("is a source language with its own label and tag", () => {
    expect(parseSourceLang("ja+en")).toBe("ja+en");
    expect(parseSourceLang("xx")).toBe("en");
    expect(sourceLabel("ja+en")).toBe("日文與英文混合");
    expect(sourceTag("ja+en")).toBe("日英混合");
    expect(sourceTag("ja")).toBe("日文影片");
  });

  it("can be translated into Traditional Chinese only, as Japanese can", () => {
    expect(canTarget("ja+en", "zh-TW")).toBe(true);
    expect(canTarget("ja+en", "ko")).toBe(false);
    expect(canTarget("en", "ko")).toBe(true);
  });

  it("says it needs the Qwen3 model files, not only the 24 GB profile", () => {
    expect(SOURCE_NOTES["ja+en"]).toContain("Qwen3");
  });

  it("marks a Japanese cue 日 and an English cue 英", () => {
    expect(cueMark("ja").mark).toBe("日");
    expect(cueMark("en").mark).toBe("英");
  });
});

describe("parseUnavailable", () => {
  it("says why in words, and ignores what it does not know", () => {
    expect(
      parseUnavailable([
        { code: "ja+en", available: false, reason: "cpu" },
        { code: "klingon", available: false, reason: "missing_files" },
        { code: "ja", available: true, reason: null },
      ]),
    ).toEqual({ "ja+en": "混合語言需要顯示卡，這台電腦目前以 CPU 執行" });
  });

  it("falls back to a general reason for a code it has no words for", () => {
    expect(parseUnavailable([{ code: "ja+en", available: false, reason: "new" }])).toEqual({
      "ja+en": "這台電腦目前無法處理這種影片",
    });
  });
});

describe("usableSource", () => {
  it("keeps a choice this machine can process, and falls back to English when it cannot", () => {
    expect(usableSource("ja+en", {})).toBe("ja+en");
    expect(usableSource("ja", { "ja+en": "x" })).toBe("ja");
    expect(usableSource("ja+en", { "ja+en": "x" })).toBe("en");
  });
});
