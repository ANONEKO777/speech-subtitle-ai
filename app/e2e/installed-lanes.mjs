// Drives an installed layout (the app folder an installer unpacks) on a bare environment: no Python,
// no ffmpeg and no CUDA on PATH, no CUDA_PATH. The bundled backend and ffmpeg must do the work.
//   [LANE_DEV=1 LANE_PYTHON=<venv python> LANE_FFMPEG_DIR=<dir>] node e2e/installed-lanes.mjs process <app.exe> <user-data> <projects> <video> <shots> <name>
//   node e2e/installed-lanes.mjs licenses <app.exe> <user-data> <projects> <shots>
//   node e2e/installed-lanes.mjs cold <installed.exe> <dev.exe> <user-data> <projects> <shots>
// The app runs on its own DevTools port and WebView2 profile (never the default ones).
import { mkdirSync } from "node:fs";
import { join } from "node:path";
import { launch, sleep } from "./lib.mjs";

const PORT = Number(process.env.VST_CDP_PORT ?? 9431);
const BARE_PATH = `${process.env.SystemRoot}\\System32;${process.env.SystemRoot}`;

const start = (exe, { userData, projects, shots, dev = false }) =>
  launch({
    exe,
    projects,
    port: PORT,
    shots,
    env: {
      PATH: BARE_PATH,
      CUDA_PATH: undefined,
      VST_FFMPEG_DIR: dev ? process.env.LANE_FFMPEG_DIR : undefined,
      VST_BACKEND_PYTHON: dev ? process.env.LANE_PYTHON : undefined,
      VST_USER_DATA: userData,
      WEBVIEW2_USER_DATA_FOLDER: join(userData, "..", "webview-profile"),
    },
  });

const [mode, ...args] = process.argv.slice(2);

if (mode === "process") {
  const [exe, userData, projects, video, shots, name] = args;
  mkdirSync(shots, { recursive: true });
  const app = await start(exe, { userData, projects, shots, dev: process.env.LANE_DEV === "1" });
  console.log(`cold start ${app.coldStartMs} ms; exe ${exe}`);
  const p = app.page;
  await p.fill('[data-testid="video-path"]', video);
  await p.click('[data-testid="import"]');
  await p.waitForSelector('[data-testid="video"]', { timeout: 20 * 60 * 1000 });
  await p.waitForSelector('[data-testid="cue-list"] li');
  await p.click('[data-testid="cue-3"] button');
  await sleep(800);
  await p.evaluate(() => document.querySelector("video").pause());
  const box = await p.evaluate(() => ({
    video: document.querySelector('[data-testid="video"]').getBoundingClientRect().toJSON(),
    subtitle: document.querySelector('[data-testid="subtitle"]').getBoundingClientRect().toJSON(),
    text: document.querySelector('[data-testid="subtitle"]').innerText,
    cues: document.querySelectorAll('[data-testid="cue-list"] li').length,
  }));
  const file = await app.shot(name);
  const below = box.subtitle.top >= box.video.bottom - 0.5;
  console.log(`${below ? "PASS" : "FAIL"} subtitle below video; ${box.cues} cues; text ${JSON.stringify(box.text)}; ${file}`);
  const { family, leftovers } = await app.closeWindow();
  console.log(`${leftovers.length ? "FAIL" : "PASS"} nothing left after close. Below the app: ${family.join(", ")}`);
  process.exit(below && leftovers.length === 0 ? 0 : 1);
}

if (mode === "cold") {
  const [installed, dev, userData, projects, shots] = args;
  const times = { installed: [], dev: [] };
  for (let i = 0; i < 5; i++) {
    for (const [label, exe] of [["dev", dev], ["installed", installed]]) {
      const app = await start(exe, { userData, projects, shots, dev: label === "dev" });
      times[label].push(app.coldStartMs);
      console.log(`${label} run ${i + 1}: ${app.coldStartMs} ms (backend ready in page ${app.readyMarkMs} ms)`);
      await app.closeWindow();
      await sleep(500);
    }
  }
  const median = (xs) => [...xs].sort((a, b) => a - b)[Math.floor(xs.length / 2)];
  const d = median(times.dev);
  const n = median(times.installed);
  console.log(`median dev ${d} ms, installed ${n} ms, difference ${n - d} ms, rule: installed at most 1000 ms slower`);
  process.exit(n - d <= 1000 ? 0 : 1);
}

if (mode === "licenses") {
  const [exe, userData, projects, shots] = args;
  const app = await start(exe, { userData, projects, shots });
  const p = app.page;
  await p.click('[data-testid="settings-open"]');
  await p.click('[data-testid="section-licenses"]');
  await p.waitForSelector('[data-testid="licenses-table"]');
  const text = await p.innerText('[data-testid="bundled-notice"]');
  const file = await app.shot("third-party.png");
  const refuse = (url) =>
    p.evaluate((u) => window.__TAURI_INTERNALS__.invoke("open_url", { url: u }).then(() => "opened", (e) => `refused: ${e}`), url);
  const results = {};
  for (const url of ["https://example.com/", "http://github.com/x", "https://github.com@evil.example/", "file:///C:/Windows/System32/calc.exe"]) {
    results[url] = await refuse(url);
  }
  console.log(text);
  console.log(JSON.stringify(results, null, 1));
  console.log(file);
  const { leftovers } = await app.closeWindow();
  process.exit(leftovers.length === 0 ? 0 : 1);
}
