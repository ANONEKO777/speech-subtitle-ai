// Imports the clip through the real window and records the screencast and the progress screenshots.
// node docs/media/tools/record-import.mjs <projects-dir> <video> <out-dir>
import { writeFileSync } from "node:fs";
import { join } from "node:path";
import { fixWindow, lib, sleep, snap, startCast } from "./capture.mjs";

const [projects, video, out] = process.argv.slice(2);
if (!projects || !video || !out) throw new Error("usage: record-import.mjs <projects> <video> <out>");
const app = await lib.launch({ projects, shots: out, port: Number(process.env.VST_CDP_PORT ?? 9441) });
const p = app.page;
console.log("viewport", await fixWindow(p));
const shot = (name) => snap(p, join(out, name));
await p.mouse.move(640, 400);
await shot("empty.png");
const cast = await startCast(p, join(out, "cast-import"));
const t0 = Date.now();
const marks = {};
const mark = (name) => (marks[name] = (Date.now() - t0) / 1000);
await sleep(1500);
await p.click('[data-testid="video-path"]');
await p.keyboard.type(video, { delay: 28 });
await sleep(700);
mark("click");
await p.click('[data-testid="import"]');
await p.waitForSelector('[data-testid="importing"]', { timeout: 30000 });
const wanted = [12, 35, 60, 85];
const seen = [];
const started = Date.now();
while (!(await p.$('[data-testid="video"]'))) {
  const pct = await p.evaluate(() => document.querySelector('[data-testid="percent"]')?.textContent ?? "");
  const n = parseInt(pct, 10);
  const step = await p.evaluate(() => document.querySelector('[data-testid="step-name"]')?.textContent ?? "");
  const next = wanted.find((w) => !seen.includes(w) && n >= w);
  if (next !== undefined) {
    seen.push(next);
    await shot(`progress-${next}.png`);
    console.log("shot", next, step, pct);
  }
  if (Date.now() - started > 20 * 60 * 1000) throw new Error("import took too long");
  await sleep(400);
}
console.log("import seconds", (Date.now() - started) / 1000);
await p.waitForSelector('[data-testid="cue-list"] li');
mark("player");
await sleep(2500);
mark("end");
writeFileSync(join(out, "marks-import.json"), JSON.stringify(marks));
console.log(await cast.stop());
const { leftovers } = await app.closeWindow();
console.log("leftovers", leftovers);
