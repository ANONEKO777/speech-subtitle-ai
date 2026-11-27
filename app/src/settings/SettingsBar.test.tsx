// @vitest-environment jsdom
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { I18nProvider } from "../i18n/I18nProvider";
import type { Locale } from "../i18n/locale";
import { SettingsBar } from "./SettingsBar";
import { DEFAULTS } from "./settings";

/**
 * jsdom lays nothing out, so these tests give the text and the box that holds it their widths: each character is
 * 10 px wide, and every box is `room` px wide.
 */
function measured(room: number) {
  vi.stubGlobal(
    "ResizeObserver",
    class {
      observe() {}
      disconnect() {}
    },
  );
  Range.prototype.getBoundingClientRect = function (this: Range) {
    return { width: this.toString().length * 10 } as DOMRect;
  };
  vi.spyOn(Element.prototype, "getBoundingClientRect").mockReturnValue({ width: room } as DOMRect);
}

const bar = (locale: Locale, langName: string) =>
  render(
    <I18nProvider initial={locale}>
      <SettingsBar langName={langName} settings={DEFAULTS} onChange={() => undefined} />
    </I18nProvider>,
  );

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

describe.each([
  ["en", "Traditional Chinese", "Traditional Chinese on top", "In bilingual mode, Traditional Chinese goes above the original"],
  ["zh-TW", "Bahasa Indonesia", "Bahasa Indonesia在上", "雙語時Bahasa Indonesia放在原文上方"],
] as const)("the subtitle language's name in a full %s toolbar", (locale, name, onTop, switchTip) => {
  it("is plain text with no tooltip or extra label while it fits", () => {
    measured(1000);
    bar(locale, name);
    const button = screen.getByRole("button", { name });
    expect(button.querySelector("[title]")).toBeNull();
    const toggle = screen.getByRole("switch", { name: onTop });
    expect(toggle.getAttribute("aria-label")).toBeNull();
    expect(toggle.closest("label")?.querySelector("[data-cut]")).toBeNull();
  });

  it("keeps the whole name in the button's tooltip and in both accessible names when it is shortened", () => {
    measured(40);
    bar(locale, name);
    const button = screen.getByRole("button", { name });
    expect(button.querySelector("[title]")?.getAttribute("title")).toBe(name);
    expect(button.textContent).toBe(name);
    const toggle = screen.getByRole("switch", { name: onTop });
    expect(toggle.getAttribute("aria-label")).toBe(onTop);
    const label = toggle.closest("label");
    expect(label?.getAttribute("title")).toBe(switchTip);
    expect(label?.querySelector("[data-cut]")?.textContent).toBe(onTop);
    expect(label?.querySelector("[data-cut] [title]")).toBeNull();
  });
});
