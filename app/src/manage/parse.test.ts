import { describe, expect, it } from "vitest";
import { parseProfileView } from "./parse";

const raw = (missing: unknown[]) => ({
  hardware: { platform: "macos-arm64", chip: "Apple M3", gpu_name: null, vram_mib: null, driver_version: null, ram_mib: 36864, disk_free_mib: 1 },
  vc_runtime_missing: false,
  recommended: { id: "metal-32gb", label: "Metal", why: "fits" },
  active: { id: "metal-32gb", label: "Metal", source: "recommended", device: "metal" },
  profiles: [
    {
      id: "metal-32gb",
      label: "Metal",
      recommend_cloud: false,
      fits_hardware: true,
      active: true,
      recommended: true,
      missing,
      download_bytes: 5,
      asr: { model: "a" },
      llm: { model: "l" },
    },
  ],
  fallback: null,
});

describe("parseProfileView", () => {
  it("reads which missing program is built on the machine", () => {
    const view = parseProfileView(
      raw([
        { id: "whispercpp-b5454-macos-metal", type: "runtime", size_bytes: 0, local_build: true },
        { id: "llama", type: "runtime", size_bytes: 5, local_build: false },
      ]),
    );
    expect(view.profiles[0]?.missing.map((m) => [m.id, m.localBuild])).toEqual([
      ["whispercpp-b5454-macos-metal", true],
      ["llama", false],
    ]);
  });

  it("treats a missing item without the flag as a download", () => {
    const view = parseProfileView(raw([{ id: "llama", type: "runtime", size_bytes: 5 }]));
    expect(view.profiles[0]?.missing[0]?.localBuild).toBe(false);
  });
});
