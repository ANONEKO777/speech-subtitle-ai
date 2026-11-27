import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";
import { HTML_LANG } from "./locale";

const css = readFileSync(new URL("../styles.css", import.meta.url), "utf8").replace(/\/\*[\s\S]*?\*\//g, "");
/** A selector list split at its top-level commas, so `:is(:lang(a), :lang(b))` stays one selector. */
function splitList(list: string): string[] {
  const out: string[] = [];
  let depth = 0;
  let start = 0;
  [...list].forEach((c, i) => {
    if (c === "(") depth++;
    if (c === ")") depth--;
    if (c === "," && depth === 0) {
      out.push(list.slice(start, i));
      start = i + 1;
    }
  });
  return [...out, list.slice(start)].map((s) => s.trim());
}
const selectors = [...css.matchAll(/([^{}]+)\{/g)].flatMap((m) => splitList(m[1])).filter((s) => s.includes(":lang("));

describe("the lang-aware font rules in styles.css", () => {
  it("scope every :lang() rule to the root or to an element that declares its own language", () => {
    // An unscoped :lang(ja) matches every element of a Japanese window and replaces each one's own font stack.
    const loose = selectors.filter((s) => !/^(:root:lang\(|\[lang\]:not\(:root\):)/.test(s));
    expect(loose).toEqual([]);
  });

  it("give the root of each window language other than English its own CJK stack", () => {
    for (const tag of [HTML_LANG.ja, HTML_LANG["zh-CN"]]) expect(css).toMatch(new RegExp(`:root:lang\\(${tag}\\)\\s*\\{[^}]*--font-sans:`));
  });

  it("draw text that declares Japanese, Traditional or Simplified Chinese with that script's fonts in any window", () => {
    expect(selectors).toContain("[lang]:not(:root):lang(ja)");
    expect(css).toMatch(/\[lang\]:not\(:root\):is\([^)]*:lang\(zh-TW\)[^{]*\{\s*font-family: var\(--font-sans-hant\)/);
    expect(css).toMatch(/\[lang\]:not\(:root\):is\([^)]*:lang\(zh-CN\)[^{]*\{\s*font-family: var\(--font-sans-hans\)/);
  });
});
