import type { Cue } from "./cues";

/** Playback speeds the [ and ] keys step through. */
export const SPEEDS = [0.5, 0.75, 1, 1.25, 1.5, 1.75, 2] as const;

/** The next speed up (`dir` 1) or down (-1) from `current`, stopping at the ends. */
export function stepSpeed(current: number, dir: 1 | -1): number {
  const i = SPEEDS.findIndex((s) => s >= current - 1e-9);
  const at = i < 0 ? SPEEDS.length - 1 : i;
  const exact = Math.abs((SPEEDS[at] ?? 1) - current) < 1e-9;
  const target = dir === 1 ? (exact ? at + 1 : at) : at - 1;
  return SPEEDS[Math.min(SPEEDS.length - 1, Math.max(0, target))] ?? 1;
}

export interface Loop {
  readonly a: number | null;
  readonly b: number | null;
}

export const NO_LOOP: Loop = { a: null, b: null };

/** One press of the loop key at `now` seconds: set A, then set B, then clear. */
export function cycleLoop(loop: Loop, now: number): Loop {
  if (loop.a === null) return { a: now, b: null };
  if (loop.b === null) return now > loop.a + 0.2 ? { a: loop.a, b: now } : { a: now, b: null };
  return NO_LOOP;
}

/** Where to jump back to when playback at `now` has reached the end of the loop, else null. */
export function loopTarget(loop: Loop, now: number): number | null {
  return loop.a !== null && loop.b !== null && now >= loop.b ? loop.a : null;
}

/** A positive offset shows every cue that many ms later. */
export const OFFSET_LIMIT_MS = 60_000;

export const clampOffset = (ms: number) => Math.min(OFFSET_LIMIT_MS, Math.max(-OFFSET_LIMIT_MS, Math.round(ms)));

/** The time to look up in the cue list for a video at `videoMs`: the cues are `offsetMs` late. */
export const cueTime = (videoMs: number, offsetMs: number) => videoMs - offsetMs;

/** When cue `c` starts on the video clock. */
export const startOnVideo = (c: Cue, offsetMs: number) => c.startMs + offsetMs;

export function formatOffset(ms: number): string {
  const s = (Math.abs(ms) / 1000).toFixed(1);
  return `${ms < 0 ? "-" : "+"}${s} s`;
}

/** Index of the cue to jump to from `nowMs`: the first one starting after now, or the last one that started more than `restartMs` ago (a press inside a cue's first moments goes to the one before). Null when there is none. */
export function adjacentCue(
  cues: readonly Cue[],
  offsetMs: number,
  nowMs: number,
  dir: 1 | -1,
  restartMs = 700,
): number | null {
  if (dir === 1) {
    const i = cues.findIndex((c) => startOnVideo(c, offsetMs) > nowMs + 1);
    return i < 0 ? null : i;
  }
  for (let i = cues.length - 1; i >= 0; i--) {
    const cue = cues[i];
    if (cue && startOnVideo(cue, offsetMs) < nowMs - restartMs) return i;
  }
  return null;
}

/** Where to start a video last left at `position` of `duration` seconds. A video left near its start or end starts over. */
export function resumeAt(position: number, duration: number): number {
  if (!(position > 5)) return 0;
  if (duration > 0 && position > duration - 10) return 0;
  return position;
}

export function playClock(seconds: number): string {
  const s = Math.max(0, Math.floor(seconds));
  const h = Math.floor(s / 3600);
  const m = String(Math.floor((s % 3600) / 60)).padStart(h > 0 ? 2 : 1, "0");
  const ss = String(s % 60).padStart(2, "0");
  return h > 0 ? `${h}:${m}:${ss}` : `${m}:${ss}`;
}

const FRAME_TRIES = 4;

/** Where a frame step starts: the frame on screen when one was reported since the last seek, otherwise the clock. The clock can sit several frames behind the picture after a pause that follows playback, so it only stands in when no frame has been reported (`shown` below 0). */
export function stepOrigin(shown: number, clock: number): number {
  return shown >= 0 ? shown : clock;
}

/** Where to seek to land on the frame after (`dir` 1) or before (-1) the one shown from `from`. The middle of the target frame, so rounding in the decoder cannot pick its neighbour. Each later `attempt` aims one frame further, for a frame that lasted longer than `frameS`. */
export function frameStepTarget(from: number, dir: 1 | -1, frameS: number, attempt: number): number {
  return dir > 0 ? from + (1.5 + attempt) * frameS : from - (0.5 + attempt) * frameS;
}

/** Whether a seek from `from` landed on a different frame in the wanted direction. */
export function frameMoved(from: number, landed: number, dir: 1 | -1, frameS: number): boolean {
  return dir > 0 ? landed > from + frameS / 4 : landed < from - frameS / 4;
}

/** Moves exactly one displayed frame from the one shown at `from` and returns the presentation time of the frame it lands on, or `from` at the ends. `seek` shows the frame at a time and resolves with that frame's own presentation time, which is how a variable-rate stream, whose frames can last two ticks, still moves by one frame. */
export async function stepFrame(
  seek: (to: number) => Promise<number>,
  from: number,
  dir: 1 | -1,
  frameS: number,
): Promise<number> {
  for (let attempt = 0; attempt < FRAME_TRIES; attempt++) {
    const target = frameStepTarget(from, dir, frameS, attempt);
    const landed = await seek(Math.max(0, target));
    if (frameMoved(from, landed, dir, frameS)) return landed;
    if (dir < 0 && target <= 0) break;
  }
  return from;
}
