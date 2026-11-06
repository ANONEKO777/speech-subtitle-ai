// P10 live check: edit, bad timing, undo, Esc, keyboard, persistence, summary seek, exports, language label.
// node e2e/editor-lanes.mjs <projects-dir> <shots-dir> <export-dir>
// <projects-dir> holds a finished project (copy it first, the lanes edit it). Needs `npx tauri build --no-bundle`.
import { existsSync, readFileSync, readdirSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import { launch, sleep } from "./lib.mjs";

const [projects, shots, exportDir] = process.argv.slice(2);
if (!projects || !shots || !exportDir) throw new Error("usage: editor-lanes.mjs <projects> <shots> <export-dir>");
process.env.VST_EXPORT_DIR = exportDir;

const folder = join(projects, readdirSync(projects)[0]);
const project = JSON.parse(readFileSync(join(folder, "project.json"), "utf8"));
const results = [];
const note = (lane, ok, detail) => {
  results.push({ lane, ok, detail });
  console.log(`${ok ? "PASS" : "FAIL"} ${lane} ${detail}`);
};

const clock = (ms) => `${Math.floor(ms / 60000)}:${String(Math.floor(ms / 1000) % 60).padStart(2, "0")}.${String(ms % 1000).padStart(3, "0")}`;
const row = (n) => `[data-testid="cue-${n}"]`;
const zhOf = (p, n) => p.textContent(`${row(n)} .zh`);
const startOf = async (p, n) => Number(await p.getAttribute(row(n), "data-start"));
const diskCues = () => JSON.parse(readFileSync(join(folder, "subs.zh-TW.json"), "utf8")).cues;

async function open() {
  const app = await launch({ projects, shots });
  const p = app.page;
  await p.fill('[data-testid="video-path"]', project.video_path);
  await p.click('[data-testid="import"]');
  await p.waitForSelector('[data-testid="cue-list"] li', { timeout: 60000 });
  return app;
}

async function beginEdit(p, n) {
  await p.dblclick(`${row(n)} button`);
  await p.waitForSelector(`${row(n)} [data-testid="cue-editor"]`);
}

let app = await open();
let p = app.page;
await p.evaluate(() => document.querySelector("video").pause());
const original = await zhOf(p, 5);
const EDIT = "人工校對：這一句是我改的。";

note("label", (await p.textContent('[data-testid="mode-zh"]')) === "繁體中文", `mode switch shows "${await p.textContent('[data-testid="mode-zh"]')}"`);
await app.shot("01-player.png");

// edit and save with Enter
await beginEdit(p, 5);
await app.shot("02-editing.png");
await p.fill(`${row(5)} [data-testid="edit-text"]`, EDIT);
const pressed = Date.now();
await p.press(`${row(5)} [data-testid="edit-text"]`, "Enter");
await p.waitForSelector(`${row(5)}[data-editing="false"]`);
const saveMs = Date.now() - pressed;
const saved = diskCues().find((c) => c.zh === EDIT);
note("edit-save", (await zhOf(p, 5)) === EDIT && !!saved && (await p.locator(`${row(5)} [data-testid="edited-mark"]`).count()) === 1, `row shows the new text with the edited mark, disk cue ${saved?.id}, Enter to saved ${saveMs} ms (rule 300 ms)`);
note("save latency", saveMs < 300, `${saveMs} ms with ${await p.locator('[data-testid^="cue-"]').count()} cues`);
await app.shot("03-edited.png");

// bad timings
const next = await startOf(p, 6);
const cur = await startOf(p, 5);
const cases = [
  ["overlap", clock(next + 400), "重疊"],
  ["too long", clock(cur + 7600), "7 秒"],
  ["end before start", clock(cur - 500), "早於"],
];
const diskBefore = readFileSync(join(folder, "subs.zh-TW.json"), "utf8");
await beginEdit(p, 5);
for (const [name, end, word] of cases) {
  await p.fill(`${row(5)} [data-testid="edit-end"]`, end);
  await p.press(`${row(5)} [data-testid="edit-end"]`, "Enter");
  await sleep(300);
  const err = await p.textContent(`${row(5)} [data-testid="edit-error"]`).catch(() => null);
  const stillEditing = (await p.getAttribute(row(5), "data-editing")) === "true";
  note(`bad-timing ${name}`, !!err && err.includes(word) && stillEditing, `error "${err}", still editing ${stillEditing}`);
  if (name === "overlap") await app.shot("04-overlap-error.png");
}
note("bad-timing not saved", readFileSync(join(folder, "subs.zh-TW.json"), "utf8") === diskBefore, "subs.zh-TW.json unchanged after three refused saves");

// Esc cancels
await p.fill(`${row(5)} [data-testid="edit-text"]`, "不該被存下來");
await p.press(`${row(5)} [data-testid="edit-text"]`, "Escape");
await sleep(300);
note("esc", (await zhOf(p, 5)) === EDIT && !diskCues().some((c) => c.zh === "不該被存下來"), `text back to the saved value "${await zhOf(p, 5)}"`);
await app.shot("05-esc.png");

// blur saves, then Ctrl+Z undoes
await beginEdit(p, 7);
const before7 = await zhOf(p, 7).catch(() => null);
await p.fill(`${row(7)} [data-testid="edit-text"]`, "失焦儲存測試");
await p.click('[data-testid="video"]', { position: { x: 20, y: 20 } });
await p.waitForSelector(`${row(7)}[data-editing="false"]`);
note("blur-save", (await zhOf(p, 7)) === "失焦儲存測試" && diskCues().some((c) => c.zh === "失焦儲存測試"), "text saved by clicking elsewhere");
await p.evaluate(() => document.activeElement?.blur());
await p.keyboard.press("Control+z");
await sleep(600);
const after7 = await zhOf(p, 7);
note("undo", after7 !== "失焦儲存測試" && !diskCues().some((c) => c.zh === "失焦儲存測試") && (await zhOf(p, 5)) === EDIT, `cue 7 is "${after7}" again, cue 5 keeps its edit`);
await app.shot("06-undo.png");

// keyboard only: focus a row, F2, type, Enter
await p.focus(`${row(8)} button`);
await p.keyboard.press("F2");
await p.waitForSelector(`${row(8)} [data-testid="cue-editor"]`);
await p.keyboard.press("Control+a");
await p.keyboard.type("鍵盤編輯");
await p.keyboard.press("Enter");
await p.waitForSelector(`${row(8)}[data-editing="false"]`);
const focused = await p.evaluate(() => document.activeElement?.closest("li")?.dataset.testid);
note("keyboard", (await zhOf(p, 8)) === "鍵盤編輯" && diskCues().some((c) => c.zh === "鍵盤編輯"), `F2, typing and Enter only; focus returned to ${focused}`);

// summary
await p.click('[data-testid="tab-summary"]');
await p.waitForSelector('[data-testid="summary"]');
await app.shot("07-summary.png");
const chapters = p.locator('[data-testid="chapter-time"]');
const total = await chapters.count();
const third = chapters.nth(2);
const seconds = Number(await third.getAttribute("data-seconds"));
await third.click();
await sleep(700);
const t = await p.evaluate(() => document.querySelector("video").currentTime);
const tabNow = await p.getAttribute('[data-testid="tab-cues"]', "aria-selected");
note("summary-seek", Math.abs(t - seconds) < 1 && tabNow === "true", `${total} chapters; third is ${seconds} s, video at ${t.toFixed(2)} s, cue tab selected ${tabNow}`);
await p.evaluate(() => document.querySelector("video").pause());
await app.shot("08-summary-jump.png");

// exports
await p.click('[data-testid="export-menu"]');
await app.shot("09-export-menu.png");
await p.keyboard.press("Escape");
const files = {};
for (const id of ["srt-en", "srt-zh", "srt-bilingual", "ass", "vtt", "summary"]) {
  await p.click('[data-testid="export-menu"]');
  const before = new Set(readdirSync(exportDir));
  await p.click(`[data-testid="export-${id}"]`);
  await sleep(1200);
  files[id] = readdirSync(exportDir).find((f) => !before.has(f)) ?? null;
}
const status = await p.textContent('[data-testid="side-status"]');
const text = (id) => (files[id] ? readFileSync(join(exportDir, files[id]), "utf8") : "");
note("export files", Object.values(files).every(Boolean), JSON.stringify(files));
note("export srt-zh has the edit", text("srt-zh").includes(EDIT), "zh srt holds the lane 2 text");
note("export srt-en is English", /[A-Za-z]{4}/.test(text("srt-en")) && !text("srt-en").includes(EDIT), "en srt has no edit");
note("export bilingual has both", text("srt-bilingual").includes(EDIT) && /[A-Za-z]{4}/.test(text("srt-bilingual")), "bilingual srt has both lines");
note("export ass", text("ass").includes("[Events]") && text("ass").includes(EDIT.slice(0, 6)), `ass ${text("ass").length} chars`);
note("export vtt", text("vtt").startsWith("WEBVTT") && text("vtt").includes(EDIT), `vtt ${text("vtt").length} chars`);
note("export summary", text("summary") === readFileSync(join(folder, "summary.md"), "utf8"), "summary.md equals the project's");
note("export status line", status.includes("已匯出"), status);
await app.shot("10-exported.png");

const { leftovers: stray } = await app.closeWindow();
note("shutdown 1", stray.length === 0, stray.join(", ") || "none left");

// restart: the edits are still there, and are marked
app = await open();
p = app.page;
await p.evaluate(() => document.querySelector("video").pause());
const marks = await p.locator('[data-testid="edited-mark"]').count();
note("persist", (await zhOf(p, 5)) === EDIT && (await zhOf(p, 8)) === "鍵盤編輯" && marks === 2, `after restart cue 5 and 8 keep their edits, ${marks} edited marks`);
await app.shot("11-after-restart.png");
const { leftovers: stray2 } = await app.closeWindow();
note("shutdown 2", stray2.length === 0, stray2.join(", ") || "none left");

writeFileSync(join(shots, "editor-lanes.json"), JSON.stringify(results, null, 1));
process.exit(results.every((r) => r.ok) ? 0 : 1);
