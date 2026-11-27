// Machine translation (Taiwan source to mainland terms). No native speaker has read it.
import type { licenses as en } from "../en/licenses";

export const licenses = {
  "lic.title": "第三方许可证",
  "lic.hint": "本软件另外下载的每个模型与可执行文件各自的许可证与来源。链接会在浏览器中打开。",
  "lic.program.pre": "本程序采用 ",
  "lic.program.post": " 许可证。源代码：",
  "lic.ffmpeg.a": "安装程序附带 FFmpeg 8.1（",
  "lic.ffmpeg.b": "构建，未含 GPL 或 nonfree 组件），以独立的 ffmpeg.exe 与 DLL 放在安装文件夹的 ffmpeg 子文件夹，可自行替换。FFmpeg 源代码：",
  "lic.ffmpeg.c": "，构建脚本：",
  "lic.ffmpeg.d": "。完整声明在安装文件夹的 THIRD_PARTY.md 中。",
  "lic.ffmpegMac.a": "本软件不附带 FFmpeg，而是使用你通过 Homebrew 安装的版本，其许可证以该版本为准。请见 ",
  "lic.ffmpegMac.b": "。",
  "lic.name": "名称",
  "lic.version": "版本",
  "lic.license": "许可证",
  "lic.links": "链接",
  "lic.fullText": "许可证全文",
  "lic.source": "下载来源",
} satisfies Record<keyof typeof en, string>;
