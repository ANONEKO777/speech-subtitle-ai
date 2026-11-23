/**
 * Calls `onTime` with the playback time on every display refresh while a file with no picture (an mp3, a wav) plays.
 * The browser presents no video frames for such a file, so `requestVideoFrameCallback` never fires and anything that
 * waits for a frame stands still. A file with a picture is left to the frame callback, which is exact.
 */
export function watchAudioClock(el: HTMLVideoElement, onTime: (seconds: number) => void): () => void {
  let handle = 0;
  const tick = () => {
    if (!el.paused && el.readyState >= 1 && el.videoWidth === 0) onTime(el.currentTime);
    handle = requestAnimationFrame(tick);
  };
  handle = requestAnimationFrame(tick);
  return () => cancelAnimationFrame(handle);
}
