// P16 live check: library, queue, resume, speed, A-B loop, line jump, frame step, volume memory, PiP,
// fullscreen, offset, screenshots (plain and burned), help, drop, burn-in export.
// node e2e/player-lanes.mjs <projects-dir> <shots-dir> <out-dir>
// <projects-dir> holds two finished projects (the second may be a copy, see the verify skill). Run on a copy.
import { appendFileSync, existsSync, mkdirSync, readFileSync, readdirSync, rmSync, statSync } from "node:fs";
import { join } from "node:path";
import { launch, powershell, sleep, strayProcesses, userDataDir } from "./lib.mjs";

const [projects, shots, out] = process.argv.slice(2);
if (!projects || !shots || !out) throw new Error("usage: player-lanes.mjs <projects> <shots> <out-dir>");
process.env.VST_EXPORT_DIR = out;
const openedLog = join(out, "..", "opened-folders.log");
rmSync(openedLog, { force: true });
process.env.VST_OPEN_FOLDER_LOG = openedLog;

const dirs = readdirSync(projects);
const meta = (d) => JSON.parse(readFileSync(join(projects, d, "project.json"), "utf8"));
const results = [];
const note = (lane, ok, detail) => {
  results.push({ lane, ok, detail });
  console.log(`${ok ? "PASS" : "FAIL"} ${lane} ${detail}`);
};
const strays0 = strayProcesses();

const t = (p) => p.evaluate(() => document.querySelector("video").currentTime);
const rate = (p) => p.evaluate(() => document.querySelector("video").playbackRate);
const paused = (p) => p.evaluate(() => document.querySelector("video").paused);
const cueStarts = (p) => p.evaluate(() => [...document.querySelectorAll('[data-testid="cue-list"] > li')].map((li) => Number(li.dataset.start) / 1000));
const activeN = (p) => p.evaluate(() => {
  const li = document.querySelector('[data-testid="cue-list"] > li[data-active="true"]');
  return li ? Number(li.dataset.testid.slice(4)) : -1;
});
const click = async (sel) => {
  await p.mouse.move(380, 260);
  await p.mouse.move(400, 280);
  await p.click(sel);
};
const pngSize = (file) => {
  const b = readFileSync(file);
  return `${b.readUInt32BE(16)}x${b.readUInt32BE(20)}`;
};
const press = async (p, key) => {
  await p.locator("body").evaluate((b) => b.focus?.());
  await p.keyboard.press(key);
};
const osd = (p) => p.textContent('[data-testid="osd"]').catch(() => null);

async function openLibrary(app) {
  await app.page.click('[data-testid="home"]').catch(() => undefined);
  await app.page.waitForSelector('[data-testid="library-list"]');
}
async function playFrom(p, id) {
  await click(`[data-testid="lib-play-${id}"]`);
  await p.waitForSelector('[data-testid="cue-list"] li', { timeout: 30000 });
  await p.waitForFunction(() => document.querySelector("video")?.readyState >= 1);
}

const KEYS = ["vst.settings.v1", "vst.queue.v1", "vst.player.v1"];
let app = await launch({ projects, shots });
let p = app.page;
// the window keeps its local storage between runs, so start from a clean queue and restore the person's values at the end
const originals = await p.evaluate((keys) => Object.fromEntries(keys.map((k) => [k, localStorage.getItem(k)])), KEYS);
if (originals["vst.settings.v1"]) {
  const s = JSON.parse(originals["vst.settings.v1"]);
  for (const k of ["outputDir", "burnShots", "fsOverlay"]) delete s[k];
  originals["vst.settings.v1"] = JSON.stringify(s);
}
originals["vst.queue.v1"] = null;
originals["vst.player.v1"] = null;
await p.evaluate(() => {
  localStorage.removeItem("vst.queue.v1");
  localStorage.removeItem("vst.player.v1");
});
await p.reload();
await p.waitForSelector('[data-testid="library-list"]');
const items = await p.locator('[data-testid="library-list"] > li').count();
await p.waitForFunction(() => document.querySelectorAll('[data-testid="library-list"] img').length >= 1, null, { timeout: 30000 }).catch(() => undefined);
const thumbs = await p.locator('[data-testid="library-list"] img').count();
note("1 library", items === dirs.length && thumbs >= 1, `${items} items for ${dirs.length} projects, ${thumbs} thumbnails loaded`);
await app.shot("01-library.png");

