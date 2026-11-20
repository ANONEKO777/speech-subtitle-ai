// @vitest-environment jsdom
import { cleanup, renderHook } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

type Drop = (paths: string[]) => void;
interface Listener {
  readonly drop: Drop;
  stopped: boolean;
}
const made: Listener[] = [];
let gate: Promise<void> | null = null;

vi.mock("../api/backend", () => ({
  watchDrops: async (drop: Drop) => {
    const listener: Listener = { drop, stopped: false };
    made.push(listener);
    if (gate) await gate;
    return () => {
      listener.stopped = true;
    };
  },
}));
import { useDrops } from "./useDrops";

afterEach(() => {
  cleanup();
  made.length = 0;
  gate = null;
});

const flush = () => new Promise((resolve) => setTimeout(resolve, 0));

describe("the window's file drop", () => {
  it("listens once, and a drop reaches the handler of the moment, not the one the listener was made with", async () => {
    const first = vi.fn();
    const second = vi.fn();
    const over = vi.fn();
    const { rerender } = renderHook(({ on }) => useDrops(true, on, over), { initialProps: { on: first } });
    await flush();
    rerender({ on: second });
    rerender({ on: second });
    await flush();
    expect(made).toHaveLength(1);
    made[0]?.drop(["D:/a.mp4"]);
    expect(first).not.toHaveBeenCalled();
    expect(second).toHaveBeenCalledWith(["D:/a.mp4"]);
  });

  it("stops listening when the window goes, also when the listener was not made yet", async () => {
    let open: () => void = () => undefined;
    gate = new Promise<void>((resolve) => {
      open = resolve;
    });
    const { unmount } = renderHook(() => useDrops(true, () => undefined, () => undefined));
    unmount();
    open();
    await flush();
    expect(made).toHaveLength(1);
    expect(made[0]?.stopped).toBe(true);
  });

  it("listens to nothing while it is not enabled", async () => {
    renderHook(() => useDrops(false, () => undefined, () => undefined));
    await flush();
    expect(made).toHaveLength(0);
  });
});
