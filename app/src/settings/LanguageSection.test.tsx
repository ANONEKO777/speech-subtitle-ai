// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { Backend } from "../api/client";
import { I18nProvider } from "../i18n/I18nProvider";
import { MIRROR_KEY } from "../i18n/locale";
import * as api from "../manage/api";
import { LanguageSection } from "./LanguageSection";

vi.mock("../manage/api", async (orig) => ({
  ...(await orig<typeof import("../manage/api")>()),
  saveUiLanguage: vi.fn(() => Promise.resolve({})),
}));

const backend = { port: 1, token: "t" } as Backend;
const options = () => [...screen.getByTestId<HTMLSelectElement>("ui-language").options].map((o) => o.value);
const choose = (value: string) => fireEvent.change(screen.getByTestId("ui-language"), { target: { value } });

beforeEach(() => {
  localStorage.clear();
  document.documentElement.lang = "zh-Hant";
});
afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

const show = (initial: "auto" | "zh-TW" | "en" | "ja" = "zh-TW", released?: Parameters<typeof LanguageSection>[0]["released"]) =>
  render(
    <I18nProvider initial={initial} browserLanguages={["zh-TW"]}>
      <LanguageSection backend={backend} released={released} />
    </I18nProvider>,
  );

describe("LanguageSection", () => {
  it("offers automatic and the released languages only, each written in itself", () => {
    show();
    expect(options()).toEqual(["auto", "zh-TW", "en"]);
    const names = [...screen.getByTestId<HTMLSelectElement>("ui-language").options].map((o) => o.textContent);
    expect(names[0]).toBe("自動（跟隨系統）");
    expect(names[2]).toBe("English");
  });

  it("shows the automatic choice in the language of the window", () => {
    show("en");
    expect(screen.getByRole("option", { name: "Automatic (follow the system)" })).toBeTruthy();
  });

  it("applies a choice at once, saves it, and mirrors it", async () => {
    show("zh-TW");
    choose("en");
    expect(screen.getByTestId("ui-language").closest("section")?.querySelector("h2")?.textContent).toBe("Interface language");
    expect(document.documentElement.lang).toBe("en");
    expect(localStorage.getItem(MIRROR_KEY)).toBe("en");
    expect(api.saveUiLanguage).toHaveBeenCalledWith(backend, "en");
    expect((await screen.findByTestId("language-saved")).textContent).toBe("Applied.");
  });

  it("goes back to the language it had, and says why, when the save fails", async () => {
    vi.mocked(api.saveUiLanguage).mockRejectedValueOnce(new Error("disk full"));
    show("zh-TW");
    choose("en");
    await waitFor(() => expect(screen.getByTestId("language-error").textContent).toBe("無法儲存語言設定：disk full"));
    expect(document.documentElement.lang).toBe("zh-Hant");
    expect(localStorage.getItem(MIRROR_KEY)).toBe("zh-TW");
    expect((screen.getByTestId("ui-language") as HTMLSelectElement).value).toBe("zh-TW");
  });

  it("lists a hidden language only once it is released, and marks a machine translation", () => {
    show("zh-TW", ["zh-TW", "en", "ja"]);
    expect(options()).toEqual(["auto", "zh-TW", "en", "ja"]);
    expect(screen.getByRole("option", { name: "日本語（機器翻譯）" })).toBeTruthy();
  });

  it("keeps a saved hidden language visible instead of showing a blank select", () => {
    show("ja");
    expect(options()).toEqual(["auto", "zh-TW", "en", "ja"]);
    expect((screen.getByTestId("ui-language") as HTMLSelectElement).value).toBe("ja");
  });
});
