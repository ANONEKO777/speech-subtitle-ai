import { asRecord } from "../api/client";
import { type SourceLang, parseSourceLang } from "../api/sourceLang";
import { type PlainKey, type Translate, tZhTW } from "../i18n";

export const STEP_ORDER = ["audio", "vad", "asr", "segment", "translate", "export", "summarize"] as const;
export type QueueStep = (typeof STEP_ORDER)[number];

/** Step names for a queue row. The language is on the row, so the translate step does not name one. */
export const STEP_NAME: Record<QueueStep, PlainKey> = {
  audio: "progress.step.audio",
  vad: "progress.step.vad",
  asr: "progress.step.asr",
  segment: "progress.step.segment",
  translate: "batch.step.translate",
  export: "progress.step.export",
  summarize: "progress.step.summarize",
};

export type ItemState = "queued" | "running" | "paused" | "done" | "failed" | "cancelled";
const STATES: readonly ItemState[] = ["queued", "running", "paused", "done", "failed", "cancelled"];

export type OnDone = "notify" | "sleep" | "shutdown";
export type PowerAction = Exclude<OnDone, "notify">;

export interface BatchItem {
  readonly id: string;
  readonly videoPath: string;
  readonly projectId: string;
  readonly lang: string;
  readonly sourceLang: SourceLang;
  readonly state: ItemState;
  readonly position: number;
  readonly step: QueueStep | null;
  /** 0 to 1 over the whole pipeline. */
  readonly progress: number;
  readonly etaS: number | null;
  readonly attempts: number;
  readonly error: string | null;
  readonly audioS: number | null;
}

export interface BatchSettings {
  readonly onDone: OnDone;
  readonly allowPower: boolean;
}

export interface Countdown {
  readonly action: PowerAction;
  readonly deadlineMs: number;
}

export type Link = "connecting" | "live" | "lost";

export interface Counts {
  readonly done: number;
  readonly failed: number;
  readonly cancelled: number;
}

export interface Batch {
  readonly items: readonly BatchItem[];
  readonly paused: boolean;
  readonly settings: BatchSettings;
  readonly countdown: Countdown | null;
  readonly link: Link;
  /** False until the first snapshot has arrived. */
  readonly loaded: boolean;
  /** Set each time the backend reports that the queue ran dry; `n` counts the reports. */
  readonly finished: { readonly n: number; readonly counts: Counts } | null;
}

export const EMPTY_BATCH: Batch = {
  items: [],
  paused: false,
  settings: { onDone: "notify", allowPower: false },
  countdown: null,
  link: "connecting",
  loaded: false,
  finished: null,
};

export interface Snapshot {
  readonly items: readonly BatchItem[];
  readonly paused: boolean;
  readonly settings: BatchSettings;
  /** Whether the backend has a power countdown running. Its deadline arrives as an event. */
  readonly counting: boolean;
}

export type BatchEvent =
  | { readonly type: "snapshot"; readonly snapshot: Snapshot }
  /** `replay` marks an event from the backend's log that happened before this connection. */
  | { readonly type: "event"; readonly kind: string; readonly data: unknown; readonly replay?: boolean }
  | { readonly type: "link"; readonly link: Link };

const isStep = (v: unknown): v is QueueStep => STEP_ORDER.some((s) => s === v);
const isState = (v: unknown): v is ItemState => STATES.some((s) => s === v);
const num = (v: unknown): number | null => (typeof v === "number" && Number.isFinite(v) ? v : null);

export function parseItem(raw: unknown): BatchItem | null {
  const o = asRecord(raw);
  if (
    typeof o?.["id"] !== "string" ||
    typeof o["video_path"] !== "string" ||
    typeof o["target_lang"] !== "string" ||
    !isState(o["state"])
  ) {
    return null;
  }
  const error = o["last_error"];
  return {
    id: o["id"],
    videoPath: o["video_path"],
    projectId: typeof o["project_id"] === "string" ? o["project_id"] : "",
    lang: o["target_lang"],
    sourceLang: parseSourceLang(o["source_lang"]),
    state: o["state"],
    position: num(o["position"]) ?? 0,
    step: isStep(o["step"]) ? o["step"] : null,
    progress: Math.min(1, Math.max(0, num(o["progress"]) ?? 0)),
    etaS: num(o["eta_s"]),
    attempts: num(o["attempts"]) ?? 0,
    error: typeof error === "string" && error !== "" ? error : null,
    audioS: num(o["audio_s"]),
  };
}

export function parseSettings(raw: unknown): BatchSettings {
  const o = asRecord(raw);
  const onDone = o?.["on_done"];
  return {
    onDone: onDone === "sleep" || onDone === "shutdown" ? onDone : "notify",
    allowPower: o?.["allow_power"] === true,
  };
}

function parseCountdown(raw: unknown): Countdown | null {
  const o = asRecord(raw);
  const action = o?.["action"];
  const deadline = num(o?.["deadline_ms"]);
  return (action === "sleep" || action === "shutdown") && deadline !== null ? { action, deadlineMs: deadline } : null;
}

/** Reads the body of `GET /api/queue`. */
export function parseSnapshot(raw: unknown): Snapshot {
  const o = asRecord(raw);
  const list = Array.isArray(o?.["items"]) ? (o["items"] as unknown[]) : [];
  return {
    items: sorted(list.flatMap((i) => parseItem(i) ?? [])),
    paused: o?.["paused"] === true,
    settings: parseSettings(o?.["settings"]),
    counting: o?.["countdown"] === true,
  };
}

const sorted = (items: readonly BatchItem[]): BatchItem[] => [...items].sort((a, b) => a.position - b.position);

