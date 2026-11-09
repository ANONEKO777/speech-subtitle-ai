import type { MissingAsset, ProfileId, ProfileView } from "../manage/types";

export interface PlanItem extends MissingAsset {
  /** A CPU program fetched too, so a failed GPU can fall back without another download. */
  readonly fallback: boolean;
}

/** What the wizard downloads for a profile: its missing assets, plus the CPU runtimes for a GPU profile. */
export function downloadPlan(view: ProfileView, selected: ProfileId): { items: readonly PlanItem[]; totalBytes: number } {
  const chosen = view.profiles.find((p) => p.id === selected);
  const cpu = view.profiles.find((p) => p.id === "cpu");
  const own: PlanItem[] = (chosen?.missing ?? []).map((m) => ({ ...m, fallback: false }));
  const twins: PlanItem[] =
    selected === "cpu" || !cpu
      ? []
      : cpu.missing.filter((m) => m.type === "runtime" && !own.some((o) => o.id === m.id)).map((m) => ({ ...m, fallback: true }));
  const items = [...own, ...twins];
  return { items, totalBytes: items.reduce((n, i) => n + i.sizeBytes, 0) };
}
