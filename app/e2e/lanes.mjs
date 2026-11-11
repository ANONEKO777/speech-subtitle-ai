// Lanes 1-9 of the P09 live check. Needs `npx tauri build --no-bundle` first.
// node e2e/lanes.mjs <projects-dir> <video.mp4> <shots-dir> [<video.mkv>]
import { appendFileSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import { launch, sleep } from "./lib.mjs";

const [projects, video, shots, mkv] = process.argv.slice(2);
if (!projects || !video || !shots) throw new Error("usage: lanes.mjs <projects> <video> <shots> [mkv]");
const results = [];
const note = (lane, ok, detail) => {
  results.push({ lane, ok, detail });
  console.log(`${ok ? "PASS" : "FAIL"} ${lane} ${detail}`);
};
const num = (v) => Number(v);

async function importVideo(app, path, shotName) {
  const p = app.page;
  await p.fill('[data-testid="video-path"]', path);
  await p.click('[data-testid="import"]');
  const samples = [];
  let shotTaken = false;
  const t0 = Date.now();
  let sawImporting = false;
  for (;;) {
    if ((await p.locator('[data-testid="video"]').count()) && (sawImporting || Date.now() - t0 > 3000)) break;
    if (await p.locator('[data-testid="error"]').count()) {
      throw new Error(await p.textContent('[data-testid="error"]'));
    }
    if (await p.locator('[data-testid="importing"]').count()) {
      sawImporting = true;
      const step = await p.textContent('[data-testid="step-name"]');
      const percent = num((await p.textContent('[data-testid="percent"]')).replace("%", ""));
      if (samples.at(-1)?.step !== step || samples.at(-1)?.percent !== percent) {
        samples.push({ t: Math.round((Date.now() - t0) / 1000), step, percent });
      }
      if (!shotTaken && percent >= 50 && shotName) {
        await app.shot(shotName);
        shotTaken = true;
      }
    }
    await sleep(500);
  }
  return samples;
}

const playerBox = (page) =>
  page.evaluate(() => {
    const r = (sel) => document.querySelector(sel).getBoundingClientRect().toJSON();
    return { video: r('[data-testid="video"]'), subtitle: r('[data-testid="subtitle"]'), list: r('[data-testid="cue-list"]'), vw: innerWidth, vh: innerHeight };
  });

async function subtitleLangs(page) {
  return page.$$eval('[data-testid="subtitle"] p', (ps) => ps.map((p) => p.dataset.lang));
}

async function seekToCue(page, n) {
  const start = num(await page.getAttribute(`[data-testid="cue-${n}"]`, "data-start")) / 1000;
  await page.click(`[data-testid="cue-${n}"] button`);
  await page.waitForFunction((t) => Math.abs(document.querySelector("video").currentTime - t) < 0.5, start);
  return start;
}

// ---- run A
let app = await launch({ projects, shots });
console.log("cold start ms", app.coldStartMs, "page", app.pageStartMs, "ready", app.readyMarkMs);
let p = app.page;
const samples = await importVideo(app, video, "progress.png");
if (samples.length) writeFileSync(join(shots, "progress-samples.json"), JSON.stringify(samples, null, 1));
const steps = [...new Set(samples.map((s) => s.step))];
const monotonic = samples.every((s, i) => i === 0 || s.percent >= samples[i - 1].percent);
if (samples.length === 0) console.log("SKIP 5 progress: the project was cached, see the first run");
else note("5 progress", samples.length > 5 && monotonic && steps.length >= 4, `${samples.length} samples, steps: ${steps.join(" | ")}, monotonic=${monotonic}`);

await p.waitForSelector('[data-testid="cue-list"] li');
await seekToCue(p, 3);
await sleep(600);
await p.evaluate(() => document.querySelector("video").pause());
await app.shot("import-to-play.png");
const box = await playerBox(p);
note("1 below", box.subtitle.top >= box.video.bottom - 0.5 && box.video.height > 200, `video bottom ${box.video.bottom}, subtitle top ${box.subtitle.top}`);

for (const [mode, expected] of [["en", ["src"]], ["zh", ["zh"]], ["both", ["zh", "src"]]]) {
  await p.click(`[data-testid="mode-${mode}"]`);
  await sleep(300);
  const got = await subtitleLangs(p);
  await app.shot(`modes-${mode}.png`);
  note(`2 mode ${mode}`, JSON.stringify(got) === JSON.stringify(expected), `subtitle shows ${got.join("+")}`);
}
await p.click('[data-testid="mode-both"]');
await app.shot("modes.png");

const total = await p.locator('[data-testid="cue-list"] li').count();
const jumpTo = Math.min(200, total);
const start = num(await p.getAttribute(`[data-testid="cue-${jumpTo}"]`, "data-start")) / 1000;
await p.click(`[data-testid="cue-${jumpTo}"] button`);
await sleep(500);
const at = await p.evaluate(() => document.querySelector("video").currentTime);
await p.evaluate(() => document.querySelector("video").pause());
await app.shot("jump.png");
note("3 jump", Math.abs(at - start) < 0.1 + 0.5 && at >= start - 0.1, `cue ${jumpTo} starts ${start}, video at ${at.toFixed(3)} (0.5 s settle after the click)`);

// the clock reading right at the click, with the video paused
await p.evaluate(() => document.querySelector("video").pause());
await p.click(`[data-testid="cue-${jumpTo + 1}"] button`);
await sleep(100);
const exact = await p.evaluate(() => document.querySelector("video").currentTime);
const exactStart = num(await p.getAttribute(`[data-testid="cue-${jumpTo + 1}"]`, "data-start")) / 1000;
note("3 jump paused", Math.abs(exact - exactStart) < 0.1, `cue ${jumpTo + 1} starts ${exactStart}, video at ${exact.toFixed(3)}`);

// lane 4 and the latency probe: play 60 s from cue jumpTo
await p.click(`[data-testid="cue-${jumpTo}"] button`);
await p.evaluate(() => {
  window.__changes = [];
  const sub = document.querySelector('[data-testid="subtitle"]');
  const v = document.querySelector("video");
  let changed = false;
  new MutationObserver(() => {
    changed = true;
  }).observe(sub, { childList: true, subtree: true, characterData: true });
  const track = (now, frame) => {
    if (changed) window.__changes.push({ now, t: frame.mediaTime });
    changed = false;
    v.requestVideoFrameCallback(track);
  };
  v.requestVideoFrameCallback(track);
  v.muted = true;
  return v.play();
});
let outOfView = 0;
const scrolls = [];
for (let i = 0; i < 60; i++) {
  await sleep(1000);
  const s = await p.evaluate(() => {
    const list = document.querySelector('[data-testid="cue-list"]').getBoundingClientRect();
    const a = document.querySelector('[data-active="true"]');
    if (!a) return { found: false };
    const r = a.getBoundingClientRect();
    return { found: true, inView: r.top >= list.top - 1 && r.bottom <= list.bottom + 1 };
  });
  scrolls.push(s);
  if (s.found && !s.inView) outOfView++;
  if (i === 30) await app.shot("autoscroll.png");
}
const played = await p.evaluate(() => document.querySelector("video").currentTime);
note("4 autoscroll", outOfView === 0 && scrolls.filter((s) => s.found).length >= 40, `60 samples, ${outOfView} out of view, ${scrolls.filter((s) => s.found).length} with an active cue, video at ${played.toFixed(1)} s`);

await sleep(75000);
const latency = await p.evaluate(async () => {
  const cues = [...document.querySelectorAll('[data-testid^="cue-"]')].map((li) => Number(li.dataset.start) / 1000);
  const out = [];
  for (const c of window.__changes) {
    const start = cues.filter((s) => s <= c.t + 0.001).at(-1);
    if (start !== undefined && c.t - start < 1) out.push((c.t - start) * 1000);
  }
  return out;
});
latency.sort((a, b) => a - b);
const take = latency.slice(0, 20);
const worst = Math.max(...take);
note("perf subtitle latency", take.length >= 15 && worst < 100, `${take.length} cue changes, median ${take[Math.floor(take.length / 2)]?.toFixed(0)} ms, max ${worst.toFixed(0)} ms (timestamp of the video frame shown at the DOM update, minus cue start)`);
await p.evaluate(() => document.querySelector("video").pause());

await p.fill('[data-testid="font-size"]', "40");
await p.fill('[data-testid="font-color"]', "#ffd54a");
await p.click('[data-testid="mode-zh"]');
await app.shot("style-before-restart.png");
const before = await p.evaluate(() => {
  const s = getComputedStyle(document.querySelector('[data-testid="subtitle"]'));
  return { size: s.fontSize, color: s.color };
});
const { family, leftovers: stray } = await app.closeWindow();
writeFileSync(join(shots, "shutdown.txt"), `window closed. below the app before closing: ${family.join(", ")}\nstill alive 1.5 s after the app exited: ${stray.length ? stray.join(", ") : "none"}\n`);
note("6 shutdown", stray.length === 0, stray.length ? stray.join(", ") : "none left");

// ---- run B
app = await launch({ projects, shots });
p = app.page;
console.log("second cold start ms", app.coldStartMs);
await importVideo(app, video, null);
await sleep(500);
const after = await p.evaluate(() => {
  const s = getComputedStyle(document.querySelector('[data-testid="subtitle"]'));
  return { size: s.fontSize, color: s.color, mode: document.querySelector('[data-testid="mode-zh"]').getAttribute("aria-pressed") };
});
await app.shot("style-persist.png");
note("8 style persist", before.size === after.size && before.color === after.color, `before ${before.size} ${before.color}, after restart ${after.size} ${after.color}, zh mode pressed=${after.mode}`);

const session = await p.context().newCDPSession(p);
const { windowId } = await session.send("Browser.getWindowForTarget");
await session.send("Browser.setWindowBounds", { windowId, bounds: { windowState: "normal", width: 1280, height: 720 } });
await sleep(800);
await p.click('[data-testid="mode-both"]');
await p.click("[data-testid=cue-3] button");
await sleep(500);
const small = await playerBox(p);
await app.shot("small-window.png");
const fits = (r) => r.top >= 0 && r.left >= 0 && r.bottom <= small.vh + 0.5 && r.right <= small.vw + 0.5 && r.height > 0;
note("9 1280x720", fits(small.video) && fits(small.subtitle) && small.video.height >= 250, `outer 1280x720 gives viewport ${small.vw}x${small.vh}; video ${Math.round(small.video.width)}x${Math.round(small.video.height)} bottom ${Math.round(small.video.bottom)}; subtitle ${Math.round(small.subtitle.top)}-${Math.round(small.subtitle.bottom)}`);

if (mkv) {
  const mk = await importVideo(app, mkv, null);
  await sleep(2500);
  const verdict = await p.evaluate(() => {
    const v = document.querySelector("video");
    return { err: v.error?.code ?? null, ready: v.readyState, w: v.videoWidth, warn: !!document.querySelector('[data-testid="unplayable"]') };
  });
  await app.shot("mkv.png");
  note("7 mkv", verdict.warn || verdict.ready >= 2, `import steps ${mk.length}; video error=${verdict.err}, readyState=${verdict.ready}, width=${verdict.w}, proxy notice shown=${verdict.warn}`);
}

const { family: family2, leftovers: stray2 } = await app.closeWindow();
note("6b shutdown 2", stray2.length === 0, stray2.length ? stray2.join(", ") : "none left");
writeFileSync(join(shots, "lanes.json"), JSON.stringify(results, null, 1));
appendFileSync(join(shots, "shutdown.txt"), `second launch: below the app ${family2.join(", ")}; still alive: ${stray2.length ? stray2.join(", ") : "none"}\n`);
process.exit(results.every((r) => r.ok) ? 0 : 1);
