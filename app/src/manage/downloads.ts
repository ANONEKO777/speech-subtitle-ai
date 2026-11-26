import { type Translate, tZhTW } from "../i18n";
import type { DownloadJob, JobState } from "./types";

const TERMINAL: ReadonlySet<JobState> = new Set(["done", "failed", "cancelled"]);

export const isActive = (job: DownloadJob): boolean => !TERMINAL.has(job.state);

export const fraction = (job: DownloadJob): number =>
  job.state === "done" ? 1 : job.bytesTotal > 0 ? Math.min(1, job.bytesDone / job.bytesTotal) : 0;

/** The newest job of each asset. The backend lists jobs oldest first. */
export function latestByAsset(jobs: readonly DownloadJob[]): ReadonlyMap<string, DownloadJob> {
  const out = new Map<string, DownloadJob>();
  for (const job of jobs) out.set(job.assetId, job);
  return out;
}

export interface Tracked {
  readonly jobs: ReadonlyMap<string, DownloadJob>;
  /** Assets whose newest job ended since the previous poll, so their rows need a fresh read. */
  readonly ended: readonly string[];
}

export function track(prev: ReadonlyMap<string, DownloadJob>, list: readonly DownloadJob[]): Tracked {
  const jobs = latestByAsset(list);
  const ended = [...jobs.values()].filter((job) => {
    const before = prev.get(job.assetId);
    return !isActive(job) && (before === undefined ? false : isActive(before) || before.id !== job.id);
  });
  return { jobs, ended: ended.map((j) => j.assetId) };
}

/** Overall progress of the jobs, weighted by size. */
export function overall(jobs: readonly DownloadJob[]): { done: number; total: number; fraction: number; speedBps: number } {
  const total = jobs.reduce((n, j) => n + j.bytesTotal, 0);
  const done = jobs.reduce((n, j) => n + (j.state === "done" ? j.bytesTotal : Math.min(j.bytesDone, j.bytesTotal)), 0);
  return { done, total, fraction: total > 0 ? done / total : 0, speedBps: jobs.reduce((n, j) => n + (isActive(j) ? j.speedBps : 0), 0) };
}

export function stateLabel(job: DownloadJob, t: Translate = tZhTW): string {
  switch (job.state) {
    case "queued":
      return t("download.state.queued");
    case "downloading":
      return job.resumedFrom > 0 ? t("download.state.resumed") : t("download.state.downloading");
    case "verifying":
      return t("download.state.verifying");
    case "extracting":
      return t("download.state.extracting");
    case "done":
      return t("download.state.done");
    case "failed":
      return t("download.state.failed");
    case "cancelled":
      return t("download.state.cancelled");
  }
}
