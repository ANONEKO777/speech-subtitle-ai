// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from "vitest";
import { LOCALES, MIRROR_KEY, type Locale, RELEASED_LOCALES, localeFromTag, readMirror, resolveLocale, writeMirror } from "./locale";

const ALL: readonly Locale[] = LOCALES;

describe("resolveLocale", () => {
  it("lets a language chosen by hand win over the browser", () => {
    expect(resolveLocale("en", ["zh-TW"])).toBe("en");
    expect(resolveLocale("zh-TW", ["en-US"])).toBe("zh-TW");
    expect(resolveLocale("ja", ["en-US"], ALL)).toBe("ja");
    expect(resolveLocale("zh-CN", ["en-US"], ALL)).toBe("zh-CN");
  });

  it.each(["zh-TW", "zh-HK", "zh-MO", "zh-Hant", "zh-Hant-TW", "ZH-tw"])("follows %s to Traditional Chinese on auto", (tag) => {
    expect(resolveLocale("auto", [tag])).toBe("zh-TW");
  });

  it.each(["zh-CN", "zh-SG", "zh-Hans", "zh-Hans-CN", "zh"])("follows %s to Simplified Chinese once it is released", (tag) => {
    expect(resolveLocale("auto", [tag], ALL)).toBe("zh-CN");
  });

  it.each(["zh-Hans-HK", "zh-Hans-TW", "zh-Hans-MO"])("lets the script decide before the region: %s is Simplified", (tag) => {
    expect(resolveLocale("auto", [tag], ALL)).toBe("zh-CN");
  });

  it.each(["zh-Hant-CN", "zh-Hant-SG", "zh-Hant-HK"])("lets the script decide before the region: %s is Traditional", (tag) => {
    expect(resolveLocale("auto", [tag], ALL)).toBe("zh-TW");
  });

  it("follows Japanese once it is released", () => {
    expect(resolveLocale("auto", ["ja-JP"], ALL)).toBe("ja");
  });

  it.each(["en", "en-US", "en-GB"])("follows %s to English on auto", (tag) => {
    expect(resolveLocale("auto", [tag])).toBe("en");
  });

  it("falls back to English for anything else, and for no language at all", () => {
    expect(resolveLocale("auto", ["fr-FR", "de"])).toBe("en");
    expect(resolveLocale("auto", [])).toBe("en");
  });

  it("takes the first browser language a released catalog speaks", () => {
    expect(resolveLocale("auto", ["fr", "zh-TW", "en"])).toBe("zh-TW");
    expect(resolveLocale("auto", ["ja", "zh-TW"])).toBe("zh-TW");
    expect(resolveLocale("auto", ["ja", "zh-TW"], ALL)).toBe("ja");
  });

  it("keeps a hidden locale out of the window until it is released, whoever asked for it", () => {
    expect(RELEASED_LOCALES).toEqual(["zh-TW", "en"]);
    expect(resolveLocale("ja", ["en-US"])).toBe("en");
    expect(resolveLocale("ja", ["zh-TW"])).toBe("zh-TW");
    expect(resolveLocale("auto", ["ja-JP"])).toBe("en");
    expect(resolveLocale("zh-CN", [])).toBe("en");
  });
});

describe("localeFromTag", () => {
  it("is null for a language no catalog speaks", () => {
    expect(localeFromTag("ko-KR")).toBeNull();
    expect(localeFromTag("")).toBeNull();
  });
});

describe("the localStorage mirror", () => {
  afterEach(() => {
    vi.restoreAllMocks();
    localStorage.clear();
  });

  it("reads back what it wrote", () => {
    writeMirror("ja");
    expect(readMirror()).toBe("ja");
    expect(localStorage.getItem(MIRROR_KEY)).toBe("ja");
  });

  it("is Traditional Chinese when nothing, or something that is not a language, is stored", () => {
    expect(readMirror()).toBe("zh-TW");
    localStorage.setItem(MIRROR_KEY, "klingon");
    expect(readMirror()).toBe("zh-TW");
  });

  it("keeps auto when auto is what is stored", () => {
    writeMirror("auto");
    expect(readMirror()).toBe("auto");
  });

  it("does not throw when storage is blocked", () => {
    vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
      throw new Error("blocked");
    });
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw new Error("blocked");
    });
    expect(readMirror()).toBe("zh-TW");
    expect(() => writeMirror("en")).not.toThrow();
  });
});
