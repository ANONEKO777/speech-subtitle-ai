import type { SubtitleMode } from "../player/cues";

export interface Settings {
  readonly mode: SubtitleMode;
  readonly fontSize: number;
  readonly color: string;
  readonly lineHeight: number;
  readonly zhFirst: boolean;
  /** Folder for screenshots and burned-in videos. Empty means the app's own folder. */
  readonly outputDir: string;
  /** Whether S puts the subtitle into the picture. Shift+S does the opposite. */
  readonly burnShots: boolean;
  /** Whether a fullscreen video shows the subtitle over the picture instead of below it. */
  readonly fsOverlay: boolean;
}

export const DEFAULTS: Settings = {
  mode: "both",
  fontSize: 24,
  color: "#ffffff",
  lineHeight: 1.4,
  zhFirst: true,
  outputDir: "",
  burnShots: false,
  fsOverlay: false,
};
export const KEY = "vst.settings.v1";

const clamp = (v: unknown, lo: number, hi: number, fallback: number) =>
  typeof v === "number" && Number.isFinite(v) ? Math.min(hi, Math.max(lo, v)) : fallback;

/** Reads stored settings, replacing anything missing or out of range with the default. */
export function parseSettings(raw: string | null): Settings {
  let o: Record<string, unknown> = {};
  try {
    const parsed: unknown = JSON.parse(raw ?? "{}");
    if (typeof parsed === "object" && parsed !== null) o = parsed as Record<string, unknown>;
  } catch {
    // a damaged store falls back to the defaults
  }
  return {
    mode: o["mode"] === "en" || o["mode"] === "zh" || o["mode"] === "both" ? o["mode"] : DEFAULTS.mode,
    fontSize: clamp(o["fontSize"], 14, 64, DEFAULTS.fontSize),
    color: typeof o["color"] === "string" && /^#[0-9a-f]{6}$/i.test(o["color"]) ? o["color"] : DEFAULTS.color,
    lineHeight: clamp(o["lineHeight"], 1, 2.2, DEFAULTS.lineHeight),
    zhFirst: typeof o["zhFirst"] === "boolean" ? o["zhFirst"] : DEFAULTS.zhFirst,
    outputDir: typeof o["outputDir"] === "string" ? o["outputDir"] : DEFAULTS.outputDir,
    burnShots: typeof o["burnShots"] === "boolean" ? o["burnShots"] : DEFAULTS.burnShots,
    fsOverlay: typeof o["fsOverlay"] === "boolean" ? o["fsOverlay"] : DEFAULTS.fsOverlay,
  };
}
