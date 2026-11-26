// @vitest-environment jsdom
import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { I18nProvider, useI18n, useT } from "./I18nProvider";
import { MIRROR_KEY } from "./locale";

function Probe() {
  const { t, locale } = useT();
  const i18n = useI18n();
  return (
    <div>
      <p data-testid="text">{t("language.title")}</p>
      <p data-testid="locale">{locale}</p>
      <button type="button" data-testid="to-en" onClick={() => i18n?.setUiLanguage("en")} />
      <button type="button" data-testid="to-auto" onClick={() => i18n?.setUiLanguage("auto")} />
    </div>
  );
}

beforeEach(() => {
  localStorage.clear();
  document.documentElement.lang = "zh-Hant";
});
afterEach(cleanup);

describe("outside a provider", () => {
  it("speaks Traditional Chinese, so a bare render keeps its text", () => {
    render(<Probe />);
    expect(screen.getByTestId("text").textContent).toBe("介面語言");
    expect(screen.getByTestId("locale").textContent).toBe("zh-TW");
    expect(document.documentElement.lang).toBe("zh-Hant");
  });
});

describe("I18nProvider", () => {
  it("sets the lang attribute of the page and the text from the language it starts with", () => {
    render(
      <I18nProvider initial="en">
        <Probe />
      </I18nProvider>,
    );
    expect(screen.getByTestId("text").textContent).toBe("Interface language");
    expect(document.documentElement.lang).toBe("en");
  });

  it("names the page and the window in the language it starts with and follows a change", () => {
    render(
      <I18nProvider initial="zh-TW">
        <Probe />
      </I18nProvider>,
    );
    expect(document.title).toBe("字幕翻譯");
    fireEvent.click(screen.getByTestId("to-en"));
    expect(document.title).toBe("Video Subtitle Translator");
  });

  it("re-renders at once when the language changes, and mirrors the choice", () => {
    render(
      <I18nProvider initial="zh-TW">
        <Probe />
      </I18nProvider>,
    );
    expect(document.documentElement.lang).toBe("zh-Hant");
    fireEvent.click(screen.getByTestId("to-en"));
    expect(screen.getByTestId("text").textContent).toBe("Interface language");
    expect(document.documentElement.lang).toBe("en");
    expect(localStorage.getItem(MIRROR_KEY)).toBe("en");
  });

  it("starts from the mirror, before the backend answers", () => {
    localStorage.setItem(MIRROR_KEY, "en");
    render(
      <I18nProvider>
        <Probe />
      </I18nProvider>,
    );
    expect(screen.getByTestId("locale").textContent).toBe("en");
  });

  it("shows Traditional Chinese on a fresh install, even when the browser speaks English", () => {
    render(
      <I18nProvider browserLanguages={["en-US"]}>
        <Probe />
      </I18nProvider>,
    );
    expect(screen.getByTestId("locale").textContent).toBe("zh-TW");
  });

  it("follows the browser language on auto, and English for a language it does not speak", () => {
    const { rerender } = render(
      <I18nProvider initial="auto" browserLanguages={["zh-HK"]}>
        <Probe />
      </I18nProvider>,
    );
    expect(screen.getByTestId("locale").textContent).toBe("zh-TW");
    rerender(
      <I18nProvider initial="auto" browserLanguages={["ko"]}>
        <Probe />
      </I18nProvider>,
    );
    expect(screen.getByTestId("locale").textContent).toBe("en");
    act(() => screen.getByTestId("to-auto").click());
    expect(document.documentElement.lang).toBe("en");
  });
});

describe("useT", () => {
  it("is checked by the compiler like t: a key with a placeholder needs its params, and a plural base is not a key", () => {
    const neverCalled = () => {
      const { t, plural } = useT();
      // @ts-expect-error a key with a placeholder needs its params
      t("language.machine");
      // @ts-expect-error a plural base is not a key
      t("queue.added");
      // @ts-expect-error a key that is not a plural base
      plural("language.title", 1);
      return [t("queue.view"), plural("queue.added", 2), plural("hw.optionMissing", 2, { size: "1 GB" })];
    };
    expect(neverCalled).toBeTypeOf("function");
  });
});
