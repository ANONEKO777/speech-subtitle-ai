// @vitest-environment jsdom
import { act, cleanup, fireEvent, render, renderHook, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ImportPanel } from "./ImportPanel";
import { useDetections, worthDetecting } from "./useDetections";

const backend = { port: 1, token: "t" };
const heard = { detected: "ja", suggested: "ja", mixed_unavailable: null, confidence: 1, sure: true, shares: { ja: 1, en: 0 } };

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  vi.useRealTimers();
});

describe("which paths are worth asking about", () => {
  it("takes an absolute path with a media extension and leaves a half-typed one", () => {
    expect(worthDetecting("D:\\talks\\talk.mp4")).toBe(true);
    expect(worthDetecting("D:/talks/talk.mkv")).toBe(true);
    expect(worthDetecting("\\\\nas\\talks\\talk.mp4")).toBe(true);
    expect(worthDetecting("D:\\talks\\ta")).toBe(false);
    expect(worthDetecting("talk.mp4")).toBe(false);
    expect(worthDetecting("")).toBe(false);
  });
});

describe("useDetections", () => {
  it("asks once per path, keeps the answer, and says failed for a refusal", async () => {
    const fetchImpl = vi.fn(async (_url: string, init: RequestInit) =>
      JSON.parse(String(init.body)).video_path.endsWith("bad.mp4")
        ? new Response("{}", { status: 503 })
        : new Response(JSON.stringify(heard), { status: 200 }),
    );
    vi.stubGlobal("fetch", fetchImpl);
    const { result, rerender } = renderHook(({ paths }) => useDetections(backend, paths), { initialProps: { paths: ["D:/a.mp4"] } });
    await waitFor(() => expect(result.current.get("D:/a.mp4")).toMatchObject({ suggested: "ja" }));
    rerender({ paths: ["D:/bad.mp4"] });
    await waitFor(() => expect(result.current.get("D:/bad.mp4")).toBe("failed"));
    rerender({ paths: ["D:/a.mp4"] });
    expect(result.current.get("D:/a.mp4")).toMatchObject({ suggested: "ja" });
    expect(fetchImpl).toHaveBeenCalledTimes(2);
  });

  it("does not ask while there is no backend, or for a path still being typed", () => {
    const fetchImpl = vi.fn();
    vi.stubGlobal("fetch", fetchImpl);
    renderHook(() => useDetections(null, ["D:/a.mp4"]));
    renderHook(() => useDetections(backend, ["D:/a"]));
    expect(fetchImpl).not.toHaveBeenCalled();
  });

  it("lets go of a path that is no longer wanted and forgets it", async () => {
    const stopped: boolean[] = [];
    vi.stubGlobal(
      "fetch",
      vi.fn(
        (_url: string, init: RequestInit) =>
          new Promise<Response>((_, reject) => {
            init.signal?.addEventListener("abort", () => {
              stopped.push(true);
              reject(new DOMException("aborted", "AbortError"));
            });
          }),
      ),
    );
    const { result, rerender } = renderHook(({ paths }) => useDetections(backend, paths), { initialProps: { paths: ["D:/a.mp4"] } });
    await waitFor(() => expect(result.current.get("D:/a.mp4")).toBe("running"));
    rerender({ paths: [] });
    await waitFor(() => expect(stopped).toEqual([true]));
    await waitFor(() => expect(result.current.has("D:/a.mp4")).toBe(false));
  });
});

describe("the import box tells the window its path once it stops changing", () => {
  it("waits for a pause, and reports an empty box at once", () => {
    vi.useFakeTimers();
    const onPath = vi.fn();
    render(<ImportPanel busy={false} sourceLang="en" unavailable={{}} onSourceLang={() => undefined} withPicker onImport={() => undefined} onPath={onPath} />);
    act(() => vi.advanceTimersByTime(10));
    expect(onPath).toHaveBeenLastCalledWith("");
    const box = screen.getByTestId("video-path");
    fireEvent.change(box, { target: { value: '"D:\\talks\\t' } });
    fireEvent.change(box, { target: { value: '"D:\\talks\\talk.mp4"' } });
    act(() => vi.advanceTimersByTime(300));
    expect(onPath).toHaveBeenLastCalledWith("");
    act(() => vi.advanceTimersByTime(300));
    expect(onPath).toHaveBeenLastCalledWith("D:\\talks\\talk.mp4");
  });
});
