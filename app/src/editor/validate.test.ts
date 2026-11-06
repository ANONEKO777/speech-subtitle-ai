import { describe, expect, it } from "vitest";
import type { Cue } from "../player/cues";
import { type Draft, formatClock, parseClock, validateDraft } from "./validate";

const cue = (id: number, startMs: number, endMs: number, zh = `字${id}`): Cue => ({ id, startMs, endMs, en: `en${id}`, zh });
const cues = [cue(1, 0, 2000), cue(2, 2000, 4000), cue(3, 4500, 6000)];
const draft = (index: number, patch: Partial<Draft>): Draft => {
  const c = cues[index] as Cue;
  return { zh: c.zh, startMs: c.startMs, endMs: c.endMs, ...patch };
};
const code = (index: number, patch: Partial<Draft>) => validateDraft(cues, index, draft(index, patch))?.code ?? null;

describe("validateDraft", () => {
  it("accepts a text edit, a shorter cue and cues that touch", () => {
    expect(code(1, { zh: "新的文字" })).toBeNull();
    expect(code(1, { endMs: 3500 })).toBeNull();
    expect(code(1, { endMs: 4500 })).toBeNull();
  });

  it("refuses an end that runs into the next cue and a start inside the previous one", () => {
    expect(code(0, { endMs: 2001 })).toBe("overlap");
    expect(code(1, { startMs: 1999 })).toBe("overlap");
    expect(validateDraft(cues, 1, draft(1, { endMs: 4600 }))?.message).toContain("下一條");
  });

  it("refuses a start earlier than the cue before it", () => {
    expect(code(2, { startMs: 1000, endMs: 1500 })).toBe("out_of_order");
  });

  it("refuses a cue longer than 7 seconds, and exactly 7 seconds passes", () => {
    expect(code(2, { endMs: 11_501 })).toBe("too_long");
    expect(code(2, { endMs: 11_500 })).toBeNull();
  });

  it("refuses an end before the start and an empty text", () => {
    expect(code(2, { startMs: 5000, endMs: 4900 })).toBe("end_before_start");
    expect(code(0, { zh: "   " })).toBe("empty");
  });

  it("lets an already empty cue stay empty", () => {
    const blank = [cue(1, 0, 1000, "")];
    expect(validateDraft(blank, 0, { zh: "", startMs: 0, endMs: 1000 })).toBeNull();
  });
});

describe("clock text", () => {
  it("round trips and reads plain seconds", () => {
    for (const ms of [0, 999, 61_005, 3_661_250]) expect(parseClock(formatClock(ms))).toBe(ms);
    expect(formatClock(61_005)).toBe("1:01.005");
    expect(formatClock(3_661_250)).toBe("1:01:01.250");
    expect(parseClock("83.5")).toBe(83_500);
    expect(parseClock("1:23")).toBe(83_000);
  });

  it("rejects text that is not a time", () => {
    for (const bad of ["", "abc", "1:75", "1:2:3:4", "1:60:00", "-3", "1.2345"]) expect(parseClock(bad)).toBeNull();
  });
});
