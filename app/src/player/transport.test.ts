import { describe, expect, it } from "vitest";
import { type Cue } from "./cues";
import {
  NO_LOOP,
  OFFSET_LIMIT_MS,
  adjacentCue,
  clampOffset,
  playClock,
  cueTime,
  cycleLoop,
  formatOffset,
  loopTarget,
  resumeAt,
  stepFrame,
  stepOrigin,
  stepSpeed,
} from "./transport";

const cue = (id: number, startMs: number, endMs: number): Cue => ({ id, startMs, endMs, src: "e", lang: "en", zh: "z" });
const cues = [cue(1, 1000, 2000), cue(2, 3000, 4000), cue(3, 6000, 7000)];

describe("stepSpeed", () => {
  it("steps through the list and stops at 0.5 and 2", () => {
    expect(stepSpeed(1, 1)).toBe(1.25);
    expect(stepSpeed(1, -1)).toBe(0.75);
    expect(stepSpeed(2, 1)).toBe(2);
    expect(stepSpeed(0.5, -1)).toBe(0.5);
  });
  it("moves a speed between two steps to the nearest one in the direction", () => {
    expect(stepSpeed(1.1, 1)).toBe(1.25);
    expect(stepSpeed(1.1, -1)).toBe(1);
  });
});

describe("A-B loop", () => {
  it("sets A, then B, then clears", () => {
    const a = cycleLoop(NO_LOOP, 10);
    expect(a).toEqual({ a: 10, b: null });
    const ab = cycleLoop(a, 20);
    expect(ab).toEqual({ a: 10, b: 20 });
    expect(cycleLoop(ab, 30)).toEqual(NO_LOOP);
  });
  it("moves A when B would not come after it", () => {
    expect(cycleLoop({ a: 10, b: null }, 5)).toEqual({ a: 5, b: null });
    expect(cycleLoop({ a: 10, b: null }, 10.1)).toEqual({ a: 10.1, b: null });
  });
  it("jumps back to A only once B is reached", () => {
    const loop = { a: 10, b: 20 };
    expect(loopTarget(loop, 19.9)).toBeNull();
    expect(loopTarget(loop, 20)).toBe(10);
    expect(loopTarget(loop, 25)).toBe(10);
    expect(loopTarget({ a: 10, b: null }, 99)).toBeNull();
  });
});

describe("subtitle offset", () => {
  it("looks a late subtitle up at an earlier time", () => {
    expect(cueTime(5000, 1500)).toBe(3500);
    expect(cueTime(5000, -500)).toBe(5500);
  });
  it("clamps and formats", () => {
    expect(clampOffset(10 ** 9)).toBe(OFFSET_LIMIT_MS);
    expect(clampOffset(-(10 ** 9))).toBe(-OFFSET_LIMIT_MS);
    expect(clampOffset(12.6)).toBe(13);
    expect(formatOffset(1500)).toBe("+1.5 s");
    expect(formatOffset(-250)).toBe("-0.3 s");
  });
  it("moves the lines a jump lands on", () => {
    expect(adjacentCue(cues, 500, 1000, 1)).toBe(0);
    expect(adjacentCue(cues, 0, 1000, 1)).toBe(1);
    expect(adjacentCue(cues, -500, 2600, 1)).toBe(2);
  });
});

describe("adjacentCue", () => {
  it("goes to the next cue that starts after now", () => {
    expect(adjacentCue(cues, 0, 0, 1)).toBe(0);
    expect(adjacentCue(cues, 0, 1500, 1)).toBe(1);
    expect(adjacentCue(cues, 0, 6000, 1)).toBeNull();
  });
  it("goes back to the start of this cue, or the one before inside its first moments", () => {
    expect(adjacentCue(cues, 0, 4200, -1)).toBe(1);
    expect(adjacentCue(cues, 0, 3500, -1)).toBe(0);
    expect(adjacentCue(cues, 0, 1200, -1)).toBeNull();
  });
});

describe("resumeAt", () => {
  it("resumes a video left in the middle", () => {
    expect(resumeAt(600, 3000)).toBe(600);
  });
  it("starts over near the start or the end, or with nothing saved", () => {
    expect(resumeAt(3, 3000)).toBe(0);
    expect(resumeAt(0, 3000)).toBe(0);
    expect(resumeAt(2995, 3000)).toBe(0);
    expect(resumeAt(Number.NaN, 3000)).toBe(0);
  });
  it("trusts the position when the length is not known", () => {
    expect(resumeAt(600, 0)).toBe(600);
  });
});

describe("playClock", () => {
  it("shows minutes under an hour and hours above", () => {
    expect(playClock(65)).toBe("1:05");
    expect(playClock(3725)).toBe("1:02:05");
    expect(playClock(-3)).toBe("0:00");
  });
});

describe("stepFrame", () => {
  const FRAME = 1 / 30;
  /** A 30 fps stream whose every 7th frame lasts two ticks, like the variable-rate talk video. */
  const frames = Array.from({ length: 400 }, (_, i) => i * FRAME + Math.floor(i / 7) * FRAME);
  /** The player: showing time `t` shows the last frame that starts at or before it. */
  const seek = async (to: number) => {
    const at = Math.min(Math.max(0, to), frames[frames.length - 1] ?? 0);
    return frames.filter((f) => f <= at + 1e-9).at(-1) ?? 0;
  };

  it("moves one frame forward and back from every frame, including the ones before a long gap", async () => {
    for (let i = 5; i < 300; i++) {
      const from = frames[i] ?? 0;
      expect(await stepFrame(seek, from, 1, FRAME)).toBe(frames[i + 1]);
      expect(await stepFrame(seek, from, -1, FRAME)).toBe(frames[i - 1]);
    }
  });

  it("stays on the first frame when there is none before it", async () => {
    expect(await stepFrame(seek, 0, -1, FRAME)).toBe(0);
  });

  it("stays on the last frame when there is none after it", async () => {
    const last = frames[frames.length - 1] ?? 0;
    expect(await stepFrame(seek, last, 1, FRAME)).toBe(last);
  });

  it("still moves one frame when the frame length it was given is too long by a third", async () => {
    const from = frames[50] ?? 0;
    expect(await stepFrame(seek, from, 1, FRAME * 1.3)).toBe(frames[51]);
  });

  it("steps forward from the frame on screen when the clock lags it by more than three frames after a pause", async () => {
    const onScreen = frames[172] ?? 0;
    const clock = onScreen - 0.144;
    expect(stepOrigin(onScreen, clock)).toBe(onScreen);
    expect(await stepFrame(seek, stepOrigin(onScreen, clock), 1, FRAME)).toBe(frames[173]);
    expect(await stepFrame(seek, stepOrigin(onScreen, clock), -1, FRAME)).toBe(frames[171]);
  });

  it("falls back to the clock only before any frame was reported", () => {
    expect(stepOrigin(-1, 4.2)).toBe(4.2);
    expect(stepOrigin(0, 4.2)).toBe(0);
  });
});
