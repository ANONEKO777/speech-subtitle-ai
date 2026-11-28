/** The window's localStorage, which a blocked or broken store cannot crash: a read gives null and a write is dropped. */
export function readStored(key: string): string | null {
  try {
    return localStorage.getItem(key);
  } catch {
    return null;
  }
}

export function writeStored(key: string, value: string): void {
  try {
    localStorage.setItem(key, value);
  } catch {
    // the window keeps working without storage; the value is only lost at the next start
  }
}
