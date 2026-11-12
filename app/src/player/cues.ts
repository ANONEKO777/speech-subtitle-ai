export interface Cue {
  readonly id: number;
  readonly startMs: number;
  readonly endMs: number;
  /** What was said, in the language `lang`. */
  readonly src: string;
  /** The spoken language of this cue, a source language code. */
  readonly lang: string;
  readonly zh: string;
}

/** Which lines show. `en` is the name the backend and the saved settings give the source text, whatever language it is in. */
export type SubtitleMode = "en" | "zh" | "both";

/**
 * Index of the cue showing at `timeMs`, or -1 in a gap. `cues` must be sorted by start time with
 * no overlaps, which the backend guarantees for every subtitle file it writes.
 */
export function cueAt(cues: readonly Cue[], timeMs: number): number {
  let lo = 0;
  let hi = cues.length - 1;
  while (lo <= hi) {
    const mid = (lo + hi) >> 1;
    const cue = cues[mid];
    if (cue === undefined) return -1;
    if (timeMs < cue.startMs) hi = mid - 1;
    else if (timeMs >= cue.endMs) lo = mid + 1;
    else return mid;
  }
  return -1;
}
