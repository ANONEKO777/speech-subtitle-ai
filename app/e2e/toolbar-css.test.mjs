import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";

// The stylesheet half of the player toolbar's layout. jsdom lays nothing out, so this only pins the rules: the proof
// that they keep the toolbar on one row is a matrix of headless renders, which is not in CI.
const read = (name) => readFileSync(new URL(`../src/${name}`, import.meta.url), "utf8").replace(/\r\n/g, "\n");
const css = read("styles.css");

/** The bodies of every rule or at-rule whose selector is exactly `head`, each up to its matching brace. */
function blocks(source, head) {
  const found = [];
  for (let at = source.indexOf(`${head} {`); at >= 0; at = source.indexOf(`${head} {`, at + 1)) {
    const before = source.slice(0, at).replace(/\/\*[\s\S]*?\*\//g, "").trimEnd();
    if (before !== "" && !before.endsWith("}") && !before.endsWith("{")) continue;
    const open = at + head.length + 1;
    let depth = 0;
    for (let i = open; i < source.length; i++) {
      if (source[i] === "{") depth++;
      if (source[i] === "}" && --depth === 0) {
        found.push(source.slice(open + 1, i));
        break;
      }
    }
  }
  return found;
}

/** The declarations of the one rule for `head` outside any at-rule block named in `within`. */
function rule(head, within) {
  const source = within === undefined ? css.replace(/^@(media|container)[^\n]*\{\n[\s\S]*?\n\}\n/gm, "") : blocks(css, within).join("\n").replace(/^ {2}/gm, "");
  const found = blocks(source, head);
  expect(found, `${within ?? "top level"}: ${head}`).toHaveLength(1);
  return found[0].replace(/\/\*[\s\S]*?\*\//g, "");
}

const WIDE = "@media (min-width: 1151px)";
const NARROW = "@media (max-width: 1150px)";

describe("the stylesheet keeps the player toolbar on one row for a language name of any length", () => {
  it("does not let the player toolbar wrap, and keeps the path box at least 66 px, 130 in a wide window", () => {
    expect(rule("header:has(.settings)")).toContain("flex-wrap: nowrap;");
    expect(rule("header:has(.settings)")).toContain("--path-floor: 66px;");
    expect(rule("header:has(.settings)", WIDE)).toContain("--path-floor: 130px;");
    expect(rule("header:has(.settings) .field")).toContain("min-width: calc(var(--path-floor) + 50px);");
    expect(rule("header:has(.settings) .field input")).toContain("width: 0;");
    expect(rule(".settings")).not.toContain("flex-wrap: wrap;");
  });

  it("holds a Traditional Chinese window to the headless figures of the toolbar it already had", () => {
    expect(rule(":root:lang(zh-Hant) header:has(.settings)")).toContain("--path-floor: 64.5px;");
    expect(rule(":root:lang(zh-Hant) header:has(.settings)", WIDE)).toContain("--path-floor: 127.5px;");
  });

  it("takes what the row is short of from the import bar's spare width, then the sliders and the switch's words, then the middle button", () => {
    expect(rule("header:has(.settings) .import")).toContain("flex-shrink: 100000;");
    expect(rule("header:has(.settings) .import")).toContain("min-width: min-content;");
    expect(rule(".settings .tools")).toContain("flex-shrink: 100000;");
    expect(rule(".settings .control.range")).toContain("flex-shrink: 100000;");
    expect(rule(".settings .control.range")).toContain("grid-template-columns: auto minmax(38px, var(--toolbar-slider, 84px)) auto;");
    expect(rule(".settings .range .slider")).toContain("width: 100%;");
    expect(rule(".settings .switch")).toContain("flex: none;");
  });

  it("keeps the four slider widths the toolbar had, as the most each slider takes", () => {
    expect(rule(".slider")).toContain("width: var(--toolbar-slider, 84px);");
    expect(rule("header:has(.queue-chip)")).toContain("--toolbar-slider: 66px;");
    expect(rule("header", NARROW)).toContain("--toolbar-slider: 56px;");
    expect(rule("header:has(.queue-chip)", NARROW)).toContain("--toolbar-slider: 38px;");
  });

  it("shortens a language name with an ellipsis and keeps 3.5em of it and the words around it", () => {
    expect(rule(".cut-name")).toContain("grid-template-columns: minmax(min(calc(3.5em + var(--name-rest, 0px)), var(--name-full, 0px)), max-content);");
    expect(rule(".cut-name > span")).toContain("white-space: nowrap;");
    // a box that clips while the name is whole changes the pixels of the usual toolbar
    expect(rule(".cut-name > span")).not.toContain("overflow");
    const clip = rule(".cut-name[data-cut] > span,\n.cut-name[data-cut] > span > span");
    for (const line of ["min-width: 0;", "overflow: hidden;", "text-overflow: ellipsis;"]) expect(clip).toContain(line);
    const lines = blocks(css, ".cut-name[data-cut] > span").at(-1);
    expect(lines).toContain("display: flex;");
    expect(lines).toContain("white-space: pre;");
  });

  it("gives the English toolbar its narrower button padding and column gap", () => {
    expect(rule(":root:lang(en) header .seg button,\n:root:lang(en) header .import button")).toContain("padding-inline: 7px;");
    expect(rule(":root:lang(en) header")).toContain("column-gap: var(--space-3);");
  });

  it("lets a language picker grow to the label it shows", () => {
    expect(rule(".target-pick select")).toContain("field-sizing: content;");
    for (const head of [".target-pick select", ".target-pick select[data-experimental=\"true\"]", ":root:lang(en) .target-pick select", ":root:lang(en) .target-pick select[data-experimental=\"true\"]"]) {
      expect(rule(head)).toMatch(/min-width: \d+px;/);
      expect(rule(head)).not.toMatch(/(^|[^-])width: \d+px;/);
    }
  });
});

describe("the stylesheet keeps the player's control row inside the picture", () => {
  it("holds the controls to the picture's width and lets only the volume slider give way", () => {
    expect(rule(".controls")).toContain("grid-template-columns: minmax(0, 1fr);");
    expect(rule(".button-row > :not(.grow, .volume)")).toContain("flex: none;");
    expect(rule(".slider.volume")).toContain("flex: 0 1 64px;");
    expect(rule(".slider.volume")).toContain("min-width: 40px;");
    expect(rule(".slider.volume", "@container (max-width: 640px)")).toContain("margin: 0 var(--space-1);");
  });
});

describe("the stylesheet keeps a library title clear of the button over it", () => {
  it("ends the title before the button in every window language", () => {
    expect(rule(".lib-title", "@container (max-width: 520px)")).toContain("padding-right: 28px;");
    expect(css).not.toContain(":root:lang(en) .lib-title");
  });
});

describe("the stylesheet keeps the licenses table's row dividers in line", () => {
  it("does not turn a table cell into a flex box", () => {
    const manage = read("manage.css");
    expect(blocks(manage, ".links").join("")).not.toContain("!important");
  });
});
