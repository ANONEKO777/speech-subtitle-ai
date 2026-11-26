import { describe, expect, it } from "vitest";
import { NOT_ENGLISH } from "./notEnglish";

describe("the check an English screen has to pass", () => {
  it.each(["中", "。", "（", "ひ", "カ", "한", "ᄀ", "ㄱ", "ไ"])("refuses %s", (char) => {
    expect(NOT_ENGLISH.test(`Save ${char}`)).toBe(true);
  });

  it("lets English interface text through, with its punctuation", () => {
    expect(NOT_ENGLISH.test("Can't save (3/7) · 1:05.250 … “quoted” – 50% café")).toBe(false);
  });
});
