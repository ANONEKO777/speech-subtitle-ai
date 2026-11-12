import { describe, expect, it } from "vitest";
import { type Cue, cueAt } from "./cues";

const cue = (id: number, startMs: number, endMs: number): Cue => ({
  id,
  startMs,
  endMs,
  src: `en ${id}`,
  lang: "en",
  zh: `zh ${id}`,
});

const cues = [cue(1, 1000, 2000), cue(2, 2000, 3500), cue(3, 5000, 6000)];

describe("cueAt", () => {
  it("finds the cue that contains the time", () => {
    expect(cueAt(cues, 1500)).toBe(0);
    expect(cueAt(cues, 5999)).toBe(2);
  });

  it("includes the start and excludes the end", () => {
    expect(cueAt(cues, 1000)).toBe(0);
    expect(cueAt(cues, 2000)).toBe(1);
    expect(cueAt(cues, 3500)).toBe(-1);
  });

  it("returns -1 before the first cue, in a gap and after the last cue", () => {
    expect(cueAt(cues, 0)).toBe(-1);
    expect(cueAt(cues, 4000)).toBe(-1);
    expect(cueAt(cues, 6000)).toBe(-1);
  });

  it("returns -1 with no cues", () => {
    expect(cueAt([], 100)).toBe(-1);
  });

  it("agrees with a linear scan on a long list", () => {
    const long = Array.from({ length: 459 }, (_, i) => cue(i + 1, i * 5000 + 120, i * 5000 + 4600));
    for (let t = 0; t < 459 * 5000; t += 37) {
      const expected = long.findIndex((c) => t >= c.startMs && t < c.endMs);
      expect(cueAt(long, t)).toBe(expected);
    }
  });
});
