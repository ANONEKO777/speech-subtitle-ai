// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { CueEditing } from "../editor/useCueEditing";
import { fresh } from "../editor/state";
import type { Cue } from "./cues";
import type { FailedKind } from "./failures";
import { SidePanel } from "./SidePanel";

const cues: readonly Cue[] = [
  { id: 1, startMs: 0, endMs: 1000, src: "こんにちは。", lang: "ja", zh: "Hello." },
  { id: 2, startMs: 1000, endMs: 2000, src: "ありがとう。", lang: "ja", zh: "" },
  { id: 3, startMs: 2000, endMs: 3000, src: "さようなら。", lang: "ja", zh: "굿바이." },
];
const editing = {
  state: fresh(cues, []),
  editingId: null,
  refusal: null,
  failure: null,
  begin: () => undefined,
  cancel: () => undefined,
  validate: () => null,
  commit: () => Promise.resolve(true),
  undo: () => Promise.resolve(),
} as unknown as CueEditing;

const languages = [
  { code: "zh-TW", name: "Traditional Chinese", nativeName: "繁體中文（台灣）", quality: "stable" as const },
  { code: "ko", name: "Korean", nativeName: "한국어", quality: "experimental" as const },
];

function panel(over: Partial<React.ComponentProps<typeof SidePanel>> = {}) {
  const onAddTarget = vi.fn();
  render(
    <SidePanel
      backend={{ port: 1, token: "t" }}
      projectId="p"
      tab="cues"
      onTab={() => undefined}
      editing={editing}
      active={0}
      mode="both"
      marks={false}
      languages={languages}
      lang="ko"
      onLang={() => undefined}
      experimental={new Set(["ko"])}
      addable={[
        { code: "en", name: "English", nativeName: "English", experimental: false },
        { code: "zh-CN", name: "Simplified Chinese", nativeName: "简体中文", experimental: false },
      ]}
      onAddTarget={onAddTarget}
      addBlocked={null}
      failed={new Map<number, FailedKind>([[2, "empty"], [3, "english"]])}
      summary={undefined}
      summaryDegraded={false}
      exports={[]}
      actions={[]}
      library={null}
      batch={null}
      batchBadge={null}
      status={null}
      onStatus={() => undefined}
      onSeekCue={() => undefined}
      onSeekSeconds={() => undefined}
      {...over}
    />,
  );
  return { onAddTarget };
}

afterEach(cleanup);

describe("the project view of a language the translator could not finish", () => {
  it("says how many cues failed and why, above the list", () => {
    panel();
    expect(screen.getByTestId("failed-note").dataset["count"]).toBe("2");
    const text = screen.getByTestId("failed-summary").textContent ?? "";
    expect(text).toContain("2 則字幕翻譯失敗");
    expect(text).toContain("1 則沒有한국어翻譯，已留空");
    expect(text).toContain("1 則改用英文顯示");
    expect(text).toContain("沒有通過檢查");
  });

  it("marks each failed cue in the list, and an empty one says it has no translation", () => {
    panel();
    expect(within(screen.getByTestId("cue-1")).queryByTestId("failed-mark")).toBeNull();
    expect(within(screen.getByTestId("cue-2")).getByTestId("failed-mark").dataset["kind"]).toBe("empty");
    expect(within(screen.getByTestId("cue-3")).getByTestId("failed-mark").dataset["kind"]).toBe("english");
    expect(screen.getByTestId("cue-2").querySelector(".zh")?.textContent).toBe("（沒有翻譯）");
  });

  it("shows only the failed cues on request, and all of them again after", () => {
    panel();
    fireEvent.click(screen.getByTestId("failed-filter"));
    expect(screen.queryByTestId("cue-1")).toBeNull();
    expect(screen.getByTestId("cue-2")).toBeTruthy();
    expect(screen.getByTestId("cue-3")).toBeTruthy();
    fireEvent.click(screen.getByTestId("failed-filter"));
    expect(screen.getByTestId("cue-1")).toBeTruthy();
  });

  it("shows nothing when the language has no failure, as for every Traditional Chinese project", () => {
    panel({ failed: new Map() });
    expect(screen.queryByTestId("failed-note")).toBeNull();
    expect(screen.queryByTestId("failed-mark")).toBeNull();
  });
});

describe("the languages of a project", () => {
  it("labels the experimental one in the language select", () => {
    panel();
    const options = [...(screen.getByTestId("lang-select") as HTMLSelectElement).options].map((o) => o.textContent);
    expect(options).toEqual(["繁體中文", "한국어（實驗性）"]);
  });

  it("offers the languages it lacks, says only the translation reruns, and asks for the one picked", () => {
    const { onAddTarget } = panel();
    fireEvent.click(screen.getByTestId("add-target"));
    expect(screen.getByTestId("add-target-list").textContent).toContain("只會重新翻譯");
    expect(screen.queryByTestId("add-target-ko")).toBeNull();
    fireEvent.click(screen.getByTestId("add-target-zh-CN"));
    expect(onAddTarget).toHaveBeenCalledWith("zh-CN");
    expect(screen.queryByTestId("add-target-list")).toBeNull();
  });

  it("labels an experimental language that can still be added, with the hint", () => {
    panel({ addable: [{ code: "ko", name: "Korean", nativeName: "한국어", experimental: true }] });
    fireEvent.click(screen.getByTestId("add-target"));
    expect(screen.getByTestId("add-target-ko").textContent).toContain("實驗性");
    expect(screen.getByTestId("add-target-hint").textContent).toContain("英文");
  });

  it("cannot add a language while a job runs on the project, and the button says why", () => {
    const why = "這部影片正在處理中，等它完成後才能新增字幕語言";
    const { onAddTarget } = panel({ addBlocked: why });
    const button = screen.getByTestId("add-target") as HTMLButtonElement;
    expect(button.disabled).toBe(true);
    expect(button.title).toBe(why);
    fireEvent.click(button);
    expect(screen.queryByTestId("add-target-list")).toBeNull();
    expect(onAddTarget).not.toHaveBeenCalled();
  });

  it("offers nothing to add once the project has every language", () => {
    panel({ addable: [] });
    expect(screen.queryByTestId("add-target")).toBeNull();
  });
});
