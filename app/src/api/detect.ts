import { type Backend, asRecord, base } from "./client";
import { MIXED, type SourceLang, type Unavailable, parseSourceLang, sourceLabel } from "./sourceLang";

/** What the backend guessed about the language of a video from a few short pieces of its audio. */
export interface Detection {
  /** What the audio holds, or null when it holds too little speech to say. */
  readonly detected: SourceLang | null;
  /** What to preselect: the detected language, or the main one when a mixed talk cannot be processed here. */
  readonly suggested: SourceLang | null;
  /** Why a mixed talk cannot be processed on this machine, when that is what was heard. */
  readonly mixedUnavailable: string | null;
  /** The share of clear pieces in the language that spoke most, from 0 to 1. */
  readonly confidence: number;
  /** Whether it is clear enough to preselect and to tell a person who chose differently. */
  readonly sure: boolean;
  readonly ja: number;
  readonly en: number;
}

/** A guess that did not come, came late or was refused. The picker stays as it is. */
export type Detected = Detection | "running" | "failed";

export const isDetection = (value: Detected | undefined): value is Detection => typeof value === "object";

const share = (shares: Record<string, unknown> | null, code: string): number => {
  const value = shares?.[code];
  return typeof value === "number" ? value : 0;
};

export function parseDetection(body: unknown): Detection | null {
  const o = asRecord(body);
  if (o === null || typeof o["confidence"] !== "number") return null;
  const shares = asRecord(o["shares"]);
  const code = (value: unknown): SourceLang | null => (value === null || value === undefined ? null : parseSourceLang(value));
  return {
    detected: code(o["detected"]),
    suggested: code(o["suggested"]),
    mixedUnavailable: typeof o["mixed_unavailable"] === "string" ? o["mixed_unavailable"] : null,
    confidence: o["confidence"],
    sure: o["sure"] === true,
    ja: share(shares, "ja"),
    en: share(shares, "en"),
  };
}

export const DETECT_TIMEOUT_MS = 25_000;

/** Asks the backend which language the video is in. Any failure, refusal or timeout is null: the guess is a help, never a requirement. */
export async function detectLanguage(b: Backend, videoPath: string, signal: AbortSignal): Promise<Detection | null> {
  try {
    const res = await fetch(`${base(b)}/api/languages/detect`, {
      method: "POST",
      signal,
      headers: { authorization: `Bearer ${b.token}`, "content-type": "application/json" },
      body: JSON.stringify({ video_path: videoPath }),
    });
    return res.ok ? parseDetection(await res.json().catch(() => null)) : null;
  } catch {
    return null;
  }
}

const percent = (value: number): string => `${Math.round(value * 100)}%`;

/** The one line under the toolbar: what was heard, and how sure that is. Null when nothing was heard. */
export function detectLine(d: Detection): string | null {
  if (d.detected === null || d.suggested === null) return null;
  if (d.detected === MIXED) {
    const mix = `日文 ${percent(d.ja)}、英文 ${percent(d.en)}`;
    return d.mixedUnavailable === null
      ? `偵測到：日文與英文混合（${mix}）`
      : `偵測到：日文與英文混合（${mix}）。這台電腦無法處理混合語言，先選${sourceLabel(d.suggested)}，另一種語言的部分可能翻不好`;
  }
  return d.sure
    ? `偵測到：${sourceLabel(d.detected)}（信心 ${percent(d.confidence)}）`
    : `可能是${sourceLabel(d.detected)}（信心 ${percent(d.confidence)}），請確認影片語言`;
}

/** The language to put in the picker for a guess, or null to leave it alone: the person already chose, the guess is not clear, or this machine cannot process it. */
export function preselect(d: Detection, touched: boolean, unavailable: Unavailable): SourceLang | null {
  if (touched || !d.sure || d.suggested === null || unavailable[d.suggested] !== undefined) return null;
  return d.suggested;
}

export interface Hint {
  readonly text: string;
  readonly switchTo: SourceLang;
}

/**
 * What to tell a person whose choice differs from a clear guess, with the one-click switch. Null
 * when they agree, the guess is not clear, or the guess is a language the mixed choice already
 * covers: the person who picked mixed knows the talk has a stretch in each.
 */
export function hintFor(d: Detection, picked: SourceLang, unavailable: Unavailable): Hint | null {
  if (!d.sure || d.suggested === null || d.suggested === picked || unavailable[d.suggested] !== undefined) return null;
  if (picked === MIXED) return null;
  const choice = sourceLabel(picked);
  if (d.suggested === MIXED) {
    return { text: `這部影片聽起來日文與英文都有，目前選的是${choice}，另一種語言會被當成${choice}處理`, switchTo: MIXED };
  }
  const heard = sourceLabel(d.suggested);
  const text =
    d.detected === MIXED
      ? `這部影片大部分是${heard}，目前選的是${choice}`
      : `這部影片聽起來是${heard}，目前選的是${choice}`;
  return { text, switchTo: d.suggested };
}

export const switchLabel = (code: SourceLang): string => `改成${sourceLabel(code)}`;
