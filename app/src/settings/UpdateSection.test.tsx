// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { EMPTY_BATCH, type BatchItem } from "../batch/model";
import * as update from "./update";
import { UpdateSectionAlone as UpdateSection } from "./updateTestkit";
import { holdingWork, parseBackendWork, windowWork } from "./work";

vi.mock("./update", async (orig) => ({
  ...(await orig<typeof import("./update")>()),
  updateBuildInfo: vi.fn(() => Promise.resolve({ supported: true, current: "0.1.0" })),
  updateCheck: vi.fn(),
  updateDownload: vi.fn(() => Promise.resolve()),
  updateInstall: vi.fn(() => Promise.resolve()),
}));

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

const NEW_VERSION: update.Checked = { state: "available", current: "0.1.0", version: "0.2.0", notes: null };

describe("UpdateSection", () => {
  it("checks nothing until the button is pressed", () => {
    render(<UpdateSection />);
    expect(update.updateCheck).not.toHaveBeenCalled();
    expect(screen.getByTestId("update-check").textContent).toContain("檢查更新");
  });

  it("shows checking, then up to date", async () => {
    let finish: (c: update.Checked) => void = () => undefined;
    vi.mocked(update.updateCheck).mockReturnValueOnce(new Promise((r) => (finish = r)));
    render(<UpdateSection />);
    fireEvent.click(screen.getByTestId("update-check"));
    expect(await screen.findByText(/正在檢查更新/)).toBeTruthy();
    expect((screen.getByTestId("update-check") as HTMLButtonElement).disabled).toBe(true);
    finish({ state: "upToDate", current: "0.1.0" });
    expect((await screen.findByTestId("update-uptodate")).textContent).toContain("已是最新版");
  });

  it("offers the new version, downloads it, then installs only on the second press", async () => {
    vi.mocked(update.updateCheck).mockResolvedValueOnce(NEW_VERSION);
    render(<UpdateSection />);
    fireEvent.click(screen.getByTestId("update-check"));
    fireEvent.click(await screen.findByTestId("update-download"));
    await screen.findByTestId("update-downloaded");
    expect(update.updateDownload).toHaveBeenCalledOnce();
    expect(update.updateInstall).not.toHaveBeenCalled();
    fireEvent.click(screen.getByTestId("update-install"));
    await vi.waitFor(() => expect(update.updateInstall).toHaveBeenCalledOnce());
  });

  it("shows the plain reason when the check fails, and allows another try", async () => {
    vi.mocked(update.updateCheck).mockRejectedValueOnce("連不上更新伺服器。請確認網路連線，稍後再試。");
    render(<UpdateSection />);
    fireEvent.click(screen.getByTestId("update-check"));
    expect((await screen.findByTestId("update-failed")).textContent).toBe("連不上更新伺服器。請確認網路連線，稍後再試。");
    expect((screen.getByTestId("update-check") as HTMLButtonElement).disabled).toBe(false);
  });

  it("shows a failed download without offering the install", async () => {
    vi.mocked(update.updateCheck).mockResolvedValueOnce(NEW_VERSION);
    vi.mocked(update.updateDownload).mockRejectedValueOnce("下載的更新檔簽章不符，已放棄，不會安裝。");
    render(<UpdateSection />);
    fireEvent.click(screen.getByTestId("update-check"));
    fireEvent.click(await screen.findByTestId("update-download"));
    expect((await screen.findByTestId("update-failed")).textContent).toContain("簽章不符");
    expect(screen.queryByTestId("update-install")).toBeNull();
    expect(screen.queryByTestId("update-retry")).toBeNull();
  });

  it("names its own button when a download stalls, and offers that button again", async () => {
    const message = "The download stopped receiving data partway, so the app gave up on it. Check your internet connection.";
    vi.mocked(update.updateCheck).mockResolvedValue(NEW_VERSION);
    vi.mocked(update.updateDownload).mockRejectedValueOnce({ message, notices: [{ code: "shell.update.stalled", params: {}, message }] });
    render(<UpdateSection />);
    fireEvent.click(screen.getByTestId("update-check"));
    fireEvent.click(await screen.findByTestId("update-download"));
    expect((await screen.findByTestId("update-failed")).textContent).toBe("更新檔下載到一半沒有再收到資料，已經放棄。請確認網路連線。");
    expect(screen.getByTestId("update-retry").textContent).toBe("要再試一次，請按「下載更新」。");
    expect(screen.getByTestId("update-download").textContent).toBe("下載更新");
    fireEvent.click(screen.getByTestId("update-download"));
    expect(await screen.findByTestId("update-install")).toBeTruthy();
  });
});

describe("what holds the install", () => {
  const item = (state: BatchItem["state"]) => ({ state }) as BatchItem;
  it("names the window's running job, a running batch, or nothing", () => {
    expect(windowWork(true, EMPTY_BATCH)).toBe("job");
    expect(windowWork(false, EMPTY_BATCH)).toBeNull();
    expect(windowWork(false, { ...EMPTY_BATCH, items: [item("running")] })).toBe("batch");
    expect(windowWork(false, { ...EMPTY_BATCH, items: [item("queued")] })).toBe("batch");
    expect(windowWork(false, { ...EMPTY_BATCH, paused: true, items: [item("queued")] })).toBeNull();
    expect(windowWork(false, { ...EMPTY_BATCH, paused: true, items: [item("running")] })).toBe("batch");
    expect(windowWork(false, { ...EMPTY_BATCH, items: [item("done"), item("failed"), item("cancelled"), item("paused")] })).toBeNull();
  });
});

describe("what the backend says it is doing", () => {
  it("keeps the kinds it knows, in the backend's order, and drops the rest", () => {
    expect(parseBackendWork({ work: ["download", "selftest"] })).toEqual(["download", "selftest"]);
    expect(parseBackendWork({ work: ["batch", "toString", 3, "move"] })).toEqual(["move"]);
    expect(parseBackendWork(null)).toEqual([]);
    expect(parseBackendWork({ work: "download" })).toEqual([]);
  });

  it("puts the window's own work first, then the backend's first kind", () => {
    expect(holdingWork("batch", ["download"])).toBe("batch");
    expect(holdingWork(null, ["move", "selftest"])).toBe("move");
    expect(holdingWork(null, [])).toBeNull();
  });
});

describe("parseChecked", () => {
  it("refuses a result it does not understand", () => {
    expect(() => update.parseChecked({ state: "weird" })).toThrow();
  });
});
