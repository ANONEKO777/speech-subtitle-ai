import { sep } from "@tauri-apps/api/path";

/**
 * True in the Mac build. The shell tells the window its path separator (`/` on a Mac, `\` on Windows),
 * so no backend call or user-agent guess is needed. Outside the shell (a browser tab, a test) there is
 * no separator and the window speaks as it did on Windows.
 */
export function isMacShell(): boolean {
  try {
    return sep() === "/";
  } catch {
    return false;
  }
}
