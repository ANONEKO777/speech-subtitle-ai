// Machine translation (Taiwan source to mainland terms). No native speaker has read it.
import type { editor as en } from "../en/editor";

export const editor = {
  "editor.start": "开始",
  "editor.end": "结束",
  "editor.textAria": "字幕文字",
  "editor.sourceTitle": "原文是翻译与摘要的来源，不能在这里修改",
  "editor.hint": "Enter 保存 · Shift+Enter 换行 · Esc 取消",
  "editor.badTime": "时间格式为 分:秒.毫秒，例如 1:05.250",
  "editor.problem.empty": "文字不能为空",
  "editor.problem.endBeforeStart": "结束时间早于开始时间",
  "editor.problem.tooLong": "超过 7 秒的上限",
  "editor.problem.overlap": "与相邻的字幕重叠",
  "editor.problem.outOfOrder": "开始时间早于上一条",
  "editor.problem.sourceLocked": "原文不能修改，只能改译文和时间",
  "editor.problem.badText": "文字有多余的空格或换行",
  "editor.tooLong": "长 {seconds} 秒，超过 7 秒的上限",
  "editor.outOfOrder": "开始时间早于上一条（{time}）",
  "editor.overlapBefore": "与上一条重叠，上一条到 {time} 才结束",
  "editor.overlapAfter": "与下一条重叠，下一条从 {time} 开始",
  "editor.noBackend": "无法连接到后端（{reason}）",
  "editor.busy": "项目正被任务使用，暂时不能保存（{reason}）",
  "editor.undoFailed": "无法撤销：{reason}",
} satisfies Record<keyof typeof en, string>;
