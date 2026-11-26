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
  "settings.title": "設定",
  "settings.nav.models": "モデルと実行環境",
  "bar.original": "原文",
  "bar.both": "二言語",
  "bar.language": "字幕の言語",
  "bar.size": "字幕のサイズ",
  "bar.color": "字幕の色",
  "bar.lineHeight": "行間",
  "bar.firstTitle": "二言語表示では{name}を原文の上に置きます",
  "bar.first": "{name}を上に",
} satisfies Record<keyof typeof en, string>;
