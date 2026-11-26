import { describe, expect, it } from "vitest";
import { CATALOGS } from "./catalog";
import { type Key, t } from ".";
import { languageName } from "./languageName";
import { LOCALES, type Locale } from "./locale";

const said = (locale: Locale) => ((key: Key) => t(locale, key as never)) as never;

describe("languageName", () => {
  it("names a language in the language of the window", () => {
    expect(languageName(said("en"), "zh-TW", "繁體中文（台灣）")).toBe("Traditional Chinese");
    expect(languageName(said("en"), "ja", "日本語")).toBe("Japanese");
    expect(languageName(said("en"), "ko", "한국어")).toBe("Korean");
    expect(languageName(said("en"), "en", "English")).toBe("English");
  });

  it("keeps the native names a Traditional Chinese window always showed", () => {
    expect(languageName(said("zh-TW"), "zh-TW", "繁體中文（台灣）")).toBe("繁體中文");
    expect(languageName(said("zh-TW"), "zh-CN", "简体中文")).toBe("简体中文");
    expect(languageName(said("zh-TW"), "ja", "日本語")).toBe("日本語");
    expect(languageName(said("zh-TW"), "vi", "Tiếng Việt")).toBe("Tiếng Việt");
    expect(languageName(said("zh-TW"), "id", "Bahasa Indonesia")).toBe("Bahasa Indonesia");
  });

  it("falls back to the backend's native name, then to the code, for a language the catalog does not know", () => {
    expect(languageName(said("en"), "sv", "Svenska（Sverige）")).toBe("Svenska");
    expect(languageName(said("zh-TW"), "sv", "Svenska")).toBe("Svenska");
    expect(languageName(said("en"), "sv")).toBe("sv");
  });

  it("has a name for every target language the backend offers, in every locale", () => {
    const codes = ["zh-TW", "zh-CN", "en", "ja", "ko", "es", "fr", "de", "pt", "it", "ru", "vi", "th", "id"];
    for (const locale of LOCALES) {
      for (const code of codes) expect(CATALOGS[locale][`lang.${code}` as Key], `${locale} ${code}`).toBeTruthy();
    }
  });
});
