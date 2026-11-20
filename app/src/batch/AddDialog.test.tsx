// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { AddDialog, rowsFor } from "./AddDialog";

const target = (code: string, nativeName: string, experimental = false) => ({ code, name: code, nativeName, experimental });
const languages = {
  defaultCode: "zh-TW",
  languages: [
    { code: "zh-TW", name: "Traditional Chinese", nativeName: "繁體中文（台灣）", quality: "stable" as const },
    { code: "zh-CN", name: "Simplified Chinese", nativeName: "简体中文", quality: "stable" as const },
    { code: "en", name: "English", nativeName: "English", quality: "stable" as const },
    { code: "ko", name: "Korean", nativeName: "한국어", quality: "experimental" as const },
  ],
  unavailable: {},
  targets: {
    en: [target("zh-TW", "繁體中文（台灣）"), target("zh-CN", "简体中文"), target("ko", "한국어", true)],
    ja: [target("zh-TW", "繁體中文（台灣）"), target("zh-CN", "简体中文"), target("en", "English"), target("ko", "한국어", true)],
    "ja+en": [target("zh-TW", "繁體中文（台灣）")],
  },
};
const codesOf = (testid: string, at = 0) => (screen.getAllByTestId(testid)[at] as HTMLElement).dataset["codes"];
const open = (testid: string, at = 0) => fireEvent.click(screen.getAllByTestId(testid)[at] as HTMLElement);
const backend = { port: 1, token: "t" };

/** Answers the language guess with a refusal, which leaves every picker as it was, and the queue with success. */
function stubFetch(detected?: unknown) {
  const fetchImpl = vi.fn((url: string) =>
    Promise.resolve(
      url.includes("/api/languages/detect")
        ? detected === undefined
          ? new Response("{}", { status: 503 })
          : new Response(JSON.stringify(detected), { status: 200 })
        : new Response(JSON.stringify({ added: [], skipped: [] }), { status: 201 }),
    ),
  );
  vi.stubGlobal("fetch", fetchImpl);
  return fetchImpl;
}

