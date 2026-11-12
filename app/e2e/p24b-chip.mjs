// Measures the toolbar of the English player once the batch queue has items, so its chip shows.
// node e2e/p24b-chip.mjs <projects-dir> <video> <shots-dir> <label> [port]
// Env: VST_USER_DATA (a folder whose queue.db has items), WEBVIEW2_USER_DATA_FOLDER, VST_APP_EXE (the build to measure).
import { writeFileSync } from "node:fs";
import { join } from "node:path";
import { launch, sleep } from "./lib.mjs";

const [projects, video, shots, label, portArg] = process.argv.slice(2);
if (!projects || !video || !shots || !label) throw new Error("usage: p24b-chip.mjs <projects> <video> <shots> <label> [port]");
const app = await launch({ projects, shots, port: Number(portArg ?? 9440), env: { VST_UPDATE_URL: "http://127.0.0.1:9/none.json" } });
const p = app.page;
const session = await p.context().newCDPSession(p);
const { windowId } = await session.send("Browser.getWindowForTarget");
const resize = async (width, height) => {
  await session.send("Browser.setWindowBounds", { windowId, bounds: { windowState: "normal", width, height } });
  await sleep(700);
};
const measure = () =>
  p.evaluate(() => {
    const h = document.querySelector("header");
    const mids = [...h.querySelectorAll("button, input, select")].map((e) => {
      const b = e.getBoundingClientRect();
      return Math.round(b.top + b.height / 2);
    });
    return {
      header: Number(h.getBoundingClientRect().height.toFixed(1)),
      spread: Math.max(...mids) - Math.min(...mids),
      box: Number(document.querySelector('[data-testid="video-path"]').getBoundingClientRect().width.toFixed(1)),
      chip: document.querySelector('[data-testid="queue-chip"]') !== null,
    };
  });
const out = { label, home: {}, player: {} };
for (const [w, h] of [[1280, 720], [960, 600]]) {
  await resize(w, h);
  await sleep(500);
  out.home[w] = await measure();
}
await resize(1280, 720);
await p.fill('[data-testid="video-path"]', video);
await p.click('[data-testid="import"]');
await p.waitForSelector('[data-testid="cue-list"] li', { timeout: 60000 });
await p.evaluate(() => document.querySelector("video")?.pause());
for (const [w, h] of [[1280, 720], [960, 600]]) {
  await resize(w, h);
  await sleep(500);
  out.player[w] = await measure();
  await p.screenshot({ path: join(shots, `chip-${label}-player-${w}.png`) });
}
console.log(JSON.stringify(out));
writeFileSync(join(shots, `chip-${label}.json`), JSON.stringify(out, null, 1));
await app.closeWindow();
