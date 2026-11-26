// Machine translation. No native speaker has read it.
import type { editor as en } from "../en/editor";

export const editor = {
  "editor.start": "開始",
  "editor.end": "終了",
  "editor.textAria": "字幕のテキスト",
  "editor.sourceTitle": "原文は翻訳と要約の元になるため、ここでは変更できません",
  "editor.hint": "Enter で保存 · Shift+Enter で改行 · Esc でキャンセル",
  "editor.badTime": "時間は 分:秒.ミリ秒 の形式で入力してください（例：1:05.250）",
  "editor.problem.empty": "テキストを空にはできません",
  "editor.problem.endBeforeStart": "終了時間が開始時間より前です",
  "editor.problem.tooLong": "上限の 7 秒を超えています",
  "editor.problem.overlap": "隣の字幕と重なっています",
  "editor.problem.outOfOrder": "開始時間が前の字幕より前です",
  "editor.problem.sourceLocked": "原文は変更できません。変更できるのは訳文と時間だけです",
  "editor.problem.badText": "テキストに余分な空白または改行があります",
  "editor.tooLong": "長さ {seconds} 秒で、上限の 7 秒を超えています",
  "editor.outOfOrder": "開始時間が前の字幕（{time}）より前です",
  "editor.overlapBefore": "前の字幕と重なっています（前の字幕は {time} に終わります）",
  "editor.overlapAfter": "次の字幕と重なっています（次の字幕は {time} に始まります）",
  "editor.noBackend": "バックエンドに接続できません（{reason}）",
  "editor.busy": "プロジェクトが処理中のため、今は保存できません（{reason}）",
  "editor.undoFailed": "元に戻せませんでした：{reason}",
} satisfies Record<keyof typeof en, string>;
