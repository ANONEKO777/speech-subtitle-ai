// Machine translation. No native speaker has read it.
import type { autoUpdate as en } from "../en/autoUpdate";

export const autoUpdate = {
  "autoUpdate.banner.label": "新しいバージョン",
  "autoUpdate.banner.notes": "更新内容",
  "autoUpdate.banner.install": "ダウンロードしてインストール",
  "autoUpdate.banner.later": "後で",
  "autoUpdate.banner.skip": "このバージョンをスキップ",
  "autoUpdate.busy.job": "動画を処理しています。インストールすると処理が中断されるため、終わってからインストールしてください。",
  "autoUpdate.busy.batch": "キューを処理しています。インストールすると処理が中断されるため、キューが終わるか一時停止してからインストールしてください。",
  "autoUpdate.atStart": "起動時に更新を確認",
  "autoUpdate.atStartHint": "オンにすると、起動後にバックグラウンドで GitHub に新しいバージョンがあるか問い合わせます（1 日 1 回まで）。お知らせするだけで、クリックするまでインストールはしません。",
  "autoUpdate.unsupported": "このプラットフォームにはまだ自動更新がないため、起動時には確認しません。",
  "autoUpdate.lastChecked": "前回の起動時の確認：{time}",
  "autoUpdate.lastFailed": "前回の起動時の確認に失敗しました（{time}）：{reason}",
} satisfies Record<keyof typeof en, string>;