// remember outputs in a chosen folder: the same two writes a folder pick makes (the shell records the folder, the page keeps the setting)
const userData = userDataDir();
mkdirSync(userData, { recursive: true });
const listFile = join(userData, "output-folders.txt");
const picked = existsSync(listFile) ? readFileSync(listFile, "utf8").split(/\r?\n/) : [];
if (!picked.includes(out)) appendFileSync(listFile, out + "\n");
await p.evaluate((dir) => {
  const key = "vst.settings.v1";
  const s = JSON.parse(localStorage.getItem(key) ?? "{}");
  localStorage.setItem(key, JSON.stringify({ ...s, outputDir: dir }));
}, out);
await p.reload();
await p.waitForSelector('[data-testid="library-list"]');

const first = dirs.find((d) => meta(d).video_path.includes("Agent"));
const second = dirs.find((d) => d !== first);
await playFrom(p, first);
await p.evaluate(() => document.querySelector("video").pause());

// 2 resume
await p.evaluate(() => (document.querySelector("video").currentTime = 600));
await sleep(500);
await click('[data-testid="ctl-play"]');
await sleep(3000);
await click('[data-testid="ctl-play"]');
await sleep(800);
const left = await t(p);
const saved = JSON.parse(readFileSync(join(projects, first, "playback.json"), "utf8"));
note("2 position saved", Math.abs(saved.position_s - left) < 1.5 && saved.duration_s > 3000, `video at ${left.toFixed(1)} s, playback.json position ${saved.position_s.toFixed(1)} s, duration ${saved.duration_s.toFixed(0)} s`);
await openLibrary(app);
await app.shot("02a-library-progress.png");
const bar = await p.locator(`[data-testid="lib-${first}"] .lib-progress span`).getAttribute("style");
await playFrom(p, first);
await p.waitForSelector('[data-testid="toast"]');
await sleep(400);
const resumed = await t(p);
note("2 resume", Math.abs(resumed - left) < 1.5 && (await p.textContent('[data-testid="toast-text"]')).includes("繼續"), `reopened at ${resumed.toFixed(1)} s (left at ${left.toFixed(1)}), toast "${await p.textContent('[data-testid="toast-text"]')}", library progress ${bar}`);
await app.shot("02b-resumed.png");

// 3 queue
await openLibrary(app);
await click(`[data-testid="lib-queue-${first}"]`);
await click(`[data-testid="lib-queue-${second}"]`);
await app.shot("03a-queue.png");
await playFrom(p, first);
const nextBefore = await p.isDisabled('[data-testid="ctl-next"]');
const src1 = await p.evaluate(() => document.querySelector("video").src);
await click('[data-testid="ctl-next"]');
await p.waitForFunction((s) => { const v = document.querySelector("video"); return !!v && v.src !== s; }, src1);
await p.waitForSelector('[data-testid="cue-list"] li');
const src2 = await p.evaluate(() => document.querySelector("video").src);
const prevEnabled = !(await p.isDisabled('[data-testid="ctl-prev"]'));
await press(p, "<");
await p.waitForFunction((s) => { const v = document.querySelector("video"); return !!v && v.src !== s; }, src2);
const src3 = await p.evaluate(() => document.querySelector("video").src);
await press(p, ">");
await p.waitForFunction((s) => { const v = document.querySelector("video"); return !!v && v.src !== s; }, src3);
const nextOff = await p.isDisabled('[data-testid="ctl-next"]');
note("3 queue", !nextBefore && prevEnabled && src1 !== src2 && src3 === src1 && nextOff, `next from video 1 loads video 2 (${src1 !== src2}), "<" goes back (${src3 === src1}), ">" returns, next disabled at the end (${nextOff})`);
await app.shot("03b-queue-step.png");
await click('[data-testid="home"]');
await p.waitForSelector('[data-testid="recent-list"]');
note("3 recent", (await p.locator('[data-testid="recent-list"] > li').count()) === 2, `recent list holds ${await p.locator('[data-testid="recent-list"] > li').count()} opened videos`);
await app.shot("03c-recent.png");
await playFrom(p, first);
await p.evaluate(() => document.querySelector("video").pause());
await p.evaluate(() => (document.querySelector("video").currentTime = 120));
await sleep(400);

