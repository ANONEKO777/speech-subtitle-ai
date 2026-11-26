import type { summary as en } from "../en/summary";

export const summary = {
  "summary.jump": "跳到 {time}",
  "summary.empty": "這個語言還沒有重點摘要。",
} satisfies Record<keyof typeof en, string>;
