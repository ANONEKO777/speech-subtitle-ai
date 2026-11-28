import type { update as en } from "../en/update";

export const update = {
  "update.title": "檢查更新",
  "update.hint": "按下按鈕就會立刻檢查。模型與設定不會因為更新而重新下載。",
  "update.check": "檢查更新",
  "update.checking": "正在檢查更新…",
  "update.upToDate": "已是最新版。",
  "update.upToDateVersion": "已是最新版（{version}）。",
  "update.available": "有新版 {version}。",
  "update.availableFrom": "有新版 {version}（目前 {current}）。",
  "update.download": "下載更新",
  "update.downloading": "正在下載 {version}，請稍候…",
  "update.downloaded": "{version} 已下載，簽章驗證通過。安裝時程式會關閉並重新開啟。",
  "update.install": "安裝並重新啟動",
  "update.installing": "正在啟動安裝程式…",
} satisfies Record<keyof typeof en, string>;
