import { type RefObject, useEffect, useState } from "react";
import { flushSync } from "react-dom";
import { type Cue, cueAt } from "./cues";

/**
 * Index of the cue showing in the video frame on screen, or -1. The browser calls back once per
 * presented frame with that frame's own timestamp, so the subtitle changes with the frame it
 * belongs to. The update is flushed inside the callback so it lands in the same composited frame.
 * `seeked` covers a paused video, which presents no new frames.
 */
export function useActiveCue(video: RefObject<HTMLVideoElement | null>, cues: readonly Cue[]): number {
  const [index, setIndex] = useState(-1);
  useEffect(() => {
    const el = video.current;
    if (!el) return;
    const show = (seconds: number) => flushSync(() => setIndex(cueAt(cues, Math.round(seconds * 1000))));
    let handle = 0;
    const onFrame: VideoFrameRequestCallback = (_now, frame) => {
      show(frame.mediaTime);
      handle = el.requestVideoFrameCallback(onFrame);
    };
    const onSeeked = () => show(el.currentTime);
    handle = el.requestVideoFrameCallback(onFrame);
    el.addEventListener("seeked", onSeeked);
    return () => {
      el.cancelVideoFrameCallback(handle);
      el.removeEventListener("seeked", onSeeked);
    };
  }, [video, cues]);
  return index;
}
