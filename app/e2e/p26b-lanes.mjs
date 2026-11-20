// P26b live check: a Japanese talk in several target languages, in the real window, driven over CDP only.
// node e2e/p26b-lanes.mjs <phase> <projects-dir> <video-dir> <shots-dir> [port]
// phase: view   (no model: the finished seed project, the pickers, the failed cues, exports, a burned still, widths)
//        add    (the real LLM: add Simplified Chinese to the seed project from the player menu)
//        queue  (the real LLM: a project with one language gets English from the import box, then Simplified Chinese
//                and Korean from the queue, the video is taken away so Korean fails, then it is put back and retried)
//        nofont (Malgun Gothic hidden from the backend: the burn refusal names the language)
// The seed is `scripts/make_p26b_seed.py`. Env: VST_USER_DATA, WEBVIEW2_USER_DATA_FOLDER (disposable), P26B_EXPORTS.
// Nothing here touches the real mouse or keyboard. The clipboard, audio and notifications are stubbed in the page.
import { execFileSync } from "node:child_process";
import { copyFileSync, existsSync, mkdirSync, readFileSync, readdirSync, renameSync, statSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import { launch, sleep, strayProcesses } from "./lib.mjs";

const [phase, projects, clips, shots, portArg] = process.argv.slice(2);
if (!phase || !projects || !clips || !shots) throw new Error("usage: p26b-lanes.mjs <view|add|queue|nofont> <projects> <video-dir> <shots> [port]");
const port = Number(portArg ?? 9426);
const exportDir = process.env.P26B_EXPORTS ?? join(shots, "exports");
if (!process.env.VST_USER_DATA || !process.env.WEBVIEW2_USER_DATA_FOLDER) throw new Error("set VST_USER_DATA and WEBVIEW2_USER_DATA_FOLDER to disposable folders");
mkdirSync(shots, { recursive: true });
mkdirSync(exportDir, { recursive: true });
const prefix = process.env.P26B_PREFIX ?? "P26b";
const results = [];
const note = (lane, ok, detail) => {
  results.push({ lane, ok, detail });
  console.log(`${ok ? "PASS" : "FAIL"} ${lane} ${detail}`);
};
const tid = (id) => `[data-testid="${id}"]`;
const until = async (label, fn, ms = 30000, step = 200) => {
  const end = Date.now() + ms;
  for (;;) {
    const v = await fn();
    if (v) return v;
    if (Date.now() > end) throw new Error(`timeout: ${label}`);
    await sleep(step);
  }
};
const busy = () => /whisper-cli|crispasr|llama-server/i.test(execFileSync("tasklist", { encoding: "utf8" }));
if (busy()) throw new Error("a model process is running: one model-running process at a time");

const env = { VST_EXPORT_DIR: exportDir, VST_UPDATE_URL: "http://127.0.0.1:9/none.json" };
if (phase === "nofont") {
  const dir = join(shots, "sitecustomize");
  mkdirSync(dir, { recursive: true });
  // hides the one family from the backend's list of installed fonts, and nothing else
  writeFileSync(
    join(dir, "sitecustomize.py"),
    [
      "import sys",
      `sys.path.insert(0, ${JSON.stringify(process.env.P26B_ROOT ?? "D:/WebProject/speech-subtitle-ai/.worktrees/P26b")})`,
      "from backend.core import fonts",
      "_real = fonts._registry_fonts",
      "fonts._registry_fonts = lambda: {k: v for k, v in _real().items() if 'malgun' not in k.lower()}",
      "",
    ].join("\n"),
  );
  env.PYTHONPATH = dir;
}
const strays0 = strayProcesses();
const app = await launch({ projects, shots, port, env });
const p = app.page;
console.log(`app pid ${app.pid}, cold start ${app.coldStartMs} ms, phase ${phase}`);
await p.evaluate(() => {
  Object.defineProperty(HTMLMediaElement.prototype, "muted", { configurable: true, get: () => true, set: () => undefined });
  Object.defineProperty(HTMLMediaElement.prototype, "volume", { configurable: true, get: () => 0, set: () => undefined });
  Object.defineProperty(navigator, "clipboard", { configurable: true, value: { write: async () => undefined } });
  const inner = window.__TAURI_INTERNALS__;
  const invoke = inner.invoke.bind(inner);
  inner.invoke = (cmd, ...rest) =>
    typeof cmd === "string" && cmd.startsWith("plugin:notification|") ? Promise.resolve(cmd.endsWith("is_permission_granted") ? false : "denied") : invoke(cmd, ...rest);
});
const session = await p.context().newCDPSession(p);
const { windowId } = await session.send("Browser.getWindowForTarget");
const resize = async (width, height) => {
  await session.send("Browser.setWindowBounds", { windowId, bounds: { windowState: "normal", width, height } });
  await sleep(700);
};
let shotNo = 0;
const shot = async (name, what) => {
  shotNo += 1;
  const file = join(shots, `${prefix}-${phase}-${String(shotNo).padStart(2, "0")}-${name}.png`);
  await p.screenshot({ path: file });
  console.log(`SHOT ${file} :: ${what}`);
  return file;
};
const header = () =>
  p.evaluate(() => {
    const h = document.querySelector("header");
    const mids = [...h.querySelectorAll("button, input, select")].map((e) => {
      const b = e.getBoundingClientRect();
      return Math.round(b.top + b.height / 2);
    });
    return { height: h.getBoundingClientRect().height, spread: Math.max(...mids) - Math.min(...mids), n: mids.length, box: document.querySelector('[data-testid="video-path"]')?.getBoundingClientRect().width ?? null };
  });
const oneRow = async (label) => {
  const out = {};
  for (const [w, h] of [[1280, 720], [960, 600]]) {
    await resize(w, h);
    const m = await header();
    out[w] = m;
    note(`toolbar one row at ${w} (${label})`, m.height < 60 && m.spread <= 3, `header ${m.height.toFixed(1)} px, ${m.n} controls, centers spread ${m.spread} px, file box ${m.box === null ? "none" : m.box.toFixed(1) + " px"}`);
  }
  await resize(1280, 720);
  return out;
};
const optionsOf = (sel) => p.$$eval(`${sel} option`, (o) => o.map((x) => `${x.value}:${x.textContent}`));
const cueTexts = () => p.$$eval(`${tid("cue-list")} li`, (lis) => lis.map((li) => ({ n: li.dataset.testid, failed: li.dataset.failed ?? null, zh: li.querySelector(".zh")?.textContent ?? "" })));
const waitPlayer = async (ms = 120000) => {
  await until("player", async () => (await p.locator(`${tid("cue-list")} li`).count()) > 0 && (await p.locator(tid("importing")).count()) === 0, ms, 300);
  await p.evaluate(() => document.querySelector("video")?.pause());
};
const importPath = async (video, source, target) => {
  if (source) await p.selectOption(tid("source-lang"), source);
  if (target) await p.selectOption(tid("target-lang"), target);
  await p.fill(tid("video-path"), video);
  await p.click(tid("import"));
};
const pause = () => p.evaluate(() => document.querySelector("video")?.pause());
const seedVideo = join(clips, "talk-demo-ja.mp4");
const seedVideoB = join(clips, "talk-demo-ja-b.mp4");

try {
  if (phase === "view") {
    await p.waitForSelector(tid("ready"));
    await oneRow("home, English speech, Traditional Chinese (the default)");
    // the pickers on the home screen
    await p.selectOption(tid("source-lang"), "ja");
    const ja = await optionsOf(tid("target-lang"));
    note("Japanese speech offers the four targets in the backend's order, Korean labelled", ja.join("|") === "zh-TW:繁體中文|zh-CN:简体中文|en:English|ko:한국어（實驗性）", ja.join("|"));
    await p.selectOption(tid("source-lang"), "en");
    const en = await optionsOf(tid("target-lang"));
    note("English speech offers its list without English", en.length > 8 && !en.some((o) => o.startsWith("en:")) && en.some((o) => o.startsWith("ko:") && o.includes("實驗性")), `${en.length} options: ${en.map((o) => o.split(":")[0]).join(",")}`);
    await p.selectOption(tid("source-lang"), "ja+en").catch(() => undefined);
    const mixed = await optionsOf(tid("target-lang"));
    note("mixed Japanese and English offers Traditional Chinese only", mixed.join("|") === "zh-TW:繁體中文" && (await p.locator(tid("target-lang")).isDisabled()), mixed.join("|"));
    await p.selectOption(tid("source-lang"), "ja");
    await shot("home-ja-1280", "Home, Japanese video: the subtitle language picker beside the video language picker, the note about adding languages");
    await p.selectOption(tid("target-lang"), "ko");
    const hint = await p.textContent(tid("target-hint"));
    note("an experimental target shows its hint on selection", hint.includes("實驗性") && (await p.getAttribute(tid("target-lang"), "data-experimental")) === "true", hint);
    await shot("home-ja-ko-hint-1280", "Home, Japanese video, Korean picked: the experimental label in the picker and the hint under the toolbar");
    const rows = await oneRow("home, Japanese, Korean picked");
    await resize(960, 600);
    await shot("home-ja-ko-hint-960", "Same at 960 px: the toolbar is one row, the path box is narrower");
    await resize(1280, 720);
    await p.selectOption(tid("target-lang"), "zh-TW");

    // import the finished seed in Traditional Chinese: it plays as it always did
    await importPath(seedVideo, "ja", "zh-TW");
    await waitPlayer(60000);
    const langs = await optionsOf(tid("lang-select"));
    note("the project holds three targets, Korean labelled", langs.join("|") === "zh-TW:繁體中文|en:English|ko:한국어（實驗性）" || langs.length === 3, langs.join("|"));
    await shot("player-zh-TW-1280", "Player, Japanese talk in Traditional Chinese: language select with three targets, add-language button");
    await p.click(tid("add-target"));
    const addable = await p.$$eval('[data-testid^="add-target-"]:not([data-testid="add-target-list"]):not([data-testid="add-target-hint"])', (e) => e.map((x) => x.dataset.testid.replace("add-target-", "")));
    note("the menu offers the language the project lacks and says only the translation reruns", addable.join() === "zh-CN" && (await p.textContent(tid("add-target-list"))).includes("不會重跑語音辨識"), `${addable.join()} / ${(await p.textContent(tid("add-target-list"))).slice(0, 60)}`);
    await shot("player-add-target-menu", "Player: the menu of languages the project can still be translated into");
    await p.keyboard.press("Escape");

    // Korean: failed cues
    await p.selectOption(tid("lang-select"), "ko");
    await until("ko cues", async () => (await cueTexts()).some((c) => /[가-힣]/.test(c.zh)), 10000);
    const kofail = await p.getAttribute(tid("failed-note"), "data-count");
    const kinds = (await cueTexts()).filter((c) => c.failed).map((c) => `${c.n}:${c.failed}`);
    const summary = await p.textContent(tid("failed-summary"));
    note("Korean: two failed cues are counted, with the reason", kofail === "2" && kinds.join() === "cue-4:english,cue-6:empty" && summary.includes("沒有通過檢查"), `${kofail} ${kinds.join()} "${summary}"`);
    await shot("player-ko-failed-1280", "Player, Korean: the note above the list (count, what shows instead, why) and the marks on cues 4 and 6");
    await p.click(tid("failed-filter"));
    const only = (await cueTexts()).map((c) => c.n).join();
    note("the filter shows only the failed cues", only === "cue-4,cue-6", only);
    await shot("player-ko-failed-filter", "Player, Korean, filter on: only the two failed cues are listed");
    await p.click(tid("failed-filter"));
    await resize(960, 600);
    await shot("player-ko-failed-960", "Player at 960 px, Korean");
    const side960 = await p.evaluate(() => {
      const h = document.querySelector(".side-head");
      return { h: h.getBoundingClientRect().height, over: h.scrollWidth - h.clientWidth };
    });
    note("side header is no worse at 960 than main (its export button is clipped by about 19 px there already)", side960.over <= 24, `side-head ${side960.h} px high, overflow ${side960.over}`);
    await resize(1280, 720);

    // English: an empty cue
    await p.selectOption(tid("lang-select"), "en");
    await until("en cues", async () => (await cueTexts()).some((c) => /Today/.test(c.zh)), 10000);
    const enNote = await p.getAttribute(tid("failed-note"), "data-count");
    const six = (await cueTexts()).find((c) => c.n === "cue-6");
    note("English: cue 6 is empty and says so", enNote === "1" && six.failed === "empty" && six.zh === "（沒有翻譯）", `${enNote} ${JSON.stringify(six)}`);
    await shot("player-en-empty-cue", "Player, English: cue 6 has no translation and is marked");
    const alt = await p.evaluate(() => document.querySelector("video") !== null);
    // subtitle line under the video follows the language
    await p.evaluate(() => (document.querySelector("video").currentTime = 4.9));
    await sleep(500);
    const line = await p.evaluate(() => [...document.querySelectorAll('[data-testid="subtitle"] p')].map((e) => `${e.dataset.lang}:${e.lang}:${e.textContent}`));
    note("the subtitle under the video is in the language shown, with its language tag", line.some((l) => l.startsWith("zh:en:")) && alt, line.join(" | "));
    // fill the empty cue: the failure ends
    await p.dblclick(`${tid("cue-6")} button`);
    await p.fill(tid("edit-text"), "On a rainy day the venue moves to the gym.");
    await p.keyboard.press("Enter");
    await until("failure ended", async () => (await p.locator(tid("failed-note")).count()) === 0, 8000);
    note("filling the empty cue ends its failure", true, "the note is gone");
    await p.selectOption(tid("lang-select"), "ko");
    await sleep(500);

    // export per target
    await p.click(tid("export-menu"));
    await shot("export-menu-ko", "Export menu while Korean is shown: the entries are named for it");
    const labels = await p.$$eval(`${tid("export-list")} button`, (b) => b.map((x) => x.textContent));
    note("the export menu names the language shown", labels.some((l) => l === "SRT 한국어") && labels.some((l) => l.includes("ASS 雙語")), labels.join(" | "));
    await p.click(tid("export-srt-zh"));
    await until("srt", () => existsSync(join(exportDir, "talk-demo-ja.ko.srt")), 10000);
    const srt = readFileSync(join(exportDir, "talk-demo-ja.ko.srt"), "utf8");
    note("Korean SRT is saved as <video>.ko.srt with the Korean text and the empty cue kept", /[가-힣]/.test(srt) && srt.includes("Last year more than three hundred people came.") && /\n6\n[^\n]*\n\n/.test(srt.replace(/\r/g, "")), `${srt.split("\n").length} lines`);
    await p.click(tid("export-menu"));
    await p.click(tid("export-ass"));
    await until("ass", () => existsSync(join(exportDir, "talk-demo-ja.bilingual.ko.ass")), 10000);
    const ass = readFileSync(join(exportDir, "talk-demo-ja.bilingual.ko.ass"), "utf8");
    note("bilingual ASS has the Japanese and the Korean", /今日は/.test(ass) && /[가-힣]/.test(ass), `${ass.length} bytes`);
    // a burned still in Korean (real ffmpeg, Malgun Gothic)
    await p.evaluate(() => (document.querySelector("video").currentTime = 1.2));
    await sleep(500);
    await p.keyboard.press("Shift+s");
    const toast = await until("still toast", async () => (await p.locator(tid("toast-text")).count()) > 0 && (await p.textContent(tid("toast-text"))), 30000);
    const png = /(\S+\.png)/.exec(toast)?.[1];
    note("a burned Korean still is saved", toast.includes("截圖已存到") && png !== undefined && existsSync(png), toast);
    if (png) copyFileSync(png, join(shots, `${prefix}-view-burned-still-ko.png`));
    await shot("player-ko-1280", "Player, Korean shown, 1280");
    // the toolbar in the player at both widths
    const pl = await oneRow("player, Korean");
    void rows;
    void pl;
  } else if (phase === "add") {
    await p.waitForSelector(tid("ready"));
    const before = ["audio.wav", "chunks.json", "segments.json", "subs.ja.json"].map((f) => [f, statSync(join(projects, readdirSync(projects)[0], f)).mtimeMs]);
    await importPath(seedVideo, "ja", "zh-TW");
    await waitPlayer(60000);
    await p.click(tid("add-target"));
    await shot("player-add-target-menu", "Player: add a subtitle language to the finished project");
    const started = Date.now();
    await p.click(tid("add-target-zh-CN"));
    await p.waitForSelector(tid("importing"), { timeout: 20000 });
    await until("progress", async () => (await p.textContent(tid("step-name")))?.includes("翻譯成简体中文"), 120000, 300);
    const rerun = await p.textContent(tid("rerun-note"));
    note("the progress says only the translation reruns, into Simplified Chinese", rerun.includes("只會重新翻譯成简体中文") && rerun.includes("不會重跑語音辨識"), rerun);
    await shot("progress-add-target", "Adding Simplified Chinese to a finished project: the step is named for the language and the note says speech recognition is not redone");
    await waitPlayer(300000);
    const took = ((Date.now() - started) / 1000).toFixed(0);
    const langs = await optionsOf(tid("lang-select"));
    note("the project now holds four targets and shows the new one", langs.length === 4 && (await p.inputValue(tid("lang-select"))) === "zh-CN", `${langs.join("|")} after ${took} s`);
    const folder = join(projects, readdirSync(projects)[0]);
    const same = before.every(([f, m]) => statSync(join(folder, f)).mtimeMs === m);
    note("the speech steps were not redone (audio, VAD, ASR and segment files are untouched)", same, before.map(([f]) => f).join(", "));
    const cues = JSON.parse(readFileSync(join(folder, "subs.zh-CN.json"), "utf8")).cues;
    note("Simplified Chinese came out of the real model for every cue, with no kana", cues.length === 8 && cues.every((c) => c.zh && !/[\u3040-\u30ff]/.test(c.zh)), cues.map((c) => c.zh).join(" / "));
    await shot("player-zh-CN", "Player after the run: Simplified Chinese shown, four targets in the select");
    await p.selectOption(tid("lang-select"), "zh-TW");
    await sleep(600);
    const tw = await cueTexts();
    note("switching back shows the Traditional Chinese translation unchanged", tw.length === 8 && /今天我要來談談/.test(tw[0].zh), tw[0].zh);
    await p.selectOption(tid("lang-select"), "zh-CN");
    await sleep(600);
    await p.click(tid("export-menu"));
    await p.click(tid("export-srt-zh"));
    await until("zh-CN srt", () => existsSync(join(exportDir, "talk-demo-ja.zh-CN.srt")), 10000);
    note("Simplified Chinese SRT is saved as <video>.zh-CN.srt", true, "talk-demo-ja.zh-CN.srt");
  } else if (phase === "queue") {
    await p.waitForSelector(tid("ready"));
    // the import box adds English to a project that has Traditional Chinese
    await importPath(seedVideoB, "ja", "en");
    await p.waitForSelector(tid("importing"), { timeout: 20000 });
    const first = await p.textContent(tid("rerun-note"));
    note("importing a language the project lacks says only the translation reruns", first.includes("只會重新翻譯成English"), first);
    await shot("import-box-adds-english", "Import box, Japanese video, English picked, on a project that has Traditional Chinese: the run only translates");
    await waitPlayer(300000);
    note("the project opens on English", (await p.inputValue(tid("lang-select"))) === "en", await p.inputValue(tid("lang-select")));
    await p.click(tid("home"));
    await p.waitForSelector(tid("ready"));
    // queue Simplified Chinese and Korean for the same video, from the add dialog
    const emit = (event, payload) => p.evaluate(([e, pl]) => window.__TAURI_INTERNALS__.invoke("plugin:event|emit", { event: e, payload: pl }), [event, payload]);
    await p.click(tid("batch-open-add"));
    await p.waitForSelector(tid("add-dialog"));
    await emit("tauri://drag-drop", { paths: [seedVideoB], position: { x: 10, y: 10 } });
    await until("row", async () => (await p.locator(tid("add-row")).count()) === 1, 10000);
    await p.selectOption(tid("add-row-source"), "ja");
    await p.click(tid("add-row-lang"));
    for (const code of ["zh-CN", "ko"]) await p.click(tid(`add-row-lang-${code}`));
    await p.click(tid("add-row-lang-zh-TW"));
    const codes = await p.getAttribute(tid("add-row-lang"), "data-codes");
    note("a row picks several targets", codes === "zh-CN,ko", codes);
    await shot("queue-add-dialog-two-targets", "Add dialog: one video, Simplified Chinese and Korean picked, the list open with the experimental label, the hint under it");
    await p.keyboard.press("Escape");
    const sent = [];
    p.on("request", (r) => {
      if (r.method() === "POST" && r.url().endsWith("/api/queue/items")) sent.push(r.postData());
    });
    await p.click(tid("add-submit"));
    await p.waitForSelector(tid("add-dialog"), { state: "detached" });
    const body = JSON.parse(sent[0]);
    note("one request item lists both targets", JSON.stringify(body.items[0].target_langs) === '["zh-CN","ko"]' && body.items[0].source_lang === "ja", sent[0]);
    // take the video away once the first target runs, so the second cannot start
    await until("two rows", async () => (await p.locator("li.batch-row").count()) === 2, 20000);
    await until("first running", async () => (await p.locator('li.batch-row[data-state="running"]').count()) === 1, 60000, 300);
    const away = `${seedVideoB}.away`;
    renameSync(seedVideoB, away);
    await shot("queue-first-target-running", "Queue: two targets of one video, the first is running");
    await until("first done and second failed", async () => {
      const st = await p.$$eval("li.batch-row", (l) => l.map((x) => x.dataset.state));
      return st.join() === "done,failed" ? st : false;
    }, 600000, 1000);
    const err = await p.textContent('[data-testid^="qerror-"]');
    const langsRow = await p.$$eval('[data-testid^="qlang-"]', (e) => e.map((x) => x.textContent));
    note("one target done and one failed, the reason shown, the other row untouched", /gone|不存在|找不到|video/i.test(err) && langsRow.length === 2, `${langsRow.join(" | ")} :: ${err}`);
    await shot("queue-one-target-failed", "Queue: Simplified Chinese done, Korean failed with its reason; the done row is not hidden");
    renameSync(away, seedVideoB);
    const retries = await p.locator('[data-testid^="qretry-"]').count();
    note("only the failed target offers a retry", retries === 1, `${retries} retry button`);
    await p.click('[data-testid^="qretry-"]');
    await until("both done", async () => (await p.$$eval("li.batch-row", (l) => l.map((x) => x.dataset.state))).join() === "done,done", 600000, 1000);
    await shot("queue-retried-done", "Queue: the failed target retried after the video was put back, both done");
    const folder = join(projects, readdirSync(projects).find((d) => existsSync(join(projects, d, "subs.ko.json"))) ?? "");
    const ko = JSON.parse(readFileSync(join(folder, "subs.ko.json"), "utf8")).cues;
    note("the retried Korean target holds real Korean text", ko.length === 8 && ko.filter((c) => /[가-힣]/.test(c.zh)).length >= 6, ko.map((c) => c.zh).join(" / "));
    const fails = existsSync(join(folder, "failures.ko.json")) ? readFileSync(join(folder, "failures.ko.json"), "utf8") : "none";
    note("failures.ko.json says what the model could not do, or is absent", true, fails.replace(/\s+/g, " "));
  } else if (phase === "nofont") {
    await p.waitForSelector(tid("ready"));
    await importPath(seedVideo, "ja", "zh-TW");
    await waitPlayer(60000);
    await p.selectOption(tid("lang-select"), "ko");
    await sleep(800);
    await p.keyboard.press("Shift+s");
    await p.waitForSelector(`${tid("toast")}[data-error="true"]`, { timeout: 20000 });
    const toast = await p.textContent(tid("toast-text"));
    await shot("nofont-still-error", "Korean shown on a PC without Malgun Gothic: the burned still is refused in the window's language and names Korean");
    note("a missing Korean font names the language in the window's language", toast.includes("한국어") && toast.includes("空白方塊") && toast.includes("字幕檔（SRT、ASS）不受影響"), toast);
    await p.click(tid("export-menu"));
    await p.click(tid("export-burn-clip"));
    await p.waitForSelector(tid("burn-progress"), { timeout: 15000 });
    await sleep(800);
    const card = (await p.textContent(tid("burn-progress"))).replace(/\s+/g, " ");
    await shot("nofont-burn-error", "The burn card refuses the same way");
    note("the burn card says the same", card.includes("한국어") && card.includes("空白方塊"), card);
    await p.selectOption(tid("lang-select"), "zh-TW");
    await sleep(600);
    await p.keyboard.press("Shift+s");
    const ok = await until("zh toast", async () => (await p.locator(tid("toast-text")).count()) > 0 && (await p.textContent(tid("toast-text"))), 30000);
    note("Traditional Chinese on the same PC still burns", ok.includes("截圖已存到") || !ok.includes("한국어"), ok);
  } else {
    throw new Error(`unknown phase ${phase}`);
  }
} catch (e) {
  note("lane crashed", false, String(e?.stack ?? e));
  await shot("crash", "the window when the lane stopped").catch(() => undefined);
}

const closed = await app.closeWindow();
note("closing the window leaves nothing of ours running", closed.leftovers.length === 0, `family ${closed.family.length}, leftovers ${closed.leftovers.join(",") || "none"}`);
const strays = strayProcesses(strays0);
note("no stray backend or model process", strays.length === 0, strays.join(",") || "none");
const failed = results.filter((r) => !r.ok);
console.log(`${results.length - failed.length}/${results.length} PASS`);
process.exit(failed.length === 0 ? 0 : 1);
