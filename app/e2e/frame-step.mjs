// Frame step on a variable-frame-rate talk: after play and pause, 24 trials of 6 key presses (. and ,) must each
// move exactly one frame of the video's own frame list (ffprobe), then taps in quick succession and a press during play.
// node e2e/frame-step.mjs <projects-dir> <video> <shots-dir> [port]   exits 1 on a wrong step. Uses CDP key events only.
import { execFileSync } from "node:child_process";
import { launch, sleep } from "./lib.mjs";
const [projects, video, shots, portArg] = process.argv.slice(2);
if (!projects || !video || !shots) throw new Error("usage: frame-step.mjs <projects> <video> <shots> [port]");
const app = await launch({ projects, shots, port: Number(portArg ?? 9222) });
const p = app.page;
await p.fill('[data-testid="video-path"]', video);
await p.click('[data-testid="import"]');
await p.waitForSelector('[data-testid="cue-list"] li', { timeout: 30000 });
await p.evaluate(() => document.querySelector("video").pause());
await p.mouse.move(0, 0);
// frame list near the trial area
const AT = 500;
const frames = execFileSync("ffprobe", ["-v", "error", "-select_streams", "v:0", "-read_intervals", `${AT - 5}%+40`, "-show_entries", "frame=pts_time", "-of", "csv=p=0", video], { encoding: "utf8", maxBuffer: 1 << 24 })
  .trim().split("\n").map(Number).filter((x) => !Number.isNaN(x)).sort((a, b) => a - b);
console.log("frames", frames.length, "gaps>40ms:", frames.slice(1).map((f, i) => f - frames[i]).filter((g) => g > 0.04).length);
const idx = (t) => { let best = 0; for (let i = 0; i < frames.length; i++) if (Math.abs(frames[i] - t) < Math.abs(frames[best] - t)) best = i; return Math.abs(frames[best] - t) < 0.004 ? best : -1; };

await p.evaluate(() => {
  const v = document.querySelector("video");
  window.__shown = -1;
  const cb = (_n, f) => { window.__shown = f.mediaTime; v.requestVideoFrameCallback(cb); };
  v.requestVideoFrameCallback(cb);
});
const shown = () => p.evaluate(() => window.__shown);
const results = [];
for (let trial = 0; trial < 24; trial++) {
  const start = AT + 2 + trial * 0.37;
  await p.evaluate((t) => { const v = document.querySelector("video"); v.currentTime = t; return v.play(); }, start);
  await sleep(trial % 3 === 0 ? 1500 : 400);
  await p.evaluate(() => document.querySelector("video").pause());
  await sleep(150);
  const keys = trial % 2 === 0 ? [".", ".", ".", ",", ",", ","] : [",", ",", ".", ".", ".", ","];
  const seq = [];
  let prev = await shown();
  for (const k of keys) {
    const t0 = Date.now();
    await p.keyboard.press(k);
    let now = prev;
    while (Date.now() - t0 < 1500) { await sleep(25); now = await shown(); if (now !== prev) break; }
    const ms = Date.now() - t0;
    await sleep(300);
    const settled = await shown();
    seq.push({ k, from: idx(prev), to: idx(settled), ms, firstSeen: idx(now) });
    prev = settled;
  }
  results.push(seq);
}
let bad = 0, total = 0;
for (const seq of results) for (const s of seq) {
  total++;
  const want = s.k === "." ? 1 : -1;
  if (s.from < 0 || s.to < 0 || s.to - s.from !== want) { bad++; console.log("BAD", JSON.stringify(s)); }
}
console.log(bad === 0 ? "PASS" : "FAIL", "steps", total, "bad", bad, "latency ms", JSON.stringify(results.flat().map((s) => s.ms).sort((a, b) => a - b).filter((_, i, a) => i % 12 === 0 || i === a.length - 1)));
for (const [n, key] of [[12, "."], [12, ","], [7, "."]]) {
  await p.evaluate(() => document.querySelector("video").pause());
  await sleep(300);
  const before = idx(await shown());
  for (let i = 0; i < n; i++) { await p.keyboard.press(key); await sleep(30); }
  await sleep(2500);
  const after = idx(await shown());
  const ok = after - before === (key === "." ? n : -n);
  if (!ok) bad++;
  console.log("TAPS", key, n, "moved", after - before, ok ? "OK" : "BAD");
}
const playing = await p.evaluate(async () => { const v = document.querySelector("video"); await v.play(); await new Promise((r) => setTimeout(r, 600)); return !v.paused; });
await p.keyboard.press(".");
await sleep(1200);
const pausedNow = await p.evaluate(() => document.querySelector("video").paused);
if (!playing || !pausedNow) bad++;
console.log("STEP WHILE PLAYING paused:", pausedNow, "wasPlaying", playing);
const { leftovers } = await app.closeWindow();
console.log("leftovers", JSON.stringify(leftovers));
process.exit(bad === 0 ? 0 : 1);
