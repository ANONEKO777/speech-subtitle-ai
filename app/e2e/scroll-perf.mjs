// Frame times while the cue list scrolls: node e2e/scroll-perf.mjs <projects-dir> <shots-dir>
// Set VST_APP_EXE to measure another build. Run on a copy of a finished project.
import { readFileSync, readdirSync } from "node:fs";
import { join } from "node:path";
import { launch } from "./lib.mjs";

const [projects, shots] = process.argv.slice(2);
const project = JSON.parse(readFileSync(join(projects, readdirSync(projects)[0], "project.json"), "utf8"));
const app = await launch({ projects, shots });
const p = app.page;
await p.fill('[data-testid="video-path"]', project.video_path);
await p.click('[data-testid="import"]');
await p.waitForSelector('[data-testid="cue-list"] li', { timeout: 60000 });
await p.evaluate(() => document.querySelector("video").pause());
const result = await p.evaluate(async () => {
  const list = document.querySelector('[data-testid="cue-list"]');
  const rows = list.children.length;
  const runs = [];
  for (let run = 0; run < 3; run++) {
    list.scrollTop = 0;
    const dts = [];
    let last = performance.now();
    const start = last;
    await new Promise((done) => {
      const step = (now) => {
        dts.push(now - last);
        last = now;
        list.scrollTop = (list.scrollTop + 90) % (list.scrollHeight - list.clientHeight);
        if (now - start < 5000) requestAnimationFrame(step);
        else done();
      };
      requestAnimationFrame(step);
    });
    dts.sort((a, b) => a - b);
    runs.push({ frames: dts.length, median: dts[Math.floor(dts.length / 2)], p99: dts[Math.floor(dts.length * 0.99)], max: dts.at(-1) });
  }
  return { rows, runs };
});
console.log(JSON.stringify(result));
const info = await app.closeWindow();
console.log(JSON.stringify({ leftovers: info.leftovers }));
