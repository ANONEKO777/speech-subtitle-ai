import { describe, expect, it } from "vitest";
import type { Cue } from "../player/cues";
import { edited, fresh, undoPlan, undone } from "./state";

const cue = (id: number, zh: string): Cue => ({ id, startMs: id * 1000, endMs: id * 1000 + 900, en: `en${id}`, zh });
const start = fresh([cue(1, "一"), cue(2, "二")], [2]);

describe("edit state", () => {
  it("marks an edited cue and remembers what it was", () => {
    const next = edited(start, cue(1, "一"), cue(1, "壹"));
    expect(next.cues[0]?.zh).toBe("壹");
    expect([...next.edited].sort()).toEqual([1, 2]);
    expect(next.undo).toEqual([cue(1, "一")]);
  });

  it("undoes edits newest first and keeps the cue marked as edited", () => {
    const one = edited(start, cue(1, "一"), cue(1, "壹"));
    const two = edited(one, cue(1, "壹"), cue(1, "弌"));
    expect(undoPlan(two)?.cues[0]?.zh).toBe("壹");
    const back = undone(two);
    expect(back.cues[0]?.zh).toBe("壹");
    expect(undone(back).cues[0]?.zh).toBe("一");
    expect(undone(undone(back)).undo).toEqual([]);
    expect(back.edited.has(1)).toBe(true);
  });

  it("has nothing to undo at the start", () => {
    expect(undoPlan(start)).toBeNull();
    expect(undone(start)).toBe(start);
  });
});
