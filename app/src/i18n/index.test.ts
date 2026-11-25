import { describe, expect, it } from "vitest";
import { CATALOGS } from "./catalog";
import { type Key, t } from ".";
import { LOCALES } from "./locale";

const placeholders = (text: string) => [...text.matchAll(/\{(\w+)\}/g)].map((m) => m[1]).sort();

describe("t", () => {
  it("returns the text of a key in each locale", () => {
    expect(t("zh-TW", "language.title")).toBe("介面語言");
    expect(t("en", "language.title")).toBe("Interface language");
    expect(t("ja", "language.title")).toBe("表示言語");
    expect(t("zh-CN", "language.title")).toBe("界面语言");
  });

  it("substitutes params, numbers included", () => {
    expect(t("en", "language.machine", { name: "日本語" })).toBe("日本語 (machine translated)");
    expect(t("zh-TW", "language.failed", { reason: "逾時" })).toBe("無法儲存語言設定：逾時");
  });

  it("keeps a missing param visible instead of crashing or printing undefined", () => {
    const loose = t as (locale: "en", key: Key, params?: Record<string, string>) => string;
    expect(loose("en", "language.machine")).toBe("{name} (machine translated)");
    expect(loose("en", "language.machine", {})).toBe("{name} (machine translated)");
  });

  it("is checked by the compiler for the params a key needs", () => {
    const neverCalled = () => {
      // @ts-expect-error a key with a placeholder needs its params
      t("en", "language.machine");
      // @ts-expect-error the param has another name
      t("en", "language.machine", { who: "x" });
      // @ts-expect-error a key without a placeholder takes no params
      t("en", "language.title", { name: "x" });
      // @ts-expect-error a key that is not in the catalog
      t("en", "language.nope");
    };
    expect(neverCalled).toBeTypeOf("function");
  });
});

describe("the catalogs", () => {
  const keys = Object.keys(CATALOGS.en) as Key[];

  it.each(LOCALES)("%s has exactly the keys English has, with text in each", (locale) => {
    expect(Object.keys(CATALOGS[locale]).sort()).toEqual([...keys].sort());
    for (const key of keys) expect(CATALOGS[locale][key].trim(), `${locale} ${key}`).not.toBe("");
  });

  it.each(LOCALES)("%s uses the same placeholders as English for every key", (locale) => {
    for (const key of keys) expect(placeholders(CATALOGS[locale][key]), `${locale} ${key}`).toEqual(placeholders(CATALOGS.en[key]));
  });
});
