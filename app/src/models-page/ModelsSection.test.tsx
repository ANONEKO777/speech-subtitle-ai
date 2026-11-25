// @vitest-environment jsdom
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { Backend } from "../api/client";
import { macInventory, windowsInventory } from "../manage/screens.fixture";
import type { Inventory } from "../manage/types";
import { ModelsSection } from "./ModelsSection";

const mocks = vi.hoisted(() => ({ inventory: null as Inventory | null }));

vi.mock("../manage/api", async (orig) => ({
  ...(await orig<typeof import("../manage/api")>()),
  fetchInventory: vi.fn(() => Promise.resolve(mocks.inventory)),
}));

const backend = { port: 1, token: "t" } as Backend;
const downloads = { list: [], byAsset: new Map(), refresh: () => undefined };

async function show(inventory: Inventory): Promise<void> {
  mocks.inventory = inventory;
  render(<ModelsSection backend={backend} downloads={downloads} />);
  await waitFor(() => screen.getByTestId("inv-table"));
}

afterEach(cleanup);

describe("the Models page", () => {
  it("reads as it always did on Windows: a size to download and a download button for what is missing", async () => {
    await show(windowsInventory());
    expect(screen.getByTestId("inv-whispercpp-b5454-win-cuda").textContent).toMatchInlineSnapshot(`"whispercpp-b5454-win-cuda執行檔 · whisper.cpp · MIT未安裝——登錄版本 1458 MB下載大小——下載"`);
    expect(screen.getByTestId("act-whispercpp-b5454-win-cuda-download").textContent).toBe("下載");
    expect(screen.queryByTestId("inv-whispercpp-b5454-win-cuda-build")).toBeNull();
  });

  it("shows the program a Mac builds for itself with no size and no download, and names the script", async () => {
    await show(macInventory());
    const row = screen.getByTestId("inv-whispercpp-b5454-macos-metal");
    expect(row.textContent).not.toContain("0 B");
    expect(row.textContent).not.toContain("下載");
    expect(row.textContent).toContain("在這台 Mac 上自行建置（scripts/mac/build_whisper_cli.sh，步驟見 docs/MACOS.md）");
    expect(screen.queryByTestId("act-whispercpp-b5454-macos-metal-download")).toBeNull();
    expect(screen.getByTestId("inv-llama-b8000-macos-metal").textContent).toContain("38.1 MB下載大小");
    expect(screen.getByTestId("act-llama-b8000-macos-metal-download").textContent).toBe("下載");
  });

  it("offers delete for a program the Mac built once it is there, and size on disk", async () => {
    const inv = macInventory();
    const built = inv.assets[0];
    if (!built) throw new Error("fixture");
    await show({ ...inv, assets: [{ ...built, state: "installed", sizeOnDisk: 800_000, path: "/r/whisper-cli", shaState: "unchecked" }] });
    expect(screen.getByTestId("act-whispercpp-b5454-macos-metal-delete")).toBeTruthy();
    expect(screen.queryByTestId("act-whispercpp-b5454-macos-metal-repair")).toBeNull();
    expect(screen.queryByTestId("act-whispercpp-b5454-macos-metal-redownload")).toBeNull();
    expect(screen.queryByTestId("inv-whispercpp-b5454-macos-metal-build")).toBeNull();
    expect(screen.getByTestId("inv-whispercpp-b5454-macos-metal").textContent).toContain("781 KB");
  });
});
