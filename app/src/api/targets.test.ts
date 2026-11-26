import { describe, expect, it } from "vitest";
import { type LanguageInfo } from "./client";
import { tZhTW } from "../i18n";
import { isExperimentalTarget, parseSourceTargets, targetFor, targetLanguage, targetsFor, targetsOf } from "./targets";

const sources = [
  {
    code: "ja",
    targets: [
      { code: "zh-TW", name: "Traditional Chinese", native_name: "繁體中文（台灣）", experimental: false },
      { code: "zh-CN", name: "Simplified Chinese", native_name: "简体中文", experimental: false },
      { code: "en", name: "English", native_name: "English", experimental: false },
      { code: "ko", name: "Korean", native_name: "한국어", experimental: true },
    ],
  },
  { code: "ja+en", targets: [{ code: "zh-TW", name: "Traditional Chinese", native_name: "繁體中文（台灣）", experimental: false }] },
];
const lang = (code: string, nativeName: string, quality: "stable" | "experimental" = "stable"): LanguageInfo => ({
  code,
  name: code,
  nativeName,
  quality,
});
const set = {
  languages: [lang("zh-TW", "繁體中文（台灣）"), lang("en", "English"), lang("ko", "한국어", "experimental"), lang("es", "Español")],
  targets: parseSourceTargets(sources),
};

describe("the targets of a video language, as the backend lists them", () => {
  it("keeps the order of the backend and its experimental flag", () => {
    expect(targetsOf(set, "ja").map((t) => [t.code, t.experimental])).toEqual([
      ["zh-TW", false],
      ["zh-CN", false],
      ["en", false],
      ["ko", true],
    ]);
  });

  it("gives a mixed talk Traditional Chinese only", () => {
    expect(targetsOf(set, "ja+en").map((t) => t.code)).toEqual(["zh-TW"]);
  });

  it("offers English speech every language it knows but English, when the backend lists none", () => {
    expect(targetsOf(set, "en").map((t) => t.code)).toEqual(["zh-TW", "ko", "es"]);
    expect(isExperimentalTarget(set, "en", "ko")).toBe(true);
    expect(isExperimentalTarget(set, "en", "es")).toBe(false);
  });

  it("follows the backend when it changes the list of a source: a data change, no code", () => {
    const more = parseSourceTargets([{ code: "ja", targets: [{ code: "fr", name: "French", native_name: "Français", experimental: true }] }]);
    expect(targetsOf({ languages: set.languages, targets: more }, "ja").map((t) => t.code)).toEqual(["fr"]);
  });

  it("ignores an entry it cannot read", () => {
    expect(parseSourceTargets("no")).toEqual({});
    expect(parseSourceTargets([{ code: "ja", targets: [{ code: 3 }, null, "x"] }])).toEqual({ ja: [] });
    expect(parseSourceTargets([{ targets: [] }, { code: "ja" }])).toEqual({});
  });
});

describe("the language wanted", () => {
  it("is kept when the video language has it, and falls back to the first one when it has not", () => {
    expect(targetFor(set, "ja", "ko")).toBe("ko");
    expect(targetFor(set, "ja", "es")).toBe("zh-TW");
    expect(targetFor(set, "ja+en", "ko")).toBe("zh-TW");
    expect(targetFor(set, "en", "en")).toBe("zh-TW");
  });

  it("keeps the several languages of a row that the new video language has, in the order of the backend, and never none", () => {
    expect(targetsFor(set, "ja", ["ko", "en"])).toEqual(["en", "ko"]);
    expect(targetsFor(set, "en", ["en", "ko"])).toEqual(["ko"]);
    expect(targetsFor(set, "ja+en", ["ko", "en"])).toEqual(["zh-TW"]);
  });

  it("finds a target's record as the backend gives it, or only its code", () => {
    expect(targetLanguage(set, "ja", "zh-CN").nativeName).toBe("简体中文");
    expect(targetLanguage(set, "ja", "xx")).toEqual({ code: "xx" });
  });
});

describe("the hint of an experimental language", () => {
  it("says the quality is not judged and what the person will see", () => {
    expect(tZhTW("targets.experimentalHint")).toContain("實驗性");
    expect(tZhTW("targets.experimentalHint")).toContain("英文");
  });
});
