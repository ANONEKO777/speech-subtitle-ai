import type { Cue } from "../player/cues";

/**
 * The cues on screen, which of them a person corrected (a rerun of translate keeps those), and
 * the earlier versions to go back to, newest last. Undo lasts for the session only.
 */
export interface EditState {
  readonly cues: readonly Cue[];
  readonly edited: ReadonlySet<number>;
  readonly undo: readonly Cue[];
}

export const fresh = (cues: readonly Cue[], edited: Iterable<number>): EditState => ({
  cues,
  edited: new Set(edited),
  undo: [],
});

export const replaceCue = (cues: readonly Cue[], cue: Cue): Cue[] => cues.map((c) => (c.id === cue.id ? cue : c));

export const sameCue = (a: Cue, b: Cue) => a.zh === b.zh && a.startMs === b.startMs && a.endMs === b.endMs;

/** The state after `after` replaced `before` and the backend saved it. */
export function edited(state: EditState, before: Cue, after: Cue): EditState {
  return {
    cues: replaceCue(state.cues, after),
    edited: new Set(state.edited).add(after.id),
    undo: [...state.undo, before],
  };
}

/** The cue list that undoing the last edit would save, or null when there is nothing to undo. */
export function undoPlan(state: EditState): { readonly cues: Cue[]; readonly restore: Cue } | null {
  const restore = state.undo.at(-1);
  return restore ? { cues: replaceCue(state.cues, restore), restore } : null;
}

/** The state after the backend saved the plan from `undoPlan`. */
export function undone(state: EditState): EditState {
  const plan = undoPlan(state);
  return plan ? { ...state, cues: plan.cues, undo: state.undo.slice(0, -1) } : state;
}

/** The marks as the backend now records them, which drop a cue that was put back to the translator's text. */
export const withEdited = (state: EditState, ids: Iterable<number>): EditState => ({ ...state, edited: new Set(ids) });
