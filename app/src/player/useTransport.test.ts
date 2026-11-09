// @vitest-environment jsdom
import { act, renderHook } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import type { Backend } from "../api/client";
import { useTransport } from "./useTransport";

vi.mock("../api/library", () => ({
  fetchFrameRate: () => Promise.resolve(30),
  putPlayback: () => Promise.resolve(),
}));

const FRAME = 1 / 30;
const FRAMES = 300;
const backend = { baseUrl: "http://x", token: "t" } as unknown as Backend;

/** A video that shows frame k at k/30 s. A seek to a time inside the video always presents a frame, even the one already shown. A seek to the end presents none. */
function fakeVideo() {
  const events = new EventTarget();
  let frameCb: ((now: number, frame: { mediaTime: number }) => void) | null = null;
  let onScreen = FRAMES - 1;
  let clock = onScreen * FRAME;
  const video = {
    duration: FRAMES * FRAME,
    paused: true,
    pause: () => undefined,
    addEventListener: events.addEventListener.bind(events),
    removeEventListener: events.removeEventListener.bind(events),
    requestVideoFrameCallback: (cb: typeof frameCb) => {
      frameCb = cb;
      return 1;
    },
    cancelVideoFrameCallback: () => {
      frameCb = null;
    },
    get currentTime() {
      return clock;
    },
    set currentTime(t: number) {
      clock = t;
      const k = Math.min(FRAMES - 1, Math.max(0, Math.floor(t / FRAME + 1e-6)));
      queueMicrotask(() => {
        props?.onSeeking();
        if (t < FRAMES * FRAME) {
          onScreen = k;
          frameCb?.(0, { mediaTime: k * FRAME });
        }
        events.dispatchEvent(new Event("seeked"));
      });
    },
  };
  let props: { onSeeking: () => void } | null = null;
  return {
    video: video as unknown as HTMLVideoElement,
    shownFrame: () => Math.round(onScreen),
    bind: (p: { onSeeking: () => void }) => {
      props = p;
    },
    showLastFrame: () => frameCb?.(0, { mediaTime: onScreen * FRAME }),
  };
}

describe("frame step at the last frame", () => {
  it("goes to the frame before the last one after a no-op step forward", async () => {
    const fake = fakeVideo();
    const { result } = renderHook(() =>
      useTransport({ current: fake.video }, { backend, projectId: "p", savedPosition: 0, onResumed: () => undefined, onEnded: () => undefined }),
    );
    fake.bind(result.current.videoProps);
    act(() => fake.showLastFrame());

    await act(async () => {
      result.current.frameStep(1);
      await new Promise((r) => setTimeout(r, 1500));
    });
    expect(fake.shownFrame()).toBe(FRAMES - 1);

    await act(async () => {
      result.current.frameStep(-1);
      await new Promise((r) => setTimeout(r, 1500));
    });
    expect(fake.shownFrame()).toBe(FRAMES - 2);
  });
});
