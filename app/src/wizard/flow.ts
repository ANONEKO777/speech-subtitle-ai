import type { DownloadJob, ProfileId, ProfileView, SelfTest } from "../manage/types";
import type { Said } from "../i18n/said";

/** What went wrong, as the screen words it: backend or shell text with its notices, or a failed download the screen names. */
export type WizardError = Said | { readonly assetId: string; readonly message: string | null };

export type WizardState =
  | { readonly step: "detect" }
  | { readonly step: "detect-failed"; readonly error: Said }
  | { readonly step: "choose"; readonly view: ProfileView; readonly selected: ProfileId }
  | {
      readonly step: "download";
      readonly view: ProfileView;
      readonly selected: ProfileId;
      readonly phase: "starting" | "running" | "cancelled" | "failed";
      readonly jobIds: readonly string[];
      readonly jobs: readonly DownloadJob[];
      readonly error: WizardError | null;
    }
  | { readonly step: "selftest"; readonly view: ProfileView; readonly selected: ProfileId }
  | {
      readonly step: "result";
      readonly view: ProfileView;
      readonly selected: ProfileId;
      readonly test: SelfTest | null;
      readonly error: Said | null;
    }
  | { readonly step: "finished" }
  | { readonly step: "skipped" };

export type WizardEvent =
  | { readonly type: "loaded"; readonly view: ProfileView }
  | { readonly type: "loadFailed"; readonly error: Said }
  | { readonly type: "select"; readonly profile: ProfileId }
  | { readonly type: "start" }
  | { readonly type: "started"; readonly jobIds: readonly string[] }
  | { readonly type: "startFailed"; readonly error: Said }
  | { readonly type: "polled"; readonly jobs: readonly DownloadJob[] }
  | { readonly type: "cancelDownload" }
  | { readonly type: "retry" }
  | { readonly type: "back" }
  | { readonly type: "selfTested"; readonly test: SelfTest }
  | { readonly type: "selfTestFailed"; readonly error: Said | null }
  | { readonly type: "rerunSelfTest" }
  | { readonly type: "finish" }
  | { readonly type: "skip" };

export const initialWizard: WizardState = { step: "detect" };

/** Whether the self-test result lets the person go on: some device runs the profile. */
export const passed = (test: SelfTest | null): boolean => test?.ok === true;

type Downloading = Extract<WizardState, { step: "download" }>;

function afterPoll(state: Downloading, polled: readonly DownloadJob[]): WizardState {
  const mine = polled.filter((j) => state.jobIds.includes(j.id));
  const failed = mine.find((j) => j.state === "failed");
  if (failed) {
    return { ...state, jobs: mine, phase: "failed", error: { assetId: failed.assetId, message: failed.failure?.message ?? null } };
  }
  if (mine.some((j) => j.state === "cancelled")) return { ...state, jobs: mine, phase: "cancelled", error: null };
  if (mine.length === state.jobIds.length && mine.every((j) => j.state === "done")) {
    return { step: "selftest", view: state.view, selected: state.selected };
  }
  return { ...state, jobs: mine };
}

function whileDownloading(state: Downloading, event: WizardEvent): WizardState {
  const stopped = state.phase === "cancelled" || state.phase === "failed";
  switch (event.type) {
    case "started":
      if (state.phase !== "starting") return state;
      return event.jobIds.length === 0
        ? { step: "selftest", view: state.view, selected: state.selected }
        : { ...state, phase: "running", jobIds: event.jobIds, jobs: [] };
    case "startFailed":
      return { ...state, phase: "failed", error: event.error };
    case "polled":
      return state.phase === "running" ? afterPoll(state, event.jobs) : state;
    case "cancelDownload":
      return state.phase === "running" ? { ...state, phase: "cancelled", error: null } : state;
    case "retry":
      return stopped ? { ...state, phase: "starting", jobIds: [], jobs: [], error: null } : state;
    case "back":
      return stopped ? { step: "choose", view: state.view, selected: state.selected } : state;
    default:
      return state;
  }
}

export function reduceWizard(state: WizardState, event: WizardEvent): WizardState {
  if (event.type === "skip") return state.step === "finished" ? state : { step: "skipped" };
  switch (state.step) {
    case "detect":
    case "detect-failed":
      if (event.type === "loaded") return { step: "choose", view: event.view, selected: event.view.recommended.id };
      if (event.type === "loadFailed") return { step: "detect-failed", error: event.error };
      return state;
    case "choose":
      if (event.type === "select") return { ...state, selected: event.profile };
      if (event.type === "loaded") return { ...state, view: event.view };
      if (event.type === "start") {
        return { step: "download", view: state.view, selected: state.selected, phase: "starting", jobIds: [], jobs: [], error: null };
      }
      return state;
    case "download":
      return whileDownloading(state, event);
    case "selftest":
      if (event.type === "selfTested") return { step: "result", view: state.view, selected: state.selected, test: event.test, error: null };
      if (event.type === "selfTestFailed") return { step: "result", view: state.view, selected: state.selected, test: null, error: event.error };
      return state;
    case "result":
      if (event.type === "rerunSelfTest") return { step: "selftest", view: state.view, selected: state.selected };
      if (event.type === "back") return { step: "choose", view: state.view, selected: state.selected };
      if (event.type === "finish") return passed(state.test) ? { step: "finished" } : state;
      return state;
    case "finished":
    case "skipped":
      return state;
  }
}
