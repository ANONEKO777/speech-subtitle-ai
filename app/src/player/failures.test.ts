import { describe, expect, it } from "vitest";
import type { Cue } from "./cues";
import { failureSummary, failureTitle, openFailures } from "./failures";

const cue = (id: number, zh: string): Cue => ({ id, startMs: id * 1000, endMs: id * 1000 + 900, src: "こんにちは", lang: "ja", zh });
const cues = [cue(1, "Hello."), cue(2, ""), cue(3, "Hello again."), cue(4, "")];

describe("the cues a translation could not do", () => {
  it("is every failed cue still empty, and every failed cue that shows English", () => {
    const open = openFailures({ failed: [2, 3, 4], english: [3] }, cues, new Set());
    expect([...open]).toEqual([
      [2, "empty"],
      [3, "english"],
      [4, "empty"],
    ]);
  });

  it("is nothing for a language with no failures, and for a cue that is not in the list", () => {
    expect(openFailures(undefined, cues, new Set()).size).toBe(0);
    expect(openFailures({ failed: [99], english: [] }, cues, new Set()).size).toBe(0);
  });

  it("ends for a cue the person filled in, or edited", () => {
    const filled = [cue(1, "Hello."), cue(2, "A line I wrote."), cue(3, "Hello again."), cue(4, "")];
    expect([...openFailures({ failed: [2, 3, 4], english: [3] }, filled, new Set([2, 3])).keys()]).toEqual([4]);
  });

  it("says how many failed, what shows instead and why, with the language named", () => {
    const open = openFailures({ failed: [2, 3, 4], english: [3] }, cues, new Set());
    const text = failureSummary(open, "English");
    expect(text).toContain("3 則字幕翻譯失敗");
    expect(text).toContain("2 則沒有English翻譯，已留空");
    expect(text).toContain("1 則改用英文顯示");
    expect(text).toContain("沒有通過檢查");
  });

  it("marks one cue with its reason, and says a bilingual file shows only the original for an empty one", () => {
    expect(failureTitle("empty", "简体中文")).toContain("沒有简体中文翻譯");
    expect(failureTitle("empty", "简体中文")).toContain("雙語字幕只會顯示原文");
    expect(failureTitle("english", "한국어")).toContain("顯示的是英文");
  });
});
