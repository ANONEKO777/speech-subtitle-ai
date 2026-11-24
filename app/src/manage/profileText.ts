import type { ProfileId } from "./types";

export const PROFILE_NAME: Record<ProfileId, string> = {
  "gpu-24gb": "24 GB 顯示卡",
  "gpu-8gb": "8 GB 顯示卡",
  cpu: "只用 CPU",
  "metal-32gb": "Apple 晶片 32 GB 以上",
  "metal-32gb-parallel": "Apple 晶片 32 GB 以上（同時執行）",
  "metal-16gb": "Apple 晶片 16 GB",
  "apple-cpu": "Apple 晶片只用處理器",
};

export const PROFILE_BLURB: Record<ProfileId, string> = {
  "gpu-24gb": "適合 RTX 4090 這類 24 GB 顯示卡，語音辨識與翻譯都用 GPU。",
  "gpu-8gb": "適合 8 GB 顯示卡，語音辨識與翻譯輪流用 GPU，LLM 的內容長度較短。",
  cpu: "沒有可用的 NVIDIA 顯示卡時使用，全部用處理器，速度慢很多。",
  "metal-32gb": "適合 32 GB 以上的 Apple 晶片 Mac，語音辨識與翻譯輪流使用 GPU（Metal）。",
  "metal-32gb-parallel": "適合 32 GB 以上的 Apple 晶片 Mac，語音辨識與翻譯同時使用 GPU（Metal），較吃記憶體。需要自己確認這台 Mac 撐得住再選。",
  "metal-16gb": "適合 16 GB 的 Apple 晶片 Mac，語音辨識與翻譯輪流使用 GPU（Metal），LLM 的內容長度較短。",
  "apple-cpu": "記憶體不足 16 GB 時使用，全部用處理器，速度慢很多。",
};
