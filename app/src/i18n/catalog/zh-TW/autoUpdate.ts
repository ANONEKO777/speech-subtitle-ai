import type { autoUpdate as en } from "../en/autoUpdate";

export const autoUpdate = {
  "autoUpdate.banner.label": "新版通知",
  "autoUpdate.banner.notes": "更新內容",
  "autoUpdate.banner.install": "下載並安裝",
  "autoUpdate.banner.later": "稍後",
  "autoUpdate.banner.skip": "略過此版本",
  "autoUpdate.busy.job": "正在處理影片。請等處理完成再安裝，因為安裝會中斷處理。",
  "autoUpdate.busy.batch": "佇列正在處理。請等佇列跑完或暫停後再安裝，因為安裝會中斷處理。",
  "autoUpdate.atStart": "啟動時檢查更新",
  "autoUpdate.atStartHint": "開啟時，程式啟動後會在背景連到 GitHub 查看有沒有新版，每天最多一次。有新版只會通知你，你按下按鈕才會安裝。",
  "autoUpdate.unsupported": "這個平台還沒有自動更新，所以啟動時不會檢查。",
  "autoUpdate.lastChecked": "上次啟動時檢查：{time}",
  "autoUpdate.lastFailed": "上次啟動時檢查失敗（{time}）：{reason}",
} satisfies Record<keyof typeof en, string>;
