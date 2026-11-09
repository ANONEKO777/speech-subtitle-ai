export interface Prefs {
  readonly volume: number;
  readonly muted: boolean;
  readonly rate: number;
}

export const PREFS_KEY = "vst.player.v1";
export const DEFAULT_PREFS: Prefs = { volume: 1, muted: false, rate: 1 };

const inRange = (v: unknown, lo: number, hi: number, fallback: number) =>
  typeof v === "number" && v >= lo && v <= hi ? v : fallback;

/** Volume, mute and speed the person last left, which every video starts with. */
export function parsePrefs(raw: string | null): Prefs {
  try {
    const o: unknown = JSON.parse(raw ?? "null");
    const r = typeof o === "object" && o !== null ? (o as Record<string, unknown>) : {};
    return {
      volume: inRange(r["volume"], 0, 1, DEFAULT_PREFS.volume),
      muted: typeof r["muted"] === "boolean" ? r["muted"] : DEFAULT_PREFS.muted,
      rate: inRange(r["rate"], 0.5, 2, DEFAULT_PREFS.rate),
    };
  } catch {
    return DEFAULT_PREFS;
  }
}
