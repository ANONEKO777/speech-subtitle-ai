// @vitest-environment jsdom
// The hooks with a stable element ref and a counter of scheduled animation frames: no loop is left after unmount or a project switch, a video stays with its frames, and a changed offset or loop is re-armed.
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
    dispatch: (n: string) => events.dispatchEvent(new Event(n)),
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

const refs = new WeakMap<object, { current: HTMLVideoElement }>();
const refOf = (m: { el: HTMLVideoElement }) => {
  let r = refs.get(m);
  if (!r) { r = { current: m.el }; refs.set(m, r); }
  return r;
};

// A counter of rAF loops still scheduled: schedule adds, cancel or run removes.
let pending = new Set<number>();
let next = 1;
let cbs = new Map<number, FrameRequestCallback>();
const refresh = () =>
  act(() => {
    const run = [...cbs.entries()];
    cbs = new Map();
    pending = new Set();
    for (const [, cb] of run) cb(0);
  });

beforeEach(() => {
  pending = new Set();
  cbs = new Map();
  next = 1;
  vi.stubGlobal("requestAnimationFrame", (cb: FrameRequestCallback) => {
    const id = next++;
    pending.add(id);
    cbs.set(id, cb);
    return id;
  });
  vi.stubGlobal("cancelAnimationFrame", (id: number) => {
    pending.delete(id);
    cbs.delete(id);
  });
});
afterEach(() => vi.unstubAllGlobals());

const opts = { backend, projectId: "p", savedPosition: 0, onResumed: () => undefined, onEnded: () => undefined };

describe("the clock of a file with no picture, with a stable ref", () => {
  it("useActiveCue leaves no rAF loop after unmount", () => {
    const m = fakeMedia(0);
    const { unmount } = renderHook(() => useActiveCue(refOf(m), CUES));
    refresh();
    refresh();
    expect(pending.size).toBe(1);
    unmount();
    expect(pending.size).toBe(0);
  });

  it("useTransport leaves no rAF loop after unmount", () => {
    const m = fakeMedia(0);
    const { unmount } = renderHook(() => useTransport(refOf(m), opts));
    refresh();
    expect(pending.size).toBe(1);
    unmount();
    expect(pending.size).toBe(0);
  });

  it("both hooks together: exactly 2 loops while mounted, 0 after", () => {
    const m = fakeMedia(0);
    const a = renderHook(() => useActiveCue(refOf(m), CUES));
    const b = renderHook(() => useTransport(refOf(m), opts));
    expect(pending.size).toBe(2);
    a.unmount();
    b.unmount();
    expect(pending.size).toBe(0);
  });

  it("project switch (new cues array, new projectId) never stacks loops", () => {
    const m = fakeMedia(0);
    const cuesB = [cue(9, 0, 100000)];
    const a = renderHook(({ c }) => useActiveCue(refOf(m), c), { initialProps: { c: CUES } });
    const b = renderHook(({ id }) => useTransport(refOf(m), { ...opts, projectId: id }), { initialProps: { id: "p" } });
    for (let i = 0; i < 5; i++) {
      a.rerender({ c: i % 2 ? CUES : cuesB });
      b.rerender({ id: `p${i}` });
      refresh();
    }
    expect(pending.size).toBe(2);
    m.raw.currentTime = 2.5;
    refresh();
    a.unmount();
    b.unmount();
    expect(pending.size).toBe(0);
  });

  it("an unloaded video (readyState 0, width 0) reports nothing; once loaded as a video it still reports nothing", () => {
    const m = fakeMedia(0);
    m.raw.readyState = 0;
    const { result } = renderHook(() => useActiveCue(refOf(m), CUES));
    m.raw.currentTime = 2.5;
    refresh();
    expect(result.current).toBe(0);
    m.raw.readyState = 4;
    m.raw.videoWidth = 640; // the metadata arrives and it is a video
    refresh();
    expect(result.current).toBe(0);
    act(() => m.frame(2.5));
    expect(result.current).toBe(1);
  });

  it("the same element turns from audio to video (new source): the clock stops, frames take over", () => {
    const m = fakeMedia(0);
    const { result } = renderHook(() => useActiveCue(refOf(m), CUES));
    m.raw.currentTime = 2.5;
    refresh();
    expect(result.current).toBe(1);
    m.raw.videoWidth = 1280;
    m.raw.currentTime = 6.5;
    refresh();
    expect(result.current).toBe(1); // clock must not drive a video
    act(() => m.frame(6.5));
    expect(result.current).toBe(2);
  });

  it("readyState 1 (metadata only) is enough to read the clock", () => {
    const m = fakeMedia(0);
    m.raw.readyState = 1;
    const { result } = renderHook(() => useActiveCue(refOf(m), CUES));
    m.raw.currentTime = 2.5;
    refresh();
    expect(result.current).toBe(1);
  });

  it("seek while paused on an mp3 still updates through `seeked`", () => {
    const m = fakeMedia(0);
    m.raw.paused = true;
    const { result } = renderHook(() => useActiveCue(refOf(m), CUES));
    m.raw.currentTime = 6.5;
    act(() => m.raw.dispatch("seeked"));
    expect(result.current).toBe(2);
  });

  it("editing cues while an mp3 plays: the list is replaced, the clock keeps driving the new list", () => {
    const m = fakeMedia(0);
    m.raw.currentTime = 2.5;
    const { result, rerender } = renderHook(({ c }) => useActiveCue(refOf(m), c), { initialProps: { c: CUES } });
    refresh();
    expect(result.current).toBe(1);
    const edited = [cue(1, 0, 2000), cue(2, 2000, 2400), cue(3, 2400, 8000)];
    rerender({ c: edited });
    expect(result.current).toBe(2); // 2.5 s is now in cue 3
    m.raw.currentTime = 1;
    refresh();
    expect(result.current).toBe(0);
  });

  it("A-B loop re-armed: changing the loop cancels the old clock and the new one jumps to the new A", () => {
    const m = fakeMedia(0);
    const { result } = renderHook(() => useTransport(refOf(m), opts));
    m.raw.currentTime = 1;
    act(() => void result.current.cycleLoop());
    m.raw.currentTime = 3;
    act(() => void result.current.cycleLoop());
    expect(pending.size).toBe(1);
    m.raw.currentTime = 3.2;
    refresh();
    expect(m.raw.currentTime).toBe(1);
    act(() => void result.current.cycleLoop()); // clears the loop
    m.raw.currentTime = 5;
    refresh();
    expect(m.raw.currentTime).toBe(5);
    expect(pending.size).toBe(1);
  });

  it("A-B loop on a video with a picture is left to frames", () => {
    const m = fakeMedia(1280);
    const { result } = renderHook(() => useTransport(refOf(m), opts));
    m.raw.currentTime = 1;
    act(() => void result.current.cycleLoop());
    m.raw.currentTime = 3;
    act(() => void result.current.cycleLoop());
    m.raw.currentTime = 3.2;
    refresh();
    expect(m.raw.currentTime).toBe(3.2);
    act(() => m.frame(3.2));
    expect(m.raw.currentTime).toBe(1);
  });

  it("offset change re-arms the clock with the new offset", () => {
    const m = fakeMedia(0);
    const { result, rerender } = renderHook(({ o }) => useActiveCue(refOf(m), CUES, o), { initialProps: { o: 0 } });
    m.raw.currentTime = 2.5;
    refresh();
    expect(result.current).toBe(1);
    rerender({ o: 1000 });
    refresh();
    expect(result.current).toBe(0);
    expect(pending.size).toBe(1);
  });
});
