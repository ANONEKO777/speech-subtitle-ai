// Machine translation. No native speaker has read it.
import type { errors as en } from "../en/errors";

export const errors = {
  "errors.jobRunning": "この動画は処理中です。完了してからもう一度お試しください。",
  "errors.backendLost": "バックエンドとの接続が切れ、処理が停止しました。バックエンドが終了した可能性があります。アプリを再起動してください。",
  "errors.updateUnreadable": "更新の確認結果を読み取れませんでした。",
  "errors.updateIncomplete": "更新は完了しませんでした。",
} satisfies Record<keyof typeof en, string>;
