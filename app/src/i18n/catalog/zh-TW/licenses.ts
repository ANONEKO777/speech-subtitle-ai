import type { licenses as en } from "../en/licenses";

export const licenses = {
  "lic.title": "第三方授權",
  "lic.hint": "App 另外下載的每個模型與執行檔，各自的授權與來源。連結會用瀏覽器開啟。",
  "lic.program.pre": "本程式以 ",
  "lic.program.post": " 授權。原始碼：",
  "lic.ffmpeg.a": "安裝程式隨附 FFmpeg 8.1（",
  "lic.ffmpeg.b": "組建，未含 GPL 或 nonfree 元件），以獨立的 ffmpeg.exe 與 DLL 放在安裝資料夾的 ffmpeg 子資料夾，可自行替換。FFmpeg 原始碼：",
  "lic.ffmpeg.c": "，組建腳本：",
  "lic.ffmpeg.d": "。完整聲明在安裝資料夾的 THIRD_PARTY.md。",
  "lic.name": "名稱",
  "lic.version": "版本",
  "lic.license": "授權",
  "lic.links": "連結",
  "lic.fullText": "授權全文",
  "lic.source": "下載來源",
} satisfies Record<keyof typeof en, string>;
