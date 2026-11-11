// Records the batch queue: drop five clips, set a language for each, run them, and take the screenshots.
// The clips are cuts of the NASA clip. VST_USER_DATA must hold the models and the GPU must be free.
// node docs/media/tools/record-queue.mjs <projects-dir> <clips-dir> <out-dir>
import { readdirSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import { fixWindow, lib, sleep, snap, startCast } from "./capture.mjs";

const [projects, clips, out] = process.argv.slice(2);
if (!projects || !clips || !out) throw new Error("usage: record-queue.mjs <projects> <clips> <out>");
const LANGS = ["zh-TW", "ja", "zh-TW", "es", "zh-CN"];
const app = await lib.launch({ projects, shots: out, port: Number(process.env.VST_CDP_PORT ?? 9444) });
const p = app.page;
console.log("viewport", await fixWindow(p));
const tid = (id) => `[data-testid="${id}"]`;
const shot = (name) => snap(p, join(out, name));
const rows = () =>
  p.evaluate(() =>
    [...document.querySelectorAll("li.batch-row")].map((li) => ({
      state: li.dataset.state,
      name: li.querySelector(".batch-name b")?.textContent ?? "",
      percent: parseInt(li.querySelector(".percent")?.textContent ?? "0", 10) || 0,
    })),
  );
const until = async (label, fn, ms) => {
  const end = Date.now() + ms;
  for (;;) {
    const v = await fn();
    if (v) return v;
    if (Date.now() > end) throw new Error(`timeout: ${label}`);
    await sleep(400);
  }
};
const files = readdirSync(clips).filter((f) => f.endsWith(".mp4")).sort().map((f) => join(clips, f));
await p.mouse.move(640, 700);
await p.waitForSelector(tid("batch-panel"));
const cast = await startCast(p, join(out, "cast-queue"));
const t0 = Date.now();
const marks = {};
const mark = (name) => (marks[name] = (Date.now() - t0) / 1000);
mark("start");
await sleep(1500);
const emit = (event, payload) => p.evaluate(([e, pl]) => window.__TAURI_INTERNALS__.invoke("plugin:event|emit", { event: e, payload: pl }), [event, payload]);
await emit("tauri://drag-enter", { paths: [], position: { x: 10, y: 10 } });
await emit("tauri://drag-drop", { paths: files, position: { x: 10, y: 10 } });
await p.waitForSelector(tid("add-dialog"));
await sleep(1200);
for (let i = 0; i < files.length; i++) {
  await p.locator(tid("add-row-lang")).nth(i).selectOption(LANGS[i]);
  await sleep(350);
}
await p.mouse.move(640, 700);
await sleep(900);
await shot("queue-add.png");
mark("add");
await p.click(tid("add-submit"));
await p.waitForSelector(tid("add-dialog"), { state: "detached" });
await p.evaluate(() => document.querySelector('[data-testid="batch-panel"]')?.scrollIntoView({ block: "start" }));
await p.mouse.move(640, 710);
const snapped = await until("second item half way", async () => {
  const r = await rows();
  return r.length === 5 && r[0].state === "done" && r[1].state === "running" && r[1].percent >= 45 ? r : null;
}, 15 * 60 * 1000);
await shot("queue-running.png");
console.log("running shot", JSON.stringify(snapped));
mark("running");
await until("all done", async () => (await rows()).every((r) => r.state === "done"), 15 * 60 * 1000);
await sleep(1500);
await shot("queue-done.png");
mark("done");
await sleep(1500);
mark("end");
writeFileSync(join(out, "marks-queue.json"), JSON.stringify(marks));
console.log(await cast.stop());
const { leftovers } = await app.closeWindow();
console.log("leftovers", leftovers);
