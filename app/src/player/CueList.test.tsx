// @vitest-environment jsdom
import { cleanup, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import type { Cue } from "./cues";
import { CueList } from "./CueList";

const cues: readonly Cue[] = [
  { id: 1, startMs: 0, endMs: 1000, src: "こんにちは。", lang: "ja", zh: "你好。" },
  { id: 2, startMs: 1000, endMs: 2000, src: "Thank you.", lang: "en", zh: "謝謝。" },
];
const editor = () => ({
  validate: () => null,
  refusal: null,
  onCommit: () => Promise.resolve(true),
  onCancel: () => undefined,
});

function list(marks: boolean) {
  render(
    <CueList
      cues={cues}
      active={0}
      mode="both"
      marks={marks}
      edited={new Set()}
      editingId={null}
      editor={editor}
      onSeek={() => undefined}
      onEdit={() => undefined}
    />,
  );
}

afterEach(cleanup);

describe("the cue list of a mixed talk", () => {
  it("marks each cue with its own language, next to the original text", () => {
    list(true);
    expect(within(screen.getByTestId("cue-1")).getByTestId("lang-mark").textContent).toBe("日");
    expect(within(screen.getByTestId("cue-2")).getByTestId("lang-mark").textContent).toBe("英");
    const src = screen.getByTestId("cue-2").querySelector(".src");
    expect(src?.getAttribute("lang")).toBe("en");
    expect(src?.getAttribute("data-cue-lang")).toBe("en");
  });

  it("shows no mark in an English or Japanese talk", () => {
    list(false);
    expect(screen.queryAllByTestId("lang-mark")).toEqual([]);
    expect(screen.getByTestId("cue-1").querySelector(".src")?.textContent).toBe("こんにちは。");
  });
});
