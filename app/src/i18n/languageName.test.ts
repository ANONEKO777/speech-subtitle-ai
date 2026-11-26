import { describe, expect, it } from "vitest";
import { CATALOGS } from "./catalog";
import type { Key } from ".";
import { languageName } from "./languageName";
import { LOCALES } from "./locale";

describe("languageName", () => {
  it("names a language in the language of the window", () => {
    expect(languageName("en", { code: "zh-TW", name: "Traditional Chinese (Taiwan)", nativeName: "繁體中文（台灣）" })).toBe("Traditional Chinese");
    expect(languageName("en", { code: "ja", nativeName: "日本語" })).toBe("Japanese");
    expect(languageName("en", { code: "ko", nativeName: "한국어" })).toBe("Korean");
    expect(languageName("en", { code: "en", nativeName: "English" })).toBe("English");
  });

  it("keeps the native names a Traditional Chinese window always showed", () => {
    expect(languageName("zh-TW", { code: "zh-TW", name: "Traditional Chinese (Taiwan)", nativeName: "繁體中文（台灣）" })).toBe("繁體中文");
    expect(languageName("zh-TW", { code: "zh-CN", nativeName: "简体中文" })).toBe("简体中文");
    expect(languageName("zh-TW", { code: "ja", nativeName: "日本語" })).toBe("日本語");
    expect(languageName("zh-TW", { code: "vi", nativeName: "Tiếng Việt" })).toBe("Tiếng Việt");
    expect(languageName("zh-TW", { code: "id", nativeName: "Bahasa Indonesia" })).toBe("Bahasa Indonesia");
  });

  it("names a language the catalog does not know yet by the backend's English name in an English window", () => {
    const swedish = { code: "sv", name: "Swedish (Sweden)", nativeName: "Svenska（Sverige）" };
    expect(languageName("en", swedish)).toBe("Swedish");
    expect(languageName("zh-TW", swedish)).toBe("Svenska");
    expect(languageName("ja", swedish)).toBe("Svenska");
  });

  it("falls back to the native name, then to the code, when the backend sends less", () => {
    expect(languageName("en", { code: "sv", nativeName: "Svenska" })).toBe("Svenska");
    expect(languageName("en", { code: "sv" })).toBe("sv");
    expect(languageName("zh-TW", { code: "sv", name: "Swedish" })).toBe("sv");
  });

  it("has a name for every target language the backend offers, in every locale", () => {
    const codes = ["zh-TW", "zh-CN", "en", "ja", "ko", "es", "fr", "de", "pt", "it", "ru", "vi", "th", "id"];
    for (const locale of LOCALES) {
      for (const code of codes) expect(CATALOGS[locale][`lang.${code}` as Key], `${locale} ${code}`).toBeTruthy();
    }
  });
});
