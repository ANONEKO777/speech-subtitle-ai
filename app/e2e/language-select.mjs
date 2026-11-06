// P10 live check: a project with two languages shows a selector, the mode switch names the language
// shown, and an edit or export goes to that language. node e2e/language-select.mjs <projects-dir> <shots-dir> <export-dir>
import { readFileSync, readdirSync } from "node:fs";
import { join } from "node:path";
import { launch, sleep } from "./lib.mjs";

const [projects, shots, exportDir] = process.argv.slice(2);
if (!projects || !shots || !exportDir) throw new Error("usage: language-select.mjs <projects> <shots> <export-dir>");
process.env.VST_EXPORT_DIR = exportDir;
const folder = join(projects, readdirSync(projects)[0]);
const project = JSON.parse(readFileSync(join(folder, "project.json"), "utf8"));
const results = [];
const note = (lane, ok, detail) => {
  results.push({ lane, ok, detail });
  console.log(`${ok ? "PASS" : "FAIL"} ${lane} ${detail}`);
};

const app = await launch({ projects, shots });
const p = app.page;
await p.fill('[data-testid="video-path"]', project.video_path);
await p.click('[data-testid="import"]');
await p.waitForSelector('[data-testid="cue-list"] li', { timeout: 60000 });
await p.evaluate(() => document.querySelector("video").pause());

const options = await p.$$eval('[data-testid="lang-select"] option', (o) => o.map((x) => `${x.value}:${x.textContent}`));
note("selector", options.length === 2, options.join(" | "));
await app.shot("lang-1-zh.png");
note("label zh", (await p.textContent('[data-testid="mode-zh"]')) === "繁體中文", await p.textContent('[data-testid="mode-zh"]'));

await p.selectOption('[data-testid="lang-select"]', "es");
await p.waitForFunction(() => document.querySelector('[data-testid="mode-zh"]')?.textContent === "Español");
const toggle = await p.textContent(".toggle .collapsible");
note("label es", toggle === "Español在上", `mode switch "Español", toggle "${toggle}"`);
await app.shot("lang-2-es.png");

const row = '[data-testid="cue-4"]';
await p.dblclick(`${row} button`);
await p.fill(`${row} [data-testid="edit-text"]`, "Texto editado en español");
await p.press(`${row} [data-testid="edit-text"]`, "Enter");
await p.waitForSelector(`${row}[data-editing="false"]`);
const es = JSON.parse(readFileSync(join(folder, "subs.es.json"), "utf8")).cues.some((c) => c.zh === "Texto editado en español");
const zh = JSON.parse(readFileSync(join(folder, "subs.zh-TW.json"), "utf8")).cues.some((c) => c.zh === "Texto editado en español");
note("edit goes to es", es && !zh, `subs.es.json has it: ${es}, subs.zh-TW.json has it: ${zh}`);

await p.click('[data-testid="export-menu"]');
await p.click('[data-testid="export-srt-zh"]');
await sleep(1000);
const files = readdirSync(exportDir);
note("export es", files.some((f) => f.endsWith(".es.srt")), files.join(", "));

await p.selectOption('[data-testid="lang-select"]', "zh-TW");
await p.waitForFunction(() => document.querySelector('[data-testid="mode-zh"]')?.textContent === "繁體中文");
note("back to zh", (await p.locator('[data-testid="edited-mark"]').count()) === 0, "no edited marks in zh-TW");
await app.shot("lang-3-back.png");
const { leftovers } = await app.closeWindow();
note("shutdown", leftovers.length === 0, leftovers.join(", ") || "none left");
process.exit(results.every((r) => r.ok) ? 0 : 1);
