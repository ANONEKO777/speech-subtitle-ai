import { invoke } from "@tauri-apps/api/core";
import { asRecord } from "../api/client";
import { type Translate, tZhTW } from "../i18n";
import { type Said, said } from "../i18n/said";

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

/** What the shell (`{ message, notices }`) or the invoke layer said, or null for a rejection that says nothing. */
export const reasonOf = (e: unknown): Said | null =>
  typeof e === "string" || e instanceof Error || typeof asRecord(e)?.["message"] === "string" ? said(e) : null;

/** Whether a download failed only because no data came for a while, so the same button can try again. */
export const stalledDownload = (reason: Said | null): boolean => reason?.notices.some((n) => n.code === "shell.update.stalled") ?? false;

/** Whether this build can update itself, and its version. Outside the shell, or from a shell without the command, nothing is supported. */
export const updateBuildInfo = async (): Promise<{ supported: boolean; current: string }> => {
  try {
    const o = asRecord(await invoke("update_build_info"));
    return { supported: o?.["supported"] === true, current: typeof o?.["current"] === "string" ? o["current"] : "" };
  } catch {
    return { supported: false, current: "" };
  }
};

export const updateCheck = async (t: Translate = tZhTW): Promise<Checked> => parseChecked(await invoke("update_check"), t);
export const updateDownload = (): Promise<void> => invoke("update_download");
export const updateInstall = (): Promise<void> => invoke("update_install");
