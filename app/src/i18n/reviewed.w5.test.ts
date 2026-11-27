import { readFileSync, writeFileSync } from "node:fs";
import { describe, expect, it } from "vitest";
import { CATALOGS, type Key } from "./catalog";

/**
 * The zh-CN and ja text a person read in W5. A reviewed entry that changes fails here until someone reads
 * the new text and runs `W5_REVIEWED=write npx vitest run src/i18n/reviewed.w5.test.ts`. A key added after
 * W5 is a machine translation nobody has read yet, and does not fail here.
 */
const FIXTURE = new URL("./reviewed.w5.json", import.meta.url);
const LOCALES = ["zh-CN", "ja"] as const;
type Reviewed = Record<(typeof LOCALES)[number], Record<string, string>>;

const current = (): Reviewed =>
  Object.fromEntries(LOCALES.map((locale) => [locale, Object.fromEntries(Object.keys(CATALOGS.en).sort().map((k) => [k, CATALOGS[locale][k as Key]]))])) as Reviewed;

if (process.env.W5_REVIEWED === "write") writeFileSync(FIXTURE, JSON.stringify(current(), null, 1) + "\n");
const reviewed = JSON.parse(readFileSync(FIXTURE, "utf8")) as Reviewed;

describe.each(LOCALES)("reviewed %s text", (locale) => {
  it("is unchanged since a person read it", () => {
    const now = current()[locale];
    const changed = Object.entries(reviewed[locale]).filter(([key, text]) => key in now && now[key] !== text);
    expect(changed.map(([key]) => key)).toEqual([]);
  });
});
