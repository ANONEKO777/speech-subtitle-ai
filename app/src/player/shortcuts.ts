import type { PlainKey } from "../i18n";

/** What a key press asks the player to do. */
export type Action =
  | { readonly kind: "toggle-play" }
  | { readonly kind: "seek"; readonly seconds: number }
  | { readonly kind: "seek-percent"; readonly percent: number }
  | { readonly kind: "volume"; readonly delta: number }
  | { readonly kind: "mute" }
  | { readonly kind: "fullscreen" }
  | { readonly kind: "screenshot"; readonly invertBurn: boolean }
  | { readonly kind: "speed"; readonly dir: 1 | -1 }
  | { readonly kind: "frame"; readonly dir: 1 | -1 }
  | { readonly kind: "line"; readonly dir: 1 | -1 }
  | { readonly kind: "loop" }
  | { readonly kind: "pip" }
  | { readonly kind: "offset"; readonly deltaMs: number }
  | { readonly kind: "video"; readonly dir: 1 | -1 }
  | { readonly kind: "help" };

export interface KeyLike {
  readonly key: string;
  readonly ctrlKey: boolean;
  readonly metaKey: boolean;
  readonly altKey: boolean;
  readonly shiftKey: boolean;
}

/** Arrow keys that a focused slider already uses to move itself. */
const ARROWS = new Set(["ArrowLeft", "ArrowRight", "ArrowUp", "ArrowDown"]);
export const isArrow = (key: string) => ARROWS.has(key);

/** The action for a key press, or null when the player does not use it. */
export function keyAction(e: KeyLike): Action | null {
  if (e.altKey || e.metaKey) return null;
  const key = e.key.length === 1 ? e.key.toLowerCase() : e.key;
  if (e.ctrlKey) {
    if (e.shiftKey) return null;
    if (key === "ArrowLeft") return { kind: "line", dir: -1 };
    if (key === "ArrowRight") return { kind: "line", dir: 1 };
    return null;
  }
  switch (key) {
    case " ":
    case "k":
      return { kind: "toggle-play" };
    case "ArrowLeft":
      return { kind: "seek", seconds: -5 };
    case "ArrowRight":
      return { kind: "seek", seconds: 5 };
    case "j":
      return { kind: "seek", seconds: -10 };
    case "l":
      return { kind: "seek", seconds: 10 };
    case "ArrowUp":
      return { kind: "volume", delta: 0.05 };
    case "ArrowDown":
      return { kind: "volume", delta: -0.05 };
    case "m":
      return { kind: "mute" };
    case "f":
      return { kind: "fullscreen" };
    case "s":
      return { kind: "screenshot", invertBurn: e.shiftKey };
    case "[":
      return { kind: "speed", dir: -1 };
    case "]":
      return { kind: "speed", dir: 1 };
    case ",":
      return { kind: "frame", dir: -1 };
    case ".":
      return { kind: "frame", dir: 1 };
    case "a":
      return { kind: "loop" };
    case "p":
      return { kind: "pip" };
    case "z":
      return { kind: "offset", deltaMs: -100 };
    case "x":
      return { kind: "offset", deltaMs: 100 };
    case "<":
      return { kind: "video", dir: -1 };
    case ">":
      return { kind: "video", dir: 1 };
    case "?":
      return { kind: "help" };
    default:
      return /^[0-9]$/.test(key) ? { kind: "seek-percent", percent: Number(key) * 10 } : null;
  }
}

export interface ShortcutRow {
  /** The key caps, which no language translates. */
  readonly keys: string;
  /** The catalog key of what the keys do. */
  readonly what: PlainKey;
}

/** What the help overlay lists. Every row is a key `keyAction` answers, which the test checks. */
export const SHORTCUTS: readonly ShortcutRow[] = [
  { keys: "Space / K", what: "player.key.play" },
  { keys: "← / →", what: "player.key.seek5" },
  { keys: "J / L", what: "player.key.seek10" },
  { keys: "0 – 9", what: "player.key.percent" },
  { keys: "↑ / ↓", what: "player.key.volume" },
  { keys: "M", what: "player.key.mute" },
  { keys: "[ / ]", what: "player.key.speed" },
  { keys: ", / .", what: "player.key.frame" },
  { keys: "Ctrl + ← / →", what: "player.key.line" },
  { keys: "A", what: "player.key.loop" },
  { keys: "Z / X", what: "player.key.offset" },
  { keys: "S", what: "player.key.shot" },
  { keys: "Shift + S", what: "player.key.shotInvert" },
  { keys: "F", what: "player.key.fs" },
  { keys: "P", what: "player.key.pip" },
  { keys: "< / >", what: "player.key.video" },
  { keys: "Ctrl + Z", what: "player.key.undo" },
  { keys: "?", what: "player.key.help" },
];
