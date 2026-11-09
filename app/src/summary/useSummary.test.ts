// @vitest-environment jsdom
import { renderHook, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import type { Backend } from "../api/client";
import { useSummary } from "./useSummary";

const backend = { baseUrl: "http://x", token: "t" } as unknown as Backend;

function serve(project: unknown, summary: string | null) {
  vi.stubGlobal(
    "fetch",
    vi.fn((url: string) =>
      Promise.resolve(
        url.includes("/summary")
          ? summary === null
            ? new Response(JSON.stringify({ detail: "no summary" }), { status: 409 })
            : new Response(summary)
          : new Response(JSON.stringify(project)),
      ),
    ),
  );
}

const project = (degraded: boolean) => ({
  id: "p",
  video_path: "v.mp4",
  languages: { ja: { summarize: { status: "done", degraded } }, "zh-TW": { summarize: { status: "done", degraded: !degraded } } },
});

describe("useSummary", () => {
  it("reports a degraded summary of the language shown", async () => {
    serve(project(true), "# 摘要");
    const { result } = renderHook(() => useSummary(backend, "p", "ja"));
    await waitFor(() => expect(result.current).toEqual({ text: "# 摘要", degraded: true }));
  });
  it("reports a normal summary as not degraded, whatever another language did", async () => {
    serve(project(true), "# 摘要");
    const { result } = renderHook(() => useSummary(backend, "p", "zh-TW"));
    await waitFor(() => expect(result.current).toEqual({ text: "# 摘要", degraded: false }));
  });
  it("shows no notice when the language has no summary", async () => {
    serve(project(true), null);
    const { result } = renderHook(() => useSummary(backend, "p", "ja"));
    await waitFor(() => expect(result.current).toEqual({ text: null, degraded: false }));
  });
});
