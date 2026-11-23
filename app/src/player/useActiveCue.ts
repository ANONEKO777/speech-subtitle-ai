import { type RefObject, useEffect, useState } from "react";
import { flushSync } from "react-dom";
import { watchAudioClock } from "./audioClock";
import { type Cue, cueAt } from "./cues";
import { cueTime } from "./transport";

/**
 * Index of the cue showing in the video frame on screen, or -1. The browser calls back once per
 * presented frame with that frame's own timestamp, so the subtitle changes with the frame it
 * belongs to. The update is flushed inside the callback so it lands in the same composited frame.
 * `seeked` covers a paused video, which presents no new frames. A file with no picture (an mp3) presents no
 * frames at all, so its clock is read on every display refresh. A subtitle `offsetMs` late is looked up at the
 * earlier time.
 */
export function useActiveCue(video: RefObject<HTMLVideoElement | null>, cues: readonly Cue[], offsetMs = 0): number {
  const [index, setIndex] = useState(-1);
  useEffect(() => {
    const el = video.current;
    if (!el) return;
    const show = (seconds: number) => flushSync(() => setIndex(cueAt(cues, cueTime(Math.round(seconds * 1000), offsetMs))));
    let handle = 0;
    const onFrame: VideoFrameRequestCallback = (_now, frame) => {
      show(frame.mediaTime);
      handle = el.requestVideoFrameCallback(onFrame);
    };
    const onSeeked = () => show(el.currentTime);
    setIndex(cueAt(cues, cueTime(Math.round(el.currentTime * 1000), offsetMs)));
    handle = el.requestVideoFrameCallback(onFrame);
    el.addEventListener("seeked", onSeeked);
    const stopClock = watchAudioClock(el, show);
    return () => {
      stopClock();
      el.cancelVideoFrameCallback(handle);
      el.removeEventListener("seeked", onSeeked);
    };
  }, [video, cues, offsetMs]);
  return index;
}
