import { invoke } from "@tauri-apps/api/core";
import { type UnlistenFn, listen } from "@tauri-apps/api/event";
import { getCurrentWebview } from "@tauri-apps/api/webview";
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

/** Opens the native folder dialog and returns the folder picked or null. */
export function pickFolder(): Promise<string | null> {
  return invoke("pick_folder");
}

/** Shows a file in Explorer, or opens a folder. */
export function openFolder(path: string): Promise<void> {
  return invoke("open_folder", { path });
}

/** Calls `onDrop` with the paths of files dropped on the window, and `onOver` while a drag is over it. */
export async function watchDrops(onDrop: (paths: string[]) => void, onOver: (over: boolean) => void): Promise<UnlistenFn> {
  return getCurrentWebview().onDragDropEvent((e) => {
    const p = e.payload;
    if (p.type === "drop") {
      onOver(false);
      onDrop(p.paths);
    } else onOver(p.type !== "leave");
  });
}
