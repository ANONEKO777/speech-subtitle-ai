// Machine translation (Taiwan source to mainland terms). No native speaker has read it.
import type { settings as en } from "../en/settings";

export const settings = {
  "language.nav": "语言",
  "language.title": "界面语言",
  "language.hint": "选择窗口使用的语言。更改会立即生效，无需重新启动。",
  "language.note": "这只会改变窗口上的文字。视频的语音语言和字幕语言保持你的设置。",
  "language.label": "窗口语言",
  "language.auto": "自动（跟随系统）",
  "language.machine": "{name}（机器翻译）",
  "language.saved": "已应用。",
  "language.failed": "无法保存语言设置：{reason}",
  "settings.title": "设置",
  "settings.nav.models": "模型与运行环境",
  "bar.original": "原文",
  "bar.both": "双语",
  "bar.language": "字幕语言",
  "bar.size": "字幕大小",
  "bar.color": "字幕颜色",
  "bar.lineHeight": "行距",
  "bar.firstTitle": "双语时{name}放在原文上方",
  "bar.first": "{name}在上",
} satisfies Record<keyof typeof en, string>;
