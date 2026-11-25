import type { settings as en } from "../en/settings";

export const settings = {
  "language.nav": "語言",
  "language.title": "介面語言",
  "language.hint": "選擇視窗使用的語言。變更會立刻套用，不需要重新啟動。",
  "language.note": "這只改變視窗上的文字。影片的語音語言和字幕語言維持你的設定。",
  "language.label": "視窗語言",
  "language.auto": "自動（跟隨系統）",
  "language.machine": "{name}（機器翻譯）",
  "language.saved": "已套用。",
  "language.failed": "無法儲存語言設定：{reason}",
} satisfies Record<keyof typeof en, string>;
