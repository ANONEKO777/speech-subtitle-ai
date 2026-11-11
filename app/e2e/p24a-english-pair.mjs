// P24a: the English flow before and after. Run once per build with the same projects folder copy:
//   VST_APP_EXE=<exe> node e2e/p24a-english-pair.mjs <projects-dir> <video> <out-dir> <label> [port]
// It opens a finished English project, and saves screenshots and the visible text of each screen to
// <out-dir>/<label>/. `node e2e/p24a-english-pair.mjs diff <out-dir> <labelA> <labelB>` prints how the texts differ.
// Everything goes over CDP. The clipboard, audio and notifications are stubbed in the page.
import { mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { join } from "node:path";

if (process.argv[2] === "diff") {
  const [, , , dir, a, b] = process.argv;
  const A = JSON.parse(readFileSync(join(dir, a, "texts.json"), "utf8"));
  const B = JSON.parse(readFileSync(join(dir, b, "texts.json"), "utf8"));
  let same = 0;
  for (const key of Object.keys(A)) {
    if (A[key] === B[key]) {
      same += 1;
      continue;
    }
    const la = A[key].split("\n");
    const lb = B[key].split("\n");
    console.log(`DIFF ${key}`);
    for (const l of la) if (!lb.includes(l)) console.log(`  - ${l}`);
    for (const l of lb) if (!la.includes(l)) console.log(`  + ${l}`);
  }
  console.log(`${same} of ${Object.keys(A).length} screens have identical text`);
  process.exit(0);
}

const [projects, video, out, label, portArg] = process.argv.slice(2);
if (!projects || !video || !out || !label) throw new Error("usage: p24a-english-pair.mjs <projects> <video> <out> <label> [port]");
const { launch, sleep } = await import("./lib.mjs");
const dir = join(out, label);
mkdirSync(dir, { recursive: true });
const app = await launch({ projects, shots: dir, port: Number(portArg ?? 9425), env: { VST_UPDATE_URL: "http://127.0.0.1:9/none.json" } });
const p = app.page;
await p.evaluate(() => {
  Object.defineProperty(HTMLMediaElement.prototype, "muted", { configurable: true, get: () => true, set: () => undefined });
  Object.defineProperty(HTMLMediaElement.prototype, "volume", { configurable: true, get: () => 0, set: () => undefined });
  const inner = window.__TAURI_INTERNALS__;
  const invoke = inner.invoke.bind(inner);
  inner.invoke = (cmd, ...rest) => (typeof cmd === "string" && cmd.startsWith("plugin:notification|") ? Promise.resolve("denied") : invoke(cmd, ...rest));
});
const session = await p.context().newCDPSession(p);
const { windowId } = await session.send("Browser.getWindowForTarget");
const resize = async (w, h) => {
  await session.send("Browser.setWindowBounds", { windowId, bounds: { windowState: "normal", width: w, height: h } });
  await sleep(700);
};
const texts = {};
const tid = (id) => `[data-testid="${id}"]`;
const grab = async (key, sel = "body") => {
  texts[key] = (await p.locator(sel).first().innerText()).replace(/\r/g, "").replace(/[ \t]+/g, " ").trim();
};

await resize(1280, 720);
await grab("home");
await app.shot("home-1280.png");
await resize(960, 600);
await app.shot("home-960.png");
await resize(1280, 720);

await p.fill(tid("video-path"), video);
await p.click(tid("import"));
await p.waitForSelector(`${tid("cue-list")} li`, { timeout: 60000 });
await p.evaluate(() => document.querySelector("video").pause());
const start = Number(await p.getAttribute(tid("cue-3"), "data-start")) / 1000;
await p.click(`${tid("cue-3")} button`);
await p.waitForFunction((t) => Math.abs(document.querySelector("video").currentTime - t) < 0.6, start);
await p.evaluate(() => document.querySelector("video").pause());
await p.mouse.move(0, 0);
await sleep(500);
for (const mode of ["en", "zh", "both"]) {
  await p.click(tid(`mode-${mode}`));
  await sleep(400);
  await grab(`player-${mode}-subtitle`, tid("subtitle"));
  await grab(`player-${mode}-toolbar`, "header");
  await app.shot(`player-${mode}-1280.png`);
}
await grab("player-cues", tid("cue-list"));
await resize(960, 600);
await app.shot("player-both-960.png");
await resize(1280, 720);
await p.dblclick(`${tid("cue-5")} button`);
await p.waitForSelector(tid("cue-editor"));
await grab("editor", tid("cue-editor"));
await app.shot("editor-1280.png");
await p.press(`${tid("cue-5")} ${tid("edit-text")}`, "Escape");
await p.click(tid("export-menu"));
await grab("export-menu", tid("export-list"));
await app.shot("export-menu-1280.png");
await p.keyboard.press("Escape");
await p.click(tid("tab-summary"));
await sleep(500);
await grab("summary-tab", tid("side-panel"));
await p.click(tid("tab-cues"));
await p.click(tid("tab-library"));
await sleep(1200);
await grab("library-tab", tid("side-panel"));
await app.shot("library-tab-1280.png");

writeFileSync(join(dir, "texts.json"), JSON.stringify(texts, null, 1));
const info = await app.closeWindow();
console.log(`${label}: ${Object.keys(texts).length} screens saved to ${dir}; leftovers ${JSON.stringify(info.leftovers)}`);
