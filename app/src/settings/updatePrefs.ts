import { type Said, parseNotices } from "../i18n/said";
import type { Checked } from "./update";

export type Available = Extract<Checked, { state: "available" }>;

/**
 * Kept in localStorage beside the window's other preferences, not in the backend's `settings.json`.
 * An earlier build refuses a `settings.json` with a key it does not know and falls back to the
 * defaults, so a key there would cost a person who goes back a version all their settings. An
 * earlier build never reads this key.
 */
export const UPDATES_KEY = "vst.updates.v1";
export const DAY_MS = 24 * 60 * 60 * 1000;

export interface UpdatePrefs {
  readonly checkAtStart: boolean;
  /** When the last check at start began, in ms since the epoch. */
  readonly lastCheckAt: number | null;
  /** Why the last check at start failed, for the settings page. The next check that answers clears it. */
  readonly lastFailure: { readonly at: number; readonly reason: Said | null } | null;
  /** The one version the person chose to skip. */
  readonly skipped: string | null;
  /** The newer version the last check at start found, offered again at each start until a check says otherwise. */
  readonly found: Available | null;
}

export const DEFAULT_PREFS: UpdatePrefs = { checkAtStart: true, lastCheckAt: null, lastFailure: null, skipped: null, found: null };

/** What the shell says about the build it runs. */
export interface ThisBuild {
  readonly supported: boolean;
  readonly current: string;
}

const record = (v: unknown): Record<string, unknown> | null =>
  typeof v === "object" && v !== null && !Array.isArray(v) ? (v as Record<string, unknown>) : null;
const time = (v: unknown): number | null => (typeof v === "number" && Number.isFinite(v) && v >= 0 ? v : null);
const text = (v: unknown): string | null => (typeof v === "string" && v !== "" ? v : null);

function parseFound(raw: unknown): Available | null {
  const o = record(raw);
  const version = text(o?.["version"]);
  const current = text(o?.["current"]);
  if (!o || !version || !current) return null;
  return { state: "available", version, current, notes: typeof o["notes"] === "string" ? o["notes"] : null };
}

function parseFailure(raw: unknown): UpdatePrefs["lastFailure"] {
  const o = record(raw);
  const at = time(o?.["at"]);
  if (!o || at === null) return null;
  const reason = record(o["reason"]);
  return { at, reason: typeof reason?.["text"] === "string" ? { text: reason["text"], notices: parseNotices(reason["notices"]) } : null };
}

/** Reads the stored preferences. Anything missing, damaged or written by a later build falls back to the default. */
export function parsePrefs(raw: string | null): UpdatePrefs {
  let o: Record<string, unknown> | null = null;
  try {
    o = record(JSON.parse(raw ?? "null"));
  } catch {
    // a damaged store falls back to the defaults
  }
  if (!o) return DEFAULT_PREFS;
  return {
    checkAtStart: typeof o["checkAtStart"] === "boolean" ? o["checkAtStart"] : DEFAULT_PREFS.checkAtStart,
    lastCheckAt: time(o["lastCheckAt"]),
    lastFailure: parseFailure(o["lastFailure"]),
    skipped: text(o["skipped"]),
    found: parseFound(o["found"]),
  };
}

/** At most one check a day. A clock set back past the last check counts as a new day. */
export const due = (lastCheckAt: number | null, now: number): boolean =>
  lastCheckAt === null || now - lastCheckAt >= DAY_MS || now < lastCheckAt;

export type StartPlan =
  | { readonly kind: "nothing" }
  | { readonly kind: "check" }
  /** No check is due, and the version found before is still newer than this build. */
  | { readonly kind: "offer"; readonly update: Available };

export function planStart(prefs: UpdatePrefs, build: ThisBuild, now: number): StartPlan {
  if (!build.supported || !prefs.checkAtStart) return { kind: "nothing" };
  if (due(prefs.lastCheckAt, now)) return { kind: "check" };
  const { found } = prefs;
  return found && found.current === build.current && found.version !== prefs.skipped ? { kind: "offer", update: found } : { kind: "nothing" };
}

export const offered = (prefs: UpdatePrefs, update: Available): boolean => update.version !== prefs.skipped;
