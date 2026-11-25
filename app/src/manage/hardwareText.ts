import type { Hardware, ProfileId } from "./types";

export const isMac = (hw: Hardware): boolean => hw.platform === "macos-arm64";

export const isCpuProfile = (id: ProfileId): boolean => id === "cpu" || id === "apple-cpu";

/** What a self-test device name reads as: `cuda` and `metal` are the GPU, anything else the processor. */
export function deviceLabel(device: string): string {
  if (device === "cuda") return "GPU";
  if (device === "metal") return "GPU（Metal）";
  return "CPU";
}

/** The first line of the detected hardware: the graphics card on a PC, the chip on a Mac. */
export function chipOrGpu(hw: Hardware): { label: string; value: string } {
  if (isMac(hw)) return { label: "晶片", value: hw.chip ?? "沒有偵測到 Apple 晶片" };
  return { label: "顯示卡", value: hw.gpuName ?? "沒有偵測到 NVIDIA 顯示卡" };
}
