// Machine translation. No native speaker has read it.
import type { update as en } from "../en/update";

export const update = {
  "update.title": "更新の確認",
  "update.hint": "ボタンを押したときだけオンラインで確認します。更新してもモデルや設定が再ダウンロードされることはありません。",
  "update.check": "更新を確認",
  "update.checking": "更新を確認しています…",
  "update.upToDate": "最新版です。",
  "update.upToDateVersion": "最新版です（{version}）。",
  "update.available": "新しいバージョン {version} があります。",
  "update.availableFrom": "新しいバージョン {version} があります（現在：{current}）。",
  "update.download": "更新をダウンロード",
  "update.downloading": "{version} をダウンロードしています。しばらくお待ちください…",
  "update.downloaded": "{version} をダウンロードし、署名を確認しました。インストール時にアプリはいったん閉じて、再び開きます。",
  "update.install": "インストールして再起動",
  "update.installing": "インストーラーを起動しています…",
} satisfies Record<keyof typeof en, string>;
