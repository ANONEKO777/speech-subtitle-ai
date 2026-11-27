// @vitest-environment jsdom
import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { I18nProvider } from "../i18n/I18nProvider";
import { NOT_ENGLISH } from "../i18n/notEnglish";
import { UpdateBanner } from "./UpdateBanner";
import { UpdateSection } from "./UpdateSection";
import * as update from "./update";
import { DAY_MS, UPDATES_KEY, parsePrefs } from "./updatePrefs";
import { type Work, useUpdates } from "./useUpdates";

vi.mock("./update", async (orig) => ({
  ...(await orig<typeof import("./update")>()),
  updateBuildInfo: vi.fn(),
  updateCheck: vi.fn(),
  updateDownload: vi.fn(),
  updateInstall: vi.fn(),
}));

const NEWER: update.Checked = { state: "available", current: "0.1.0", version: "0.2.0", notes: "Faster export.\nA new player." };

beforeEach(() => {
  localStorage.clear();
  vi.mocked(update.updateBuildInfo).mockResolvedValue({ supported: true, current: "0.1.0" });
  vi.mocked(update.updateCheck).mockResolvedValue(NEWER);
  vi.mocked(update.updateDownload).mockResolvedValue();
  vi.mocked(update.updateInstall).mockResolvedValue();
});

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

/** The window as the app builds it: one update state, the banner over the screen and the settings section. */
function Window({ work = null, section = false }: { work?: Work; section?: boolean }) {
  const updates = useUpdates(work, 0);
  return (
    <>
      <UpdateBanner updates={updates} />
      {section && <UpdateSection updates={updates} />}
    </>
  );
}

const stored = () => parsePrefs(localStorage.getItem(UPDATES_KEY));
/** Each round lets React apply what the last one resolved: the shell's answer, then the timer, then the check. */
const settle = async () => {
  for (let i = 0; i < 4; i++) await act(() => new Promise((r) => setTimeout(r, 5)));
};
const start = async (props: { work?: Work; section?: boolean } = {}) => {
  const view = render(<Window {...props} />);
  await settle();
  return view;
};
const click = (id: string) => fireEvent.click(screen.getByTestId(id));

