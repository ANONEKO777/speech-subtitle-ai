import type { CueFailures } from "../api/client";
import { type PluralTranslate, type Translate, pluralZhTW, tZhTW } from "../i18n";
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

/** What a message needs to speak: the window's translator, Traditional Chinese when none is given. */
export interface Speech {
  readonly t: Translate;
  readonly plural: PluralTranslate;
}
const ZH_TW: Speech = { t: tZhTW, plural: pluralZhTW };

/** The line above the cue list: how many cues failed, what is shown instead and why. */
export function failureSummary(open: ReadonlyMap<number, FailedKind>, target: string, say: Speech = ZH_TW): string {
  const empty = countKind(open, "empty");
  const english = countKind(open, "english");
  const parts = [
    empty > 0 ? say.t("player.failedEmpty", { n: empty, target }) : "",
    english > 0 ? say.t("player.failedEnglish", { n: english }) : "",
  ].filter(Boolean);
  return say.plural("player.failedNote", open.size, { parts: parts.join(say.t("player.failedJoin")) });
}

/** What the mark on one cue says. */
export const failureTitle = (kind: FailedKind, target: string, t: Translate = tZhTW): string =>
  kind === "empty" ? t("player.failedEmptyTitle", { target }) : t("player.failedEnglishTitle");
