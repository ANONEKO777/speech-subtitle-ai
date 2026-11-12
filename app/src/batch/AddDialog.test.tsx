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
  unavailable: {},
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

  it("a mixed row can only target Traditional Chinese, shows the 24 GB note and sends ja+en", async () => {
    const fetchImpl = vi.fn(() => Promise.resolve(new Response(JSON.stringify({ added: [], skipped: [] }), { status: 201 })));
    vi.stubGlobal("fetch", fetchImpl);
    render(
      <AddDialog
        backend={backend}
        languages={languages}
        initial={rowsFor(["D:/a.mp4"], "ko", "en")}
        onClose={() => undefined}
        onAdded={() => undefined}
      />,
    );
    fireEvent.change(screen.getByTestId("add-row-source"), { target: { value: "ja+en" } });
    const target = screen.getByTestId("add-row-lang") as HTMLSelectElement;
    expect([...target.options].map((o) => o.value)).toEqual(["zh-TW"]);
    expect(screen.getByTestId("add-source-note").textContent).toContain("24 GB");
    fireEvent.click(screen.getByTestId("add-submit"));
    await waitFor(() => expect(fetchImpl).toHaveBeenCalled());
    const init = (fetchImpl.mock.calls[0] as unknown as [string, RequestInit])[1];
    expect(JSON.parse(String(init.body)).items).toEqual([{ path: "D:/a.mp4", target_lang: "zh-TW", source_lang: "ja+en" }]);
  });

  it("shows the mixed choice disabled with its reason when this machine cannot run it", () => {
    render(
      <AddDialog
        backend={backend}
        languages={{ ...languages, unavailable: { "ja+en": "這台電腦沒有安裝混合語言所需的模型" } }}
        initial={[]}
        onClose={() => undefined}
        onAdded={() => undefined}
      />,
    );
    const options = [...(screen.getByTestId("add-default-source") as HTMLSelectElement).options];
    const mixed = options.find((o) => o.value === "ja+en");
    expect(mixed?.disabled).toBe(true);
    expect(mixed?.textContent).toContain("這台電腦沒有安裝混合語言所需的模型");
  });
});
