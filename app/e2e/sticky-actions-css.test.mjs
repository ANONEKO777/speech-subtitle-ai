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
});
