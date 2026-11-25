import { describe, expect, it } from "vitest";
import { chipOrGpu, deviceLabel, isCpuProfile, isMac } from "./hardwareText";
import { parseProfileView } from "./parse";
import { PROFILE_BLURB, PROFILE_NAME } from "./profileText";
import { PROFILE_IDS } from "./types";

const mac = {
  platform: "macos-arm64",
  chip: "Apple M3 Pro",
  gpu_name: null,
  vram_mib: null,
  driver_version: null,
  ram_mib: 36864,
  disk_free_mib: 500000,
};
const pc = { ...mac, platform: "win-x64", chip: null, gpu_name: "RTX 4090", vram_mib: 24564, driver_version: "596.36" };

const option = (id: string) => ({
  id,
  label: id,
  recommend_cloud: id === "apple-cpu",
  fits_hardware: true,
  active: id === "metal-32gb",
  recommended: id === "metal-32gb",
  missing: [],
  download_bytes: 0,
  asr_model: "whisper",
  llm_model: "qwen3-8b",
});

const macView = (hardware: object) => ({
  hardware,
  vc_runtime_missing: false,
  recommended: { id: "metal-32gb", label: "Metal 32 GB", why: "fits" },
  active: { id: "metal-32gb", label: "Metal 32 GB", source: "recommended", device: "metal" },
  profiles: ["metal-32gb", "metal-32gb-parallel", "metal-16gb", "apple-cpu"].map(option),
  fallback: null,
});

describe("hardware text", () => {
  it("shows the chip on a Mac and the graphics card on a PC", () => {
    const hw = parseProfileView(macView(mac)).hardware;
    expect(isMac(hw)).toBe(true);
    expect(chipOrGpu(hw)).toEqual({ label: "晶片", value: "Apple M3 Pro" });
    const pcHw = parseProfileView({ ...macView(pc), recommended: { id: "gpu-24gb", label: "x", why: "y" }, active: { id: "gpu-24gb", label: "x", source: "user", device: "cuda" }, profiles: [] }).hardware;
    expect(chipOrGpu(pcHw)).toEqual({ label: "顯示卡", value: "RTX 4090" });
  });

  it("does not claim an NVIDIA card is missing on a Mac with no chip name", () => {
    const hw = parseProfileView(macView({ ...mac, chip: null })).hardware;
    expect(chipOrGpu(hw).value).not.toContain("NVIDIA");
  });

  it("calls Metal the GPU and only an unknown device the CPU", () => {
    expect(deviceLabel("cuda")).toBe("GPU");
    expect(deviceLabel("metal")).toBe("GPU（Metal）");
    expect(deviceLabel("cpu")).toBe("CPU");
  });

  it("reads a Mac profile view, whose profile ids the page used to reject", () => {
    const view = parseProfileView(macView(mac));
    expect(view.active.id).toBe("metal-32gb");
    expect(view.profiles.map((p) => p.id)).toEqual(["metal-32gb", "metal-32gb-parallel", "metal-16gb", "apple-cpu"]);
  });

  it("has a name, a blurb and a CPU flag for every profile id", () => {
    for (const id of PROFILE_IDS) {
      expect(PROFILE_NAME[id].length).toBeGreaterThan(0);
      expect(PROFILE_BLURB[id].length).toBeGreaterThan(0);
    }
    expect(PROFILE_IDS.filter(isCpuProfile)).toEqual(["cpu", "apple-cpu"]);
  });
});
