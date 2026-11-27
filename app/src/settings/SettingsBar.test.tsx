// @vitest-environment jsdom
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { I18nProvider } from "../i18n/I18nProvider";
import type { Locale } from "../i18n/locale";
import { SettingsBar } from "./SettingsBar";
import { DEFAULTS } from "./settings";

/**
 * jsdom lays nothing out, so these tests give the text and the box that holds it their widths: each character is
 * 10 px wide, the toolbar's type is 10 px (so one em is one character), and every box is `room` px wide.
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
  const real = window.getComputedStyle.bind(window);
  vi.spyOn(window, "getComputedStyle").mockImplementation((element, pseudo) => {
    const style = real(element, pseudo);
    if (element.classList.contains("cut-name")) Object.defineProperty(style, "fontSize", { value: "10px" });
    return style;
  });
}

const barOf = (locale: Locale, langName: string) => (
  <I18nProvider initial={locale}>
    <SettingsBar langName={langName} settings={DEFAULTS} onChange={() => undefined} />
  </I18nProvider>
);
const bar = (locale: Locale, langName: string) => render(barOf(locale, langName));

/** The two places the name is shown: on the middle button and in the switch's words. */
const places = (view: ReturnType<typeof bar>) => [...view.container.querySelectorAll<HTMLElement>(".cut-name")];
/** For each place: whether the name may shrink, and whether it is shortened now. */
const states = (view: ReturnType<typeof bar>) => places(view).map((place) => [place.hasAttribute("data-shrinks"), place.hasAttribute("data-cut")]);

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

describe("which names the toolbar may shorten", () => {
  it.each(["日本語", "繁體中文", "ไทย", "Five."])("never lets %s shrink", (name) => {
    measured(1000);
    expect(states(bar("en", name))).toEqual([
      [false, false],
      [false, false],
    ]);
  });

  it("lets a name longer than five characters of type shrink, keeping three and a half of them and the words around it", () => {
    measured(1000);
    const [button, words] = places(bar("en", "Korean"));
    for (const place of [button, words]) {
      expect(place?.hasAttribute("data-shrinks")).toBe(true);
      expect(place?.style.getPropertyValue("--name-kept")).toBe("3.5em");
    }
    expect(button?.style.getPropertyValue("--name-rest")).toBe("0px");
    expect(words?.style.getPropertyValue("--name-rest")).toBe(`${" on top".length * 10}px`);
  });

  it("calls a name shortened as soon as its box is a pixel short of it", () => {
    const name = "Bahasa Indonesia";
    measured(name.length * 10 - 1);
    const [button] = places(bar("en", name));
    expect(button?.hasAttribute("data-cut")).toBe(true);
    expect(button?.querySelector("[title]")?.getAttribute("title")).toBe(name);
  });

  it("measures again when the language playing changes, though no box changed its size", () => {
    measured(150);
    const view = bar("en", "Thai");
    expect(states(view)).toEqual([
      [false, false],
      [false, false],
    ]);
    view.rerender(barOf("en", "Bahasa Indonesia"));
    expect(states(view)).toEqual([
      [true, true],
      [true, true],
    ]);
    expect(screen.getByRole("switch").getAttribute("aria-label")).toBe("Bahasa Indonesia on top");
    view.rerender(barOf("en", "Thai"));
    expect(states(view)).toEqual([
      [false, false],
      [false, false],
    ]);
    expect(screen.getByRole("switch").getAttribute("aria-label")).toBeNull();
  });
});
