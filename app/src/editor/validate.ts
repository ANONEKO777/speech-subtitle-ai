import type { Cue } from "../player/cues";

/** The longest a cue may last. The backend enforces the same limit (`cue_edits.MAX_CUE_MS`). */
export const MAX_CUE_MS = 7000;

export interface Draft {
  readonly zh: string;
  readonly startMs: number;
  readonly endMs: number;
}

export type ProblemCode = "empty" | "end_before_start" | "too_long" | "overlap" | "out_of_order";

/** What the backend's codes mean to the person editing, for the ones the checks above did not catch first. */
export const BACKEND_PROBLEM: Readonly<Record<string, string>> = {
  empty: "文字不能是空的",
  end_before_start: "結束時間早於開始時間",
  too_long: "超過 7 秒的上限",
  overlap: "與相鄰的字幕重疊",
  out_of_order: "開始時間早於上一條",
  english_changed: "英文原文不能修改",
  bad_text: "文字有多餘的空白或換行",
};

/** One text per line, with no blank lines and no spaces around a line, which is how the backend stores a cue. */
export const normalizeText = (text: string): string =>
  text
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter((line) => line !== "")
    .join("\n");

export interface Problem {
  readonly code: ProblemCode;
  readonly message: string;
}

const clockText = (ms: number) => {
  const total = Math.floor(ms / 1000);
  const m = Math.floor(total / 60);
  return `${m}:${String(total % 60).padStart(2, "0")}`;
};

/**
 * What is wrong with `draft` as the new content of `cues[index]`, or null when it can be saved.
 * Mirrors the rules of the backend, which still checks them: a collision is reported on the cue
 * being edited.
 */
export function validateDraft(cues: readonly Cue[], index: number, draft: Draft): Problem | null {
  const cue = cues[index];
  if (!cue) return null;
  if (draft.zh.trim() === "" && cue.zh !== "") return { code: "empty", message: "文字不能是空的" };
  if (draft.endMs < draft.startMs) return { code: "end_before_start", message: "結束時間早於開始時間" };
  if (draft.endMs - draft.startMs > MAX_CUE_MS) {
    const seconds = ((draft.endMs - draft.startMs) / 1000).toFixed(1);
    return { code: "too_long", message: `長 ${seconds} 秒，超過 7 秒的上限` };
  }
  const before = cues[index - 1];
  if (before && draft.startMs < before.startMs) {
    return { code: "out_of_order", message: `開始時間早於上一條（${clockText(before.startMs)}）` };
  }
  const reach = cues.slice(0, index).reduce((end, c) => Math.max(end, c.endMs), 0);
  if (draft.startMs < reach) {
    return { code: "overlap", message: `與上一條重疊，上一條到 ${formatClock(reach)} 才結束` };
  }
  const after = cues[index + 1];
  if (after && draft.endMs > after.startMs) {
    return { code: "overlap", message: `與下一條重疊，下一條從 ${formatClock(after.startMs)} 開始` };
  }
  return null;
}

/** `m:ss.mmm`, or `h:mm:ss.mmm` from one hour on. */
export function formatClock(ms: number): string {
  const whole = Math.max(0, Math.round(ms));
  const h = Math.floor(whole / 3_600_000);
  const m = Math.floor(whole / 60_000) % 60;
  const s = Math.floor(whole / 1000) % 60;
  const milli = String(whole % 1000).padStart(3, "0");
  const ss = String(s).padStart(2, "0");
  return h > 0 ? `${h}:${String(m).padStart(2, "0")}:${ss}.${milli}` : `${m}:${ss}.${milli}`;
}

/** Reads `h:mm:ss.mmm`, `m:ss.mmm`, `m:ss` or plain seconds. Null when the text is not a time. */
export function parseClock(text: string): number | null {
  const parts = text.trim().split(":");
  const shaped = parts.every((p, i) => (i === parts.length - 1 ? /^\d+(\.\d{1,3})?$/ : /^\d+$/).test(p));
  if (parts.length > 3 || !shaped) return null;
  const seconds = Number(parts.at(-1));
  const minutes = parts.slice(0, -1).map(Number);
  if ((minutes.length > 0 && seconds >= 60) || minutes.slice(1).some((n) => n >= 60)) return null;
  return Math.round(minutes.reduce((total, n) => total * 60 + n, 0) * 60_000 + seconds * 1000);
}
