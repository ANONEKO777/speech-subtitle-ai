import { describe, expect, it } from "vitest";
import { parseAsset, parseProfileView, parseSettings } from "./parse";

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

describe("parseAsset", () => {
  const row = (extra: Record<string, unknown>) => ({ id: "x", type: "runtime", state: "not_installed", sha256_state: "not_installed", size_bytes: 0, ...extra });

  it("reads which inventory row is built on the machine, and none without the flag", () => {
    expect(parseAsset(row({ local_build: true })).localBuild).toBe(true);
    expect(parseAsset(row({ local_build: false })).localBuild).toBe(false);
    expect(parseAsset(row({})).localBuild).toBe(false);
  });

  it("reads whether the program was found outside the runtimes folder, and not without the flag", () => {
    expect(parseAsset(row({ found_outside_runtimes: true })).foundOutsideRuntimes).toBe(true);
    expect(parseAsset(row({ found_outside_runtimes: false })).foundOutsideRuntimes).toBe(false);
    expect(parseAsset(row({})).foundOutsideRuntimes).toBe(false);
  });
});

describe("parseSettings", () => {
  it("reads the window language the backend saved", () => {
    expect(parseSettings({ ui_language: "ja" }).uiLanguage).toBe("ja");
    expect(parseSettings({ ui_language: "zh-TW" }).uiLanguage).toBe("zh-TW");
  });

  it("takes auto from a backend that does not send it yet, or sends something unknown", () => {
    expect(parseSettings({}).uiLanguage).toBe("auto");
    expect(parseSettings({ ui_language: "fr" }).uiLanguage).toBe("auto");
  });
});
