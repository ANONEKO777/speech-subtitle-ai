import { useEffect, useState } from "react";
import { type Backend, fetchSummary, fetchSummaryDegraded } from "../api/client";

export interface Summary {
  /** Null when that language has none. */
  readonly text: string | null;
  readonly degraded: boolean;
}

/** The summary of `lang`: undefined while loading. */
export function useSummary(backend: Backend, projectId: string, lang: string): Summary | undefined {
  const [loaded, setLoaded] = useState<{ key: string; summary: Summary } | null>(null);
  const key = `${projectId}:${lang}`;
  useEffect(() => {
    let current = true;
    Promise.all([fetchSummary(backend, projectId, lang), fetchSummaryDegraded(backend, projectId, lang).catch(() => false)])
      .then(([text, degraded]) => current && setLoaded({ key, summary: { text, degraded: text !== null && degraded } }))
      .catch(() => current && setLoaded({ key, summary: { text: null, degraded: false } }));
    return () => {
      current = false;
    };
  }, [backend, projectId, lang, key]);
  return loaded?.key === key ? loaded.summary : undefined;
}
