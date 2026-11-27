// Machine translation (Taiwan source to mainland terms). No native speaker has read it.
import type { errors as en } from "../en/errors";

export const errors = {
  "errors.jobRunning": "这部视频正在处理中，请等它完成后再试。",
  "errors.backendLost": "与后端的连接中断，处理已停止。后端可能已退出，请重新启动本软件。",
  "errors.updateUnreadable": "更新检查返回了无法识别的结果。",
  "errors.updateIncomplete": "更新没有完成。",
} satisfies Record<keyof typeof en, string>;
