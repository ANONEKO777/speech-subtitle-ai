/** The play queue: project ids in the order they play, and the one playing now. */
export interface Queue {
  readonly ids: readonly string[];
  readonly current: string | null;
}

export const EMPTY_QUEUE: Queue = { ids: [], current: null };
export const QUEUE_KEY = "vst.queue.v1";

export function parseQueue(raw: string | null): Queue {
  try {
    const o: unknown = JSON.parse(raw ?? "null");
    const ids = typeof o === "object" && o !== null ? (o as { ids?: unknown }).ids : null;
    if (!Array.isArray(ids)) return EMPTY_QUEUE;
    const clean = [...new Set(ids.filter((id): id is string => typeof id === "string"))];
    const current = (o as { current?: unknown }).current;
    return { ids: clean, current: typeof current === "string" && clean.includes(current) ? current : null };
  } catch {
    return EMPTY_QUEUE;
  }
}

export const enqueue = (q: Queue, id: string): Queue => (q.ids.includes(id) ? q : { ...q, ids: [...q.ids, id] });

export const dequeue = (q: Queue, id: string): Queue => ({
  ids: q.ids.filter((i) => i !== id),
  current: q.current === id ? null : q.current,
});

/** Marks `id` as playing. A video outside the queue leaves the queue as it is. */
export const playing = (q: Queue, id: string): Queue => ({ ...q, current: q.ids.includes(id) ? id : null });

/** The id one step from the current one, or null at either end or when nothing in the queue plays. */
export function neighbour(q: Queue, dir: 1 | -1): string | null {
  const at = q.current === null ? -1 : q.ids.indexOf(q.current);
  if (at < 0) return null;
  return q.ids[at + dir] ?? null;
}

/** Drops ids the library no longer has. */
export function pruned(q: Queue, known: ReadonlySet<string>): Queue {
  const ids = q.ids.filter((id) => known.has(id));
  return ids.length === q.ids.length ? q : { ids, current: q.current !== null && ids.includes(q.current) ? q.current : null };
}
