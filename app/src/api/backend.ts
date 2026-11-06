import { invoke } from "@tauri-apps/api/core";
import { type UnlistenFn, listen } from "@tauri-apps/api/event";
import type { Backend } from "./client";

export type BackendStatus =
  | { readonly kind: "starting" }
  | { readonly kind: "ready"; readonly backend: Backend }
  | { readonly kind: "failed"; readonly message: string };

/** Reports the sidecar state until it is ready or has failed. */
export async function watchBackend(onStatus: (status: BackendStatus) => void): Promise<UnlistenFn> {
  const stops = [
    await listen<Backend>("backend-ready", (e) => onStatus({ kind: "ready", backend: e.payload })),
    await listen<string>("backend-failed", (e) => onStatus({ kind: "failed", message: e.payload })),
  ];
  const known = await invoke<Backend | null>("backend_info");
  if (known) onStatus({ kind: "ready", backend: known });
  return () => stops.forEach((stop) => stop());
}

export function allowVideo(path: string): Promise<void> {
  return invoke("allow_video", { path });
}

/** Opens the native file dialog, which the app itself runs, and returns the picked path or null. */
export function pickVideo(): Promise<string | null> {
  return invoke("pick_video");
}

/**
 * Opens the native save dialog, which the app itself runs, and writes `content` to the chosen
 * file. Returns the path written, or null when the person cancelled.
 */
export function saveExport(name: string, content: string): Promise<string | null> {
  return invoke("save_export", { name, content });
}
