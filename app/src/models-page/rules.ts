import type { Refusal } from "../manage/api";
import { isActive } from "../manage/downloads";
import type { Asset, DownloadJob, UpdateItem } from "../manage/types";

export type RowAction = "download" | "resume" | "verify" | "repair" | "redownload" | "update" | "delete" | "cancel";

/** The actions a row offers, from what is on disk and what is downloading. */
export function rowActions(asset: Asset, job: DownloadJob | undefined, update?: UpdateItem): RowAction[] {
  if (job && isActive(job)) return ["cancel"];
  switch (asset.state) {
    case "installing":
      return ["cancel"];
    case "not_installed":
      return ["download"];
    case "partial":
      return ["resume", "delete"];
    case "installed": {
      const out: RowAction[] = asset.type === "model" ? ["verify", "repair", "redownload"] : ["repair", "redownload"];
      if (update?.status === "update_available" && update.installable) out.unshift("update");
      return [...out, "delete"];
    }
  }
}

export const MIN_REASON = 8;

export const forceReasonError = (reason: string): string | null =>
  reason.trim().length >= MIN_REASON ? null : `請輸入至少 ${MIN_REASON} 個字的原因，會記錄在日誌`;

export type DeleteStep =
  | { readonly step: "confirm" }
  | { readonly step: "refused"; readonly refusal: Refusal }
  | { readonly step: "force"; readonly refusal: Refusal; readonly reason: string }
  | { readonly step: "failed"; readonly message: string };

export type DeleteEvent =
  | { readonly type: "refused"; readonly refusal: Refusal }
  | { readonly type: "wantForce" }
  | { readonly type: "reason"; readonly text: string }
  | { readonly type: "failed"; readonly message: string };

/** A delete is plain at first. A refusal shows its blockers, and force (with a typed reason) only when the backend allows it. */
export function reduceDelete(state: DeleteStep, event: DeleteEvent): DeleteStep {
  switch (event.type) {
    case "refused":
      return event.refusal.canForce || event.refusal.blockers.length > 0
        ? { step: "refused", refusal: event.refusal }
        : { step: "failed", message: event.refusal.message };
    case "wantForce":
      return state.step === "refused" && state.refusal.canForce ? { step: "force", refusal: state.refusal, reason: "" } : state;
    case "reason":
      return state.step === "force" ? { ...state, reason: event.text } : state;
    case "failed":
      return { step: "failed", message: event.message };
  }
}

export function stateText(asset: Asset): string {
  switch (asset.state) {
    case "installed":
      return "已安裝";
    case "partial":
      return "下載到一半";
    case "installing":
      return "下載中";
    case "not_installed":
      return "未安裝";
  }
}

export function shaText(asset: Asset): string {
  switch (asset.shaState) {
    case "verified":
      return asset.shaScope === "archive_at_install" ? "安裝時已驗證" : "SHA256 相符";
    case "unchecked":
      return "尚未驗證";
    case "corrupt":
      return "SHA256 不符";
    case "not_installed":
      return "—";
  }
}
