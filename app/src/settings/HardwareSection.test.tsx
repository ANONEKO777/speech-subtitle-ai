// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { Backend } from "../api/client";
import { tZhTW } from "../i18n";
import { macView, windowsView } from "../manage/screens.fixture";
import type { ProfileView } from "../manage/types";
import { HardwareSection, selfTestText } from "./HardwareSection";
import { plainText } from "../i18n/said";

const mocks = vi.hoisted(() => ({ view: null as ProfileView | null }));

vi.mock("../manage/api", async (orig) => ({
  ...(await orig<typeof import("../manage/api")>()),
  fetchProfile: vi.fn(() => Promise.resolve(mocks.view)),
  fetchLastSelfTest: vi.fn(() => Promise.resolve(null)),
  chooseProfile: vi.fn(() => Promise.resolve({ profile: mocks.view, warnings: [] })),
}));

const backend = { port: 1, token: "t" } as Backend;
const downloads = { list: [], byAsset: new Map(), refresh: () => undefined };

const option = (id: ProfileView["profiles"][number]["id"]): ProfileView["profiles"][number] => ({
  id,
  label: id,
  recommendCloud: id === "apple-cpu",
  fitsHardware: true,
  active: id === "metal-32gb",
  recommended: id === "metal-32gb",
  missing: [],
  downloadBytes: 0,
  asrModel: "whisper",
  llmModel: "qwen3-8b",
});

afterEach(cleanup);

describe("HardwareSection on a Mac", () => {
  it("shows the chip and the unified memory, no NVIDIA wording, and names every Metal profile", async () => {
    mocks.view = {
      hardware: { platform: "macos-arm64", chip: "Apple M3 Pro", gpuName: null, vramMib: null, driverVersion: null, ramMib: 36864, diskFreeMib: 500000 },
      vcRuntimeMissing: false,
      recommended: { id: "metal-32gb", label: "Metal 32 GB", why: "fits" },
      active: { id: "metal-32gb", label: "Metal 32 GB", source: "recommended", device: "metal" },
      profiles: [option("metal-32gb"), option("metal-32gb-parallel"), option("metal-16gb"), option("apple-cpu")],
      fallback: null,
    };
    render(<HardwareSection backend={backend} downloads={downloads} onOpenLlm={() => undefined} />);
    await waitFor(() => screen.getByTestId("hw-gpu"));
    expect(screen.getByTestId("hw-gpu").textContent).toBe("Apple M3 Pro");
    expect(screen.getByTestId("hardware-section").textContent).toContain("統一記憶體");
    expect(screen.queryByTestId("hw-vram")).toBeNull();
    expect(screen.queryByTestId("hw-driver")).toBeNull();
    expect(screen.getByTestId("hardware-section").textContent).not.toContain("NVIDIA");
    expect(screen.getByTestId("hw-recommended").textContent).toContain("Apple 晶片 32 GB 以上");
    expect(screen.getByTestId("profile-apple-cpu")).toBeTruthy();
  });
});

describe("selfTestText", () => {
  it("says GPU (Metal) for a Metal run and CPU for a CPU run", () => {
    const run = { ok: true, device: "metal", stages: [], fallback: null, seconds: 3, message: plainText("ok") };
    expect(selfTestText(run, tZhTW, "zh-TW").title).toContain("GPU（Metal）");
    expect(selfTestText({ ...run, device: "cpu" }, tZhTW, "zh-TW").title).toContain("CPU");
  });
});

describe("HardwareSection and the program a Mac builds for itself", () => {
  const show = async (view: ProfileView) => {
    mocks.view = view;
    render(<HardwareSection backend={backend} downloads={downloads} onOpenLlm={() => undefined} />);
    await waitFor(() => screen.getByTestId("hw-gpu"));
    return screen.getByTestId("hardware-section");
  };

  it("reads as it always did on Windows", async () => {
    const section = await show(windowsView());
    expect(section.textContent).toMatchInlineSnapshot(`"硬體與效能App 偵測這台電腦的硬體並建議設定檔。你隨時可以改選，不必重裝。偵測到的硬體顯示卡RTX 4090顯示記憶體24.0 GB驅動程式596.36記憶體64.0 GB磁碟可用空間488 GB建議的設定檔：24 GB 顯示卡為什麼這樣建議fits24 GB 顯示卡適合 RTX 4090 這類 24 GB 顯示卡，語音辨識與翻譯都用 GPU。目前使用建議缺少 2 項，要下載 1.94 GB使用中8 GB 顯示卡適合 8 GB 顯示卡，語音辨識與翻譯輪流用 GPU，LLM 的內容長度較短。缺少 2 項，要下載 1.94 GB使用這個設定檔只用 CPU沒有可用的 NVIDIA 顯示卡時使用，全部用處理器，速度慢很多。缺少 2 項，要下載 1.50 GBCPU 設定檔沒有 GPU 加速，本機內建的 LLM 會慢很多。建議改用雲端 LLM：翻譯快、品質好，差別是影片的逐字稿與字幕內容會傳送到雲端服務，離開這台電腦。內建與 Ollama 全程在本機，不會外傳。使用這個設定檔自檢用目前的設定檔實際啟動語音辨識與 LLM。GPU 失敗時會自動改用 CPU，並寫出原因。執行自檢"`);
  });

  it("counts only downloads as missing and names the script for the rest", async () => {
    await show(macView());
    const text = screen.getByTestId("profile-metal-32gb-missing").textContent ?? "";
    expect(text).toContain("缺少 2 項，要下載 1.53 GB");
    expect(text).toContain("另有 1 項要在這台 Mac 上自行建置（scripts/mac/build_whisper_cli.sh，步驟見 docs/MACOS.md）");
    expect(text).not.toContain("0 B");
  });

  it("says the notice under a processor-only Mac profile is about Metal, and keeps the CPU wording on Windows", async () => {
    const section = await show(macView());
    const mac = screen.getByTestId("profile-apple-cpu").textContent ?? "";
    expect(mac).toContain("這個設定檔只用處理器，不用 GPU（Metal）");
    expect(mac).not.toContain("CPU 設定檔");
    expect(section.textContent).not.toContain("NVIDIA");
    cleanup();
    await show(windowsView());
    expect(screen.getByTestId("profile-cpu").textContent).toContain("CPU 設定檔沒有 GPU 加速，本機內建的 LLM 會慢很多。");
  });

  it("lists only the build step after a switch when nothing is left to download", async () => {
    const view = macView();
    mocks.view = { ...view, profiles: view.profiles.map((p) => ({ ...p, missing: p.missing.filter((m) => m.localBuild), downloadBytes: 0 })) };
    render(<HardwareSection backend={backend} downloads={downloads} onOpenLlm={() => undefined} />);
    await waitFor(() => screen.getByTestId("profile-use-metal-16gb"));
    fireEvent.click(screen.getByTestId("profile-use-metal-16gb"));
    await waitFor(() => screen.getByTestId("switch-missing"));
    expect(screen.getByTestId("switch-missing-title").textContent).toBe("還缺的項目要在這台 Mac 上自行建置：");
    const list = screen.getByTestId("switch-missing").textContent ?? "";
    expect(list).toContain("whispercpp-b5454-macos-metal（執行檔，在這台 Mac 上自行建置（scripts/mac/build_whisper_cli.sh，步驟見 docs/MACOS.md））");
    expect(list).not.toContain("0 B");
    expect(screen.queryByTestId("switch-download")).toBeNull();
  });
});
