// Machine translation (Taiwan source to mainland terms). No native speaker has read it.
import type { autoUpdate as en } from "../en/autoUpdate";

export const autoUpdate = {
  "autoUpdate.banner.label": "新版本通知",
  "autoUpdate.banner.notes": "更新内容",
  "autoUpdate.banner.install": "下载并安装",
  "autoUpdate.banner.later": "稍后",
  "autoUpdate.banner.skip": "跳过此版本",
  "autoUpdate.busy.job": "正在处理视频。请等处理完成再安装，因为安装会中断处理。",
  "autoUpdate.busy.batch": "队列正在处理。请等队列运行完或暂停后再安装，因为安装会中断处理。",
  "autoUpdate.busy.export": "正在导出烧录字幕的视频。请等导出完成再安装，因为安装会中断导出。",
  "autoUpdate.busy.download": "正在下载模型或运行环境。请等下载完成再安装，因为安装会中断下载。",
  "autoUpdate.busy.move": "正在移动模型文件夹。请等移动完成再安装，因为安装会中断移动。",
  "autoUpdate.busy.selftest": "正在运行自检。请等自检完成再安装，因为安装会中断自检。",
  "autoUpdate.retry": "要重试，请点击“{button}”。",
  "autoUpdate.atStart": "启动时检查更新",
  "autoUpdate.atStartHint": "开启后，程序启动后会在后台连接 GitHub 查看是否有新版本，每天最多一次。有新版本只会通知你，你点击按钮后才会安装。",
  "autoUpdate.unsupported": "这个平台还没有自动更新，所以启动时不会检查。",
  "autoUpdate.lastChecked": "上次启动时检查：{time}",
  "autoUpdate.lastFailed": "上次启动时检查失败（{time}）：{reason}",
} satisfies Record<keyof typeof en, string>;
