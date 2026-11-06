import { useEffect, useState } from "react";
import { type Backend, fetchSummary } from "../api/client";

/** The summary text of `lang`: undefined while loading, null when that language has none. */
export function useSummary(backend: Backend, projectId: string, lang: string): string | null | undefined {
  const [loaded, setLoaded] = useState<{ key: string; text: string | null } | null>(null);
  const key = `${projectId}:${lang}`;
  useEffect(() => {
    let current = true;
    fetchSummary(backend, projectId, lang)
      .then((text) => current && setLoaded({ key, text }))
      .catch(() => current && setLoaded({ key, text: null }));
    return () => {
      current = false;
    };
  }, [backend, projectId, lang, key]);
  return loaded?.key === key ? loaded.text : undefined;
}