function counts(raw: unknown): Counts {
  const c = asRecord(asRecord(raw)?.["counts"]);
  return { done: num(c?.["done"]) ?? 0, failed: num(c?.["failed"]) ?? 0, cancelled: num(c?.["cancelled"]) ?? 0 };
}

function applyEvent(b: Batch, kind: string, data: unknown): Batch {
  switch (kind) {
    case "item": {
      const item = parseItem(data);
      if (!item) return b;
      const rest = b.items.filter((i) => i.id !== item.id);
      return { ...b, items: sorted([...rest, item]) };
    }
    case "removed": {
      const ids = asRecord(data)?.["ids"];
      if (!Array.isArray(ids)) return b;
      return { ...b, items: b.items.filter((i) => !ids.includes(i.id)) };
    }
    case "order": {
      const ids = asRecord(data)?.["ids"];
      if (!Array.isArray(ids)) return b;
      return { ...b, items: sorted(b.items.map((i) => ({ ...i, position: positionIn(ids, i) }))) };
    }
    case "queue": {
      const o = asRecord(data);
      return { ...b, paused: o?.["paused"] === true, settings: parseSettings(o?.["settings"]) };
    }
    case "done":
      return { ...b, finished: { n: (b.finished?.n ?? 0) + 1, counts: counts(data) } };
    case "countdown":
      return { ...b, countdown: parseCountdown(data) };
    case "countdown_cancelled":
    case "power":
      return { ...b, countdown: null };
    default:
      return b;
  }
}

/** The place of `item` in the order the backend sent. An item the list lacks goes after it. */
function positionIn(ids: readonly unknown[], item: BatchItem): number {
  const at = ids.indexOf(item.id);
  return at >= 0 ? at : ids.length + item.position;
}

export function reduceBatch(b: Batch, e: BatchEvent): Batch {
  switch (e.type) {
    case "snapshot":
      return {
        ...b,
        items: e.snapshot.items,
        paused: e.snapshot.paused,
        settings: e.snapshot.settings,
        countdown: e.snapshot.counting ? b.countdown : null,
        loaded: true,
      };
    case "event":
      return e.replay === true && e.kind === "done" ? b : applyEvent(b, e.kind, e.data);
    case "link":
      return e.link === b.link ? b : { ...b, link: e.link };
  }
}

/** Moves the item shown at `from` to `to` and returns the new id order. */
export function moveId(ids: readonly string[], from: number, to: number): string[] {
  const out = [...ids];
  const [moved] = out.splice(from, 1);
  if (moved === undefined) return out;
  out.splice(Math.max(0, Math.min(out.length, to)), 0, moved);
  return out;
}

/** The slot a dragged row would drop into, given the vertical middle of every row and the pointer's y. */
export function slotAt(middles: readonly number[], y: number): number {
  return middles.filter((m) => m < y).length;
}

export interface Overall {
  readonly total: number;
  readonly finished: number;
  /** 0 to 1, weighted by the length of each video. */
  readonly fraction: number;
  readonly etaS: number | null;
  readonly active: boolean;
}

/**
 * Progress over the items the person still wants (a cancelled one is not counted). A failed item
 * counts as finished, since it will not take more time. Items are weighted by audio length, and an
 * item of unknown length takes the mean of the known ones.
 */
export function overall(items: readonly BatchItem[]): Overall {
  const wanted = items.filter((i) => i.state !== "cancelled");
  const known = wanted.flatMap((i) => (i.audioS !== null && i.audioS > 0 ? [i.audioS] : []));
  const mean = known.length > 0 ? known.reduce((a, b) => a + b, 0) / known.length : 1;
  let weight = 0;
  let done = 0;
  for (const i of wanted) {
    const w = i.audioS !== null && i.audioS > 0 ? i.audioS : mean;
    weight += w;
    done += w * (i.state === "done" || i.state === "failed" ? 1 : i.state === "running" ? i.progress : 0);
  }
  const etas = wanted.flatMap((i) => (i.state === "queued" || i.state === "running") && i.etaS !== null ? [i.etaS] : []);
  return {
    total: wanted.length,
    finished: wanted.filter((i) => i.state === "done" || i.state === "failed").length,
    fraction: weight > 0 ? done / weight : 0,
    etaS: etas.length > 0 ? Math.max(...etas) : null,
    active: wanted.some((i) => i.state === "running" || i.state === "queued"),
  };
}

/** "約 12 分鐘", "約 2 小時 5 分", or "不到 1 分鐘". */
export function formatEta(seconds: number, t: Translate = tZhTW): string {
  if (seconds < 45) return t("eta.under");
  const minutes = Math.round(seconds / 60);
  if (minutes < 60) return t("eta.minutes", { n: minutes });
  const h = Math.floor(minutes / 60);
  const m = minutes % 60;
  return m === 0 ? t("eta.hours", { n: h }) : t("eta.hoursMinutes", { h, m });
}

/** Whole seconds left until `deadlineMs`, never below 0. */
export const secondsLeft = (deadlineMs: number, nowMs: number): number => Math.max(0, Math.ceil((deadlineMs - nowMs) / 1000));

export const isFinished = (s: ItemState): boolean => s === "done" || s === "failed" || s === "cancelled";

/** What a row offers for each state, matching the backend's rules (409 otherwise). */
export function actionsFor(s: ItemState): readonly ("pause" | "resume" | "cancel" | "retry" | "remove")[] {
  switch (s) {
    case "queued":
    case "running":
      return ["pause", "cancel"];
    case "paused":
      return ["resume", "cancel"];
    case "failed":
    case "cancelled":
      return ["retry", "remove"];
    case "done":
      return ["remove"];
  }
}
