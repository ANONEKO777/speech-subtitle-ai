// Records the player tour on an already translated project: playback, the three modes, an edit,
// the summary and a chapter jump, the export menu, and the language selector.
// VST_EXPORT_DIR must be set so the export click writes a file instead of opening the native dialog.
// node docs/media/tools/record-tour.mjs <projects-dir> <video> <out-dir> <cue-to-edit> <new-text>
import { writeFileSync } from "node:fs";
import { join } from "node:path";
import { fixWindow, lib, sleep, startCast } from "./capture.mjs";

const [projects, video, out, editCue, editText] = process.argv.slice(2);
if (!projects || !video || !out || !editCue || !editText) throw new Error("usage: record-tour.mjs <projects> <video> <out> <cue> <text>");
const app = await lib.launch({ projects, shots: out, port: Number(process.env.VST_CDP_PORT ?? 9442) });
const p = app.page;
console.log("viewport", await fixWindow(p));
await p.mouse.move(640, 700);
await p.fill('[data-testid="video-path"]', video);
await p.click('[data-testid="import"]');
await p.waitForSelector('[data-testid="cue-list"] li');
await p.selectOption('[data-testid="lang-select"]', "zh-TW");
await sleep(600);
await p.evaluate(() => document.querySelector("video").pause());
const cast = await startCast(p, join(out, "cast-tour"));
const t0 = Date.now();
const marks = {};
const mark = (name) => (marks[name] = (Date.now() - t0) / 1000);
const click = (id) => p.click(`[data-testid="${id}"]`);
const video$ = (code) => p.evaluate(code);

mark("play");
await sleep(300);
await p.click('[data-testid="cue-2"] button');
await video$(() => document.querySelector("video").play());
await sleep(7800);

mark("modes");
await click("mode-en");
await sleep(2200);
await click("mode-zh");
await sleep(2200);
await click("mode-both");
await sleep(1500);
await video$(() => document.querySelector("video").pause());

mark("edit");
await p.dblclick(`[data-testid="cue-${editCue}"] button`);
await p.waitForSelector('[data-testid="edit-text"]');
await sleep(900);
await p.fill('[data-testid="edit-text"]', "");
await p.keyboard.type(editText, { delay: 45 });
await sleep(900);
await p.keyboard.press("Enter");
await p.waitForSelector(`[data-testid="cue-${editCue}"] [data-testid="edited-mark"]`);
await sleep(2200);

mark("summary");
await click("tab-summary");
await sleep(2600);
const chapters = await p.$$('[data-testid="chapter-time"]');
await chapters[chapters.length - 1].click();
await video$(() => document.querySelector("video").play());
await sleep(3000);

mark("lang");
await p.selectOption('[data-testid="lang-select"]', "ja");
await sleep(1200);
await p.click('[data-testid="cue-3"] button');
await video$(() => document.querySelector("video").play());
await sleep(5000);
await video$(() => document.querySelector("video").pause());
mark("export");
await click("export-menu");
await sleep(2400);
await click("export-srt-bilingual");
await sleep(1500);

mark("end");
writeFileSync(join(out, "marks-tour.json"), JSON.stringify(marks));
console.log(await cast.stop());
const { leftovers } = await app.closeWindow();
console.log("leftovers", leftovers);
