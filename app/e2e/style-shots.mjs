// Screenshot set for a visual review: empty state, the three modes at 1280x720 and 960x600, a hovered cue,
// and optionally the import progress screen. Checks the video and subtitle boxes do not move between modes.
// node e2e/style-shots.mjs <projects-dir> <video> <shots-dir> [cue-number] [<progress-video>]
// VST_APP_EXE picks another build.
import { writeFileSync } from "node:fs";
import { join } from "node:path";
import { launch, sleep } from "./lib.mjs";

const [projects, video, shots, cueArg, progressVideo] = process.argv.slice(2);
if (!projects || !video || !shots) throw new Error("usage: style-shots.mjs <projects> <video> <shots> [cue] [progress-video]");
const cueN = Number(cueArg ?? 40);
const report = { failures: [] };
const check = (ok, what) => {
  console.log(`${ok ? "PASS" : "FAIL"} ${what}`);
  if (!ok) report.failures.push(what);
};

const app = await launch({ projects, shots });
const p = app.page;
report.coldStartMs = app.coldStartMs;

const session = await p.context().newCDPSession(p);
const { windowId } = await session.send("Browser.getWindowForTarget");
const resize = async (width, height) => {
  await session.send("Browser.setWindowBounds", { windowId, bounds: { windowState: "normal", width, height } });
  await sleep(600);
};

await resize(1280, 720);
await app.shot("empty.png");

await p.fill('[data-testid="video-path"]', video);
await p.click('[data-testid="import"]');
await p.waitForSelector('[data-testid="cue-list"] li', { timeout: 30000 });
const start = Number(await p.getAttribute(`[data-testid="cue-${cueN}"]`, "data-start")) / 1000;
await p.click(`[data-testid="cue-${cueN}"] button`);
await p.waitForFunction((t) => Math.abs(document.querySelector("video").currentTime - t) < 0.5, start);
await p.evaluate(() => document.querySelector("video").pause());
await p.mouse.move(0, 0);

const boxes = () =>
  p.evaluate(() => {
    const r = (sel) => {
      const b = document.querySelector(sel).getBoundingClientRect();
      return [b.left, b.top, b.width, b.height];
    };
    return { video: r('[data-testid="video"]'), subtitle: r('[data-testid="subtitle"]'), list: r('[data-testid="cue-list"]') };
  });

for (const [w, h] of [[1280, 720], [960, 600]]) {
  await resize(w, h);
  const seen = [];
  for (const mode of ["en", "zh", "both"]) {
    await p.click(`[data-testid="mode-${mode}"]`);
    await p.mouse.move(0, 0);
    await sleep(400);
    seen.push(await boxes());
    await app.shot(`${w}-${mode}.png`);
  }
  report[`boxes${w}`] = seen;
  const same = (a, b) => a.every((v, i) => Math.abs(v - b[i]) <= 1);
  const steady = seen.every((b) => same(b.video, seen[0].video) && same(b.subtitle, seen[0].subtitle));
  check(steady, `${w}x${h} video and subtitle boxes within 1 px in all modes: ${JSON.stringify(seen.map((b) => b.video.concat(b.subtitle).map(Math.round)))}`);
  const below = await p.evaluate(() => {
    const v = document.querySelector('[data-testid="video"]').getBoundingClientRect();
    const s = document.querySelector('[data-testid="subtitle"]').getBoundingClientRect();
    return s.top >= v.bottom - 0.5 && s.bottom <= innerHeight + 0.5;
  });
  check(below, `${w}x${h} subtitle below the video and inside the window`);
}

await resize(1280, 720);
await p.hover(`[data-testid="cue-${cueN + 2}"] button`);
await sleep(300);
await app.shot("hover.png");

if (progressVideo) {
  await p.fill('[data-testid="video-path"]', progressVideo);
  await p.click('[data-testid="import"]');
  await p.waitForSelector('[data-testid="importing"]', { timeout: 30000 });
  const t0 = Date.now();
  while (Date.now() - t0 < 90000) {
    const percent = Number((await p.textContent('[data-testid="percent"]')).replace("%", ""));
    if (percent >= 25) break;
    await sleep(500);
  }
  await app.shot("progress.png");
  await p.click('[data-testid="importing"] button');
  await p.waitForSelector('[data-testid="importing"]', { state: "detached", timeout: 60000 });
}

const { leftovers } = await app.closeWindow();
check(leftovers.length === 0, `no process left after closing: ${leftovers.join(", ") || "none"}`);
writeFileSync(join(shots, "style-shots.json"), JSON.stringify(report, null, 1));
process.exit(report.failures.length ? 1 : 0);
