import type { Translate } from "../i18n";
import type { Refusal } from "../manage/api";
import { isActive } from "../manage/downloads";
import type { Asset, DownloadJob, UpdateItem } from "../manage/types";
import type { Said } from "../i18n/said";

export type RowAction = "download" | "resume" | "verify" | "repair" | "redownload" | "update" | "delete" | "cancel";

/** The actions a row offers, from what is on disk and what is downloading. A program this machine builds
 * for itself has nothing to download, verify or fetch again (the backend refuses all three), so it offers
 * only delete once it is there, and not even that when it was found outside the runtimes folder (PATH,
 * Homebrew): the app does not own that file and the backend refuses to delete it. */
export function rowActions(asset: Asset, job: DownloadJob | undefined, update?: UpdateItem): RowAction[] {
  if (job && isActive(job)) return ["cancel"];
  if (asset.localBuild) return asset.state === "installed" && !asset.foundOutsideRuntimes ? ["delete"] : [];
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

export const forceReasonError = (reason: string, t: Translate): string | null =>
  reason.trim().length >= MIN_REASON ? null : t("delete.reasonShort", { min: MIN_REASON });

export type DeleteStep =
  | { readonly step: "confirm" }
  | { readonly step: "refused"; readonly refusal: Refusal }
  | { readonly step: "force"; readonly refusal: Refusal; readonly reason: string }
  | { readonly step: "failed"; readonly message: Said };

export type DeleteEvent =
  | { readonly type: "refused"; readonly refusal: Refusal }
  | { readonly type: "wantForce" }
  | { readonly type: "reason"; readonly text: string }
  | { readonly type: "failed"; readonly message: Said };

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

export function stateText(asset: Asset, t: Translate): string {
  switch (asset.state) {
    case "installed":
      return t("models.state.installed");
    case "partial":
      return t("models.state.partial");
    case "installing":
      return t("models.state.installing");
    case "not_installed":
      return t("models.state.notInstalled");
  }
}

export function shaText(asset: Asset, t: Translate): string {
  switch (asset.shaState) {
    case "verified":
      return asset.shaScope === "archive_at_install" ? t("models.sha.atInstall") : t("models.sha.matches");
    case "unchecked":
      return t("models.sha.unchecked");
    case "corrupt":
      return t("models.sha.mismatch");
    case "not_installed":
      return "—";
  }
}