const queued = (fetchImpl: ReturnType<typeof stubFetch>) => {
  const call = fetchImpl.mock.calls.find(([url]) => url.includes("/api/queue/items")) as unknown as [string, RequestInit];
  return JSON.parse(String(call[1].body)).items;
};

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("the add dialog and the video language", () => {
  it("a Japanese row offers the targets the backend lists for it, and the body carries source_lang", async () => {
    const fetchImpl = stubFetch();
    render(
      <AddDialog
        backend={backend}
        languages={languages}
        initial={[...rowsFor(["D:/a.mp4"], ["ko"], "en"), ...rowsFor(["D:/b.mp4"], ["zh-TW"], "en")]}
        onClose={() => undefined}
        onAdded={() => undefined}
      />,
    );
    const [first] = screen.getAllByTestId("add-row-source");
    fireEvent.change(first as HTMLElement, { target: { value: "ja" } });
    expect(codesOf("add-row-lang", 0)).toBe("ko");
    expect(codesOf("add-row-lang", 1)).toBe("zh-TW");
    open("add-row-lang", 0);
    const offered = [...document.querySelectorAll('input[data-testid^="add-row-lang-"]')].map((e) => e.getAttribute("data-testid"));
    expect(offered).toEqual(["add-row-lang-zh-TW", "add-row-lang-zh-CN", "add-row-lang-en", "add-row-lang-ko"]);
    expect(screen.getByTestId("add-source-note").textContent).toContain("只會重新翻譯");
    fireEvent.click(screen.getByTestId("add-submit"));
    await waitFor(() => expect(fetchImpl.mock.calls.some(([url]) => url.includes("/api/queue/items"))).toBe(true));
    expect(queued(fetchImpl)).toEqual([
      { path: "D:/a.mp4", target_lang: "ko", source_lang: "ja" },
      { path: "D:/b.mp4", target_lang: "zh-TW", source_lang: "en" },
    ]);
  });

  it("a row can pick several targets: one request item lists them in the backend's order, and the experimental one is labelled", async () => {
    const fetchImpl = stubFetch();
    render(
      <AddDialog backend={backend} languages={languages} initial={rowsFor(["D:/a.mp4"], ["zh-TW"], "ja")} onClose={() => undefined} onAdded={() => undefined} />,
    );
    open("add-row-lang");
    fireEvent.click(screen.getByTestId("add-row-lang-ko"));
    fireEvent.click(screen.getByTestId("add-row-lang-en"));
    expect(codesOf("add-row-lang")).toBe("zh-TW,en,ko");
    expect(screen.getByTestId("add-row-lang-list").textContent).toContain("實驗性");
    expect(screen.getByTestId("add-source-note").textContent).toContain("實驗性：");
    fireEvent.click(screen.getByTestId("add-submit"));
    await waitFor(() => expect(fetchImpl.mock.calls.some(([url]) => url.includes("/api/queue/items"))).toBe(true));
    expect(queued(fetchImpl)).toEqual([{ path: "D:/a.mp4", target_langs: ["zh-TW", "en", "ko"], source_lang: "ja" }]);
  });

  it("the last language of a row cannot be unchecked", () => {
    render(
      <AddDialog backend={backend} languages={languages} initial={rowsFor(["D:/a.mp4"], ["zh-TW"], "ja")} onClose={() => undefined} onAdded={() => undefined} />,
    );
    open("add-row-lang");
    const only = screen.getByTestId("add-row-lang-zh-TW") as HTMLInputElement;
    expect(only.disabled).toBe(true);
    fireEvent.click(screen.getByTestId("add-row-lang-en"));
    expect((screen.getByTestId("add-row-lang-zh-TW") as HTMLInputElement).disabled).toBe(false);
  });

  it("changing a row to English speech takes English away from its targets, and keeps the rest", () => {
    render(
      <AddDialog backend={backend} languages={languages} initial={rowsFor(["D:/a.mp4"], ["zh-TW"], "ja")} onClose={() => undefined} onAdded={() => undefined} />,
    );
    open("add-row-lang");
    fireEvent.click(screen.getByTestId("add-row-lang-en"));
    fireEvent.click(screen.getByTestId("add-row-lang-ko"));
    fireEvent.change(screen.getByTestId("add-row-source"), { target: { value: "en" } });
    expect(codesOf("add-row-lang")).toBe("zh-TW,ko");
  });

  it("a mixed row has Traditional Chinese only, shows the 24 GB note and sends ja+en", async () => {
    const fetchImpl = stubFetch();
    render(
      <AddDialog
        backend={backend}
        languages={languages}
        initial={rowsFor(["D:/a.mp4"], ["ko"], "en")}
        onClose={() => undefined}
        onAdded={() => undefined}
      />,
    );
    fireEvent.change(screen.getByTestId("add-row-source"), { target: { value: "ja+en" } });
    expect(codesOf("add-row-lang")).toBe("zh-TW");
    expect((screen.getByTestId("add-row-lang") as HTMLButtonElement).disabled).toBe(true);
    expect(screen.getByTestId("add-source-note").textContent).toContain("24 GB");
    fireEvent.click(screen.getByTestId("add-submit"));
    await waitFor(() => expect(fetchImpl.mock.calls.some(([url]) => url.includes("/api/queue/items"))).toBe(true));
    expect(queued(fetchImpl)).toEqual([{ path: "D:/a.mp4", target_lang: "zh-TW", source_lang: "ja+en" }]);
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

  describe("the guess about each video", () => {
    const guess = (code: string, extra: object = {}) => ({
      detected: code,
      suggested: code,
      mixed_unavailable: null,
      confidence: 1,
      sure: true,
      shares: { ja: code === "ja" ? 1 : 0, en: code === "en" ? 1 : 0 },
      ...extra,
    });
    const open = (paths: string[]) =>
      render(
        <AddDialog backend={backend} languages={languages} initial={rowsFor(paths, ["zh-TW"], "en")} onClose={() => undefined} onAdded={() => undefined} />,
      );
    const rowSource = () => (screen.getByTestId("add-row-source") as HTMLSelectElement).value;

    it("preselects the language heard and says so on the row", async () => {
      const fetchImpl = stubFetch(guess("ja"));
      open(["D:/a.mp4"]);
      await waitFor(() => expect(rowSource()).toBe("ja"));
      expect(screen.getByTestId("add-row-detect").textContent).toBe("偵測到：日文（信心 100%）");
      expect(screen.queryByTestId("add-row-hint")).toBeNull();
      fireEvent.click(screen.getByTestId("add-submit"));
      await waitFor(() => expect(fetchImpl.mock.calls.some(([url]) => url.includes("/api/queue/items"))).toBe(true));
      expect(queued(fetchImpl)).toEqual([{ path: "D:/a.mp4", target_lang: "zh-TW", source_lang: "ja" }]);
    });

    it("asks about one video at a time", async () => {
      let running = 0;
      let most = 0;
      vi.stubGlobal(
        "fetch",
        vi.fn(async () => {
          most = Math.max(most, ++running);
          await new Promise((r) => setTimeout(r, 10));
          running--;
          return new Response(JSON.stringify(guess("en")), { status: 200 });
        }),
      );
      open(["D:/a.mp4", "D:/b.mp4", "D:/c.mp4"]);
      await waitFor(() => {
        const notes = screen.getAllByTestId("add-row-detect");
        expect(notes).toHaveLength(3);
        expect(notes.every((n) => n.getAttribute("data-state") === "done")).toBe(true);
      });
      expect(most).toBe(1);
    });

    it("never replaces a language the person chose, and offers the switch instead", async () => {
      let answer: (r: Response) => void = () => undefined;
      vi.stubGlobal("fetch", vi.fn(() => new Promise<Response>((resolve) => (answer = resolve))));
      open(["D:/a.mp4"]);
      fireEvent.change(screen.getByTestId("add-row-source"), { target: { value: "en" } });
      answer(new Response(JSON.stringify(guess("ja")), { status: 200 }));
      await waitFor(() => expect(screen.getByTestId("add-row-hint").textContent).toContain("這部影片聽起來是日文，目前選的是英文"));
      expect(rowSource()).toBe("en");
      fireEvent.click(screen.getByTestId("add-row-switch"));
      expect(rowSource()).toBe("ja");
      expect(screen.queryByTestId("add-row-hint")).toBeNull();
    });

    it("leaves the row alone when the guess fails, and when it is not clear", async () => {
      stubFetch();
      open(["D:/a.mp4"]);
      await waitFor(() => expect(screen.queryByTestId("add-row-detect")).toBeNull());
      expect(rowSource()).toBe("en");
      cleanup();
      stubFetch(guess("ja", { sure: false, confidence: 0.75 }));
      open(["D:/a.mp4"]);
      await waitFor(() => expect(screen.getByTestId("add-row-detect").textContent).toBe("可能是日文（信心 75%），請確認影片語言"));
      expect(rowSource()).toBe("en");
      expect(screen.queryByTestId("add-row-hint")).toBeNull();
    });

    it("does not ask about a folder", () => {
      const fetchImpl = stubFetch();
      open(["D:/clips"]);
      expect(fetchImpl).not.toHaveBeenCalled();
    });
  });
});
