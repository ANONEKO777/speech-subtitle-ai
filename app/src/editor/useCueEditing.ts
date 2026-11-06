import { useCallback, useState } from "react";
import { ApiError, type Backend, fetchEditedIds, putCues } from "../api/client";
import type { Cue } from "../player/cues";
import { type EditState, edited, fresh, replaceCue, sameCue, undoPlan, undone, withEdited } from "./state";
import { BACKEND_PROBLEM, type Draft, normalizeText, validateDraft } from "./validate";

export interface Loaded {
  readonly cues: readonly Cue[];
  readonly editedIds: readonly number[];
}

export interface CueEditing {
  readonly state: EditState;
  readonly editingId: number | null;
  /** The reason the last save of the cue being edited failed, until the next save attempt. */
  readonly refusal: string | null;
  /** A failure that belongs to no cue, such as a refused undo. */
  readonly failure: string | null;
  readonly begin: (id: number) => void;
  readonly cancel: () => void;
  readonly validate: (id: number, draft: Draft) => string | null;
  /** Saves the draft. True when the edit is over: saved, or nothing changed. */
  readonly commit: (id: number, draft: Draft) => Promise<boolean>;
  readonly undo: () => Promise<void>;
}

const reason = (e: unknown, id: number): string => {
  if (!(e instanceof ApiError)) return `無法連線到後端（${e instanceof Error ? e.message : String(e)}）`;
  const own = e.problems.find((p) => p.id === id) ?? e.problems[0];
  if (own) return BACKEND_PROBLEM[own.code] ?? own.message;
  return e.status === 409 ? `專案正被工作使用，暫時不能儲存（${e.message}）` : e.message;
};

/**
 * The cues of one project language and the edits made to them in this session. Every save sends
 * the whole list, which the backend checks again. `loaded` is a new object whenever the cues are
 * read afresh, such as after a change of language, and the edit state starts over then.
 */
export function useCueEditing(backend: Backend, projectId: string, lang: string, loaded: Loaded): CueEditing {
  const [state, setState] = useState(() => fresh(loaded.cues, loaded.editedIds));
  const [source, setSource] = useState(loaded);
  const [editingId, setEditingId] = useState<number | null>(null);
  const [refusal, setRefusal] = useState<string | null>(null);
  const [failure, setFailure] = useState<string | null>(null);
  if (source !== loaded) {
    setSource(loaded);
    setState(fresh(loaded.cues, loaded.editedIds));
    setEditingId(null);
    setRefusal(null);
    setFailure(null);
  }

  const begin = useCallback((id: number) => {
    setEditingId(id);
    setRefusal(null);
    setFailure(null);
  }, []);
  const cancel = useCallback(() => {
    setEditingId(null);
    setRefusal(null);
  }, []);

  const validate = useCallback(
    (id: number, draft: Draft) => {
      const index = state.cues.findIndex((c) => c.id === id);
      return validateDraft(state.cues, index, draft)?.message ?? null;
    },
    [state.cues],
  );

  const commit = useCallback(
    async (id: number, draft: Draft): Promise<boolean> => {
      const before = state.cues.find((c) => c.id === id);
      if (!before) return true;
      const after: Cue = { ...before, zh: normalizeText(draft.zh), startMs: draft.startMs, endMs: draft.endMs };
      if (sameCue(before, after)) {
        cancel();
        return true;
      }
      if (validate(id, { ...draft, zh: after.zh })) return false;
      setRefusal(null);
      try {
        await putCues(backend, projectId, lang, replaceCue(state.cues, after));
      } catch (e) {
        setRefusal(reason(e, id));
        return false;
      }
      const marks = await fetchEditedIds(backend, projectId, lang).catch(() => null);
      setState((s) => {
        const next = edited(s, before, after);
        return marks ? withEdited(next, marks) : next;
      });
      setEditingId(null);
      setRefusal(null);
      setFailure(null);
      return true;
    },
    [backend, projectId, lang, state.cues, validate, cancel],
  );

  const undo = useCallback(async () => {
    const plan = undoPlan(state);
    if (!plan) return;
    try {
      await putCues(backend, projectId, lang, plan.cues);
    } catch (e) {
      setFailure(`無法復原：${reason(e, plan.restore.id)}`);
      return;
    }
    const marks = await fetchEditedIds(backend, projectId, lang).catch(() => null);
    setState((s) => {
      const next = undone(s);
      return marks ? withEdited(next, marks) : next;
    });
    setEditingId(null);
    setFailure(null);
  }, [backend, projectId, lang, state]);

  return { state, editingId, refusal, failure, begin, cancel, validate, commit, undo };
}
