/**
 * Whether a folder path the backend reported is a Windows path (a drive letter or a UNC share).
 * The backend writes paths of the machine it runs on, so this tells the window which example to show.
 */
export const isWindowsPath = (path: string): boolean => /^[A-Za-z]:[\\/]/.test(path) || path.startsWith("\\\\");
