import { type Backend, asRecord, call } from "../api/client";
import type { Batch } from "../batch/model";
import type { PlainKey, Translate } from "../i18n";

/** What the backend runs on its own (`GET /api/work`), in the order it lists them. */
const BACKEND_WORK = ["job", "export", "download", "move", "selftest"] as const;
export type BackendWork = (typeof BACKEND_WORK)[number];

/** Work that installing would cut off, because the installer stops the backend first. */
export type Work = "batch" | BackendWork | null;

const REASON: Readonly<Record<Exclude<Work, null>, PlainKey>> = {
  job: "autoUpdate.busy.job",
  batch: "autoUpdate.busy.batch",
  export: "autoUpdate.busy.export",
  download: "autoUpdate.busy.download",
  move: "autoUpdate.busy.move",
  selftest: "autoUpdate.busy.selftest",
};

export const workReason = (work: Exclude<Work, null>, t: Translate): string => t(REASON[work]);

const isBackendWork = (v: unknown): v is BackendWork => BACKEND_WORK.some((w) => w === v);

export function parseBackendWork(raw: unknown): readonly BackendWork[] {
  const list = asRecord(raw)?.["work"];
  return Array.isArray(list) ? list.filter(isBackendWork) : [];
}

/** A backend that does not answer within this time is taken to be doing what it last said. */
const ASK_TIMEOUT_MS = 3000;

export const fetchBackendWork = async (b: Backend): Promise<readonly BackendWork[]> =>
  parseBackendWork(await call(b, "/api/work", { signal: AbortSignal.timeout(ASK_TIMEOUT_MS) }));

/** The work the window follows itself: the video it is processing and the batch. */
export function windowWork(importing: boolean, batch: Batch): Work {
  if (importing) return "job";
  const running = batch.items.some((i) => i.state === "running");
  const waiting = !batch.paused && batch.items.some((i) => i.state === "queued");
  return running || waiting ? "batch" : null;
}

/** The one rule for what holds the install: the window's own work first, then the backend's. */
export const holdingWork = (window: Work, backend: readonly BackendWork[]): Work => window ?? backend[0] ?? null;
