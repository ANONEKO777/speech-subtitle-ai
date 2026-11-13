import { describe, expect, it } from "vitest";
import { type Detection, detectLine, hintFor, parseDetection, preselect } from "./detect";

const one = (code: "en" | "ja", confidence = 1, extra: Partial<Detection> = {}): Detection => ({
  detected: code,
  suggested: code,
  mixedUnavailable: null,
  confidence,
  sure: confidence >= 0.9,
  ja: code === "ja" ? confidence : 1 - confidence,
  en: code === "en" ? confidence : 1 - confidence,
  ...extra,
});
const mixed = (extra: Partial<Detection> = {}): Detection => ({
  detected: "ja+en",
  suggested: "ja+en",
  mixedUnavailable: null,
  confidence: 0.57,
  sure: true,
  ja: 0.57,
  en: 0.43,
  ...extra,
});
const cannotMix = mixed({ suggested: "ja", mixedUnavailable: "cpu" });

describe("parseDetection", () => {
  it("reads the backend's answer", () => {
    expect(
      parseDetection({ detected: "ja+en", suggested: "ja", mixed_unavailable: "cpu", confidence: 0.6, sure: true, shares: { ja: 0.6, en: 0.4 }, clear: 24, samples: [] }),
    ).toEqual({ detected: "ja+en", suggested: "ja", mixedUnavailable: "cpu", confidence: 0.6, sure: true, ja: 0.6, en: 0.4 });
  });

  it("reads an answer with no guess, and refuses what is not an answer", () => {
    expect(parseDetection({ detected: null, suggested: null, mixed_unavailable: null, confidence: 0, sure: false, shares: {} })?.suggested).toBeNull();
    expect(parseDetection(null)).toBeNull();
    expect(parseDetection({ detail: "x" })).toBeNull();
  });
});

describe("the line that says what was heard", () => {
  it("names the language and how sure the guess is", () => {
    expect(detectLine(one("ja"))).toBe("偵測到：日文（信心 100%）");
    expect(detectLine(one("en", 0.92))).toBe("偵測到：英文（信心 92%）");
  });

  it("asks for a check when the guess is not clear", () => {
    expect(detectLine(one("ja", 0.75))).toBe("可能是日文（信心 75%），請確認影片語言");
  });

  it("gives the share of each language for a mixed talk", () => {
    expect(detectLine(mixed())).toBe("偵測到：日文與英文混合（日文 57%、英文 43%）");
  });

  it("says mixed is not available here and which language was picked instead", () => {
    const line = detectLine(cannotMix) ?? "";
    expect(line).toContain("日文與英文混合");
    expect(line).toContain("這台電腦無法處理混合語言，先選日文");
  });

  it("says nothing when nothing was heard", () => {
    expect(detectLine({ ...one("en"), detected: null, suggested: null })).toBeNull();
  });
});

describe("preselect", () => {
  it("returns the guess when the person has not chosen and the guess is clear", () => {
    expect(preselect(one("ja"), false, {})).toBe("ja");
    expect(preselect(mixed(), false, {})).toBe("ja+en");
    expect(preselect(cannotMix, false, { "ja+en": "x" })).toBe("ja");
  });

  it("never replaces what the person chose", () => {
    expect(preselect(one("ja"), true, {})).toBeNull();
  });

  it("leaves a guess that is not clear, or that this machine cannot process", () => {
    expect(preselect(one("ja", 0.8), false, {})).toBeNull();
    expect(preselect(mixed(), false, { "ja+en": "x" })).toBeNull();
  });
});

describe("hintFor", () => {
  it("says nothing when the choice is the guess, or the guess is not clear", () => {
    expect(hintFor(one("ja"), "ja", {})).toBeNull();
    expect(hintFor(one("ja", 0.8), "en", {})).toBeNull();
    expect(hintFor({ ...one("en"), suggested: null, detected: null }, "ja", {})).toBeNull();
  });

  it("offers the language heard to a person who chose another", () => {
    expect(hintFor(one("ja"), "en", {})).toEqual({ text: "這部影片聽起來是日文，目前選的是英文", switchTo: "ja" });
    expect(hintFor(one("en"), "ja+en", {})?.switchTo).toBe("en");
  });

  it("offers mixed when both languages were heard and mixed can run", () => {
    expect(hintFor(mixed(), "en", {})).toEqual({
      text: "這部影片聽起來日文與英文都有，目前選的是英文，另一種語言會被當成英文處理",
      switchTo: "ja+en",
    });
  });

  it("offers the main language of a mixed talk when mixed cannot run here", () => {
    expect(hintFor(cannotMix, "en", { "ja+en": "x" })).toEqual({ text: "這部影片大部分是日文，目前選的是英文", switchTo: "ja" });
    expect(hintFor(cannotMix, "ja", { "ja+en": "x" })).toBeNull();
  });
});
