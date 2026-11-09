import { type Backend, base } from "../api/client";
import { fetchQueue } from "./api";
import type { Link, Snapshot } from "./model";
import { parseSse } from "./sse";

export interface Sink {
  snapshot(s: Snapshot): void;
  event(kind: string, data: unknown, replay: boolean): void;
  link(l: Link): void;
}

/** The backend sends a keepalive every 15 s, so a silence this long means the connection is dead. */
export const SILENCE_MS = 40_000;
export const RETRY_MS = 1000;
/** Events in the first moments of a connection that starts at the top of the log are old news. */
export const REPLAY_MS = 600;

const pause = (ms: number, signal: AbortSignal) =>
  new Promise<void>((resolve) => {
    const t = setTimeout(resolve, ms);
    signal.addEventListener("abort", () => (clearTimeout(t), resolve()), { once: true });
  });

/**
 * Follows `/api/queue/events` until `signal` aborts. The stream needs the Authorization header,
 * which EventSource cannot send, so this reads a fetch body. Each (re)connect first takes a
 * snapshot, then resumes the stream after the last id seen, so a short drop loses nothing. A
 * restarted backend is a new `Backend` and so a new call, which starts from the top of its log.
 */
export async function followQueue(b: Backend, sink: Sink, signal: AbortSignal): Promise<void> {
  let lastId = -1;
  while (!signal.aborted) {
    const watchdog = new AbortController();
    const stop = () => watchdog.abort();
    signal.addEventListener("abort", stop, { once: true });
    let timer = setTimeout(stop, SILENCE_MS);
    try {
      sink.link("connecting");
      sink.snapshot(await fetchQueue(b));
      const res = await fetch(`${base(b)}/api/queue/events`, {
        headers: { authorization: `Bearer ${b.token}`, ...(lastId >= 0 ? { "last-event-id": String(lastId) } : {}) },
        signal: watchdog.signal,
      });
      if (!res.ok || !res.body) throw new Error(`queue stream answered ${res.status}`);
      sink.link("live");
      const replayUntil = lastId < 0 ? Date.now() + REPLAY_MS : 0;
      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";
      for (;;) {
        const { done, value } = await reader.read();
        if (done) break;
        clearTimeout(timer);
        timer = setTimeout(stop, SILENCE_MS);
        const parsed = parseSse(buffer + decoder.decode(value, { stream: true }));
        buffer = parsed.rest;
        for (const m of parsed.messages) {
          if (m.id !== null && Number.isInteger(Number(m.id))) lastId = Number(m.id);
          try {
            sink.event(m.event, JSON.parse(m.data), Date.now() < replayUntil);
          } catch {
            // a frame that is not JSON carries nothing we know
          }
        }
      }
    } catch {
      // fall through to the retry below
    } finally {
      clearTimeout(timer);
      signal.removeEventListener("abort", stop);
    }
    if (signal.aborted) return;
    sink.link("lost");
    await pause(RETRY_MS, signal);
  }
}
