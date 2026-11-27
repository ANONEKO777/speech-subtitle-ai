// Machine translation (Taiwan source to mainland terms). No native speaker has read it.
import type { update as en } from "../en/update";

export const update = {
  "update.title": "检查更新",
  "update.hint": "只在你点击按钮时才联网检查。模型与设置不会因为更新而重新下载。",
  "update.check": "检查更新",
  "update.checking": "正在检查更新…",
  "update.upToDate": "已是最新版。",
  "update.upToDateVersion": "已是最新版（{version}）。",
  "update.available": "有新版 {version}。",
  "update.availableFrom": "有新版 {version}（当前 {current}）。",
  "update.download": "下载更新",
  "update.downloading": "正在下载 {version}，请稍候…",
  "update.downloaded": "{version} 已下载，签名验证通过。安装时本软件会关闭并重新打开。",
  "update.install": "安装并重新启动",
  "update.installing": "正在启动安装程序…",
} satisfies Record<keyof typeof en, string>;
