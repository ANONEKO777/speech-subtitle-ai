import type { ProfileId } from "./types";

export const PROFILE_NAME: Record<ProfileId, string> = { "gpu-24gb": "24 GB 顯示卡", "gpu-8gb": "8 GB 顯示卡", cpu: "只用 CPU" };

export const PROFILE_BLURB: Record<ProfileId, string> = {
  "gpu-24gb": "適合 RTX 4090 這類 24 GB 顯示卡，語音辨識與翻譯都用 GPU。",
  "gpu-8gb": "適合 8 GB 顯示卡，語音辨識與翻譯輪流用 GPU，LLM 的內容長度較短。",
  cpu: "沒有可用的 NVIDIA 顯示卡時使用，全部用處理器，速度慢很多。",
};
