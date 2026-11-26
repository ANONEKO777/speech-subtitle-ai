import type { exports as en } from "../en/export";

export const exports = {
  "export.button": "匯出",
  "export.done": "已匯出 {path}",
  "export.cancelled": "已取消匯出",
  "export.failed": "匯出失敗：{reason}",
  "export.srtOriginal": "SRT 原文",
  "export.srtTarget": "SRT {name}",
  "export.bilingual": "{format} 雙語",
  "export.summary": "摘要 summary.md",
  "export.noSummary": "這個語言還沒有摘要",
} satisfies Record<keyof typeof en, string>;
