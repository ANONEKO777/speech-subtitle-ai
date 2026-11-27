// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { plainText } from "../i18n/said";
import type { Backend } from "../api/client";
import { windowsInventory } from "../manage/screens.fixture";
import type { DownloadJob } from "../manage/types";
import { ModelsSection } from "./ModelsSection";

/**
 * At the narrowest window the models table scrolls sideways and its action buttons must stay on screen.
 * jsdom lays nothing out and runs no container query, so this holds the markup the rule targets, and
 * e2e/sticky-actions-css.test.mjs holds the rule. Real rectangles were measured in Edge (docs/i18n-notes/w2.md).
 */
vi.mock("../manage/api", async (orig) => ({
  ...(await orig<typeof import("../manage/api")>()),
  fetchInventory: () => Promise.resolve(windowsInventory()),
  verifyAsset: () => Promise.reject(new Error("a job is running")),
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

  it("marks a download's failure in that cell as the note that must not widen it", async () => {
    const id = "whispercpp-b5454-win-cuda";
    const failed: DownloadJob = {
      id: "j1", assetId: id, state: "failed", bytesDone: 0, bytesTotal: 1, speedBps: 0, resumedFrom: 0, retries: 0, note: null,
      failure: { kind: "hash_mismatch", message: plainText("it failed its SHA256 check") },
    };
    render(<ModelsSection backend={{ port: 1, token: "t" } as Backend} downloads={{ ...downloads, list: [failed], byAsset: new Map([[id, failed]]) }} />);
    const note = await waitFor(() => screen.getByTestId(`inv-${id}-note`));
    expect(note.textContent).toBe("it failed its SHA256 check");
    expect(note.getAttribute("role")).toBe("alert");
    expect(note.matches("td.actions-cell > .note-line.job-failure")).toBe(true);
  });

  it("does not cap any other note in that cell, such as a refused action", async () => {
    render(<ModelsSection backend={{ port: 1, token: "t" } as Backend} downloads={downloads} />);
    const button = (await waitFor(() => screen.getAllByTestId(/^act-.+-verify$/)))[0]!;
    const id = button.getAttribute("data-testid")!.slice("act-".length, -"-verify".length);
    fireEvent.click(button);
    const note = await waitFor(() => screen.getByTestId(`inv-${id}-note`));
    expect(note.textContent).toContain("a job is running");
    expect(note.matches("td.actions-cell > .note-line")).toBe(true);
    expect(note.classList.contains("job-failure")).toBe(false);
  });
});
