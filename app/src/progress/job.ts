import { asRecord } from "../api/client";
import { type Translate, tZhTW } from "../i18n";

export const STEPS = ["audio", "vad", "asr", "segment", "translate", "export", "summarize"] as const;
export type Step = (typeof STEPS)[number];

/** The name of a step for a run that translates into `target`: 翻譯成繁體中文, 翻譯成English. */
export const stepLabel = (step: Step, target: string, t: Translate = tZhTW): string => {
  switch (step) {
    case "translate":
      return t("progress.translateTo", { target });
    case "audio":
      return t("progress.step.audio");
    case "vad":
      return t("progress.step.vad");
    case "asr":
      return t("progress.step.asr");
    case "segment":
      return t("progress.step.segment");
    case "export":
      return t("progress.step.export");
    case "summarize":
      return t("progress.step.summarize");
  }
};

/** The steps a run that only adds a language redoes. The speech steps are kept from the first run. */
export const ADD_TARGET_STEPS: readonly Step[] = ["translate", "export", "summarize"];

export type JobView =
  | { readonly kind: "waiting" }
  | { readonly kind: "running"; readonly step: Step | null; readonly stepFraction: number; readonly overall: number }
  | { readonly kind: "done"; readonly edits: EditsReport }
  /** `disconnected` is set when the event stream dropped: the window says so in its own language. */
  | { readonly kind: "failed"; readonly error: string; readonly disconnected?: true }
  | { readonly kind: "cancelled" };

/** What the run did with the cues a person had corrected: put back over the new translation, or no longer fitting it. */
export interface EditsReport {
  readonly kept: number;
  readonly unmatched: number;
}

export const WAITING: JobView = { kind: "waiting" };

const isStep = (value: unknown): value is Step => STEPS.some((s) => s === value);

/** Folds one SSE event, or the local `disconnected` event, into the job view. Unknown events leave it unchanged. */
export function reduceJob(view: JobView, event: string, data: unknown): JobView {
  const o = asRecord(data);
  switch (event) {
    case "progress": {
      const step = isStep(o?.["step"]) ? o["step"] : null;
      const fraction = typeof o?.["fraction"] === "number" ? o["fraction"] : 0;
      const overall = typeof o?.["overall"] === "number" ? o["overall"] : 0;
      return { kind: "running", step, stepFraction: fraction, overall };
    }
    case "done": {
      const report = asRecord(o?.["report"]);
      const count = (key: string) => (typeof report?.[key] === "number" ? report[key] : 0);
      return { kind: "done", edits: { kept: count("edits_kept"), unmatched: count("edits_unmatched") } };
    }
    case "failed":
      return { kind: "failed", error: typeof o?.["error"] === "string" ? o["error"] : "unknown error" };
    case "cancelled":
      return { kind: "cancelled" };
    case "disconnected":
      if (view.kind === "done" || view.kind === "failed" || view.kind === "cancelled") return view;
      return { kind: "failed", error: "connection lost", disconnected: true };
    default:
      return view;
  }
}
