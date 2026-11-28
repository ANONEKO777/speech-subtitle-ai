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
  "autoUpdate.busy.export": "字幕を焼き込んだ動画を書き出しています。インストールすると書き出しが中断されるため、終わってからインストールしてください。",
  "autoUpdate.busy.download": "モデルまたは実行環境をダウンロードしています。インストールするとダウンロードが中断されるため、終わってからインストールしてください。",
  "autoUpdate.busy.move": "モデルフォルダーを移動しています。インストールすると移動が中断されるため、終わってからインストールしてください。",
  "autoUpdate.busy.selftest": "セルフテストを実行しています。インストールするとセルフテストが中断されるため、終わってからインストールしてください。",
  "autoUpdate.retry": "もう一度試すには「{button}」を押してください。",
  "autoUpdate.atStart": "起動時に更新を確認",
  "autoUpdate.atStartHint": "オンにすると、起動後にバックグラウンドで GitHub に新しいバージョンがあるか問い合わせます（1 日 1 回まで）。お知らせするだけで、クリックするまでインストールはしません。",
  "autoUpdate.unsupported": "このプラットフォームにはまだ自動更新がないため、起動時には確認しません。",
  "autoUpdate.lastChecked": "前回の起動時の確認：{time}",
  "autoUpdate.lastFailed": "前回の起動時の確認に失敗しました（{time}）：{reason}",
} satisfies Record<keyof typeof en, string>;