// 4 speed
const speeds = [];
await press(p, "]");
speeds.push(await rate(p));
await press(p, "]");
speeds.push(await rate(p));
const osdText = await osd(p);
await app.shot("04a-speed-osd.png");
await press(p, "[");
await press(p, "[");
await press(p, "[");
speeds.push(await rate(p));
for (let i = 0; i < 4; i++) await press(p, "[");
speeds.push(await rate(p));
for (let i = 0; i < 9; i++) await press(p, "]");
speeds.push(await rate(p));
await click('[data-testid="ctl-speed"]');
await click('[data-testid="speed-1"]');
speeds.push(await rate(p));
note("4 speed", JSON.stringify(speeds) === JSON.stringify([1.25, 1.5, 0.75, 0.5, 2, 1]) && osdText?.includes("1.5"), `[ ] gave ${JSON.stringify(speeds)}, OSD "${osdText}"`);
await click('[data-testid="ctl-speed"]');
await app.shot("04b-speed-menu.png");
await click('[data-testid="speed-1.5"]');
note("4 speed menu", (await rate(p)) === 1.5, `menu set ${await rate(p)}`);
await click('[data-testid="ctl-speed"]');
await click('[data-testid="speed-1"]');

// 5 A-B loop
const starts = await cueStarts(p);
const a0 = starts[99] + 0.1;
await p.evaluate((a) => (document.querySelector("video").currentTime = a), a0);
await sleep(300);
await press(p, "a");
const sayA = await osd(p);
await p.evaluate((a) => (document.querySelector("video").currentTime = a + 4), a0);
await sleep(300);
await press(p, "a");
const sayB = await osd(p);
await p.evaluate((a) => (document.querySelector("video").currentTime = a), a0);
await p.evaluate(() => document.querySelector("video").play());
const loopSeen = [];
for (let i = 0; i < 30; i++) {
  await sleep(500);
  loopSeen.push(await t(p));
}
await p.mouse.move(380, 260);
await p.mouse.move(400, 280);
await app.shot("05-loop.png");
const inside = loopSeen.every((x) => x >= a0 - 0.3 && x <= a0 + 4.4);
const wrapped = loopSeen.some((x, i) => i > 0 && x < loopSeen[i - 1] - 1);
const marks = await p.locator('[data-testid="loop-a"], [data-testid="loop-b"]').count();
note("5 A-B loop", inside && wrapped && marks === 2, `15 s of play stayed within ${a0.toFixed(1)} to ${(a0 + 4).toFixed(1)} s (min ${Math.min(...loopSeen).toFixed(2)}, max ${Math.max(...loopSeen).toFixed(2)}), wrapped ${wrapped}, OSD "${sayA}" then "${sayB}"`);
await press(p, "a");
await p.evaluate(() => document.querySelector("video").play());
await sleep(5500);
const afterOff = await t(p);
note("5 loop off", afterOff > a0 + 4.2 && (await osd(p)) !== undefined, `third A press cleared it, video moved on to ${afterOff.toFixed(1)} s`);
await p.evaluate(() => document.querySelector("video").pause());

