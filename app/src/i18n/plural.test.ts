import { describe, expect, it, vi } from "vitest";

vi.mock("./catalog", () => {
  const en = { "files.one": "{n} file", "files.other": "{n} files", "ok.one": "ok", "ok.other": "ok" };
  const zh = { "files.one": "{n} 個檔案", "files.other": "{n} 個檔案", "ok.one": "好", "ok.other": "好" };
  return { CATALOGS: { en, "zh-TW": zh, "zh-CN": zh, ja: zh } };
});
import { plural } from ".";

describe("plural", () => {
  it("picks the English form by count", () => {
    const say = (n: number) => (plural as (l: string, b: string, n: number) => string)("en", "files", n);
    expect(say(1)).toBe("1 file");
    expect(say(0)).toBe("0 files");
    expect(say(2)).toBe("2 files");
  });

  it("gives the one form of a language without plurals for every count", () => {
    const say = (n: number) => (plural as (l: string, b: string, n: number) => string)("zh-TW", "files", n);
    expect(say(1)).toBe("1 個檔案");
    expect(say(5)).toBe("5 個檔案");
    expect((plural as (l: string, b: string, n: number) => string)("ja", "files", 2)).toBe("2 個檔案");
  });
});
