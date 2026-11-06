import { describe, expect, it } from "vitest";
import { parseInline, parseSummary } from "./parse";

describe("summary markdown", () => {
  it("turns a chapter line into a timestamp, a bold title and text", () => {
    expect(parseInline("[11:08](#t=668) **建立技能**：講者討論")).toEqual([
      { kind: "time", label: "11:08", seconds: 668 },
      { kind: "text", text: " " },
      { kind: "bold", text: "建立技能" },
      { kind: "text", text: "：講者討論" },
    ]);
  });

  it("leaves other links and stray marks as plain text", () => {
    expect(parseInline("see [docs](https://x.y) **")).toEqual([{ kind: "text", text: "see [docs](https://x.y) **" }]);
  });

  it("reads headings, the quote and one list per run of bullets", () => {
    const blocks = parseSummary("# 標題\n\n> 摘要\n\n## 章節\n\n- [00:00](#t=0) **甲**\n- 乙\n\n## 其他\n- 丙\n");
    expect(blocks.map((b) => b.kind)).toEqual(["heading", "quote", "heading", "list", "heading", "list"]);
    const chapters = blocks[3];
    expect(chapters?.kind === "list" && chapters.items.length).toBe(2);
  });
});
