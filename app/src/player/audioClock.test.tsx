// @vitest-environment jsdom
import { act, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { Backend } from "../api/client";
import type { Cue } from "./cues";
import { useActiveCue } from "./useActiveCue";
import { useTransport } from "./useTransport";

vi.mock("../api/library", () => ({
  fetchFrameRate: () => Promise.resolve(null),
  putPlayback: () => Promise.resolve(),
}));

const backend = { baseUrl: "http://x", token: "t" } as unknown as Backend;
const cue = (id: number, startMs: number, endMs: number): Cue => ({ id, startMs, endMs, src: `s${id}`, lang: "en", zh: `z${id}` });
const CUES = [cue(1, 0, 2000), cue(2, 2000, 4000), cue(3, 6000, 8000)];

/** A media element that plays on its own clock. `picture` is the video width: 0 for an mp3. It presents frames only when `frame()` is called. */
function fakeMedia(picture: number) {
  const events = new EventTarget();
  let frameCb: ((now: number, frame: { mediaTime: number }) => void) | null = null;
  const el = {
    paused: false,
    readyState: 4,
    videoWidth: picture,
    duration: 100,
    currentTime: 0,
    addEventListener: events.addEventListener.bind(events),
    removeEventListener: events.removeEventListener.bind(events),
    requestVideoFrameCallback: (cb: typeof frameCb) => {
      frameCb = cb;
      return 1;
    },
    cancelVideoFrameCallback: () => {
      frameCb = null;
    },
  };
  return { el: el as unknown as HTMLVideoElement, raw: el, frame: (t: number) => frameCb?.(0, { mediaTime: t }) };
}

const refresh = () => act(() => vi.advanceTimersByTime(20));

beforeEach(() => vi.useFakeTimers({ toFake: ["requestAnimationFrame", "cancelAnimationFrame"] }));
afterEach(() => vi.useRealTimers());

describe("the subtitle of a file with no picture", () => {
  it("follows the playing time with no video frames", () => {
    const m = fakeMedia(0);
    const { result } = renderHook(() => useActiveCue({ current: m.el }, CUES));
    expect(result.current).toBe(0);
    m.raw.currentTime = 2.5;
    refresh();
    expect(result.current).toBe(1);
    m.raw.currentTime = 5;
    refresh();
    expect(result.current).toBe(-1);
    m.raw.currentTime = 6.5;
    refresh();
    expect(result.current).toBe(2);
  });

  it("stands still while paused", () => {
    const m = fakeMedia(0);
    const { result } = renderHook(() => useActiveCue({ current: m.el }, CUES));
    m.raw.paused = true;
    m.raw.currentTime = 2.5;
    refresh();
    expect(result.current).toBe(0);
  });

  it("waits for the metadata before it reads the clock", () => {
    const m = fakeMedia(0);
    m.raw.readyState = 0;
    const { result } = renderHook(() => useActiveCue({ current: m.el }, CUES));
    m.raw.currentTime = 2.5;
    refresh();
    expect(result.current).toBe(0);
  });

  it("applies the subtitle offset", () => {
    const m = fakeMedia(0);
    const { result } = renderHook(() => useActiveCue({ current: m.el }, CUES, 1000));
    m.raw.currentTime = 2.5;
    refresh();
    expect(result.current).toBe(0);
  });

  it("leaves a video to its frames", () => {
    const m = fakeMedia(640);
    const { result } = renderHook(() => useActiveCue({ current: m.el }, CUES));
    m.raw.currentTime = 2.5;
    refresh();
    expect(result.current).toBe(0);
    act(() => m.frame(2.5));
    expect(result.current).toBe(1);
  });
});

describe("the A-B loop of a file with no picture", () => {
  it("jumps back to A when playback reaches B", () => {
    const m = fakeMedia(0);
    const { result } = renderHook(() =>
      useTransport({ current: m.el }, { backend, projectId: "p", savedPosition: 0, onResumed: () => undefined, onEnded: () => undefined }),
    );
    m.raw.currentTime = 1;
    act(() => void result.current.cycleLoop());
    m.raw.currentTime = 3;
    act(() => void result.current.cycleLoop());
    m.raw.currentTime = 2;
    refresh();
    expect(m.raw.currentTime).toBe(2);
    m.raw.currentTime = 3.1;
    refresh();
    expect(m.raw.currentTime).toBe(1);
  });
});
