// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { AddDialog, rowsFor } from "./AddDialog";

const languages = {
  defaultCode: "zh-TW",
  languages: [
    { code: "zh-TW", name: "Traditional Chinese", nativeName: "繁體中文（台灣）", quality: "stable" as const },
    { code: "ko", name: "Korean", nativeName: "한국어", quality: "stable" as const },
  ],
};
const backend = { port: 1, token: "t" };

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("the add dialog and the video language", () => {
  it("a Japanese row can only target Traditional Chinese, and the body carries source_lang", async () => {
    const fetchImpl = vi.fn(() => Promise.resolve(new Response(JSON.stringify({ added: [], skipped: [] }), { status: 201 })));
    vi.stubGlobal("fetch", fetchImpl);
    render(
      <AddDialog
        backend={backend}
        languages={languages}
        initial={[...rowsFor(["D:/a.mp4"], "ko", "en"), ...rowsFor(["D:/b.mp4"], "zh-TW", "en")]}
        onClose={() => undefined}
        onAdded={() => undefined}
      />,
    );
    const [first] = screen.getAllByTestId("add-row-source");
    fireEvent.change(first as HTMLElement, { target: { value: "ja" } });
    const targets = screen.getAllByTestId("add-row-lang") as HTMLSelectElement[];
    expect(targets[0]?.value).toBe("zh-TW");
    expect([...(targets[0]?.options ?? [])].map((o) => o.value)).toEqual(["zh-TW"]);
    expect([...(targets[1]?.options ?? [])].map((o) => o.value)).toEqual(["zh-TW", "ko"]);
    expect(screen.getByTestId("add-source-note").textContent).toContain("繁體中文");
    fireEvent.click(screen.getByTestId("add-submit"));
    await waitFor(() => expect(fetchImpl).toHaveBeenCalled());
    const init = (fetchImpl.mock.calls[0] as unknown as [string, RequestInit])[1];
    expect(JSON.parse(String(init.body)).items).toEqual([
      { path: "D:/a.mp4", target_lang: "zh-TW", source_lang: "ja" },
      { path: "D:/b.mp4", target_lang: "zh-TW", source_lang: "en" },
    ]);
  });
});
