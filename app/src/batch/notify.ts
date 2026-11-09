import { isPermissionGranted, requestPermission, sendNotification } from "@tauri-apps/plugin-notification";

/** A Windows notification. A refusal or a missing permission is not an error, the in-app toast still shows. */
export async function notifyWindows(title: string, body: string): Promise<void> {
  try {
    const ok = (await isPermissionGranted()) || (await requestPermission()) === "granted";
    if (ok) sendNotification({ title, body });
  } catch {
    // the toast in the window is the fallback
  }
}
