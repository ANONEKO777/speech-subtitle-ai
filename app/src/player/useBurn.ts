import { useCallback, useEffect, useRef, useState } from "react";
import {
  type Backend,
} from "../api/client";
import { type BurnView, type Look, cancelBurn, fetchBurn, startBurn } from "../api/library";
import { type Said, said } from "../i18n/said";

/** The burned-in video export that is running or just ended, followed by polling the backend. */
export function useBurn(backend: Backend, onEnd: (view: BurnView) => void) {
  const [view, setView] = useState<BurnView | null>(null);
  const [error, setError] = useState<Said | null>(null);
  const end = useRef(onEnd);
  end.current = onEnd;
  const id = view?.state === "running" ? view.id : null;

  useEffect(() => {
    if (id === null) return;
    let alive = true;
    const tick = window.setInterval(() => {
      fetchBurn(backend, id).then(
        (next) => {
          if (!alive) return;
          setView(next);
          if (next.state !== "running") end.current(next);
        },
        (e: unknown) => alive && setError(said(e)),
      );
    }, 500);
    return () => {
      alive = false;
      window.clearInterval(tick);
    };
  }, [backend, id]);

  const start = useCallback(
    async (projectId: string, req: { lang: string; dir: string; look: Look; startS: number; durationS: number | null }) => {
      setError(null);
      try {
        setView(await startBurn(backend, projectId, req));
      } catch (e) {
        setError(said(e));
      }
    },
    [backend],
  );
  const cancel = useCallback(() => {
    if (id !== null) void cancelBurn(backend, id);
  }, [backend, id]);
  return { view, error, start, cancel };
}
