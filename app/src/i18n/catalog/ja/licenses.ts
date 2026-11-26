// Machine translation. No native speaker has read it.
import type { licenses as en } from "../en/licenses";

export const licenses = {
  "lic.title": "サードパーティのライセンス",
  "lic.hint": "アプリが別途ダウンロードする各モデルと実行ファイルのライセンスと入手元です。リンクはブラウザーで開きます。",
  "lic.program.pre": "このプログラムは ",
  "lic.program.post": " の下でライセンスされています。ソースコード：",
  "lic.ffmpeg.a": "インストーラーには FFmpeg 8.1（",
  "lic.ffmpeg.b": " ビルド、GPL および nonfree コンポーネントは含まない）が同梱されています。独立した ffmpeg.exe と DLL としてインストールフォルダーの ffmpeg サブフォルダーに置かれ、ご自身で置き換えられます。FFmpeg のソースコード：",
  "lic.ffmpeg.c": "、ビルドスクリプト：",
  "lic.ffmpeg.d": "。完全な表記は、インストールフォルダーの THIRD_PARTY.md にあります。",
  "lic.ffmpegMac.a": "このアプリには FFmpeg は含まれません。Homebrew でインストールしたものを使い、ライセンスはそのコピーに付属するものに従います。詳しくは ",
  "lic.ffmpegMac.b": "。",
  "lic.name": "名前",
  "lic.version": "バージョン",
  "lic.license": "ライセンス",
  "lic.links": "リンク",
  "lic.fullText": "ライセンス全文",
  "lic.source": "ダウンロード元",
} satisfies Record<keyof typeof en, string>;
