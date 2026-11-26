// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { BatchPanel } from "./BatchPanel";
import { EMPTY_BATCH, type Batch, type BatchItem } from "./model";
import { plainText } from "../i18n/said";

const calls: string[] = [];
vi.mock("./api", async (orig) => ({
  ...(await orig<typeof import("./api")>()),
  itemAction: (_b: unknown, id: string, action: string) => {
    calls.push(`${action} ${id}`);
    return Promise.resolve();
  },
}));

const languages = [
  { code: "en", name: "English", nativeName: "English", quality: "stable" as const },
  { code: "zh-CN", name: "Simplified Chinese", nativeName: "简体中文", quality: "stable" as const },
  { code: "ko", name: "Korean", nativeName: "한국어", quality: "experimental" as const },
];
const item = (id: string, lang: string, state: BatchItem["state"], error: string | null = null, path = "C:/v/talk.mp4"): BatchItem => ({
  id,
  videoPath: path,
  projectId: "p",
  lang,
  sourceLang: "ja",
  state,
  position: 0,
  step: null,
  progress: state === "done" ? 1 : 0,
  etaS: null,
  attempts: 1,
  error: error === null ? null : plainText(error),
  audioS: 60,
});

function show(items: BatchItem[]) {
  const batch: Batch = { ...EMPTY_BATCH, loaded: true, items };
  render(<BatchPanel backend={{ port: 1, token: "t" }} batch={batch} languages={languages} onOpen={() => undefined} onAdd={() => undefined} onError={() => undefined} />);
}

afterEach(() => {
  cleanup();
  calls.length = 0;
});

describe("one video queued for several targets", () => {
  const items = [
    item("a1", "en", "done"),
    item("a2", "zh-CN", "failed", "the translation failed: the server went away"),
    item("a3", "ko", "queued"),
  ];

  it("shows each target with its own state, and the reason of the failed one without hiding the others", () => {
    show(items);
    expect(screen.getByTestId("qstate-a1").textContent).toBe("完成");
    expect(screen.getByTestId("qstate-a2").textContent).toBe("失敗");
    expect(screen.getByTestId("qstate-a3").textContent).toBe("等待中");
    expect(screen.getByTestId("qerror-a2").textContent).toContain("the server went away");
    expect(screen.queryByTestId("qerror-a1")).toBeNull();
    expect(screen.getByTestId("qlang-a1").textContent).toContain("English");
    expect(screen.getByTestId("qlang-a2").textContent).toContain("简体中文");
    expect(screen.getByTestId("qlang-a3").textContent).toContain("實驗性");
  });

  it("retries the failed target only", () => {
    show(items);
    expect(screen.queryByTestId("qretry-a1")).toBeNull();
    expect(screen.queryByTestId("qretry-a3")).toBeNull();
    fireEvent.click(screen.getByTestId("qretry-a2"));
    expect(calls).toEqual(["retry a2"]);
  });

  it("groups the targets of one video and not those of the next one", () => {
    show([...items, item("b1", "en", "queued", null, "C:/v/other.mp4")]);
    const next = ["a1", "a2", "a3", "b1"].map((id) => screen.getByTestId(`qrow-${id}`).dataset["nextTarget"]);
    expect(next).toEqual(["false", "true", "true", "false"]);
  });
});
