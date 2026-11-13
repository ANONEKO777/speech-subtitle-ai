import { useEffect, useRef, useState } from "react";
import { DETECT_TIMEOUT_MS, type Detected, detectLanguage } from "../api/detect";
import type { Backend } from "../api/client";

export type DetectionBook = ReadonlyMap<string, Detected>;

/** Whether a path is worth asking about: an absolute path with a media extension. Whatever else is typed is the person still typing. */
export const worthDetecting = (path: string): boolean => /^([A-Za-z]:[\\/]|\\\\|\/)/.test(path) && /\.[A-Za-z0-9]{2,4}$/.test(path);

const PATH_SETTLE_MS = 500;

/**
 * The path typed into the import box once it has stopped changing for a moment, or an empty one
 * while it is still changing (so the note of the old path goes at the first key) and when
 * `askable` is false: the language is only asked where the picker it fills is shown.
 */
export function useSettledPath(typed: string, askable: boolean): string {
  const [settled, setSettled] = useState("");
  useEffect(() => {
    const timer = window.setTimeout(() => setSettled(typed), typed === "" ? 0 : PATH_SETTLE_MS);
    return () => window.clearTimeout(timer);
  }, [typed]);
  return askable && typed === settled ? typed : "";
}

/**
 * Names the language of each video in `paths`, one at a time and in the background, and keeps the
 * answers: a path asked about once is not asked again. A path that is no longer wanted when its
 * turn comes is skipped, and one that stops being wanted while it runs is let go of. A refusal,
 * a failure or a timeout is `failed`, which the window shows as nothing, and is forgotten once its
 * path is no longer wanted, so typing it again asks again.
 */
export function useDetections(backend: Backend | null, paths: readonly string[]): DetectionBook {
  const [book, setBook] = useState<DetectionBook>(new Map());
  const [tick, setTick] = useState(0);
  const running = useRef<{ readonly path: string; readonly stop: AbortController; dropped: boolean } | null>(null);
  const wanted = paths.filter(worthDetecting);
  const key = wanted.join("\n");

  useEffect(() => {
    const stale = [...book].filter(([path, found]) => found === "failed" && !wanted.includes(path));
    if (stale.length > 0) {
      setBook((b) => {
        const after = new Map(b);
        for (const [path] of stale) after.delete(path);
        return after;
      });
    }
    const current = running.current;
    if (current !== null && !wanted.includes(current.path)) {
      current.dropped = true;
      current.stop.abort();
    }
    if (!backend || running.current !== null) return;
    const next = wanted.find((path) => !book.has(path));
    if (next === undefined) return;
    const job = { path: next, stop: new AbortController(), dropped: false };
    const timer = window.setTimeout(() => job.stop.abort(), DETECT_TIMEOUT_MS);
    running.current = job;
    setBook((b) => new Map(b).set(next, "running"));
    void detectLanguage(backend, next, job.stop.signal).then((found) => {
      window.clearTimeout(timer);
      running.current = null;
      setBook((b) => {
        const after = new Map(b);
        if (job.dropped) after.delete(next);
        else after.set(next, found ?? "failed");
        return after;
      });
      setTick((n) => n + 1);
    });
  }, [backend, key, tick]);

  return book;
}
