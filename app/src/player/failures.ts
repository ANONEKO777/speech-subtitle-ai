import type { CueFailures } from "../api/client";
import type { Cue } from "./cues";

/** How a cue the translator could not do looks now: no translation at all, or its English in place of the translation. */
export type FailedKind = "empty" | "english";

/**
 * The cues of `failures` that are still wrong. A cue left empty counts until it has text, so a
 * person's edit that fills it ends it. A cue that shows its English counts until the person edits it.
 */
export function openFailures(
  failures: CueFailures | undefined,
  cues: readonly Cue[],
  edited: ReadonlySet<number>,
): ReadonlyMap<number, FailedKind> {
  const open = new Map<number, FailedKind>();
  if (failures === undefined) return open;
  const english = new Set(failures.english);
  const byId = new Map(cues.map((c) => [c.id, c]));
  for (const id of failures.failed) {
    const cue = byId.get(id);
    if (cue === undefined) continue;
    if (english.has(id)) {
      if (!edited.has(id)) open.set(id, "english");
    } else if (cue.zh.trim() === "") open.set(id, "empty");
  }
  return open;
}

export const countKind = (open: ReadonlyMap<number, FailedKind>, kind: FailedKind): number =>
  [...open.values()].filter((k) => k === kind).length;

/** The line above the cue list: how many cues failed, what is shown instead and why. */
export function failureSummary(open: ReadonlyMap<number, FailedKind>, target: string): string {
  const empty = countKind(open, "empty");
  const english = countKind(open, "english");
  const parts = [
    empty > 0 ? `${empty} 則沒有${target}翻譯，已留空` : "",
    english > 0 ? `${english} 則改用英文顯示` : "",
  ].filter(Boolean);
  return `${open.size} 則字幕翻譯失敗：${parts.join("，")}。原因是模型多次的回答都沒有通過檢查，例如夾雜日文、字數不合。`;
}

/** What the mark on one cue says. */
export const failureTitle = (kind: FailedKind, target: string): string =>
  kind === "empty"
    ? `這一則沒有${target}翻譯（模型多次的回答都沒有通過檢查）。雙語字幕只會顯示原文，可以按兩下自己補上。`
    : "這一則翻譯失敗，顯示的是英文（模型多次的回答都沒有通過檢查）。可以按兩下自己改。";
