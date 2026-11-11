import { invoke } from "@tauri-apps/api/core";
import { asRecord } from "../api/client";

export type Checked =
  | { readonly state: "upToDate"; readonly current: string }
  | { readonly state: "available"; readonly current: string; readonly version: string; readonly notes: string | null };

export function parseChecked(raw: unknown): Checked {
  const o = asRecord(raw);
  const current = typeof o?.["current"] === "string" ? o["current"] : "";
  if (o?.["state"] === "upToDate") return { state: "upToDate", current };
  if (o?.["state"] === "available" && typeof o["version"] === "string") {
    return { state: "available", current, version: o["version"], notes: typeof o["notes"] === "string" ? o["notes"] : null };
  }
  throw new Error("更新檢查回傳了看不懂的結果。");
}

/** The shell turns every failure into a plain zh-TW sentence, so a rejection is shown as it is. */
export const reasonOf = (e: unknown): string => (typeof e === "string" ? e : e instanceof Error ? e.message : "更新沒有完成。");

export const updateCheck = async (): Promise<Checked> => parseChecked(await invoke("update_check"));
export const updateDownload = (): Promise<void> => invoke("update_download");
export const updateInstall = (): Promise<void> => invoke("update_install");
