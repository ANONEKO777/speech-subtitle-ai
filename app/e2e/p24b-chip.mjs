// Measures the toolbar of the home screen and of the English, Japanese and mixed player at 1280 and 960 px, and fails
// when the batch queue chip (shown once the queue has items) wraps the toolbar, squeezes the file box, or clips a control.
// node e2e/p24b-chip.mjs <projects-dir> <clips-dir> <shots-dir> <label> [port]
// <projects-dir> holds finished projects of queue-en-45s.mp4, queue-ja-60s.mp4 and queue-mixed-90s.mp4 (from <clips-dir>), so no import runs.
// Env: VST_USER_DATA (a disposable folder; with queue items the chip shows, without it the numbers are the baseline),
// WEBVIEW2_USER_DATA_FOLDER, VST_APP_EXE (the build to measure). Exit 1 on a failed check.
import { writeFileSync } from "node:fs";
import { join } from "node:path";
import { launch, sleep } from "./lib.mjs";

const [projects, clips, shots, label, portArg] = process.argv.slice(2);
if (!projects || !clips || !shots || !label) throw new Error("usage: p24b-chip.mjs <projects> <clips> <shots> <label> [port]");
const app = await launch({ projects, shots, port: Number(portArg ?? 9440), env: { VST_UPDATE_URL: "http://127.0.0.1:9/none.json" } });
const p = app.page;
const session = await p.context().newCDPSession(p);
const { windowId } = await session.send("Browser.getWindowForTarget");
const tid = (id) => `[data-testid="${id}"]`;
const resize = async (width, height) => {
  await session.send("Browser.setWindowBounds", { windowId, bounds: { windowState: "normal", width, height } });
  await sleep(700);
};
const measure = () =>
  p.evaluate(() => {
    const q = (id) => document.querySelector(`[data-testid="${id}"]`);
    const width = (e) => (e ? Number(e.getBoundingClientRect().width.toFixed(1)) : null);
    const h = document.querySelector("header");
    const mids = [...h.querySelectorAll("button, input, select")].map((e) => {
      const b = e.getBoundingClientRect();
      return Math.round(b.top + b.height / 2);
    });
    // how many px of the element lie outside the window or an ancestor that clips (0 is fully visible)
    const cut = (e) => {
      if (!e) return null;
      const b = e.getBoundingClientRect();
      let worst = Math.max(0, b.right - innerWidth, -b.left, b.bottom - innerHeight, -b.top);
      for (let a = e.parentElement; a && a !== document.body; a = a.parentElement) {
        if (getComputedStyle(a).overflow === "visible") continue;
        const r = a.getBoundingClientRect();
        worst = Math.max(worst, b.right - r.right, r.left - b.left, b.bottom - r.bottom, r.top - b.top);
      }
      return Number(worst.toFixed(1));
    };
    const chip = q("queue-chip");
    const slider = h.querySelector(".slider");
    return {
      header: Number(h.getBoundingClientRect().height.toFixed(1)),
      spread: Math.max(...mids) - Math.min(...mids),
      box: width(q("video-path")),
      picker: width(h.querySelector(tidSel("source-lang"))),
      slider: width(slider),
      chip: chip !== null,
      chipText: chip?.querySelector(".chip-badge")?.textContent ?? null,
      chipTitle: chip?.getAttribute("title") ?? null,
      chipCut: cut(chip),
      exportBtn: q("export-menu") !== null,
      exportCut: cut(q("export-menu")),
    };
    function tidSel(id) {
      return `[data-testid="${id}"]`;
    }
  });

