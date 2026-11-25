import type { errors as en } from "../en/errors";

export const errors = {
  "errors.jobRunning": "這部影片正在處理中，請等它完成後再試。",
  "errors.backendLost": "與後端的連線中斷，處理已停止。後端可能已結束，請重新啟動程式。",
  "errors.updateUnreadable": "更新檢查回傳了看不懂的結果。",
  "errors.updateIncomplete": "更新沒有完成。",
} satisfies Record<keyof typeof en, string>;