describe("the check at start", () => {
  it("checks once in the background and offers the new version with its notes", async () => {
    await start();
    expect(update.updateCheck).toHaveBeenCalledOnce();
    const banner = screen.getByTestId("update-banner");
    expect(banner.textContent).toContain("有新版 0.2.0（目前 0.1.0）");
    expect(screen.getByTestId("update-banner-notes").textContent).toContain("A new player.");
    expect(stored().lastCheckAt).not.toBeNull();
    expect(update.updateDownload).not.toHaveBeenCalled();
    expect(update.updateInstall).not.toHaveBeenCalled();
  });

  it("does not check again the same day, and offers the version it found without going online", async () => {
    (await start()).unmount();
    await start();
    expect(update.updateCheck).toHaveBeenCalledOnce();
    expect(screen.getByTestId("update-banner").textContent).toContain("0.2.0");
  });

  it("checks again the next day", async () => {
    (await start()).unmount();
    localStorage.setItem(UPDATES_KEY, JSON.stringify({ ...stored(), lastCheckAt: Date.now() - DAY_MS - 1 }));
    await start();
    expect(update.updateCheck).toHaveBeenCalledTimes(2);
  });

  it("says nothing when it is up to date", async () => {
    vi.mocked(update.updateCheck).mockResolvedValue({ state: "upToDate", current: "0.1.0" });
    await start({ section: true });
    expect(screen.queryByTestId("update-banner")).toBeNull();
    expect(screen.queryByTestId("update-uptodate")).toBeNull();
    expect(screen.getByTestId("update-last-checked").textContent).toContain("上次啟動時檢查");
  });

  it("fails silently and keeps the reason for the settings page", async () => {
    const message = "The update server didn't respond within 10 seconds. Try again later.";
    vi.mocked(update.updateCheck).mockRejectedValue({ message, notices: [{ code: "shell.update.timeout", params: {}, message }] });
    await start({ section: true });
    expect(screen.queryByRole("alert")).toBeNull();
    expect(screen.queryByTestId("update-banner")).toBeNull();
    expect(screen.queryByTestId("update-failed")).toBeNull();
    expect(screen.getByTestId("update-last-failed").textContent).toMatch(/^上次啟動時檢查失敗（.+）：更新伺服器沒有在 10 秒內回應。請稍後再試。$/);
    expect(stored().lastFailure?.reason?.notices[0]?.code).toBe("shell.update.timeout");
  });

  it("clears the kept failure when a later check answers", async () => {
    vi.mocked(update.updateCheck).mockRejectedValueOnce("offline");
    (await start()).unmount();
    expect(stored().lastFailure).not.toBeNull();
    localStorage.setItem(UPDATES_KEY, JSON.stringify({ ...stored(), lastCheckAt: 0 }));
    await start();
    expect(stored().lastFailure).toBeNull();
  });

  it("does not run when the person turned it off in settings", async () => {
    vi.mocked(update.updateCheck).mockResolvedValue({ state: "upToDate", current: "0.1.0" });
    const first = await start({ section: true });
    const toggle = screen.getByTestId<HTMLInputElement>("update-at-start-toggle");
    expect(toggle.checked).toBe(true);
    fireEvent.click(toggle);
    expect(stored().checkAtStart).toBe(false);
    first.unmount();
    localStorage.setItem(UPDATES_KEY, JSON.stringify({ ...stored(), lastCheckAt: 0 }));
    await start();
    expect(update.updateCheck).toHaveBeenCalledOnce();
  });

  it("does not run where this build cannot update itself, and the toggle says why", async () => {
    vi.mocked(update.updateBuildInfo).mockResolvedValue({ supported: false, current: "0.1.0" });
    await start({ section: true });
    expect(update.updateCheck).not.toHaveBeenCalled();
    expect(screen.queryByTestId("update-banner")).toBeNull();
    const toggle = screen.getByTestId<HTMLInputElement>("update-at-start-toggle");
    expect(toggle.disabled).toBe(true);
    expect(screen.getByTestId("update-at-start").textContent).toContain("這個平台還沒有自動更新");
  });
});

describe("the banner", () => {
  it("Later hides it until the next start", async () => {
    (await start()).unmount();
    await start();
    click("update-banner-later");
    expect(screen.queryByTestId("update-banner")).toBeNull();
    cleanup();
    await start();
    expect(screen.getByTestId("update-banner")).toBeTruthy();
    expect(update.updateCheck).toHaveBeenCalledOnce();
  });

  it("Skip remembers that version only", async () => {
    (await start()).unmount();
    await start();
    click("update-banner-skip");
    expect(screen.queryByTestId("update-banner")).toBeNull();
    expect(stored().skipped).toBe("0.2.0");
    cleanup();
    await start();
    expect(screen.queryByTestId("update-banner")).toBeNull();
    cleanup();
    vi.mocked(update.updateCheck).mockResolvedValue({ ...NEWER, version: "0.3.0" });
    localStorage.setItem(UPDATES_KEY, JSON.stringify({ ...stored(), lastCheckAt: 0 }));
    await start();
    expect(screen.getByTestId("update-banner").textContent).toContain("0.3.0");
  });

  it("downloads and installs on one click", async () => {
    await start();
    click("update-banner-install");
    await waitFor(() => expect(update.updateInstall).toHaveBeenCalledOnce());
    expect(update.updateDownload).toHaveBeenCalledOnce();
    expect(update.updateCheck).toHaveBeenCalledOnce();
  });

  it("checks again before it downloads a version remembered from an earlier start", async () => {
    (await start()).unmount();
    await start();
    click("update-banner-install");
    await waitFor(() => expect(update.updateInstall).toHaveBeenCalledOnce());
    expect(update.updateCheck).toHaveBeenCalledTimes(2);
    expect(vi.mocked(update.updateCheck).mock.invocationCallOrder[1]).toBeLessThan(vi.mocked(update.updateDownload).mock.invocationCallOrder[0]!);
  });

  it("shows why a download failed and offers it again", async () => {
    vi.mocked(update.updateDownload).mockRejectedValueOnce("下載的更新檔簽章不符，已放棄，不會安裝。");
    await start();
    click("update-banner-install");
    expect((await screen.findByTestId("update-banner-failed")).textContent).toContain("簽章不符");
    expect(update.updateInstall).not.toHaveBeenCalled();
    click("update-banner-install");
    await waitFor(() => expect(update.updateInstall).toHaveBeenCalledOnce());
  });
});

