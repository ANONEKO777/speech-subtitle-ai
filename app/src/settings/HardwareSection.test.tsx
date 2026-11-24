// @vitest-environment jsdom
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { Backend } from "../api/client";
import type { ProfileView } from "../manage/types";
import { HardwareSection, selfTestText } from "./HardwareSection";

const mocks = vi.hoisted(() => ({ view: null as ProfileView | null }));

vi.mock("../manage/api", async (orig) => ({
  ...(await orig<typeof import("../manage/api")>()),
  fetchProfile: vi.fn(() => Promise.resolve(mocks.view)),
  fetchLastSelfTest: vi.fn(() => Promise.resolve(null)),
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
    const run = { ok: true, device: "metal", stages: [], fallback: null, seconds: 3, message: "ok" };
    expect(selfTestText(run).title).toContain("GPU（Metal）");
    expect(selfTestText({ ...run, device: "cpu" }).title).toContain("CPU");
  });
});
