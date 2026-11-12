import { type Backend, asRecord, call } from "../api/client";
import type { SourceLang } from "../api/sourceLang";
import type { BatchSettings, Snapshot } from "./model";
import { parseSettings, parseSnapshot } from "./model";

export const fetchQueue = async (b: Backend): Promise<Snapshot> => parseSnapshot(await call(b, "/api/queue"));

export interface AddEntry {
  readonly path: string;
  readonly lang: string;
  /** The language spoken in the video. */
  readonly source: SourceLang;
  /** A folder is scanned by the backend for videos. */
  readonly folder?: { readonly recursive: boolean };
}

export interface Skipped {
  readonly path: string;
  readonly reason: string;
}

export async function addToQueue(b: Backend, entries: readonly AddEntry[]): Promise<{ added: number; skipped: Skipped[] }> {
  const items = entries.filter((e) => !e.folder).map((e) => ({ path: e.path, target_lang: e.lang, source_lang: e.source }));
  const folders = entries.flatMap((e) =>
    e.folder ? [{ path: e.path, target_lang: e.lang, source_lang: e.source, recursive: e.folder.recursive }] : [],
  );
  const body = asRecord(await call(b, "/api/queue/items", { method: "POST", body: JSON.stringify({ items, folders }) }));
  const skipped = (Array.isArray(body?.["skipped"]) ? (body["skipped"] as unknown[]) : []).flatMap((s): Skipped[] => {
    const o = asRecord(s);
    return typeof o?.["path"] === "string" ? [{ path: o["path"], reason: String(o["reason"] ?? "") }] : [];
  });
  return { added: Array.isArray(body?.["added"]) ? body["added"].length : 0, skipped };
}

export type ItemAction = "pause" | "resume" | "cancel" | "retry";

export const itemAction = (b: Backend, id: string, action: ItemAction) =>
  call(b, `/api/queue/items/${encodeURIComponent(id)}/${action}`, { method: "POST" });

export const removeItem = (b: Backend, id: string) =>
  call(b, `/api/queue/items/${encodeURIComponent(id)}`, { method: "DELETE" });

export const removeFinished = (b: Backend) => call(b, "/api/queue/finished", { method: "DELETE" });

export const reorderQueue = (b: Backend, ids: readonly string[]) =>
  call(b, "/api/queue/order", { method: "PUT", body: JSON.stringify({ ids }) });

export const setQueuePaused = (b: Backend, paused: boolean, interrupt = false) =>
  call(b, `/api/queue/${paused ? "pause" : "resume"}`, {
    method: "POST",
    ...(paused ? { body: JSON.stringify({ interrupt }) } : {}),
  });

export async function putSettings(b: Backend, s: BatchSettings): Promise<BatchSettings> {
  const body = await call(b, "/api/queue/settings", {
    method: "PUT",
    body: JSON.stringify({ on_done: s.onDone, allow_power: s.allowPower }),
  });
  return parseSettings(asRecord(body)?.["settings"]);
}

export const cancelPower = (b: Backend) => call(b, "/api/queue/power/cancel", { method: "POST" });
