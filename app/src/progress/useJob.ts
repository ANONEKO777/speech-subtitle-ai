import { useEffect, useState } from "react";
import { type Backend, eventsUrl } from "../api/client";
import { type JobView, WAITING, reduceJob } from "./job";

const EVENTS = ["status", "progress", "done", "failed", "cancelled"] as const;

/**
 * Follows a job over server-sent events and closes the stream at the final event. The backend
 * runs on this machine, so a stream error means it died: stop waiting and report it instead of
 * letting EventSource retry forever behind a frozen bar.
 */
export function useJob(backend: Backend, jobId: string): JobView {
  const [view, setView] = useState<JobView>(WAITING);
  useEffect(() => {
    setView(WAITING);
    const source = new EventSource(eventsUrl(backend, jobId));
    for (const name of EVENTS) {
      source.addEventListener(name, (e) => {
        let data: unknown = null;
        try {
          data = JSON.parse((e as MessageEvent<string>).data);
        } catch {
          return;
        }
        setView((v) => reduceJob(v, name, data));
        if (name === "done" || name === "failed" || name === "cancelled") source.close();
      });
    }
    source.onerror = () => {
      source.close();
      setView((v) => reduceJob(v, "disconnected", null));
    };
    return () => source.close();
  }, [backend, jobId]);
  return view;
}
