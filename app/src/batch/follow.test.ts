import { afterEach, describe, expect, it, vi } from "vitest";
import { followQueue } from "./follow";
import type { Link } from "./model";

const backend = { port: 5, token: "secret" };
const enc = new TextEncoder();

const json = (body: unknown) => new Response(JSON.stringify(body), { headers: { "content-type": "application/json" } });
const stream = (frames: string[]) =>
  new Response(
    new ReadableStream({
      start(c) {
        for (const f of frames) c.enqueue(enc.encode(f));
        c.close();
      },
    }),
  );
const frame = (id: number, kind: string, data: unknown) => `id: ${id}\nevent: ${kind}\ndata: ${JSON.stringify(data)}\n\n`;

afterEach(() => vi.unstubAllGlobals());

describe("following the queue stream", () => {
  it("sends the token in a header, resumes after the last id on a drop, and reports the link", async () => {
    const calls: { url: string; headers: Record<string, string> }[] = [];
    const answers = [
      () => json({ items: [], paused: false }),
      () => stream([frame(1, "queue", { paused: true }), frame(2, "removed", { ids: [] })]),
      () => json({ items: [], paused: false }),
      () => stream([frame(3, "queue", { paused: false })]),
    ];
    const stop = new AbortController();
    vi.stubGlobal("fetch", async (url: string, init: RequestInit) => {
      calls.push({ url, headers: { ...(init.headers as Record<string, string>) } });
      const next = answers.shift();
      if (!next) {
        stop.abort();
        throw new Error("done");
      }
      return next();
    });
    const links: Link[] = [];
    const events: [string, boolean][] = [];
    await followQueue(
      backend,
      { snapshot: () => undefined, event: (k, _d, replay) => events.push([k, replay]), link: (l) => links.push(l) },
      stop.signal,
    );
    expect(calls[1]?.url).toBe("http://127.0.0.1:5/api/queue/events");
    expect(calls[1]?.headers["authorization"]).toBe("Bearer secret");
    expect(calls[1]?.headers["last-event-id"]).toBeUndefined();
    expect(calls[3]?.headers["last-event-id"]).toBe("2");
    expect(events.map(([k]) => k)).toEqual(["queue", "removed", "queue"]);
    expect(events[0]?.[1]).toBe(true);
    expect(events[2]?.[1]).toBe(false);
    expect(links).toContain("lost");
    expect(links.filter((l) => l === "live")).toHaveLength(2);
  }, 10_000);

  it("keeps retrying while the backend is down", async () => {
    let tries = 0;
    const stop = new AbortController();
    vi.stubGlobal("fetch", async () => {
      if (++tries >= 2) stop.abort();
      throw new TypeError("failed to fetch");
    });
    const links: Link[] = [];
    await followQueue(backend, { snapshot: () => undefined, event: () => undefined, link: (l) => links.push(l) }, stop.signal);
    expect(tries).toBe(2);
    expect(links).toContain("lost");
  }, 10_000);
});
