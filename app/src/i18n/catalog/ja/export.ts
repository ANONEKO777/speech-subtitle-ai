// Machine translation. No native speaker has read it.
import type { exports as en } from "../en/export";

export const exports = {
  "export.button": "書き出し",
  "export.done": "書き出しました：{path}",
  "export.cancelled": "書き出しをキャンセルしました",
  "export.failed": "書き出しに失敗しました：{reason}",
  "export.srtOriginal": "SRT 原文",
  "export.srtTarget": "SRT {name}",
  "export.bilingual": "{format} 対訳",
  "export.summary": "要約 summary.md",
  "export.noSummary": "この言語の要約はまだありません",
} satisfies Record<keyof typeof en, string>;
