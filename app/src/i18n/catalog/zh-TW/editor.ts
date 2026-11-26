import type { editor as en } from "../en/editor";

export const editor = {
  "editor.start": "開始",
  "editor.end": "結束",
  "editor.textAria": "字幕文字",
  "editor.sourceTitle": "原文是翻譯與摘要的來源，不能在這裡修改",
  "editor.hint": "Enter 儲存 · Shift+Enter 換行 · Esc 取消",
  "editor.badTime": "時間格式為 分:秒.毫秒，例如 1:05.250",
  "editor.problem.empty": "文字不能是空的",
  "editor.problem.endBeforeStart": "結束時間早於開始時間",
  "editor.problem.tooLong": "超過 7 秒的上限",
  "editor.problem.overlap": "與相鄰的字幕重疊",
  "editor.problem.outOfOrder": "開始時間早於上一條",
  "editor.problem.sourceLocked": "原文不能修改，只能改譯文和時間",
  "editor.problem.badText": "文字有多餘的空白或換行",
  "editor.tooLong": "長 {seconds} 秒，超過 7 秒的上限",
  "editor.outOfOrder": "開始時間早於上一條（{time}）",
  "editor.overlapBefore": "與上一條重疊，上一條到 {time} 才結束",
  "editor.overlapAfter": "與下一條重疊，下一條從 {time} 開始",
  "editor.noBackend": "無法連線到後端（{reason}）",
  "editor.busy": "專案正被工作使用，暫時不能儲存（{reason}）",
  "editor.undoFailed": "無法復原：{reason}",
} satisfies Record<keyof typeof en, string>;
