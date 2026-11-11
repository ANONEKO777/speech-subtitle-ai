// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { Backend } from "../api/client";
import * as api from "../manage/api";
import { LicensesSection, PROJECT_URL } from "./LicensesSection";

vi.mock("../manage/api", async (orig) => ({
  ...(await orig<typeof import("../manage/api")>()),
  fetchLicenses: vi.fn(() => Promise.resolve([])),
  openUrl: vi.fn(() => Promise.resolve()),
}));

const backend = { port: 1, token: "t" } as Backend;

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

describe("LicensesSection", () => {
  it("names the AGPL source address and the FFmpeg LGPL notice", () => {
    render(<LicensesSection backend={backend} />);
    expect(screen.getByTestId("project-source-link").textContent).toBe(PROJECT_URL);
    expect(screen.getByTestId("ffmpeg-notice").textContent).toContain("LGPL-3.0-or-later");
  });

  it("hands a link to the app to open and never opens it in the page when the app refuses", async () => {
    vi.mocked(api.openUrl).mockRejectedValueOnce(new Error("not a host this app opens"));
    const open = vi.spyOn(window, "open");
    vi.spyOn(console, "error").mockImplementation(() => undefined);
    render(<LicensesSection backend={backend} />);
    fireEvent.click(screen.getByTestId("project-source-link"));
    await vi.waitFor(() => expect(console.error).toHaveBeenCalled());
    expect(api.openUrl).toHaveBeenCalledWith(PROJECT_URL);
    expect(open).not.toHaveBeenCalled();
  });
});
