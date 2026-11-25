// Machine translation. No native speaker has read it.
import type { settings as en } from "../en/settings";

export const settings = {
  "language.nav": "言語",
  "language.title": "表示言語",
  "language.hint": "ウィンドウに使う言語を選びます。変更はすぐに反映され、再起動は不要です。",
  "language.note": "変わるのはウィンドウの文字だけです。動画の音声の言語と字幕の言語は、設定したままです。",
  "language.label": "ウィンドウの言語",
  "language.auto": "自動（システムに合わせる）",
  "language.machine": "{name}（機械翻訳）",
  "language.saved": "反映しました。",
  "language.failed": "言語の設定を保存できませんでした：{reason}",
} satisfies Record<keyof typeof en, string>;