// 6 line jump
await p.evaluate(() => (document.querySelector("video").currentTime = 200));
await sleep(400);
const n0 = await activeN(p);
const here = await t(p);
await p.keyboard.press("Control+ArrowRight");
await sleep(500);
const afterNext = await t(p);
const nNext = await activeN(p);
await p.keyboard.press("Control+ArrowRight");
await sleep(500);
const n2 = await activeN(p);
await p.keyboard.press("Control+ArrowLeft");
await sleep(500);
const nBack = await activeN(p);
const nextStart = starts.find((s) => s > here + 0.001);
await app.shot("06-line-jump.png");
note("6 line jump", Math.abs(afterNext - nextStart) < 0.2 && n2 === nNext + 1 && nBack === nNext, `from ${here.toFixed(2)} s (cue ${n0}) Ctrl+Right to ${afterNext.toFixed(2)} s (next cue starts ${nextStart}), cue ${nNext}, again ${n2}, Ctrl+Left ${nBack}`);
await click('[data-testid="ctl-line-next"]');
await sleep(400);
note("6 line button", (await activeN(p)) === nBack + 1, `button went to cue ${await activeN(p)}`);

// 7 frame step
await p.evaluate(() => document.querySelector("video").play());
await sleep(500);
const f0 = await t(p);
await press(p, ".");
await sleep(300);
const f1 = await t(p);
await press(p, ".");
await sleep(300);
const f2 = await t(p);
await press(p, ",");
await sleep(300);
const f3 = await t(p);
note("7 frame step", (await paused(p)) && f1 > f0 - 0.5 && f2 - f1 > 0.01 && f2 - f1 < 0.1 && Math.abs(f3 - f1) < 0.01, `step forward ${(f2 - f1) * 1000 | 0} ms, back to ${f3.toFixed(3)} (was ${f1.toFixed(3)}), paused ${await paused(p)}`);

// 8 volume and mute
await press(p, "ArrowDown");
await press(p, "ArrowDown");
await press(p, "ArrowDown");
const vol = await p.evaluate(() => document.querySelector("video").volume);
await press(p, "m");
const muted = await p.evaluate(() => document.querySelector("video").muted);
await app.shot("08-volume.png");
await p.reload();
await p.waitForSelector('[data-testid="library-list"]');
await playFrom(p, first);
const vol2 = await p.evaluate(() => [document.querySelector("video").volume, document.querySelector("video").muted]);
note("8 volume memory", Math.abs(vol - 0.85) < 0.01 && muted && Math.abs(vol2[0] - vol) < 0.01 && vol2[1], `volume ${vol}, muted ${muted}, after reload ${JSON.stringify(vol2)}`);
await press(p, "m");
await press(p, "ArrowUp");
await press(p, "ArrowUp");
await press(p, "ArrowUp");
await p.evaluate(() => document.querySelector("video").pause());

// seek keys
await p.evaluate(() => (document.querySelector("video").currentTime = 300));
await sleep(300);
await press(p, "ArrowRight");
await sleep(200);
const s1 = await t(p);
await press(p, "l");
await sleep(200);
const s2 = await t(p);
await press(p, "j");
await sleep(200);
const s3 = await t(p);
await press(p, "ArrowLeft");
await sleep(200);
const s4 = await t(p);
await press(p, "5");
await sleep(400);
const s5 = await t(p);
const dur = await p.evaluate(() => document.querySelector("video").duration);
note("8 seek keys", Math.abs(s1 - 305) < 0.3 && Math.abs(s2 - 315) < 0.3 && Math.abs(s3 - 305) < 0.3 && Math.abs(s4 - 300) < 0.3 && Math.abs(s5 - dur * 0.5) < 1, `300 -> ${s1.toFixed(1)} -> ${s2.toFixed(1)} -> ${s3.toFixed(1)} -> ${s4.toFixed(1)}, 5 -> ${s5.toFixed(0)} of ${dur.toFixed(0)}`);
await press(p, " ");
await sleep(500);
const playing = !(await paused(p));
await press(p, "k");
await sleep(300);
note("8 space and k", playing && (await paused(p)), `Space played (${playing}), K paused (${await paused(p)})`);

