// Shared helpers for the promo capture scripts: a fixed-size window, a CDP screencast
// that writes timestamped JPEG frames, and a concat list that ffmpeg turns into a video.
// Run the scripts from the repository root. They need a built app and a user-data folder
// with the models (VST_USER_DATA), see docs/media/README.md.
import { mkdirSync, writeFileSync } from "node:fs";
import { join, resolve } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const here = fileURLToPath(new URL(".", import.meta.url));
const root = resolve(here, "../../..");
export const lib = await import(pathToFileURL(join(root, "app/e2e/lib.mjs")).href);
export const { sleep } = lib;

export const VIEW = { width: 1280, height: 720 };

/** Sizes the window so the page viewport is exactly 1280x720 CSS pixels, whatever the title bar and display scaling add. */
export async function fixWindow(page, { width, height } = VIEW) {
  const session = await page.context().newCDPSession(page);
  const { windowId } = await session.send("Browser.getWindowForTarget");
  const measure = () => page.evaluate(() => [window.innerWidth, window.innerHeight, window.devicePixelRatio]);
  let w = width + 16;
  let h = height + 80;
  for (let i = 0; i < 8; i++) {
    await session.send("Browser.setWindowBounds", { windowId, bounds: { windowState: "normal", width: w, height: h } });
    await sleep(500);
    const [iw, ih, dpr] = await measure();
    if (iw === width && ih === height) {
      displayScale = dpr;
      return { width: iw, height: ih, dpr };
    }
    w += width - iw;
    h += height - ih;
  }
  const [iw, ih, dpr] = await measure();
  throw new Error(`cannot size the viewport to ${width}x${height}, got ${iw}x${ih} at ${dpr}x`);
}

const SCALE = 1.25;
let displayScale = 1;

/** Saves a PNG of the 1280x720 viewport. The capture scale is multiplied by the display scaling, so divide it out to get 1600x900. */
export async function snap(page, file) {
  const session = await page.context().newCDPSession(page);
  const { data } = await session.send("Page.captureScreenshot", {
    format: "png",
    captureBeyondViewport: false,
    clip: { x: 0, y: 0, width: VIEW.width, height: VIEW.height, scale: SCALE / displayScale },
  });
  writeFileSync(file, Buffer.from(data, "base64"));
  await session.detach();
  return file;
}

/** Starts a screencast. `stop()` writes `list.txt` for ffmpeg's concat demuxer and returns the frame count. */
export async function startCast(page, dir) {
  mkdirSync(dir, { recursive: true });
  const session = await page.context().newCDPSession(page);
  const frames = [];
  session.on("Page.screencastFrame", (e) => {
    const name = `f${String(frames.length).padStart(6, "0")}.jpg`;
    writeFileSync(join(dir, name), Buffer.from(e.data, "base64"));
    frames.push({ name, t: e.metadata.timestamp });
    session.send("Page.screencastFrameAck", { sessionId: e.sessionId }).catch(() => {});
  });
  await session.send("Page.startScreencast", { format: "jpeg", quality: 92, maxWidth: VIEW.width, maxHeight: VIEW.height, everyNthFrame: 1 });
  return {
    async stop(tailSeconds = 0.5) {
      await session.send("Page.stopScreencast").catch(() => {});
      const lines = [];
      frames.forEach((f, i) => {
        const next = frames[i + 1]?.t ?? f.t + tailSeconds;
        lines.push(`file '${f.name}'`, `duration ${Math.max(next - f.t, 0.001).toFixed(4)}`);
      });
      if (frames.length) lines.push(`file '${frames[frames.length - 1].name}'`);
      writeFileSync(join(dir, "list.txt"), lines.join("\n") + "\n");
      return { frames: frames.length, seconds: frames.length ? frames[frames.length - 1].t - frames[0].t + tailSeconds : 0 };
    },
  };
}