const out = { label, rows: {} };
const fails = [];
const check = (name, ok, detail) => {
  console.log(`${ok ? "PASS" : "FAIL"} ${name} ${detail}`);
  if (!ok) fails.push(name);
};
// the side panel head is 17.5 px too narrow for its tabs and the export button on main (padding only, the label stays); the queue badge must not add to it
const EXPORT_CUT = 18;
const BOX = { 1280: 130, 960: 66 };
// P26b added the subtitle language picker to the toolbar. Measured on the P26b fix build with an empty queue (a queue item takes 36 px more):
// English and Japanese 656.2 px at 1280 and 500.8 at 960, mixed 634.2 and 478.9. Main measured 789.1, 600.8 and 725.1.
// Each minimum is the measurement minus 10 px.
const CHIP_BOX = 36;
const BOX_HOME = { en: { 1280: 646, 960: 490 }, ja: { 1280: 646, 960: 490 }, "ja+en": { 1280: 624, 960: 468 } };
const waitPlayer = async () => {
  await p.waitForSelector(`${tid("cue-list")} li`, { timeout: 60000 });
  await p.evaluate(() => document.querySelector("video")?.pause());
};
const names = { en: "English", ja: "Japanese", "ja+en": "mixed" };
const files = { en: "queue-en-45s.mp4", ja: "queue-ja-60s.mp4", "ja+en": "queue-mixed-90s.mp4" };

for (const lang of ["en", "ja", "ja+en"]) {
  if (await p.locator(tid("home")).count()) {
    await p.click(tid("home"));
    await p.waitForSelector(tid("library-list"));
  }
  await p.selectOption(tid("source-lang"), lang);
  for (const [w, h] of [[1280, 720], [960, 600]]) {
    await resize(w, h);
    const m = await measure();
    out.rows[`home-${lang}-${w}`] = m;
    check(`home ${names[lang]} ${w} one row`, m.header < 52 && m.spread <= 3, `header ${m.header} px, spread ${m.spread}`);
    const needBox = BOX_HOME[lang][w] - (m.chip ? CHIP_BOX : 0);
    check(`home ${names[lang]} ${w} file box`, m.box >= needBox, `video-path ${m.box} px, needs ${needBox}${m.chip ? ` (${BOX_HOME[lang][w]} less ${CHIP_BOX} for the chip)` : ""}`);
    if (lang === "ja+en") check(`home mixed ${w} picker`, m.picker === 128, `picker ${m.picker} px`);
    if (m.chip) check(`home ${names[lang]} ${w} chip`, m.chipCut === 0 && !!m.chipTitle && /^\d+\/\d+$/.test(m.chipText ?? ""), `chip ${m.chipText}, title "${m.chipTitle}", ${m.chipCut} px cut`);
  }
  await resize(1280, 720);
  await p.fill(tid("video-path"), join(clips, files[lang]));
  await p.click(tid("import"));
  await waitPlayer();
  for (const [w, h] of [[1280, 720], [960, 600]]) {
    await resize(w, h);
    await sleep(300);
    const m = await measure();
    out.rows[`player-${lang}-${w}`] = m;
    check(`player ${names[lang]} ${w} one row`, m.header >= 50 && m.header <= 52 && m.spread <= 3, `header ${m.header} px, spread ${m.spread}`);
    check(`player ${names[lang]} ${w} file box`, m.box >= BOX[w], `video-path ${m.box} px, needs ${BOX[w]}`);
    check(`player ${names[lang]} ${w} export button`, m.exportBtn && m.exportCut <= EXPORT_CUT, `export-menu present ${m.exportBtn}, ${m.exportCut} px outside the side panel, allowed ${EXPORT_CUT}`);
    check(`player ${names[lang]} ${w} sliders usable`, m.slider >= 38, `slider ${m.slider} px`);
    if (m.chip) check(`player ${names[lang]} ${w} chip`, m.chipCut === 0 && !!m.chipTitle && /^\d+\/\d+$/.test(m.chipText ?? ""), `chip ${m.chipText}, title "${m.chipTitle}", ${m.chipCut} px cut`);
    await p.screenshot({ path: join(shots, `chip-${label}-player-${lang.replace("+", "")}-${w}.png`) });
  }
  await resize(1280, 720);
}

if (await p.locator(tid("queue-chip")).count()) {
  await resize(960, 600);
  await p.click(tid("queue-chip"));
  await sleep(500);
  const shown = await p.locator(tid("batch-panel")).isVisible().catch(() => false);
  check("chip click opens the queue in the player", shown, `batch-panel visible ${shown}`);
  await p.screenshot({ path: join(shots, `chip-${label}-queue-960.png`) });
  await resize(1280, 720);
}
out.fails = fails;
console.log(JSON.stringify(out));
writeFileSync(join(shots, `chip-${label}.json`), JSON.stringify(out, null, 1));
await app.closeWindow();
process.exit(fails.length ? 1 : 0);
