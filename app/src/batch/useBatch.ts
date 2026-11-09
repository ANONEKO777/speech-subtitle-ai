import { useEffect, useReducer } from "react";
import type { Backend } from "../api/client";
import { EMPTY_BATCH, type Batch, reduceBatch } from "./model";
import { followQueue } from "./follow";

/** The queue as the backend reports it, kept live over the queue stream while `backend` is set. */
export function useBatch(backend: Backend | null): Batch {
  const [batch, dispatch] = useReducer(reduceBatch, EMPTY_BATCH);
  useEffect(() => {
    if (!backend) return;
    const stop = new AbortController();
    void followQueue(
      backend,
      {
        snapshot: (snapshot) => dispatch({ type: "snapshot", snapshot }),
        event: (kind, data, replay) => dispatch({ type: "event", kind, data, replay }),
        link: (link) => dispatch({ type: "link", link }),
      },
      stop.signal,
    );
    return () => stop.abort();
  }, [backend]);
  return batch;
}
