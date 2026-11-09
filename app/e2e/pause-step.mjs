// The first frame-step press after play then pause must move exactly one frame in its direction, even when the
// video clock lags the picture. Each trial plays from a random point, pauses, waits a random moment, presses once,
// and compares the frame on screen (requestVideoFrameCallback mediaTime) with ffprobe's own frame list.
// node e2e/pause-step.mjs <projects-dir> <project-id> <video> <shots-dir> <repeats> <from-s> <span-s> [lag-s]
// Needs VST_CDP_PORT for its own DevTools port. A lag above 0 makes the page's video clock read that many seconds
// behind, which is what the pause after playback can do on a loaded machine. Exits 1 on a wrong step. CDP key events only.
import { execFileSync } from "node:child_process";
import { launch, sleep } from "./lib.mjs";
const [projects, pid, video, shots, repeatsArg, fromArg, spanArg, lagArg] = process.argv.slice(2);
if (!spanArg) throw new Error("usage: pause-step.mjs <projects> <project-id> <video> <shots> <repeats> <from-s> <span-s> [lag-s]");
const repeats = Number(repeatsArg);
const from = Number(fromArg);
const span = Number(spanArg);
const lag = Number(lagArg ?? 0);
const frames = execFileSync("ffprobe", ["-v", "error", "-select_streams", "v:0", "-read_intervals", `${from}%+${span + 5}`, "-show_entries", "frame=pts_time", "-of", "csv=p=0", video], { encoding: "utf8", maxBuffer: 1 << 26 })
  .trim().split("\n").map((x) => Number.parseFloat(x)).filter((x) => !Number.isNaN(x)).sort((a, b) => a - b);
const gaps = frames.slice(1).map((f, i) => f - frames[i]);
console.log("frames", frames.length, "gap>45ms", gaps.filter((g) => g > 0.045).length, "lag", lag);
const idx = (t) => {
  let best = 0;
  for (let i = 0; i < frames.length; i++) if (Math.abs(frames[i] - t) < Math.abs(frames[best] - t)) best = i;
  return Math.abs(frames[best] - t) < 0.004 ? best : -1;
};

const app = await launch({ projects, shots });
const p = app.page;
await p.mouse.move(300, 300);
await p.locator(`[data-testid="lib-play-${pid}"]`).click({ force: true });
await p.waitForSelector('[data-testid="cue-list"] li', { timeout: 30000 });
await p.waitForFunction(() => document.querySelector("video")?.readyState >= 1);
await p.evaluate((lagS) => {
  const v = document.querySelector("video");
  v.pause();
  window.__shown = -1;
  const cb = (_n, f) => { window.__shown = f.mediaTime; v.requestVideoFrameCallback(cb); };
  v.requestVideoFrameCallback(cb);
  if (lagS > 0) {
    const real = Object.getOwnPropertyDescriptor(HTMLMediaElement.prototype, "currentTime");
    Object.defineProperty(v, "currentTime", { configurable: true, get: () => real.get.call(v) - lagS, set: (x) => real.set.call(v, x) });
  }
}, lag);
await p.mouse.move(0, 0);
const shown = () => p.evaluate(() => window.__shown);
let bad = 0;
const ms = [];
for (let trial = 0; trial < repeats; trial++) {
  const start = frames[8 + Math.floor(Math.random() * (frames.length - 60))] ?? from;
  await p.evaluate((t) => { const v = document.querySelector("video"); v.currentTime = t; return v.play(); }, start);
  await sleep(500 + Math.floor(Math.random() * 900));
  await p.evaluate(() => document.querySelector("video").pause());
  await sleep(Math.floor(Math.random() * 250));
  let prev = await shown();
  const settle0 = Date.now();
  while ((await shown()) === prev && Date.now() - settle0 < 120) await sleep(20);
  prev = await shown();
  await p.locator("body").evaluate((b) => b.focus?.());
  const t0 = Date.now();
  await p.keyboard.press(".");
  let now = prev;
  while (Date.now() - t0 < 1500) { await sleep(25); now = await shown(); if (now !== prev) break; }
  await sleep(350);
  const settled = await shown();
  ms.push(Date.now() - t0);
  const a = idx(prev);
  const b = idx(settled);
  if (a < 0 || b < 0 || b - a !== 1) { bad++; console.log("BAD", trial, JSON.stringify({ from: prev, fromIdx: a, to: settled, toIdx: b })); }
}
ms.sort((x, y) => x - y);
console.log(bad === 0 ? "PASS" : "FAIL", "first presses after play then pause", repeats, "bad", bad, "latency ms p50", ms[ms.length >> 1], "max", ms.at(-1));
const { leftovers } = await app.closeWindow();
console.log("leftovers", JSON.stringify(leftovers));
process.exit(bad === 0 ? 0 : 1);
