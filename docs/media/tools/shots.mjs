// Takes the promo screenshots in the real window, 1280x720 CSS pixels at 1.25x (1600x900 PNG).
// Run it on a copy of a project that holds two languages (zh-TW and ja), it edits and exports.
// VST_EXPORT_DIR must be set. node docs/media/tools/shots.mjs <projects-dir> <video> <out-dir> <hero-cue> <edit-cue>
import { join } from "node:path";
import { fixWindow, lib, sleep, snap } from "./capture.mjs";

const [projects, video, out, heroCue, editCue] = process.argv.slice(2);
if (!projects || !video || !out || !heroCue || !editCue) throw new Error("usage: shots.mjs <projects> <video> <out> <hero-cue> <edit-cue>");
const app = await lib.launch({ projects, shots: out, port: Number(process.env.VST_CDP_PORT ?? 9443) });
const p = app.page;
console.log("viewport", await fixWindow(p));
const shot = (name) => snap(p, join(out, name));
await p.fill('[data-testid="video-path"]', video);
await p.click('[data-testid="import"]');
await p.waitForSelector('[data-testid="cue-list"] li');
await p.selectOption('[data-testid="lang-select"]', "zh-TW");
await sleep(600);

const settle = async (ms = 700) => {
  await p.mouse.move(640, 710);
  await sleep(ms);
};
const seekTo = async (n) => {
  const start = Number(await p.getAttribute(`[data-testid="cue-${n}"]`, "data-start")) / 1000;
  await p.click(`[data-testid="cue-${n}"] button`);
  await p.waitForFunction((t) => Math.abs(document.querySelector("video").currentTime - t) < 0.6, start);
  await p.evaluate(() => document.querySelector("video").pause());
};

await seekTo(Number(heroCue));
await p.click('[data-testid="mode-both"]');
await p.evaluate(() => document.querySelector("video").play());
await sleep(1800);
await p.mouse.move(500, 300);
await sleep(300);
await shot("hero.png");
await p.evaluate(() => document.querySelector("video").pause());
await seekTo(Number(heroCue));
for (const mode of ["en", "zh", "both"]) {
  await p.click(`[data-testid="mode-${mode}"]`);
  await settle();
  await shot(`mode-${mode}.png`);
}

const cue = `[data-testid="cue-${editCue}"]`;
await p.dblclick(`${cue} button`);
await p.waitForSelector('[data-testid="edit-start"]');
await p.fill('[data-testid="edit-start"]', "0:46.000");
await p.keyboard.press("Enter");
await p.waitForSelector('[data-testid="edit-error"]');
await settle(500);
await shot("edit-error.png");
await p.keyboard.press("Escape");
await sleep(400);

await p.dblclick(`${cue} button`);
await p.waitForSelector('[data-testid="edit-text"]');
const text = await p.inputValue('[data-testid="edit-text"]');
await p.fill('[data-testid="edit-text"]', process.env.VST_EDIT_TEXT ?? text.replace(/\s*workforce\s*/i, "團隊"));
await p.keyboard.press("Enter");
await p.waitForSelector(`${cue} [data-testid="edited-mark"]`);
await settle();
await shot("edit-saved.png");

await p.click('[data-testid="tab-summary"]');
await settle(900);
await shot("summary.png");
await p.click('[data-testid="tab-library"]');
await p.mouse.move(640, 700);
await settle(1200);
await shot("library.png");
await p.click('[data-testid="tab-cues"]');
await sleep(300);
await p.focus("body");
await p.keyboard.press("?");
await p.waitForSelector('[data-testid="help"]');
await settle(500);
await shot("shortcuts.png");
await p.click('[data-testid="help-close"]');
await sleep(300);

await p.click('[data-testid="export-menu"]');
await p.mouse.move(1100, 330);
await sleep(600);
await shot("export-menu.png");
await p.keyboard.press("Escape");
await p.mouse.click(300, 700);
await sleep(300);

await p.selectOption('[data-testid="lang-select"]', "ja");
await seekTo(Number(heroCue));
await p.focus('[data-testid="lang-select"]');
await sleep(500);
await shot("languages.png");

const { leftovers } = await app.closeWindow();
console.log("leftovers", leftovers);
