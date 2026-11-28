import { useCallback, useEffect, useReducer, useRef, useState } from "react";
import { useT } from "../i18n/I18nProvider";
import type { Said } from "../i18n/said";
import { type Checked, reasonOf, updateBuildInfo, updateCheck, updateDownload, updateInstall } from "./update";
import { type Available, type ThisBuild, type UpdatePrefs, UPDATES_KEY, offered, parsePrefs, planStart } from "./updatePrefs";
import { readStored, writeStored } from "../storage";
import { type BackendWork, type Work, holdingWork } from "./work";

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
  /** The work that holds the install now, from the window and the backend. */
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
/** How often the backend is asked about its work while there is a version to install. */
export const WORK_POLL_MS = 2000;

export type AskBackend = () => Promise<readonly BackendWork[]>;

/** Whether a view shows a button that could start the installer, so the backend's work matters. */
const installable = (phase: Phase): boolean =>
  phase.kind === "available" || phase.kind === "downloading" || phase.kind === "downloaded" || (phase.kind === "failed" && phase.update !== null);

/**
 * `startDelayMs` null means no check at start, as on a page that only shows the settings. A failure
 * of the check at start is kept for the settings page and never shown anywhere else. `windowWork`
 * is the work the window follows itself; `ask` reads the rest from the backend, or is null when
 * there is no backend to ask.
 */
export function useUpdates(windowWork: Work, startDelayMs: number | null = null, ask: AskBackend | null = null): Updates {
  const { t } = useT();
  const [state, dispatch] = useReducer(reduceUpdates, undefined, (): UpdateState => ({ phase: { kind: "idle" }, banner: false, prefs: parsePrefs(readStored(UPDATES_KEY)) }));
  const [build, setBuild] = useState<ThisBuild | null>(null);
  const [asked, setAsked] = useState<readonly BackendWork[]>([]);
  const work = holdingWork(windowWork, asked);
  const latest = useRef({ state, windowWork, work, asked, ask, t });
  latest.current = { state, windowWork, work, asked, ask, t };

  /** What the backend is doing now. A backend that does not answer is taken to be doing what it last said. */
  const askNow = useCallback(async (): Promise<readonly BackendWork[]> => {
    const { ask, asked } = latest.current;
    if (!ask) return [];
    const now = await ask().catch(() => asked);
    setAsked((a) => (a.length === now.length && a.every((w, i) => w === now[i]) ? a : now));
    return now;
  }, []);

  const watching = ask !== null && installable(state.phase);
  useEffect(() => {
    if (!watching) {
      setAsked((a) => (a.length > 0 ? [] : a));
      return;
    }
    void askNow();
    const timer = window.setInterval(() => void askNow(), WORK_POLL_MS);
    return () => window.clearInterval(timer);
  }, [watching, askNow]);

  useEffect(() => writeStored(UPDATES_KEY, JSON.stringify(state.prefs)), [state.prefs]);

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
    const update = phase.kind === "available" || phase.kind === "failed" ? phase.update : null;
    if (!update) return null;
    dispatch({ type: "downloading", update });
    try {
      if (phase.kind !== "available" || !phase.staged) {
        const result = await updateCheck(t);
        if (result.state !== "available" || result.version !== update.version) {
          // Only the version the person saw installs. A newer one is shown with its notes, and waits for a click.
          dispatch({ type: "checked", auto: false, result });
          return null;
        }
      }
      await updateDownload();
      dispatch({ type: "downloaded", update });
      return update;
    } catch (e) {
      dispatch({ type: "failed", reason: reasonOf(e), update });
      return null;
    }
  }, [t]);

  /** The one place that starts the installer, so no view can start it while work runs. It asks the backend once more first. */
  const installNow = useCallback(async (update: Available) => {
    if (latest.current.work !== null) return;
    if (latest.current.ask && holdingWork(latest.current.windowWork, await askNow()) !== null) return;
    dispatch({ type: "installing", update });
    try {
      await updateInstall();
    } catch (e) {
      dispatch({ type: "failed", reason: reasonOf(e), update });
    }
  }, [askNow]);

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
