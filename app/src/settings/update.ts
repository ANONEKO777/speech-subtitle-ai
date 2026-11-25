import { invoke } from "@tauri-apps/api/core";
import { asRecord } from "../api/client";
import { type Translate, tZhTW } from "../i18n";

export type Checked =
  | { readonly state: "upToDate"; readonly current: string }
  | { readonly state: "available"; readonly current: string; readonly version: string; readonly notes: string | null };

export function parseChecked(raw: unknown, t: Translate = tZhTW): Checked {
  const o = asRecord(raw);
  const current = typeof o?.["current"] === "string" ? o["current"] : "";
  if (o?.["state"] === "upToDate") return { state: "upToDate", current };
  if (o?.["state"] === "available" && typeof o["version"] === "string") {
    return { state: "available", current, version: o["version"], notes: typeof o["notes"] === "string" ? o["notes"] : null };
  }
  throw new Error(t("errors.updateUnreadable"));
}

/** The shell still turns every failure into a plain zh-TW sentence (W4 moves it to codes), so a rejection is shown as it is. */
export const reasonOf = (e: unknown, t: Translate = tZhTW): string =>
  typeof e === "string" ? e : e instanceof Error ? e.message : t("errors.updateIncomplete");

export const updateCheck = async (t: Translate = tZhTW): Promise<Checked> => parseChecked(await invoke("update_check"), t);
export const updateDownload = (): Promise<void> => invoke("update_download");
export const updateInstall = (): Promise<void> => invoke("update_install");
