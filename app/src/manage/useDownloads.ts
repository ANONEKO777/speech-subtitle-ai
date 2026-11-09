import { useCallback, useEffect, useRef, useState } from "react";
import type { Backend } from "../api/client";
import { fetchDownloads } from "./api";
import { track } from "./downloads";
import type { DownloadJob } from "./types";

export interface Downloads {
  /** Every job the backend lists, oldest first. */
  readonly list: readonly DownloadJob[];
  readonly byAsset: ReadonlyMap<string, DownloadJob>;
  /** Reads the list now, for example right after starting a job. */
  readonly refresh: () => void;
}

/** Polls the download list once a second. `onEnded` gets the assets whose newest job just ended. */
export function useDownloads(backend: Backend, onEnded?: (assets: readonly string[]) => void): Downloads {
  const [state, setState] = useState<{ list: readonly DownloadJob[]; byAsset: ReadonlyMap<string, DownloadJob> }>({
    list: [],
    byAsset: new Map(),
  });
  const prev = useRef<ReadonlyMap<string, DownloadJob>>(new Map());
  const ended = useRef(onEnded);
  ended.current = onEnded;
  const wake = useRef<() => void>(() => undefined);

  useEffect(() => {
    let alive = true;
    let timer: number | undefined;
    const tick = async () => {
      try {
        const list = await fetchDownloads(backend);
        if (!alive) return;
        const t = track(prev.current, list);
        prev.current = t.jobs;
        setState({ list, byAsset: t.jobs });
        if (t.ended.length > 0) ended.current?.(t.ended);
      } catch {
        // the backend is gone or busy; the next tick asks again
      }
      if (alive) timer = window.setTimeout(() => void tick(), 1000);
    };
    wake.current = () => {
      window.clearTimeout(timer);
      void tick();
    };
    void tick();
    return () => {
      alive = false;
      window.clearTimeout(timer);
    };
  }, [backend]);

  const refresh = useCallback(() => wake.current(), []);
  return { ...state, refresh };
}
