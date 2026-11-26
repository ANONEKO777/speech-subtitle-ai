import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";

// The stylesheet half of src/models-page/stickyActions.test.tsx (Vitest hands that file an empty CSS import).
const css = readFileSync(new URL("../src/manage.css", import.meta.url), "utf8");

/** The bodies of every block that opens with `head`, each up to its matching brace. */
function blocks(source, head) {
  const found = [];
  for (let at = source.indexOf(`${head} {`); at >= 0; at = source.indexOf(`${head} {`, at + 1)) {
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

const bodyOf = (source, head) => blocks(source, head).join("\n");

describe("the stylesheet keeps the models table's Actions column on screen", () => {
  it("lets the table scroll sideways and asks whether it does", () => {
    expect(bodyOf(css, ".table-wrap")).toContain("overflow-x: auto;");
    expect(bodyOf(css, ".table-wrap")).toContain("container-type: scroll-state;");
  });

  it.each(["@container scroll-state(scrollable: inline)", "@supports not (container-type: scroll-state)"])(
    "pins the cell to the right edge with a solid background under %s",
    (head) => {
      const rule = bodyOf(bodyOf(css, head), "table.inv .actions-cell");
      expect(rule).toContain("position: sticky;");
      expect(rule).toContain("right: 0;");
      expect(rule).toContain("background: var(--surface-1);");
    },
  );

  // A box-shadow here is in the computed style but never painted: the table is border-collapse.
  it("draws the divider as a one pixel pseudo-element, only while more table is to the right", () => {
    const head = "table.inv .actions-cell::before";
    expect(blocks(css, head)).toHaveLength(1);
    const rule = bodyOf(bodyOf(css, "@container scroll-state(scrollable: right)"), head);
    for (const line of ['content: "";', "position: absolute;", "top: 0;", "bottom: 0;", "left: 0;", "width: 1px;", "background: var(--hairline-strong);"]) {
      expect(rule).toContain(line);
    }
  });

  it("wraps a download's failure inside the column instead of widening it", () => {
    const rule = bodyOf(css, ".actions-cell .note-line.job-failure");
    expect(rule).toContain("max-width: 196px;");
    expect(rule).toContain("overflow-wrap: anywhere;");
  });
});

describe("the stylesheet keeps the wizard's recommended title whole in English", () => {
  it("lets only the title with a chip wrap, so the chip drops below the name", () => {
    expect(bodyOf(css, ":root:lang(en) .wizard-profiles .profile-title:has(.chip-tag)")).toContain("flex-wrap: wrap;");
  });
});