// 9 picture in picture
await click('[data-testid="ctl-pip"]');
await sleep(1200);
const pip = await p.evaluate(() => !!document.pictureInPictureElement);
await app.shot("09-pip.png");
if (pip) await p.evaluate(() => document.exitPictureInPicture());
await sleep(500);
note("9 picture in picture", pip, `pictureInPictureElement set after the button: ${pip}`);

// 10 fullscreen, subtitle below and overlaid
await p.evaluate(() => (document.querySelector("video").currentTime = 220));
await sleep(500);
await press(p, "f");
await sleep(1200);
const fsBelow = await p.evaluate(() => {
  const v = document.querySelector("video").getBoundingClientRect();
  const s = document.querySelector('[data-testid="subtitle"]').getBoundingClientRect();
  return { fs: !!document.fullscreenElement, vBottom: v.bottom, sTop: s.top, w: innerWidth, h: innerHeight };
});
await app.shot("10a-fullscreen-below.png");
await press(p, "f");
await sleep(800);
await click('[data-testid="ctl-more"]');
await click('[data-testid="opt-overlay"]');
await click('[data-testid="ctl-more"]').catch(() => undefined);
await press(p, "f");
await sleep(1200);
const fsOver = await p.evaluate(() => {
  const v = document.querySelector("video").getBoundingClientRect();
  const s = document.querySelector('[data-testid="subtitle"]').getBoundingClientRect();
  return { fs: !!document.fullscreenElement, vBottom: v.bottom, sTop: s.top, sBottom: s.bottom, h: innerHeight };
});
await app.shot("10b-fullscreen-overlay.png");
await press(p, "f");
await sleep(800);
note("10 fullscreen", fsBelow.fs && fsBelow.sTop >= fsBelow.vBottom - 1 && fsOver.fs && fsOver.sBottom <= fsOver.vBottom + 1 && fsOver.sTop < fsOver.vBottom, `below: video ends ${fsBelow.vBottom} subtitle starts ${fsBelow.sTop} (screen ${fsBelow.w}x${fsBelow.h}); overlay: subtitle ${fsOver.sTop.toFixed(0)}-${fsOver.sBottom.toFixed(0)} inside video ending ${fsOver.vBottom}`);
await click('[data-testid="ctl-more"]');
await click('[data-testid="opt-overlay"]');
await click('[data-testid="ctl-more"]').catch(() => undefined);

// 11 offset
const cs = await cueStarts(p);
const probe = cs[149] + 0.3;
await p.evaluate((x) => (document.querySelector("video").currentTime = x), probe);
await sleep(500);
const n150 = await activeN(p);
await click('[data-testid="ctl-offset"]');
for (let i = 0; i < 20; i++) await click('[data-testid="offset-plus"]');
await app.shot("11a-offset-pop.png");
const off = await p.textContent('[data-testid="offset-value"]');
await sleep(600);
const nShift = await activeN(p);
const diskOff = JSON.parse(readFileSync(join(projects, first, "playback.json"), "utf8")).offset_ms;
await p.keyboard.press("Escape");
await p.mouse.click(5, 300);
await press(p, "z");
const offZ = await p.textContent('[data-testid="offset-value"]');
note("11 offset", off.includes("+2.0") && nShift < n150 && diskOff === 2000 && offZ.includes("1.9"), `offset ${off}, cue at ${probe.toFixed(1)} s went from ${n150} to ${nShift}, playback.json offset_ms ${diskOff}, Z gives ${offZ}`);
await press(p, "x");
await sleep(700);
await click('[data-testid="export-menu"]');
await click('[data-testid="export-ass"]');
await sleep(800);
const ass = readFileSync(join(out, readdirSync(out).filter((f) => f.endsWith(".ass")).at(-1)), "utf8");
const firstDialogue = /Dialogue: 0,(\d+:\d+:\d+\.\d+)/.exec(ass)?.[1];
const baseAss = readFileSync(join(projects, first, "bilingual.ass"), "utf8");
const baseFirst = /Dialogue: 0,(\d+:\d+:\d+\.\d+)/.exec(baseAss)?.[1];
const secs = (s) => s.split(":").reduce((a, x) => a * 60 + Number(x), 0);
note("11 offset on export", Math.abs(secs(firstDialogue) - secs(baseFirst) - 2) < 0.05, `first cue starts ${baseFirst} without offset and ${firstDialogue} in the exported ASS (offset +2.0 s)`);
await app.shot("11b-offset-export.png");
await click('[data-testid="ctl-offset"]');
await click('[data-testid="offset-reset"]');
await sleep(700);
await p.mouse.click(5, 300);

