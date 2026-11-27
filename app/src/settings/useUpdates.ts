import { useCallback, useEffect, useReducer, useRef, useState } from "react";
import type { Batch } from "../batch/model";
import { useT } from "../i18n/I18nProvider";
import type { Said } from "../i18n/said";
import { type Checked, reasonOf, updateBuildInfo, updateCheck, updateDownload, updateInstall } from "./update";
import { type Available, type ThisBuild, type UpdatePrefs, UPDATES_KEY, offered, parsePrefs, planStart } from "./updatePrefs";

/** Work that installing would cut off, because the installer stops the backend first. */
export type Work = "job" | "batch" | null;

export function workInProgress(importing: boolean, batch: Batch): Work {
  if (importing) return "job";
  const running = batch.items.some((i) => i.state === "running");
  const waiting = !batch.paused && batch.items.some((i) => i.state === "queued");
  return running || waiting ? "batch" : null;
}

/** The one update process of the window. The banner and the settings section are two views of it. */
export type Phase =
  | { readonly kind: "idle" }
  | { readonly kind: "checking" }
  | { readonly kind: "upToDate"; readonly current: string }
  /** `staged` is false for a version remembered from an earlier start, which the shell must check again before it downloads. */
  | { readonly kind: "available"; readonly update: Available; readonly staged: boolean }
  | { readonly kind: "downloading"; readonly update: Available }
  | { readonly kind: "downloaded"; readonly update: Available }
  | { readonly kind: "installing"; readonly update: Available }
  | { readonly kind: "failed"; readonly reason: Said | null; readonly update: Available | null };

export interface UpdateState {
  readonly phase: Phase;
  /** Whether the banner is open. Later and Skip close it until the next start. */
  readonly banner: boolean;
  readonly prefs: UpdatePrefs;
}

export type UpdateEvent =
  | { readonly type: "checking"; readonly auto: boolean; readonly now: number }
  | { readonly type: "checked"; readonly auto: boolean; readonly result: Checked }
  | { readonly type: "checkFailed"; readonly auto: boolean; readonly reason: Said | null; readonly now: number }
  | { readonly type: "offer"; readonly update: Available }
  | { readonly type: "downloading"; readonly update: Available }
  | { readonly type: "downloaded"; readonly update: Available }
  | { readonly type: "installing"; readonly update: Available }
  | { readonly type: "failed"; readonly reason: Said | null; readonly update: Available | null }
  | { readonly type: "later" }
  | { readonly type: "skip" }
  | { readonly type: "checkAtStart"; readonly on: boolean };

/** The version the banner speaks about, or null when it has nothing to show. */
export function bannerUpdate({ phase, banner }: UpdateState): Available | null {
  if (!banner) return null;
  return phase.kind === "available" || phase.kind === "downloading" || phase.kind === "downloaded" || phase.kind === "installing" || phase.kind === "failed"
    ? phase.update
    : null;
}

export function reduceUpdates(state: UpdateState, event: UpdateEvent): UpdateState {
  const { prefs } = state;
  switch (event.type) {
    case "checking":
      return { ...state, phase: { kind: "checking" }, prefs: event.auto ? { ...prefs, lastCheckAt: event.now } : prefs };
    case "checked": {
      const { result, auto } = event;
      const found = result.state === "available" ? result : null;
      const known = auto ? { ...prefs, lastFailure: null, found } : { ...prefs, found };
      if (result.state === "upToDate") return { ...state, phase: auto ? { kind: "idle" } : { kind: "upToDate", current: result.current }, prefs: known };
      return { phase: { kind: "available", update: result, staged: true }, banner: state.banner || (auto && offered(prefs, result)), prefs: known };
    }
    case "checkFailed":
      return event.auto
        ? { ...state, phase: { kind: "idle" }, prefs: { ...prefs, lastFailure: { at: event.now, reason: event.reason } } }
        : { ...state, phase: { kind: "failed", reason: event.reason, update: null } };
    case "offer":
      return state.phase.kind === "idle" ? { ...state, phase: { kind: "available", update: event.update, staged: false }, banner: true } : state;
    case "downloading":
      return { ...state, phase: { kind: "downloading", update: event.update } };
    case "downloaded":
      return { ...state, phase: { kind: "downloaded", update: event.update } };
    case "installing":
      return { ...state, phase: { kind: "installing", update: event.update } };
    case "failed":
      return { ...state, phase: { kind: "failed", reason: event.reason, update: event.update } };
    case "later":
      return { ...state, banner: false };
    case "skip": {
      const shown = bannerUpdate(state);
      return { ...state, banner: false, prefs: shown ? { ...prefs, skipped: shown.version } : prefs };
    }
    case "checkAtStart":
      return { ...state, prefs: { ...prefs, checkAtStart: event.on } };
  }
}

