// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ImportPanel, SourcePick, TargetPick } from "./ImportPanel";

afterEach(cleanup);

describe("the video language picker", () => {
  it("offers three choices, and the mixed one is picked like the others", () => {
    const onSourceLang = vi.fn();
    render(<SourcePick busy={false} sourceLang="en" unavailable={{}} onSourceLang={onSourceLang} />);
    const select = screen.getByTestId("source-lang") as HTMLSelectElement;
    expect([...select.options].map((o) => o.label)).toEqual(["英文", "日文", "日文與英文混合"]);
    fireEvent.change(select, { target: { value: "ja+en" } });
    expect(onSourceLang).toHaveBeenCalledWith("ja+en");
  });

  it("shows the mixed choice disabled with the reason when this machine cannot run it", () => {
    const why = "這台電腦沒有安裝混合語言所需的模型";
    render(<SourcePick busy={false} sourceLang="en" unavailable={{ "ja+en": why }} onSourceLang={() => undefined} />);
    const options = [...(screen.getByTestId("source-lang") as HTMLSelectElement).options];
    const mixed = options.find((o) => o.value === "ja+en");
    expect(mixed?.disabled).toBe(true);
    expect(mixed?.textContent).toBe(`日文與英文混合（${why}）`);
    expect(mixed?.title).toBe(why);
  });
});

describe("the language of the subtitles", () => {
  const targets = [
    { code: "zh-TW", name: "Traditional Chinese", nativeName: "繁體中文（台灣）", experimental: false },
    { code: "en", name: "English", nativeName: "English", experimental: false },
    { code: "ko", name: "Korean", nativeName: "한국어", experimental: true },
  ];

  it("lists the targets given, labels the experimental one and marks it when picked", () => {
    const onTarget = vi.fn();
    const { rerender } = render(<TargetPick busy={false} targets={targets} target="zh-TW" onTarget={onTarget} />);
    const select = screen.getByTestId("target-lang") as HTMLSelectElement;
    expect([...select.options].map((o) => o.label)).toEqual(["繁體中文", "English", "한국어（實驗性）"]);
    expect(select.dataset["experimental"]).toBe("false");
    fireEvent.change(select, { target: { value: "ko" } });
    expect(onTarget).toHaveBeenCalledWith("ko");
    rerender(<TargetPick busy={false} targets={targets} target="ko" onTarget={onTarget} />);
    expect((screen.getByTestId("target-lang") as HTMLSelectElement).dataset["experimental"]).toBe("true");
  });

  it("is plain text when the video language has one target only, as a mixed talk has, so it takes no room for a choice", () => {
    render(<TargetPick busy={false} targets={targets.slice(0, 1)} target="zh-TW" onTarget={() => undefined} />);
    const fixed = screen.getByTestId("target-lang");
    expect(fixed.tagName).toBe("SPAN");
    expect(fixed.textContent).toContain("繁體中文");
    expect(fixed.querySelector("select")).toBeNull();
  });

  it("sits in the import bar only where the video language does", () => {
    const props = { busy: false, sourceLang: "ja" as const, unavailable: {}, onSourceLang: () => undefined, targets, target: "en", onTarget: () => undefined, onImport: () => undefined, onPath: () => undefined };
    const { rerender } = render(<ImportPanel {...props} withPicker />);
    expect((screen.getByTestId("target-lang") as HTMLSelectElement).value).toBe("en");
    rerender(<ImportPanel {...props} withPicker={false} />);
    expect(screen.queryByTestId("target-lang")).toBeNull();
  });
});