// 12 screenshots. The clipboard write and the Explorer call are stubbed (the page and the shell seam), so the machine's clipboard and desktop stay untouched.
await p.evaluate(() => {
  window.__clip = "none";
  Object.defineProperty(navigator, "clipboard", {
    configurable: true,
    value: {
      write: async (items) => {
        const png = await items[0].getType("image/png");
        const bitmap = await createImageBitmap(png);
        window.__clip = `${bitmap.width}x${bitmap.height}`;
      },
    },
  });
});
const before = new Set(readdirSync(out));
await p.evaluate(() => (document.querySelector("video").currentTime = 305));
await sleep(500);
const shotAt = await t(p);
await press(p, "s");
await p.waitForSelector('[data-testid="toast-action"]');
const toast1 = await p.textContent('[data-testid="toast-text"]');
await app.shot("12a-screenshot-toast.png");
await press(p, "Shift+s");
await sleep(2500);
await p.waitForFunction(() => document.querySelector('[data-testid="toast-text"]')?.textContent?.includes("_sub"), null, { timeout: 15000 });
const toast2 = await p.textContent('[data-testid="toast-text"]');
const pngs = readdirSync(out).filter((f) => f.endsWith(".png") && !before.has(f));
const plain = pngs.find((f) => !f.includes("_sub"));
const burned = pngs.find((f) => f.includes("_sub"));
await app.shot("12b-screenshot-burn-toast.png");
console.log(JSON.stringify({ plain: join(out, plain ?? ""), burned: join(out, burned ?? ""), shotAt }));

// open folder from the toast: the shell records the resolved path in VST_OPEN_FOLDER_LOG instead of starting Explorer
await click('[data-testid="toast-action"]');
await sleep(1000);
const opened = existsSync(openedLog) ? readFileSync(openedLog, "utf8").trim().split(/\r?\n/) : [];
note("12 open folder", opened.length === 1 && opened[0].toLowerCase() === join(out, burned ?? "").toLowerCase(), `toast button asked the shell to show ${opened.at(-1)}`);
const clip = await p.evaluate(() => window.__clip);
note("12 screenshot files", !!plain && !!burned && toast1.includes("剪貼簿") && clip === pngSize(join(out, burned)), `S saved ${plain}, Shift+S saved ${burned} at video time ${shotAt.toFixed(2)} s, toast "${toast1.slice(0, 40)}...", clipboard image ${clip}`);

// 13 help
await press(p, "?");
await sleep(300);
const helpRows = await p.locator('[data-testid="help"] .key-row').count();
await app.shot("13-help.png");
await press(p, "Escape");
await sleep(300);
note("13 help", helpRows >= 15 && (await p.locator('[data-testid="help"]').count()) === 0, `? shows ${helpRows} rows, Esc closes it`);

