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
  readonly keys: string;
  readonly what: string;
}

/** What the help overlay lists. Every row is a key `keyAction` answers, which the test checks. */
export const SHORTCUTS: readonly ShortcutRow[] = [
  { keys: "Space / K", what: "播放或暫停" },
  { keys: "← / →", what: "倒退或快轉 5 秒" },
  { keys: "J / L", what: "倒退或快轉 10 秒" },
  { keys: "0 – 9", what: "跳到影片的 0% 到 90%" },
  { keys: "↑ / ↓", what: "音量加或減" },
  { keys: "M", what: "靜音" },
  { keys: "[ / ]", what: "播放速度降低或提高" },
  { keys: ", / .", what: "上一格或下一格（會暫停）" },
  { keys: "Ctrl + ← / →", what: "跳到上一句或下一句字幕" },
  { keys: "A", what: "A-B 循環：設 A 點、設 B 點、取消" },
  { keys: "Z / X", what: "字幕提早或延後 0.1 秒" },
  { keys: "S", what: "截圖（依設定是否燒入字幕）" },
  { keys: "Shift + S", what: "截圖，燒入字幕的選擇與設定相反" },
  { keys: "F", what: "全螢幕" },
  { keys: "P", what: "子母畫面" },
  { keys: "< / >", what: "上一部或下一部（播放佇列）" },
  { keys: "Ctrl + Z", what: "復原上一次字幕修改" },
  { keys: "?", what: "顯示或關閉這份說明" },
];