export interface Updates {
  readonly state: UpdateState;
  /** Null until the shell has answered. */
  readonly build: ThisBuild | null;
  readonly work: Work;
  readonly check: () => Promise<void>;
  readonly download: () => Promise<Available | null>;
  readonly install: () => Promise<void>;
  /** The banner's one click: download, then install unless work started meanwhile. */
  readonly downloadAndInstall: () => Promise<void>;
  readonly later: () => void;
  readonly skip: () => void;
  readonly setCheckAtStart: (on: boolean) => void;
}

/** How long after start the check waits, so it never competes with opening the window. */
export const START_DELAY_MS = 5000;

const loadPrefs = (): UpdatePrefs => {
  try {
    return parsePrefs(localStorage.getItem(UPDATES_KEY));
  } catch {
    return parsePrefs(null);
  }
};

/**
 * `startDelayMs` null means no check at start, as on a page that only shows the settings. A failure
 * of the check at start is kept for the settings page and never shown anywhere else.
 */
export function useUpdates(work: Work, startDelayMs: number | null = null): Updates {
  const { t } = useT();
  const [state, dispatch] = useReducer(reduceUpdates, undefined, (): UpdateState => ({ phase: { kind: "idle" }, banner: false, prefs: loadPrefs() }));
  const [build, setBuild] = useState<ThisBuild | null>(null);
  const latest = useRef({ state, work, t });
  latest.current = { state, work, t };

  useEffect(() => {
    try {
      localStorage.setItem(UPDATES_KEY, JSON.stringify(state.prefs));
    } catch {
      // a store that cannot be written keeps the defaults for the next start
    }
  }, [state.prefs]);

  useEffect(() => {
    let alive = true;
    void updateBuildInfo().then((b) => alive && setBuild(b));
    return () => {
      alive = false;
    };
  }, []);

  useEffect(() => {
    if (!build || startDelayMs === null) return;
    const plan = planStart(latest.current.state.prefs, build, Date.now());
    if (plan.kind === "offer") dispatch({ type: "offer", update: plan.update });
    if (plan.kind !== "check") return;
    const timer = window.setTimeout(() => {
      if (latest.current.state.phase.kind !== "idle") return;
      dispatch({ type: "checking", auto: true, now: Date.now() });
      updateCheck(latest.current.t).then(
        (result) => dispatch({ type: "checked", auto: true, result }),
        (e: unknown) => dispatch({ type: "checkFailed", auto: true, reason: reasonOf(e), now: Date.now() }),
      );
    }, startDelayMs);
    return () => window.clearTimeout(timer);
  }, [build, startDelayMs]);

  const check = useCallback(async () => {
    dispatch({ type: "checking", auto: false, now: Date.now() });
    try {
      dispatch({ type: "checked", auto: false, result: await updateCheck(t) });
    } catch (e) {
      dispatch({ type: "checkFailed", auto: false, reason: reasonOf(e), now: Date.now() });
    }
  }, [t]);

  const download = useCallback(async (): Promise<Available | null> => {
    const { phase } = latest.current.state;
    const from = phase.kind === "available" || phase.kind === "failed" ? phase.update : null;
    if (!from) return null;
    let update = from;
    dispatch({ type: "downloading", update });
    try {
      if (phase.kind !== "available" || !phase.staged) {
        const result = await updateCheck(t);
        if (result.state !== "available") {
          dispatch({ type: "checked", auto: false, result });
          return null;
        }
        update = result;
        dispatch({ type: "downloading", update });
      }
      await updateDownload();
      dispatch({ type: "downloaded", update });
      return update;
    } catch (e) {
      dispatch({ type: "failed", reason: reasonOf(e), update });
      return null;
    }
  }, [t]);

  /** The one place that starts the installer, so no view can start it while work runs. */
  const installNow = useCallback(async (update: Available) => {
    if (latest.current.work !== null) return;
    dispatch({ type: "installing", update });
    try {
      await updateInstall();
    } catch (e) {
      dispatch({ type: "failed", reason: reasonOf(e), update });
    }
  }, []);

  const install = useCallback(async () => {
    const { phase } = latest.current.state;
    if (phase.kind === "downloaded") await installNow(phase.update);
  }, [installNow]);

  const downloadAndInstall = useCallback(async () => {
    const update = await download();
    if (update) await installNow(update);
  }, [download, installNow]);

  return {
    state,
    build,
    work,
    check,
    download,
    install,
    downloadAndInstall,
    later: useCallback(() => dispatch({ type: "later" }), []),
    skip: useCallback(() => dispatch({ type: "skip" }), []),
    setCheckAtStart: useCallback((on: boolean) => dispatch({ type: "checkAtStart", on }), []),
  };
}