// 14 drop
await p.evaluate(() => window.__TAURI_INTERNALS__.invoke("plugin:event|emit", { event: "tauri://drag-enter", payload: { paths: [], position: { x: 10, y: 10 } } }));
await sleep(300);
const hint = await p.locator('[data-testid="drop-hint"]').count();
await app.shot("14a-drop-hint.png");
const src0 = await p.evaluate(() => document.querySelector("video").src);
await click('[data-testid="home"]');
await p.waitForSelector('[data-testid="library-list"]');
await p.evaluate((path) => window.__TAURI_INTERNALS__.invoke("plugin:event|emit", { event: "tauri://drag-drop", payload: { paths: [path], position: { x: 10, y: 10 } } }), meta(second).video_path);
await p.waitForSelector('[data-testid="cue-list"] li', { timeout: 30000 });
const src4 = await p.evaluate(() => document.querySelector("video").src);
note("14 drop", hint === 1 && src4 !== src0 && src4.includes(encodeURIComponent("上個月").slice(0, 6)), `drag-enter shows the hint (${hint}), a drop event with the second video's path opened it (${src4.slice(-60)})`);
await app.shot("14b-dropped.png");

// 15 burn-in export: full video, cancelled; then a 30 s clip of the first (real) project
await click('[data-testid="home"]');
await playFrom(p, first);
await p.evaluate(() => document.querySelector("video").pause());
await click('[data-testid="export-menu"]');
await click('[data-testid="export-burn-full"]');
await p.waitForSelector('[data-testid="burn-progress"]');
await p.waitForFunction(() => Number(document.querySelector('[data-testid="burn-percent"]')?.textContent?.replace("%", "")) >= 1, null, { timeout: 60000 });
await app.shot("15a-burn-progress.png");
const pct = await p.textContent('[data-testid="burn-percent"]');
const ffRunning = powershell(`(Get-Process ffmpeg -ErrorAction SilentlyContinue | Measure-Object).Count`);
await click('[data-testid="burn-cancel"]');
await p.waitForFunction(() => !document.querySelector('[data-testid="burn-progress"]'), null, { timeout: 15000 });
await sleep(1500);
const ffAfter = powershell(`(Get-Process ffmpeg -ErrorAction SilentlyContinue | Measure-Object).Count`);
const partials = readdirSync(out).filter((f) => f.includes("burned") || f.includes("part"));
note("15 burn cancel", Number(ffRunning) >= 1 && Number(ffAfter) === 0 && partials.length === 0, `progress ${pct}, ffmpeg processes ${ffRunning} while running and ${ffAfter} after cancel, output files left ${JSON.stringify(partials)}`);
await app.shot("15b-burn-cancelled.png");
await p.evaluate(() => (document.querySelector("video").currentTime = 305));
await sleep(500);
await click('[data-testid="export-menu"]');
await click('[data-testid="export-burn-clip"]');
await p.waitForSelector('[data-testid="burn-progress"]');
await p.waitForFunction(() => !document.querySelector('[data-testid="burn-progress"]'), null, { timeout: 300000 });
const clipFiles = readdirSync(out).filter((f) => f.endsWith(".mp4"));
await p.waitForSelector('[data-testid="toast-text"]');
const doneToast = await p.textContent('[data-testid="toast-text"]');
await app.shot("15c-burn-done.png");
note("15 burn clip", clipFiles.length === 1 && doneToast.includes("burned"), `clip ${clipFiles[0]} ${(statSync(join(out, clipFiles[0] ?? "")).size / 1e6).toFixed(1)} MB, toast "${doneToast.slice(0, 60)}..."`);
console.log(JSON.stringify({ clip: join(out, clipFiles[0] ?? "") }));

await p.evaluate((saved) => {
  for (const [k, v] of Object.entries(saved)) v === null ? localStorage.removeItem(k) : localStorage.setItem(k, v);
}, originals);
const info = await app.closeWindow();
note("shutdown", info.leftovers.length === 0 && strayProcesses(strays0).length === 0, `family ${JSON.stringify(info.family)} leftovers ${JSON.stringify(info.leftovers)} stray ${JSON.stringify(strayProcesses(strays0))}`);

const failed = results.filter((r) => !r.ok);
console.log(`\n${results.length - failed.length}/${results.length} PASS`);
process.exit(failed.length ? 1 : 0);
