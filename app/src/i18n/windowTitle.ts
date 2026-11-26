import { getCurrentWindow } from "@tauri-apps/api/window";

/**
 * Sets the title of the native window, which `document.title` does not reach. A page outside the shell
 * (a browser tab, a test) has no native window, so a failure is not an error.
 */
export async function setWindowTitle(title: string): Promise<void> {
  try {
    await getCurrentWindow().setTitle(title);
  } catch {
    return;
  }
}
