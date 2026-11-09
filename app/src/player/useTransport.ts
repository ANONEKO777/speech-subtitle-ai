import { type RefObject, useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { Backend } from "../api/client";
import { fetchFrameRate, putPlayback } from "../api/library";
import { PREFS_KEY, parsePrefs } from "./prefs";
import { type Loop, NO_LOOP, cycleLoop, loopTarget, playClock, resumeAt, stepFrame, stepOrigin, stepSpeed } from "./transport";

const SAVE_EVERY_MS = 5000;
const SEEK_WAIT_MS = 1000;
const FRAME_AFTER_SEEK_MS = 250;
const PAUSE_SETTLE_MS = 60;

interface Options {
  readonly backend: Backend;
  readonly projectId: string;
  /** Where the project was left, in seconds. */
  readonly savedPosition: number;
  /** Called when a video starts where it was left. */
  readonly onResumed: (at: number) => void;
  readonly onEnded: () => void;
}

/** The state and the actions of the video element: play, seek, volume, speed, frame step, A-B loop, and remembering where the person stopped. Each action returns the line the on-screen display shows. */
export function useTransport(video: RefObject<HTMLVideoElement | null>, o: Options) {
  const prefs = useRef(parsePrefs(localStorage.getItem(PREFS_KEY)));
  const [paused, setPaused] = useState(true);
  const [time, setTime] = useState(0);
  const [duration, setDuration] = useState(0);
  const [volume, setVolume] = useState(prefs.current.volume);
  const [muted, setMuted] = useState(prefs.current.muted);
  const [rate, setRate] = useState(prefs.current.rate);
  const [loop, setLoop] = useState<Loop>(NO_LOOP);
  const frameS = useRef(1 / 30);
  const shown = useRef(-1);
  const waiting = useRef<((mediaTime: number) => void) | null>(null);
  const stepping = useRef(Promise.resolve());
  const lastSaved = useRef(0);
  const position = useRef({ s: 0, d: 0 });
  const onEnded = useRef(o.onEnded);
  onEnded.current = o.onEnded;
  const onResumed = useRef(o.onResumed);
  onResumed.current = o.onResumed;
  const { backend, projectId, savedPosition } = o;

  const save = useCallback(
    (keepalive = false, at = position.current.s) => {
      lastSaved.current = performance.now();
      void putPlayback(backend, projectId, { positionS: at, durationS: position.current.d }, keepalive).catch(() => undefined);
    },
    [backend, projectId],
  );

  useEffect(() => {
    position.current = { s: 0, d: 0 };
    setLoop(NO_LOOP);
    setTime(0);
    setDuration(0);
    void putPlayback(backend, projectId, { opened: true }).catch(() => undefined);
    const leave = () => save(true);
    window.addEventListener("pagehide", leave);
    return () => {
      window.removeEventListener("pagehide", leave);
      if (position.current.d > 0) save(true);
    };
  }, [backend, projectId, save]);

  useEffect(() => {
    let current = true;
    frameS.current = 1 / 30;
    shown.current = -1;
    fetchFrameRate(backend, projectId).then(
      (fps) => {
        if (current && fps) frameS.current = 1 / fps;
      },
      () => undefined,
    );
    return () => {
      current = false;
    };
  }, [backend, projectId]);

  useEffect(() => {
    const el = video.current;
    if (!el) return;
    let handle = 0;
    const onFrame: VideoFrameRequestCallback = (_now, frame) => {
      shown.current = frame.mediaTime;
      const waiter = waiting.current;
      waiting.current = null;
      waiter?.(frame.mediaTime);
      const back = loopTarget(loop, frame.mediaTime);
      if (back !== null) el.currentTime = back;
      handle = el.requestVideoFrameCallback(onFrame);
    };
    handle = el.requestVideoFrameCallback(onFrame);
    return () => el.cancelVideoFrameCallback(handle);
  }, [video, projectId, loop]);

  const videoProps = useMemo(
    () => ({
      onLoadedMetadata: (e: { currentTarget: HTMLVideoElement }) => {
        const el = e.currentTarget;
        setDuration(el.duration);
        position.current.d = el.duration;
        el.volume = prefs.current.volume;
        el.muted = prefs.current.muted;
        el.playbackRate = prefs.current.rate;
        const at = resumeAt(savedPosition, el.duration);
        if (at > 0) {
          el.currentTime = at;
          onResumed.current(at);
        }
      },
      onDurationChange: (e: { currentTarget: HTMLVideoElement }) => setDuration(e.currentTarget.duration || 0),
      onVolumeChange: (e: { currentTarget: HTMLVideoElement }) => {
        const el = e.currentTarget;
        setVolume(el.volume);
        setMuted(el.muted);
        prefs.current = { ...prefs.current, volume: el.volume, muted: el.muted };
        localStorage.setItem(PREFS_KEY, JSON.stringify(prefs.current));
      },
      onRateChange: (e: { currentTarget: HTMLVideoElement }) => {
        setRate(e.currentTarget.playbackRate);
        prefs.current = { ...prefs.current, rate: e.currentTarget.playbackRate };
        localStorage.setItem(PREFS_KEY, JSON.stringify(prefs.current));
      },
      onPlay: () => setPaused(false),
      onPause: () => {
        setPaused(true);
        if (position.current.d > 0) save();
      },
      onTimeUpdate: (e: { currentTarget: HTMLVideoElement }) => {
        const t = e.currentTarget.currentTime;
        setTime(t);
        position.current.s = t;
        if (performance.now() - lastSaved.current > SAVE_EVERY_MS && position.current.d > 0) save();
      },
      onSeeking: () => {
        shown.current = -1;
      },
      onSeeked: (e: { currentTarget: HTMLVideoElement }) => setTime(e.currentTarget.currentTime),
      onEnded: () => {
        position.current.s = 0;
        save(false, 0);
        onEnded.current();
      },
    }),
    [savedPosition, save],
  );

  /** Shows the frame at `to` and resolves with its own presentation time, or with the frame already shown when none arrives after the seek ends. */
  const showFrameAt = (e: HTMLVideoElement, to: number) =>
    new Promise<number>((resolve) => {
      const before = shown.current >= 0 ? shown.current : e.currentTime;
      const onScreen = () => {
        if (shown.current < 0) shown.current = before;
        return shown.current;
      };
      let timer = 0;
      const finish = (mediaTime: number) => {
        window.clearTimeout(timer);
        e.removeEventListener("seeked", onSeeked);
        if (waiting.current === onFrame) waiting.current = null;
        resolve(mediaTime);
      };
      const onFrame = (mediaTime: number) => finish(mediaTime);
      const onSeeked = () => {
        window.clearTimeout(timer);
        timer = window.setTimeout(() => finish(onScreen()), FRAME_AFTER_SEEK_MS);
      };
      e.addEventListener("seeked", onSeeked, { once: true });
      timer = window.setTimeout(() => finish(onScreen()), SEEK_WAIT_MS);
      waiting.current = onFrame;
      e.currentTime = clampTo(e, to);
    });

  const stepOneFrame = async (e: HTMLVideoElement, dir: 1 | -1, wasPlaying: boolean) => {
    if (wasPlaying) await new Promise((r) => window.setTimeout(r, PAUSE_SETTLE_MS));
    await stepFrame((to) => showFrameAt(e, to), stepOrigin(shown.current, e.currentTime), dir, frameS.current);
  };

  const el = () => video.current;
  const clampTo = (e: HTMLVideoElement, t: number) => Math.min(Math.max(0, t), e.duration || t);

  return {
    paused,
    time,
    duration,
    volume,
    muted,
    rate,
    loop,
    videoProps,
    seekTo(seconds: number) {
      const e = el();
      if (e) e.currentTime = clampTo(e, seconds);
    },
    seekBy(seconds: number) {
      const e = el();
      if (!e) return;
      e.currentTime = clampTo(e, e.currentTime + seconds);
      return `${seconds > 0 ? "+" : "−"}${Math.abs(seconds)} 秒`;
    },
    seekPercent(percent: number) {
      const e = el();
      if (e && e.duration) e.currentTime = (e.duration * percent) / 100;
      return `${percent}%`;
    },
    togglePlay() {
      const e = el();
      if (!e) return;
      if (e.paused) void e.play().catch(() => undefined);
      else e.pause();
    },
    setVolumeTo(v: number) {
      const e = el();
      if (!e) return;
      e.volume = Math.min(1, Math.max(0, v));
      if (v > 0) e.muted = false;
    },
    volumeBy(delta: number) {
      const e = el();
      if (!e) return;
      const next = Math.round(Math.min(1, Math.max(0, e.volume + delta)) * 100) / 100;
      e.volume = next;
      if (delta > 0) e.muted = false;
      return `音量 ${Math.round(next * 100)}%`;
    },
    toggleMute() {
      const e = el();
      if (!e) return;
      e.muted = !e.muted;
      return e.muted ? "靜音" : `音量 ${Math.round(e.volume * 100)}%`;
    },
    setRateTo(r: number) {
      const e = el();
      if (e) e.playbackRate = r;
      return `速度 ${r}×`;
    },
    speedStep(dir: 1 | -1) {
      const e = el();
      if (!e) return;
      const next = stepSpeed(e.playbackRate, dir);
      e.playbackRate = next;
      return `速度 ${next}×`;
    },
    frameStep(dir: 1 | -1) {
      const e = el();
      if (!e) return;
      const wasPlaying = !e.paused;
      e.pause();
      stepping.current = stepping.current.then(() => stepOneFrame(e, dir, wasPlaying));
      return dir > 0 ? "下一格" : "上一格";
    },
    cycleLoop() {
      const e = el();
      if (!e) return;
      const next = cycleLoop(loop, e.currentTime);
      setLoop(next);
      if (next.b !== null) return `A-B 循環 ${playClock(next.a ?? 0)} – ${playClock(next.b)}`;
      return next.a !== null ? `A 點 ${playClock(next.a)}` : "A-B 循環已取消";
    },
  };
}
