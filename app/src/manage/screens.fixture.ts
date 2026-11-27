import { plainText } from "../i18n/said";
import type { Asset, Inventory, LicenseEntry, MissingAsset, ProfileId, ProfileOption, ProfileView } from "./types";

const option = (id: ProfileId, over: Partial<ProfileOption>): ProfileOption => ({
  id,
  label: id,
  recommendCloud: id === "cpu" || id === "apple-cpu",
  fitsHardware: true,
  active: false,
  recommended: false,
  missing: [],
  downloadBytes: 0,
  asrModel: "whisper-large-v3-turbo",
  llmModel: "qwen3-8b",
  ...over,
});

const need = (id: string, type: string, sizeBytes: number, localBuild = false): MissingAsset => ({ id, type, sizeBytes, localBuild });

const sum = (list: readonly MissingAsset[]) => list.reduce((n, m) => n + m.sizeBytes, 0);

/** An RTX 4090 PC with 64 GB: what the screens showed before the Mac work. */
export function windowsView(): ProfileView {
  const gpu = [need("whisper-large-v3-turbo", "model", 1_600_000_000), need("whispercpp-b5454-win-cuda", "runtime", 480_000_000)];
  const cpu = [need("whisper-large-v3-turbo", "model", 1_600_000_000), need("whispercpp-b5454-win-cpu", "runtime", 9_000_000)];
  return {
    vcRuntimeMissing: false,
    hardware: { platform: "win-x64", chip: null, gpuName: "RTX 4090", vramMib: 24564, driverVersion: "596.36", ramMib: 65536, diskFreeMib: 500000 },
    recommended: { id: "gpu-24gb", label: "24 GB", why: plainText("fits") },
    active: { id: "gpu-24gb", label: "24 GB", source: "recommended", device: "cuda" },
    profiles: [
      option("gpu-24gb", { recommended: true, active: true, missing: gpu, downloadBytes: sum(gpu) }),
      option("gpu-8gb", { missing: gpu, downloadBytes: sum(gpu) }),
      option("cpu", { missing: cpu, downloadBytes: sum(cpu) }),
    ],
    fallback: null,
  };
}

/** A 36 GB M3 MacBook Pro. `whispercpp-b5454-macos-metal` is built by a script, so it has no size. */
export function macView(): ProfileView {
  const metal = [
    need("whisper-large-v3-turbo", "model", 1_600_000_000),
    need("whispercpp-b5454-macos-metal", "runtime", 0, true),
    need("llama-b8000-macos-metal", "runtime", 40_000_000),
  ];
  return {
    vcRuntimeMissing: false,
    hardware: { platform: "macos-arm64", chip: "Apple M3", gpuName: null, vramMib: null, driverVersion: null, ramMib: 36864, diskFreeMib: 500000 },
    recommended: { id: "metal-32gb", label: "Metal 32 GB", why: plainText("fits") },
    active: { id: "metal-32gb", label: "Metal 32 GB", source: "recommended", device: "metal" },
    profiles: [
      option("metal-32gb", { recommended: true, active: true, missing: metal, downloadBytes: sum(metal) }),
      option("metal-32gb-parallel", { missing: metal, downloadBytes: sum(metal) }),
      option("metal-16gb", { missing: metal, downloadBytes: sum(metal) }),
      option("apple-cpu", { missing: metal, downloadBytes: sum(metal) }),
    ],
    fallback: null,
  };
}

export const licenses: readonly LicenseEntry[] = [
  { id: "whisper-large-v3-turbo", type: "model", version: "1", license: "MIT", licenseUrl: "https://spdx.org/licenses/MIT.html", parts: [], sourceUrl: "https://huggingface.co/openai/whisper-large-v3-turbo" },
  { id: "whispercpp-b5454-win-cuda", type: "runtime", version: "b5454", license: "MIT", licenseUrl: "https://spdx.org/licenses/MIT.html", parts: [], sourceUrl: "https://github.com/ggml-org/whisper.cpp" },
  { id: "whispercpp-b5454-macos-metal", type: "runtime", version: "b5454", license: "MIT", licenseUrl: "https://spdx.org/licenses/MIT.html", parts: [], sourceUrl: "https://github.com/ggml-org/whisper.cpp" },
];

const asset = (id: string, type: Asset["type"], over: Partial<Asset> = {}): Asset => ({
  id,
  type,
  kind: type === "model" ? "asr" : "whisper.cpp",
  state: "not_installed",
  version: "1",
  installedVersion: null,
  sizeBytes: 0,
  sizeOnDisk: null,
  path: null,
  shaState: "not_installed",
  shaScope: type === "model" ? "file" : "archive_at_install",
  usedByProfiles: [],
  inActiveProfile: false,
  dependents: [],
  blockers: [],
  license: "MIT",
  licenseUrl: "https://spdx.org/licenses/MIT.html",
  localBuild: false,
  foundOutsideRuntimes: false,
  ...over,
});

/** What `/api/inventory` lists on the Windows PC: the model is there, the CUDA runtime is not. */
export function windowsInventory(): Inventory {
  return {
    activeProfile: "gpu-24gb",
    modelsDir: "C:/m",
    runtimesDir: "C:/r",
    installedBytes: 1_600_000_000,
    assets: [
      asset("whisper-large-v3-turbo", "model", { state: "installed", sizeBytes: 1_600_000_000, sizeOnDisk: 1_600_000_000, path: "C:/m/w.bin", shaState: "verified" }),
      asset("whispercpp-b5454-win-cuda", "runtime", { sizeBytes: 480_000_000 }),
    ],
  };
}

/** The 36 GB M3: `whispercpp-b5454-macos-metal` is built by a script, so it has no size and no archive. */
export function macInventory(): Inventory {
  return {
    activeProfile: "metal-32gb",
    modelsDir: "/m",
    runtimesDir: "/r",
    installedBytes: 0,
    assets: [
      asset("whispercpp-b5454-macos-metal", "runtime", { localBuild: true }),
      asset("llama-b8000-macos-metal", "runtime", { sizeBytes: 40_000_000 }),
    ],
  };
}
