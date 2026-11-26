import { type Translate, tZhTW } from "../i18n";
import type { Hardware, ProfileId } from "./types";

export const isMac = (hw: Hardware): boolean => hw.platform === "macos-arm64";

export const isCpuProfile = (id: ProfileId): boolean => id === "cpu" || id === "apple-cpu";

/** What a self-test device name reads as: `cuda` and `metal` are the GPU, anything else the processor. */
export function deviceLabel(device: string, t: Translate = tZhTW): string {
  if (device === "cuda") return "GPU";
  if (device === "metal") return t("hw.device.metal");
  return "CPU";
}

/** The first line of the detected hardware: the graphics card on a PC, the chip on a Mac. */
export function chipOrGpu(hw: Hardware, t: Translate = tZhTW): { label: string; value: string } {
  if (isMac(hw)) return { label: t("hw.chip"), value: hw.chip ?? t("hw.noChip") };
  return { label: t("hw.gpuCard"), value: hw.gpuName ?? t("hw.noGpu") };
}
