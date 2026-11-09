import { useCallback, useEffect, useRef, useState } from "react";
import type { Backend } from "../api/client";
import { putPlayback } from "../api/library";
import { clampOffset } from "./transport";

/** The subtitle offset of a project in ms. A change reaches the project file 400 ms after the last one, and when the project closes. */
export function useOffset(backend: Backend, projectId: string, saved: number) {
  const [offsetMs, setOffset] = useState(saved);
  const pending = useRef<number | null>(null);
  const timer = useRef(0);

  const flush = useCallback(() => {
    window.clearTimeout(timer.current);
    if (pending.current === null) return;
    const ms = pending.current;
    pending.current = null;
    void putPlayback(backend, projectId, { offsetMs: ms }, true).catch(() => undefined);
  }, [backend, projectId]);

  useEffect(() => {
    setOffset(saved);
    return flush;
  }, [saved, flush]);

  const change = useCallback(
    (ms: number) => {
      const next = clampOffset(ms);
      setOffset(next);
      pending.current = next;
      window.clearTimeout(timer.current);
      timer.current = window.setTimeout(flush, 400);
    },
    [flush],
  );
  return { offsetMs, change };
}