describe("never install while work runs", () => {
  it("disables the button with the reason, and enables it when the work ends", async () => {
    const view = await start({ work: "job" });
    const button = screen.getByTestId<HTMLButtonElement>("update-banner-install");
    expect(button.disabled).toBe(true);
    expect(screen.getByTestId("update-banner-blocked").textContent).toBe("正在處理影片。請等處理完成再安裝，因為安裝會中斷處理。");
    fireEvent.click(button);
    await settle();
    expect(update.updateDownload).not.toHaveBeenCalled();

    view.rerender(<Window work="batch" />);
    expect(screen.getByTestId("update-banner-blocked").textContent).toContain("佇列正在處理");

    view.rerender(<Window work={null} />);
    expect(screen.queryByTestId("update-banner-blocked")).toBeNull();
    click("update-banner-install");
    await waitFor(() => expect(update.updateInstall).toHaveBeenCalledOnce());
  });

  it("does not install when work started during the download, and offers the install when it ends", async () => {
    let finish: () => void = () => undefined;
    vi.mocked(update.updateDownload).mockReturnValueOnce(new Promise((r) => (finish = r)));
    const view = await start();
    click("update-banner-install");
    view.rerender(<Window work="batch" />);
    await act(async () => finish());
    await settle();
    expect(update.updateInstall).not.toHaveBeenCalled();
    const now = screen.getByTestId<HTMLButtonElement>("update-banner-install-now");
    expect(now.disabled).toBe(true);
    fireEvent.click(now);
    await settle();
    expect(update.updateInstall).not.toHaveBeenCalled();

    view.rerender(<Window work={null} />);
    click("update-banner-install-now");
    await waitFor(() => expect(update.updateInstall).toHaveBeenCalledOnce());
  });

  it("holds the settings page's install button too", async () => {
    vi.mocked(update.updateCheck).mockResolvedValue({ state: "upToDate", current: "0.1.0" });
    const view = await start({ work: "batch", section: true });
    vi.mocked(update.updateCheck).mockResolvedValue(NEWER);
    click("update-check");
    fireEvent.click(await screen.findByTestId("update-download"));
    const install = await screen.findByTestId<HTMLButtonElement>("update-install");
    expect(install.disabled).toBe(true);
    expect(screen.getByTestId("update-install-blocked").textContent).toContain("佇列正在處理");
    view.rerender(<Window work={null} section />);
    click("update-install");
    await waitFor(() => expect(update.updateInstall).toHaveBeenCalledOnce());
  });
});

describe("in English", () => {
  it("says everything in English: the banner, the reason it waits, and the settings section", async () => {
    vi.mocked(update.updateCheck).mockRejectedValueOnce("offline");
    (await start()).unmount();
    localStorage.setItem(UPDATES_KEY, JSON.stringify({ ...JSON.parse(localStorage.getItem(UPDATES_KEY) ?? "{}"), found: NEWER, lastCheckAt: Date.now() }));
    render(
      <I18nProvider initial="en">
        <Window work="batch" section />
      </I18nProvider>,
    );
    await settle();
    const banner = screen.getByTestId("update-banner").textContent ?? "";
    expect(banner).toContain("Version 0.2.0 is available (you have 0.1.0).");
    expect(banner).toContain("Download and install");
    expect(banner).toContain("Skip this version");
    expect(screen.getByTestId("update-banner-blocked").textContent).toBe("The batch is running. Install when it's done or paused, because installing stops the processing.");
    expect(screen.getByTestId("update-at-start").textContent).toContain("Check for updates at startup");
    expect(screen.getByTestId("update-last-failed").textContent).toMatch(/^The last check at startup failed \(.+\): offline$/);
    expect(document.body.textContent).not.toMatch(NOT_ENGLISH);
  });
});
