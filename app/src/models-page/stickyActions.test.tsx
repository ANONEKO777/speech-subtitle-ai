// @vitest-environment jsdom
import { cleanup, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { Backend } from "../api/client";
import { windowsInventory } from "../manage/screens.fixture";
import { ModelsSection } from "./ModelsSection";

/**
 * At the narrowest window the models table scrolls sideways and its action buttons must stay on screen.
 * jsdom lays nothing out and runs no container query, so this holds the markup the rule targets, and
 * e2e/sticky-actions-css.test.mjs holds the rule. Real rectangles were measured in Edge (docs/i18n-notes/w2.md).
 */
vi.mock("../manage/api", async (orig) => ({
  ...(await orig<typeof import("../manage/api")>()),
  fetchInventory: () => Promise.resolve(windowsInventory()),
}));

const downloads = { list: [], byAsset: new Map(), refresh: () => undefined };

afterEach(cleanup);

describe("the models table keeps its Actions column on screen", () => {
  it("marks the header and the cell of every row, with every action button inside it", async () => {
    render(<ModelsSection backend={{ port: 1, token: "t" } as Backend} downloads={downloads} />);
    const table = await waitFor(() => screen.getByTestId("inv-table"));
    expect(table.parentElement?.classList.contains("table-wrap")).toBe(true);
    const rows = [...table.querySelectorAll("tr")];
    expect(rows.length).toBeGreaterThan(1);
    for (const row of rows) expect(row.lastElementChild?.classList.contains("actions-cell")).toBe(true);
    const buttons = within(table).getAllByRole("button");
    expect(buttons.length).toBeGreaterThan(0);
    for (const button of buttons) expect(button.closest("td.actions-cell")).not.toBeNull();
  });
});
