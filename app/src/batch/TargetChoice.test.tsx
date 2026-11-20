// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { TargetChoice, choiceSummary } from "./TargetChoice";

afterEach(cleanup);

const targets = [
  { code: "zh-TW", name: "Traditional Chinese", nativeName: "繁體中文（台灣）", experimental: false },
  { code: "zh-CN", name: "Simplified Chinese", nativeName: "简体中文", experimental: false },
  { code: "en", name: "English", nativeName: "English", experimental: false },
  { code: "ko", name: "Korean", nativeName: "한국어", experimental: true },
];

describe("the closed target control", () => {
  it("names the first language and counts the others", () => {
    expect(choiceSummary(targets, ["zh-TW"])).toBe("繁體中文");
    expect(choiceSummary(targets, ["zh-CN", "ko"])).toBe("简体中文 +1");
    expect(choiceSummary(targets, ["zh-TW", "zh-CN", "en"])).toBe("繁體中文 +2");
  });

  it("shows the count on the button itself", () => {
    render(<TargetChoice targets={targets} value={["zh-CN", "en"]} onChange={() => undefined} label="字幕語言" testid="pick" />);
    expect(screen.getByTestId("pick").textContent).toContain("简体中文 +1");
  });

  it("shows the experimental mark when a checked language is experimental, and not otherwise", () => {
    const { rerender } = render(<TargetChoice targets={targets} value={["zh-CN", "ko"]} onChange={() => undefined} label="字幕語言" testid="pick" />);
    expect(screen.getByTestId("pick-experimental").textContent).toBe("實驗性");
    rerender(<TargetChoice targets={targets} value={["zh-CN", "en"]} onChange={() => undefined} label="字幕語言" testid="pick" />);
    expect(screen.queryByTestId("pick-experimental")).toBeNull();
  });

  it("keeps the last language checked", () => {
    const onChange = vi.fn();
    render(<TargetChoice targets={targets} value={["en"]} onChange={onChange} label="字幕語言" testid="pick" />);
    fireEvent.click(screen.getByTestId("pick"));
    expect((screen.getByTestId("pick-en") as HTMLInputElement).disabled).toBe(true);
    fireEvent.click(screen.getByTestId("pick-ko"));
    expect(onChange).toHaveBeenCalledWith(["en", "ko"]);
  });
});
