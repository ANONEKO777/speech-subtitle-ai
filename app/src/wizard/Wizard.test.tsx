// @vitest-environment jsdom
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { Backend } from "../api/client";
import { licenses, macView, windowsView } from "../manage/screens.fixture";
import type { ProfileView } from "../manage/types";
import { Wizard } from "./Wizard";

const mocks = vi.hoisted(() => ({ view: null as ProfileView | null }));

vi.mock("../manage/api", async (orig) => ({
  ...(await orig<typeof import("../manage/api")>()),
  fetchProfile: vi.fn(() => Promise.resolve(mocks.view)),
  fetchLicenses: vi.fn(() => Promise.resolve(licenses)),
}));
vi.mock("../manage/useDownloads", () => ({ useDownloads: () => ({ list: [], byAsset: new Map(), refresh: () => undefined }) }));

const backend = { port: 1, token: "t" } as Backend;

async function choose(view: ProfileView, licensed = true): Promise<HTMLElement> {
  mocks.view = view;
  render(<Wizard backend={backend} onExit={() => undefined} />);
  await waitFor(() => screen.getByTestId("wizard-choose"));
  if (licensed) await waitFor(() => screen.getByTestId("wizard-license-whisper-large-v3-turbo"));
  return screen.getByTestId("wizard-choose");
}

afterEach(cleanup);

describe("the wizard's profile step", () => {
  it("reads as it always did on Windows", async () => {
    const text = (await choose(windowsView())).textContent;
    expect(text).toMatchInlineSnapshot(`"RTX 4090 · 顯示記憶體 24.0 GB · 驅動 596.36記憶體 64.0 GB · 磁碟可用 488 GB建議使用 24 GB 顯示卡 設定檔。你也可以改選下面另外兩個。24 GB 顯示卡建議適合 RTX 4090 這類 24 GB 顯示卡，語音辨識與翻譯都用 GPU。8 GB 顯示卡適合 8 GB 顯示卡，語音辨識與翻譯輪流用 GPU，LLM 的內容長度較短。只用 CPU沒有可用的 NVIDIA 顯示卡時使用，全部用處理器，速度慢很多。會下載的項目項目大小授權whisper-large-v3-turbo模型1.49 GBMITwhispercpp-b5454-win-cuda執行檔458 MBMITwhispercpp-b5454-win-cpu執行檔，GPU 失敗時改用 CPU 的備援8.58 MB—共 1.95 GB，磁碟可用 488 GB下載並開始略過，之後在設定裡處理"`);
    expect(screen.getByTestId("wizard-recommended").textContent).toContain("另外兩個");
  });

  it("lists the runtime a Mac builds for itself without a size and says where the script is", async () => {
    await choose(macView());
    const row = screen.getByTestId("wizard-asset-whispercpp-b5454-macos-metal").textContent ?? "";
    expect(row).toContain("在這台 Mac 上自行建置");
    expect(row).toContain("scripts/mac/build_whisper_cli.sh");
    expect(row).toContain("docs/MACOS.md");
    expect(row).not.toContain("0 B");
    expect(screen.getByTestId("wizard-asset-llama-b8000-macos-metal").textContent).toContain("38.1 MB");
    expect(screen.getByTestId("wizard-recommended").textContent).toContain("另外三個");
    expect(screen.getByTestId("wizard-total").textContent).toContain("共 1.53 GB");
    expect(screen.getByTestId("wizard-start").textContent).toBe("下載並開始");
  });

  it("says nothing is left to download when the only missing program is the one the Mac builds", async () => {
    const view = macView();
    const profiles = view.profiles.map((p) => ({ ...p, missing: p.missing.filter((m) => m.localBuild), downloadBytes: 0 }));
    await choose({ ...view, profiles }, false);
    expect(screen.getByTestId("wizard-total").textContent).toContain("沒有要下載的項目");
    expect(screen.getByTestId("wizard-start").textContent).toBe("開始自檢");
  });
});
