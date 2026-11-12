// P24a and P24b live check of the video language (英文, 日文, 日文與英文混合) in the real window, driven over CDP only.
// node e2e/p24a-lanes.mjs <phase> <projects-dir> <clips-dir> <shots-dir> [port]
// phase: ja | en | queue | nofont | layout (the toolbar and the file box, on a finished English project plus one short Japanese and one short English import)
//   P24b: mixed (a 10 minute Japanese and English talk end to end) | mixed-queue | unavailable (a user data folder without the Qwen3 files)
// Env: VST_USER_DATA (a disposable copy), WEBVIEW2_USER_DATA_FOLDER (a profile folder of its own),
// P24A_MEDIA (where review PNGs and the recording go), P24A_EXPORTS (where exports land).
// Every action goes through the DevTools protocol. The clipboard, the Windows notification, the
// audio and the open-url/open-folder seams are stubbed or logged, so the desktop stays untouched.
import { execFileSync } from "node:child_process";
import { copyFileSync, existsSync, mkdirSync, readFileSync, readdirSync, rmSync, statSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import { launch, sleep, strayProcesses } from "./lib.mjs";

const [phase, projects, clips, shots, portArg] = process.argv.slice(2);
if (!phase || !projects || !clips || !shots) throw new Error("usage: p24a-lanes.mjs <ja|en|queue|nofont> <projects> <clips> <shots> [port]");
const port = Number(portArg ?? 9424);
const media = process.env.P24A_MEDIA ?? shots;
const exportDir = process.env.P24A_EXPORTS ?? join(shots, "exports");
const ud = process.env.VST_USER_DATA;
if (!ud || !process.env.WEBVIEW2_USER_DATA_FOLDER) throw new Error("set VST_USER_DATA and WEBVIEW2_USER_DATA_FOLDER to disposable folders");
mkdirSync(media, { recursive: true });
mkdirSync(exportDir, { recursive: true });
mkdirSync(shots, { recursive: true });
const FFMPEG = process.env.P24A_FFMPEG ?? "C:/Program Files/ffmpeg-n6.1-latest-win64-gpl-shared-6.1/bin/ffmpeg.exe";
const FFPROBE = FFMPEG.replace(/ffmpeg\.exe$/, "ffprobe.exe");

const reviewPrefix = process.env.P24A_REVIEW_PREFIX ?? "P24a-review";
const results = [];
const note = (lane, ok, detail) => {
  results.push({ lane, ok, detail });
  console.log(`${ok ? "PASS" : "FAIL"} ${lane} ${detail}`);
};
const tid = (id) => `[data-testid="${id}"]`;
const hasKana = (s) => /[\u3040-\u30ff]/.test(s);
const until = async (label, fn, ms = 30000, step = 200) => {
  const end = Date.now() + ms;
  for (;;) {
    const v = await fn();
    if (v) return v;
    if (Date.now() > end) throw new Error(`timeout: ${label}`);
    await sleep(step);
  }
};

const gpuBusy = () => {
  const out = execFileSync("tasklist", { encoding: "utf8" });
  return /whisper-cli|crispasr|llama-server/i.test(out);
};
if (phase !== "nofont" && phase !== "ja-restart" && gpuBusy()) throw new Error("the GPU is busy (whisper-cli, crispasr or llama-server is running)");

const strays0 = strayProcesses();
const app = await launch({
  projects,
  shots,
  port,
  env: { VST_EXPORT_DIR: exportDir, VST_UPDATE_URL: "http://127.0.0.1:9/none.json" },
});
const p = app.page;
console.log(`app pid ${app.pid}, cold start ${app.coldStartMs} ms, phase ${phase}`);

// seams and stubs, before the first click
await p.evaluate(() => {
  Object.defineProperty(HTMLMediaElement.prototype, "muted", { configurable: true, get: () => true, set: () => undefined });
  Object.defineProperty(HTMLMediaElement.prototype, "volume", { configurable: true, get: () => 0, set: () => undefined });
  window.__clip = "none";
  Object.defineProperty(navigator, "clipboard", {
    configurable: true,
    value: {
      write: async (items) => {
        const png = await items[0].getType("image/png");
        const bitmap = await createImageBitmap(png);
        window.__clip = `${bitmap.width}x${bitmap.height}`;
      },
    },
  });
  const inner = window.__TAURI_INTERNALS__;
  const invoke = inner.invoke.bind(inner);
  window.__notified = 0;
  inner.invoke = (cmd, ...rest) => {
    if (typeof cmd === "string" && cmd.startsWith("plugin:notification|")) {
      window.__notified += 1;
      return Promise.resolve(cmd.endsWith("is_permission_granted") ? false : "denied");
    }
    return invoke(cmd, ...rest);
  };
});
const seamLogs = { url: join(shots, "open-url.log"), folder: join(shots, "open-folder.log") };
note("seams on", true, `VST_OPEN_URL_LOG, VST_OPEN_FOLDER_LOG in ${shots}; VST_UPDATE_URL is a dead local address; clipboard, audio and notifications stubbed in the page`);

const session = await p.context().newCDPSession(p);
const { windowId } = await session.send("Browser.getWindowForTarget");
const resize = async (width, height) => {
  await session.send("Browser.setWindowBounds", { windowId, bounds: { windowState: "normal", width, height } });
  await sleep(700);
};

// recording: screencast frames, a caption bar that the screenshots hide
const frameDir = join(shots, `frames-${phase}`);
rmSync(frameDir, { recursive: true, force: true });
mkdirSync(frameDir, { recursive: true });
const frames = [];
session.on("Page.screencastFrame", (f) => {
  writeFileSync(join(frameDir, `${String(frames.length).padStart(5, "0")}.jpg`), Buffer.from(f.data, "base64"));
  frames.push(f.metadata.timestamp);
  session.send("Page.screencastFrameAck", { sessionId: f.sessionId }).catch(() => undefined);
});
await session.send("Page.startScreencast", { format: "jpeg", quality: 80, maxWidth: 1280, maxHeight: 800, everyNthFrame: 1 });
const caption = (text) =>
  p.evaluate((t) => {
    let el = document.getElementById("p24a-cap");
    if (!el) {
      el = document.createElement("div");
      el.id = "p24a-cap";
      el.style.cssText =
        "position:fixed;left:50%;bottom:6px;transform:translateX(-50%);z-index:99999;padding:4px 12px;border-radius:8px;background:rgba(0,0,0,.78);color:#ffd699;font:13px 'Segoe UI','Microsoft JhengHei',sans-serif;pointer-events:none;white-space:nowrap";
      document.body.appendChild(el);
    }
    el.textContent = t;
    el.style.display = t ? "block" : "none";
  }, text);
const review = async (name, text) => {
  await caption("");
  await sleep(150);
  const file = join(media, `${reviewPrefix}-${name}.png`);
  await p.screenshot({ path: file });
  await caption(text ?? "");
  return file;
};
const step = async (text, ms = 900) => {
  await caption(text);
  await sleep(ms);
};

const header = () =>
  p.evaluate(() => {
    const h = document.querySelector("header");
    const mids = [...h.querySelectorAll("button, input, select")].map((e) => {
      const b = e.getBoundingClientRect();
      return Math.round(b.top + b.height / 2);
    });
    return { height: h.getBoundingClientRect().height, spread: Math.max(...mids) - Math.min(...mids), n: mids.length, vw: innerWidth };
  });
const oneRow = async (label) => {
  const out = [];
  for (const [w, h] of [[1280, 720], [960, 600]]) {
    await resize(w, h);
    const m = await header();
    out.push(`${w}: header ${m.height.toFixed(1)} px, top spread ${m.spread}`);
    note(`toolbar one row at ${w} (${label})`, m.height < 60 && m.spread <= 3, `header ${m.height.toFixed(1)} px high, ${m.n} controls, vertical centers spread ${m.spread} px, viewport ${m.vw}`);
  }
  await resize(1280, 720);
  return out;
};

// the import box in the toolbar must stay readable. Widths are what main measured before the picker existed.
const fileBox = () => p.evaluate(() => document.querySelector('[data-testid="video-path"]').getBoundingClientRect().width);
const fileBoxChecks = async (label, min) => {
  const out = {};
  for (const [w, h] of [[1280, 720], [960, 600]]) {
    await resize(w, h);
    const width = await fileBox();
    out[w] = width;
    note(`file box wide enough at ${w} (${label})`, width >= min[w], `video-path ${width.toFixed(1)} px wide, needs ${min[w]}`);
  }
  await resize(1280, 720);
  return out;
};
const PLAYER_BOX = { 1280: 130, 960: 66 };
const HOME_BOX = { 1280: 780, 960: 590 };
const HOME_BOX_MIXED = { 1280: 700, 960: 520 };
const MIXED_NOTE = "日英混合影片目前只輸出繁體中文字幕，需要 24 GB 的模型組。";

const folderOf = (needle) => {
  for (const d of readdirSync(projects)) {
    const f = join(projects, d, "project.json");
    if (existsSync(f) && JSON.parse(readFileSync(f, "utf8")).video_path.includes(needle)) return join(projects, d);
  }
  return null;
};
// English cues keep the first release layout on disk (text under `en`, no `lang`), so both layouts are read as `src` and `lang`.
const diskCues = (folder) => JSON.parse(readFileSync(join(folder, "subs.zh-TW.json"), "utf8")).cues.map((c) => ({ ...c, lang: c.lang ?? "en", src: c.src ?? c.en }));
const row = (n) => tid(`cue-${n}`);
const zhOf = (n) => p.textContent(`${row(n)} .zh`);
const srcOf = (n) =>
  p.evaluate((sel) => {
    const e = document.querySelector(sel).cloneNode(true);
    e.querySelectorAll(".lang-mark").forEach((m) => m.remove());
    return e.textContent;
  }, `${row(n)} .src`);
const startOf = async (n) => Number(await p.getAttribute(row(n), "data-start"));
const clock = (ms) => `${Math.floor(ms / 60000)}:${String(Math.floor(ms / 1000) % 60).padStart(2, "0")}.${String(ms % 1000).padStart(3, "0")}`;
const noOverlap = (cues) => cues.every((c, i) => c.end_ms > c.start_ms && (i === 0 || c.start_ms >= cues[i - 1].end_ms));
const errorVisible = (n) =>
  p.evaluate((sel) => {
    const e = document.querySelector(sel);
    const list = document.querySelector('[data-testid="cue-list"]');
    if (!e) return false;
    const a = e.getBoundingClientRect();
    const b = list.getBoundingClientRect();
    return a.top >= b.top - 1 && a.bottom <= b.bottom + 1;
  }, `${row(n)} [data-testid="edit-error"]`);
const beginEdit = async (n) => {
  await p.dblclick(`${row(n)} button`);
  await p.waitForSelector(`${row(n)} ${tid("cue-editor")}`);
};
const jobBodies = [];
p.on("request", (r) => {
  if (r.method() === "POST" && /\/api\/projects\/[^/]+\/jobs$/.test(r.url())) jobBodies.push(r.postData());
});

async function importVideo(path, lang) {
  await p.selectOption(tid("source-lang"), lang);
  await p.fill(tid("video-path"), path);
  await p.click(tid("import"));
}

async function watchProgress(prefix) {
  await p.waitForSelector(tid("importing"), { timeout: 20000 });
  let shot1 = false;
  let shot2 = false;
  const seen = new Set();
  const started = Date.now();
  for (;;) {
    if ((await p.locator(`${tid("cue-list")} li`).count()) > 0) break;
    const err = await p.locator(tid("error")).count();
    if (err) throw new Error(`import failed: ${await p.textContent(tid("error"))}`);
    const name = await p.textContent(tid("step-name")).catch(() => null);
    const pct = await p.textContent(tid("percent")).catch(() => null);
    if (name) seen.add(name.trim());
    if (!shot1 && name?.includes("語音辨識")) {
      shot1 = true;
      await review(`${prefix}-progress-asr`, `${prefix}: 語音辨識 ${pct ?? ""}`);
    }
    if (!shot2 && name?.includes("翻譯")) {
      shot2 = true;
      await review(`${prefix}-progress-translate`, `${prefix}: 翻譯 ${pct ?? ""}`);
    }
    if (Date.now() - started > 25 * 60 * 1000) throw new Error("processing took over 25 minutes");
    await sleep(700);
  }
  return { seconds: (Date.now() - started) / 1000, steps: [...seen] };
}

async function playerChecks(prefix, { japanese, mixed = false }) {
  const cueCount = await p.locator(`${tid("cue-list")} li`).count();
  await p.evaluate(() => document.querySelector("video").pause());
  const idx = Math.min(cueCount, 30);
  const start = (await startOf(idx)) / 1000;
  await p.click(`${row(idx)} button`);
  await p.waitForFunction((t) => Math.abs(document.querySelector("video").currentTime - t) < 0.6, start);
  await p.evaluate(() => document.querySelector("video").pause());
  await sleep(500);
  const geo = await p.evaluate(() => {
    const r = (s) => document.querySelector(s).getBoundingClientRect();
    const v = r('[data-testid="video"]');
    const s = r('[data-testid="subtitle"]');
    return { vBottom: v.bottom, sTop: s.top, w: innerWidth, lines: [...document.querySelectorAll('[data-testid="subtitle"] p')].map((e) => ({ side: e.dataset.lang, lang: e.lang, text: e.textContent })) };
  });
  note(`${prefix} subtitle under the video`, geo.sTop >= geo.vBottom - 1, `video ends ${geo.vBottom.toFixed(0)}, subtitle starts ${geo.sTop.toFixed(0)}`);
  await p.click(tid("mode-both"));
  await sleep(300);
  const both = await p.evaluate(() => [...document.querySelectorAll('[data-testid="subtitle"] p')].map((e) => ({ side: e.dataset.lang, lang: e.lang, cueLang: e.dataset.cueLang ?? null, text: e.textContent })));
  const srcLine = (l) => {
    if (l.side !== "src") return false;
    const isJa = hasKana(l.text) || /[\u4e00-\u9fff]/.test(l.text);
    if (mixed) return (l.lang === "ja" || l.lang === "en") && l.cueLang === l.lang && (l.lang === "ja" ? isJa : /[A-Za-z]/.test(l.text));
    return l.lang === (japanese ? "ja" : "en") && (japanese ? isJa : /[A-Za-z]/.test(l.text));
  };
  note(
    `${prefix} bilingual shows original and Chinese`,
    both.length === 2 && both.some(srcLine) && both.some((l) => l.side === "zh" && /[\u4e00-\u9fff]/.test(l.text) && !hasKana(l.text)),
    JSON.stringify(both),
  );
  const labels = await p.evaluate(() => ["en", "zh", "both"].map((m) => document.querySelector(`[data-testid="mode-${m}"]`).textContent));
  note(`${prefix} mode toggle says 原文`, labels[0] === "原文" && labels[2] === "雙語", `labels ${labels.join(" | ")}`);
  const m = await oneRow(prefix);
  await fileBoxChecks(`player, ${prefix}`, PLAYER_BOX);
  await review(`${prefix}-player-both-1280`, `${prefix}: 雙語（原文加繁體中文）`);
  await resize(960, 600);
  await review(`${prefix}-player-both-960`, `${prefix}: 雙語，960 px 寬，工具列一排`);
  await resize(1280, 720);
  for (const mode of ["en", "zh", "both"]) {
    await p.click(tid(`mode-${mode}`));
    await sleep(400);
    const shown = await p.evaluate(() => [...document.querySelectorAll('[data-testid="subtitle"] p')].map((e) => e.dataset.lang));
    const want = mode === "en" ? ["src"] : mode === "zh" ? ["zh"] : ["src", "zh"];
    note(`${prefix} mode ${mode}`, [...shown].sort().join() === want.sort().join(), `lines ${shown.join()}`);
    if (mode !== "both") await review(`${prefix}-player-${mode === "en" ? "source" : "zh"}`, `${prefix}: ${mode === "en" ? "只看原文" : "只看繁體中文"}`);
  }
  await p.click(tid("mode-both"));
  return { cueCount, m };
}

async function offsetCheck(prefix, folder) {
  const idx = 12;
  const t0 = (await startOf(idx)) / 1000 + 0.3;
  await p.evaluate((x) => (document.querySelector("video").currentTime = x), t0);
  await sleep(500);
  const active = () => p.evaluate(() => [...document.querySelectorAll('[data-testid^="cue-"][data-active="true"]')].map((e) => e.dataset.testid).join());
  const before = await active();
  await p.click(tid("ctl-offset"));
  for (let i = 0; i < 20; i++) await p.click(tid("offset-plus"));
  await review(`${prefix}-offset`, `${prefix}: 字幕偏移 +2.0 秒`);
  const off = await p.textContent(tid("offset-value"));
  await sleep(600);
  const after = await active();
  const disk = JSON.parse(readFileSync(join(folder, "playback.json"), "utf8")).offset_ms;
  note(`${prefix} subtitle offset`, off.includes("+2.0") && after !== before && disk === 2000, `offset ${off}; at ${t0.toFixed(1)} s active ${before} became ${after}; playback.json offset_ms ${disk}`);
  await p.click(tid("offset-reset"));
  await p.keyboard.press("Escape");
  await sleep(500);
  const back = await active();
  note(`${prefix} offset reset`, back === before, `active ${back}`);
}

async function editChecks(prefix, folder, { japanese }) {
  const n = 5;
  const EDIT = japanese ? "人工校對：這是我改的一句。" : "人工校對：這一句是我改的。";
  const srcBefore = await srcOf(n);
  await beginEdit(n);
  await review(`${prefix}-edit-open`, `${prefix}: 編輯第 ${n} 條字幕`);
  await p.fill(`${row(n)} ${tid("edit-text")}`, EDIT);
  await p.press(`${row(n)} ${tid("edit-text")}`, "Enter");
  await p.waitForSelector(`${row(n)}[data-editing="false"]`);
  const saved = diskCues(folder).find((c) => c.zh === EDIT);
  note(`${prefix} edit saved`, (await zhOf(n)) === EDIT && !!saved && (await p.locator(`${row(n)} ${tid("edited-mark")}`).count()) === 1 && saved[japanese ? "src" : "en"] === srcBefore, `row shows the text with the edited mark; disk cue ${saved?.id}; source line kept "${srcBefore}"`);
  await review(`${prefix}-edit-saved`, `${prefix}: 已儲存，旁邊有鉛筆記號`);

  const next = await startOf(n + 1);
  const cur = await startOf(n);
  const overlapEnd = Math.min(next + 400, cur + 6900);
  const diskBefore = readFileSync(join(folder, "subs.zh-TW.json"), "utf8");
  await beginEdit(n);
  const cases = [
    ["overlap", clock(overlapEnd), "重疊"],
    ["too long", clock(cur + 7600), "7 秒"],
    ["end before start", clock(cur - 500), "早於"],
  ];
  for (const [name, end, word] of cases) {
    await p.fill(`${row(n)} ${tid("edit-end")}`, end);
    await p.press(`${row(n)} ${tid("edit-end")}`, "Enter");
    await sleep(300);
    const err = await p.textContent(`${row(n)} ${tid("edit-error")}`).catch(() => null);
    note(`${prefix} bad timing ${name}`, !!err && err.includes(word), `message "${err}"`);
    if (name === "overlap") await review(`${prefix}-edit-overlap`, `${prefix}: 時間重疊被拒絕`);
  }
  note(`${prefix} refused timings are not saved`, readFileSync(join(folder, "subs.zh-TW.json"), "utf8") === diskBefore, "subs.zh-TW.json unchanged");
  await p.press(`${row(n)} ${tid("edit-text")}`, "Escape");
  await sleep(300);

  // the source line: typing on it says it cannot be changed
  await beginEdit(n + 2);
  await p.focus(`${row(n + 2)} ${tid("edit-source")}`);
  await p.keyboard.type("x");
  await sleep(250);
  const typed = await p.textContent(`${row(n + 2)} ${tid("edit-error")}`).catch(() => null);
  const typedVisible = await errorVisible(n + 2);
  const offsetAfter = await p.textContent(tid("offset-value"));
  note(`${prefix} typing on the source line`, typed === "原文不能修改，只能改譯文和時間" && typedVisible && offsetAfter.includes("+0.0"), `message "${typed}", fully inside the cue list ${typedVisible}, the key did not reach the player shortcuts (offset ${offsetAfter})`);
  await review(`${prefix}-edit-source-locked`, `${prefix}: 原文不能在這裡修改`);
  await p.press(`${row(n + 2)} ${tid("edit-text")}`, "Escape").catch(() => undefined);
  await sleep(300);

  // the backend itself refuses a changed source line with 422, and the window shows it
  let intercepted = 0;
  await p.route("**/subtitles?*", async (route) => {
    const req = route.request();
    if (req.method() !== "PUT") return route.continue();
    intercepted += 1;
    const body = JSON.parse(req.postData());
    body.cues[0].en += japanese ? "あ" : "x";
    return route.continue({ postData: JSON.stringify(body) });
  });
  const diskPre = readFileSync(join(folder, "subs.zh-TW.json"), "utf8");
  const m = n + 3;
  await beginEdit(m);
  await p.fill(`${row(m)} ${tid("edit-text")}`, "會被後端拒絕的修改");
  await p.press(`${row(m)} ${tid("edit-text")}`, "Enter");
  await sleep(700);
  const refused = await p.textContent(`${row(m)} ${tid("edit-error")}`).catch(() => null);
  const refusedVisible = await errorVisible(m);
  await p.unroute("**/subtitles?*");
  note(`${prefix} 422 for a changed source line`, intercepted === 1 && refused === "原文不能修改，只能改譯文和時間" && refusedVisible && readFileSync(join(folder, "subs.zh-TW.json"), "utf8") === diskPre, `PUT intercepted ${intercepted} time(s), the backend answered 422 english_changed, the window shows "${refused}", disk unchanged`);
  await review(`${prefix}-edit-422`, `${prefix}: 後端回 422，畫面顯示原因`);
  await p.press(`${row(m)} ${tid("edit-text")}`, "Escape");
  await sleep(300);
  const cues = diskCues(folder);
  note(`${prefix} times never overlap on disk`, noOverlap(cues), `${cues.length} cues, sorted, no overlap`);
  return EDIT;
}

async function exportChecks(prefix, folder, stem, source, EDIT) {
  const labels = await p.evaluate(async () => {
    document.querySelector('[data-testid="export-menu"]').click();
    await new Promise((r) => setTimeout(r, 200));
    const out = [...document.querySelectorAll('[data-testid="export-list"] button')].map((b) => b.textContent.trim());
    return out;
  });
  await review(`${prefix}-export-menu`, `${prefix}: 匯出選單`);
  await p.keyboard.press("Escape");
  const files = {};
  for (const id of ["srt-en", "srt-zh", "srt-bilingual", "ass", "vtt", "summary"]) {
    await p.click(tid("export-menu"));
    const since = Date.now() - 500;
    await p.click(tid(`export-${id}`));
    await sleep(1200);
    files[id] = readdirSync(exportDir).find((f) => statSync(join(exportDir, f)).mtimeMs >= since) ?? null;
  }
  const text = (id) => (files[id] ? readFileSync(join(exportDir, files[id]), "utf8") : "");
  const ja = source !== "en";
  const fileTag = source.replace("+", "-");
  note(`${prefix} export menu says 原文`, labels.some((l) => l.includes("SRT 原文")) && !labels.some((l) => l.includes("英文")), labels.join(" | "));
  note(`${prefix} export file names`, files["srt-en"] === `${stem}.${fileTag}.srt`, JSON.stringify(files));
  note(`${prefix} source srt`, ja ? hasKana(text("srt-en")) && !text("srt-en").includes(EDIT) : /[A-Za-z]{4}/.test(text("srt-en")) && !text("srt-en").includes(EDIT), `${text("srt-en").length} chars`);
  note(`${prefix} zh srt has the edit and no kana`, text("srt-zh").includes(EDIT) && !hasKana(text("srt-zh")), `${text("srt-zh").length} chars`);
  note(`${prefix} bilingual srt has both`, text("srt-bilingual").includes(EDIT) && (ja ? hasKana(text("srt-bilingual")) : /[A-Za-z]{4}/.test(text("srt-bilingual"))), `${text("srt-bilingual").length} chars`);
  note(`${prefix} ass and vtt`, text("ass").includes("[Events]") && text("ass").includes(EDIT.slice(0, 6)) && text("vtt").startsWith("WEBVTT") && text("vtt").includes(EDIT), `ass ${text("ass").length}, vtt ${text("vtt").length} chars`);
  if (source === "ja+en") note(`${prefix} mixed source srt holds both languages`, hasKana(text("srt-en")) && /[A-Za-z]{4}/.test(text("srt-en")) && /[A-Za-z]{4}/.test(text("srt-bilingual")), `kana ${hasKana(text("srt-en"))}, Latin words ${/[A-Za-z]{4}/.test(text("srt-en"))}`);
  note(`${prefix} summary`, text("summary") === readFileSync(join(folder, "summary.md"), "utf8"), "summary.md equals the project's");
  return files;
}

async function shotAndBurn(prefix, folder, { japanese }) {
  const shotsDir = join(ud, "screenshots");
  mkdirSync(shotsDir, { recursive: true });
  const had = new Set(readdirSync(shotsDir));
  const cueN = 40;
  const t = (await startOf(cueN)) / 1000 + 0.4;
  await p.evaluate((x) => { const v = document.querySelector("video"); v.pause(); v.currentTime = x; }, t);
  await sleep(600);
  await p.evaluate(() => document.activeElement?.blur());
  await p.keyboard.press("s");
  await p.waitForSelector(tid("toast-action"), { timeout: 20000 });
  const toast1 = await p.textContent(tid("toast-text"));
  await p.keyboard.press("Shift+s");
  await p.waitForFunction(() => document.querySelector('[data-testid="toast-text"]')?.textContent?.includes("_sub"), null, { timeout: 30000 });
  const toast2 = await p.textContent(tid("toast-text"));
  await review(`${prefix}-screenshot-toast`, `${prefix}: 截圖已存檔（剪貼簿與資料夾都被攔下）`);
  const pngs = readdirSync(shotsDir).filter((f) => f.endsWith(".png") && !had.has(f));
  const plain = pngs.find((f) => !f.includes("_sub"));
  const burned = pngs.find((f) => f.includes("_sub"));
  if (burned) copyFileSync(join(shotsDir, burned), join(media, `${reviewPrefix}-${prefix}-screenshot-burned-file.png`));
  const clip = await p.evaluate(() => window.__clip);
  note(`${prefix} screenshot plain and burned`, !!plain && !!burned && toast1.includes("截圖已存到") && clip !== "none", `S saved ${plain}, Shift+S saved ${burned}, clipboard stub got ${clip}`);
  await p.click(tid("toast-action"));
  await sleep(500);
  const opened = existsSync(seamLogs.folder) ? readFileSync(seamLogs.folder, "utf8").trim().split(/\r?\n/) : [];
  note(`${prefix} open folder goes to the seam`, opened.length >= 1 && opened.at(-1).toLowerCase().includes((burned ?? "").toLowerCase().slice(0, 12)), `seam log: ${opened.at(-1)}`);

  // burned-in export of 30 s from here
  await p.evaluate((x) => (document.querySelector("video").currentTime = x), t);
  await sleep(400);
  await p.click(tid("export-menu"));
  await p.click(tid("export-burn-clip"));
  await p.waitForSelector(tid("burn-progress"));
  await p.waitForFunction(() => Number(document.querySelector('[data-testid="burn-percent"]')?.textContent?.replace("%", "")) >= 1, null, { timeout: 90000 }).catch(() => undefined);
  await review(`${prefix}-burn-progress`, `${prefix}: 燒入字幕進行中`);
  await p.waitForFunction(() => !document.querySelector('[data-testid="burn-progress"]'), null, { timeout: 600000 });
  const doneText = await p.textContent(tid("toast-text"));
  await review(`${prefix}-burn-done`, `${prefix}: 燒入完成`);
  const m = /已匯出燒入字幕的影片 (.+?)(?:，|$)/.exec(doneText) ?? /(\S+\.mp4)/.exec(doneText);
  const out = m?.[1]?.trim();
  let detail = `toast "${doneText.slice(0, 90)}"`;
  let ok = !!out && existsSync(out);
  if (ok) {
    const dur = Number(execFileSync(FFPROBE, ["-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", out], { encoding: "utf8" }).trim());
    const frameOut = join(media, `${reviewPrefix}-${prefix}-burned-frame.png`);
    const inWindow = diskCues(folder).filter((c) => c.start_ms / 1000 >= t + 1 && c.end_ms / 1000 <= t + 29);
    const cue = inWindow[1] ?? inWindow[0];
    const at = cue ? ((cue.start_ms + cue.end_ms) / 2000 - t).toFixed(2) : "6";
    execFileSync(FFMPEG, ["-v", "error", "-y", "-ss", at, "-i", out, "-frames:v", "1", frameOut]);
    const decode = execFileSync(FFMPEG, ["-v", "error", "-i", out, "-f", "null", "-"], { encoding: "utf8" });
    ok = dur > 28 && dur < 32 && decode.trim() === "" && statSync(frameOut).size > 20000;
    detail = `${out}, ${dur.toFixed(1)} s, ${(statSync(out).size / 1e6).toFixed(1)} MB, full decode printed ${JSON.stringify(decode.trim())}, frame at ${at} s (cue ${cue?.id}: ${cue?.zh}) saved to ${frameOut}`;
  }
  note(`${prefix} burned-in export plays`, ok, detail);
  return { out };
}

async function libraryChecks(prefix, expect) {
  await p.click(tid("home"));
  await p.waitForSelector(tid("library-list"));
  await sleep(1500);
  const chips = await p.evaluate(() => [...document.querySelectorAll('[data-testid="library-list"] li')].map((li) => ({ title: li.querySelector(".lib-title")?.textContent, tags: [...li.querySelectorAll(".chip")].map((c) => c.textContent) })));
  for (const [needle, tag] of expect) {
    const item = chips.find((c) => c.title?.includes(needle));
    const want = tag === true ? "日文影片" : tag;
    const has = want ? (item?.tags.includes(want) ?? false) : !(item?.tags ?? []).some((t) => /影片|混合/.test(t));
    note(`${prefix} library tag ${want ? `${want} present` : "absent"} for ${needle}`, item !== undefined && has, JSON.stringify(item));
  }
  const show = () => p.evaluate(() => document.querySelector('[data-testid="library-list"]').scrollIntoView({ block: "center" }));
  await show();
  await sleep(300);
  await review(`${prefix}-library-1280`, `${prefix}: 媒體庫，日文影片有小標籤`);
  await resize(960, 600);
  await show();
  await sleep(500);
  await review(`${prefix}-library-960`, `${prefix}: 媒體庫 960 px`);
  await resize(1280, 720);
}

async function homeChecks() {
  await step("首頁：影片語言預設是英文", 900);
  const first = await p.inputValue(tid("source-lang"));
  const opts = await p.locator(`${tid("source-lang")} option`).allInnerTexts();
  note("video language picker", first === "en" && opts.length === 3 && opts[0] === "英文" && opts[1] === "日文" && opts[2].startsWith("日文與英文混合"), `default ${first}, options ${opts.join()}`);
  note("no note for English", (await p.locator(tid("source-note")).count()) === 0, "no note under the toolbar");
  await oneRow("home, English");
  await fileBoxChecks("home, English", HOME_BOX);
  await review("home-english-1280", "首頁：影片語言 英文（預設）");
  await p.selectOption(tid("source-lang"), "ja");
  await sleep(300);
  const noteText = await p.textContent(tid("source-note"));
  note("note for Japanese", noteText.includes("日文") && noteText.includes("繁體中文"), `"${noteText}"`);
  await oneRow("home, Japanese note");
  await review("home-japanese-1280", "首頁：選日文，顯示一行說明");
  await resize(960, 600);
  await review("home-japanese-960", "首頁：選日文，960 px 寬");
  await resize(1280, 720);
  const mixedOption = p.locator(`${tid("source-lang")} option[value="ja+en"]`);
  if (!(await mixedOption.evaluate((e) => e.disabled))) {
    await p.selectOption(tid("source-lang"), "ja+en");
    await sleep(300);
    const mixedNote = await p.textContent(tid("source-note"));
    note("note for the mixed choice", mixedNote === MIXED_NOTE, `"${mixedNote}"`);
    await oneRow("home, mixed note");
    await fileBoxChecks("home, mixed", HOME_BOX_MIXED);
    await review("home-mixed-1280", "首頁：選日文與英文混合，顯示一行說明");
    await resize(960, 600);
    await review("home-mixed-960", "首頁：選日文與英文混合，960 px 寬");
    await resize(1280, 720);
  }
  await p.selectOption(tid("source-lang"), "en");
}

async function mixedChecks(label, folder, { quiet = false } = {}) {
  await p.click(tid("mode-both"));
  await p.evaluate(() => document.querySelector('[data-testid="cue-list"]').scrollTo(0, 0));
  await sleep(300);
  const disk = diskCues(folder);
  const rows = await p.evaluate(() =>
    [...document.querySelectorAll('[data-testid="cue-list"] > li')].map((li) => {
      const src = li.querySelector(".src");
      const mark = li.querySelector('[data-testid="lang-mark"]');
      const clone = src?.cloneNode(true);
      clone?.querySelectorAll(".lang-mark").forEach((m) => m.remove());
      return { lang: src?.lang ?? null, cueLang: src?.dataset.cueLang ?? null, mark: mark?.textContent ?? null, markLang: mark?.dataset.cueLang ?? null, text: clone?.textContent ?? "" };
    }),
  );
  const mapMark = { ja: "日", en: "英" };
  const same = rows.length === disk.length && rows.every((r, i) => r.lang === disk[i].lang && r.cueLang === disk[i].lang && r.markLang === disk[i].lang && r.mark === mapMark[disk[i].lang] && r.text === disk[i].src);
  const ja = disk.filter((c) => c.lang === "ja").length;
  const en = disk.filter((c) => c.lang === "en").length;
  const scriptOk = rows.every((r) => (r.lang === "ja" ? hasKana(r.text) || /[一-鿿]/.test(r.text) : /[A-Za-z]/.test(r.text)));
  note(`${label}: each cue row carries its own language mark`, same && scriptOk && ja > 10 && en > 10, `${rows.length} rows against ${disk.length} on disk; ${ja} Japanese (日) and ${en} English (英); lang attribute, data-cue-lang, mark and text equal the file for every row`);
  let flips = 0;
  for (let i = 1; i < disk.length; i++) if (disk[i].lang !== disk[i - 1].lang) flips += 1;
  note(`${label}: neighbours of different languages stay separate cues`, flips > 5 && rows.length === disk.length, `${flips} language changes between neighbouring cues, one row each (${rows.length} rows)`);
  if (quiet) return;
  await review("mixed-cue-marks", "mixed: 清單每條字幕有日或英記號，原文用該條的語言");
  for (const mode of ["en", "zh", "both"]) {
    await p.click(tid(`mode-${mode}`));
    await sleep(250);
    const marks = await p.locator(tid("lang-mark")).count();
    note(`${label}: marks in mode ${mode}`, mode === "zh" ? marks === 0 : marks === disk.length, `${marks} marks`);
  }
  const jaIdx = disk.findIndex((c) => c.lang === "ja");
  const enIdx = disk.findIndex((c) => c.lang === "en");
  for (const [lang, idx] of [["ja", jaIdx], ["en", enIdx]]) {
    const n = idx + 1;
    await p.click(`${row(n)} button`);
    await sleep(700);
    await p.evaluate(() => document.querySelector("video").pause());
    const line = await p.evaluate(() => {
      const e = document.querySelector('[data-testid="subtitle"] p[data-lang="src"]');
      return e ? { lang: e.lang, cueLang: e.dataset.cueLang, text: e.textContent, font: getComputedStyle(e).fontFamily } : null;
    });
    note(`${label}: the player line of a ${lang} cue follows that cue`, line !== null && line.lang === lang && line.cueLang === lang && line.text === disk[idx].src, JSON.stringify(line));
    await review(`mixed-player-${lang}-cue`, `mixed: ${lang === "ja" ? "日文" : "英文"}字幕，原文行是${lang === "ja" ? "日文" : "英文"}`);
  }
  for (const lang of ["ja", "en"]) {
    const n = disk.findIndex((c) => c.lang === lang) + 1;
    await beginEdit(n);
    const editorSrc = await p.evaluate((sel) => {
      const e = document.querySelector(sel);
      return { lang: e.lang, cueLang: e.dataset.cueLang, mark: e.querySelector(".lang-mark")?.textContent ?? null };
    }, `${row(n)} ${tid("edit-source")}`);
    note(`${label}: the editor's source line of a ${lang} cue`, editorSrc.lang === lang && editorSrc.cueLang === lang && editorSrc.mark === mapMark[lang], JSON.stringify(editorSrc));
    if (lang === "en") await review("mixed-editor-en", "mixed: 編輯英文字幕，原文行有英記號");
    await p.press(`${row(n)} ${tid("edit-text")}`, "Escape");
    await sleep(250);
  }
}

async function finish() {
  await session.send("Page.stopScreencast");
  await sleep(300);
  const url = existsSync(seamLogs.url) ? readFileSync(seamLogs.url, "utf8").trim() : "";
  const notified = await p.evaluate(() => window.__notified).catch(() => 0);
  note("no browser or Explorer opened", true, `open-url log: ${JSON.stringify(url)}; notification calls stubbed: ${notified}`);
  let list = "";
  for (let i = 0; i < frames.length; i++) {
    const d = i + 1 < frames.length ? Math.max(0.04, Math.min(2.2, frames[i + 1] - frames[i])) : 0.8;
    list += `file '${String(i).padStart(5, "0")}.jpg'\nduration ${d.toFixed(3)}\n`;
  }
  list += `file '${String(frames.length - 1).padStart(5, "0")}.jpg'\n`;
  writeFileSync(join(frameDir, "list.txt"), list);
  execFileSync(FFMPEG, ["-v", "error", "-y", "-f", "concat", "-safe", "0", "-i", join(frameDir, "list.txt"), "-vf", "scale=1280:800:force_original_aspect_ratio=decrease,pad=1280:800:(ow-iw)/2:(oh-ih)/2,fps=15,format=yuv420p", "-c:v", "libx264", "-crf", "26", join(shots, `phase-${phase}.mp4`)]);
  console.log(`recording ${frames.length} frames -> ${join(shots, `phase-${phase}.mp4`)}`);
  const info = await app.closeWindow();
  note("shutdown", info.leftovers.length === 0 && strayProcesses(strays0).length === 0, `family ${JSON.stringify(info.family)} leftovers ${JSON.stringify(info.leftovers)} stray ${JSON.stringify(strayProcesses(strays0))}`);
  const failed = results.filter((r) => !r.ok);
  writeFileSync(join(shots, `results-${phase}.json`), JSON.stringify(results, null, 1));
  console.log(`\n${phase}: ${results.length - failed.length}/${results.length} PASS`);
  process.exit(failed.length ? 1 : 0);
}

try {
  await resize(1280, 720);
  if (phase === "ja") {
    const video = join(clips, "cedec-25-35.mp4");
    await homeChecks();
    await step("匯入日文影片：影片語言選日文", 600);
    await p.selectOption(tid("source-lang"), "ja");
    await review("ja-import-form", "匯入：影片語言 日文，路徑已貼上");
    await importVideo(video, "ja");
    const prog = await watchProgress("ja");
    const body = jobBodies.at(-1);
    note("job body carries source_lang ja", body !== undefined && JSON.parse(body).source_lang === "ja", `POST /jobs body ${body}`);
    const folder = folderOf("cedec-25-35");
    const proj = JSON.parse(readFileSync(join(folder, "project.json"), "utf8"));
    note("japanese project processed", proj.source_lang === "ja" && existsSync(join(folder, "ja.srt")) && existsSync(join(folder, "subs.zh-TW.json")), `${prog.seconds.toFixed(0)} s, steps seen ${prog.steps.join(" / ")}; project.json source_lang ${proj.source_lang}; files ${readdirSync(folder).filter((f) => /srt|json|md/.test(f)).join(" ")}`);
    await p.waitForSelector(tid("cue-list"));
    const { cueCount } = await playerChecks("ja", { japanese: true });
    note("japanese cue list", cueCount > 50 && hasKana(await srcOf(3)), `${cueCount} cues; cue 3 source "${(await srcOf(3)).slice(0, 40)}", zh "${(await zhOf(3)).slice(0, 30)}"`);
    await offsetCheck("ja", folder);
    const EDIT = await editChecks("ja", folder, { japanese: true });
    await p.click(tid("tab-summary"));
    await p.waitForSelector(tid("summary"));
    await review("ja-summary", "ja: 重點摘要（繁體中文）");
    await p.click(tid("tab-cues"));
    await exportChecks("ja", folder, "cedec-25-35", "ja", EDIT);
    await shotAndBurn("ja", folder, { japanese: true });
    await libraryChecks("ja", [["cedec-25-35", true], ["Agent", false]]);
  } else if (phase === "ja-restart") {
    const video = join(clips, "cedec-25-35.mp4");
    const folder = folderOf("cedec-25-35");
    await importVideo(video, "en");
    await p.waitForSelector(`${tid("cue-list")} li`, { timeout: 60000 });
    const status = await p.textContent(tid("side-status"));
    note("a finished Japanese project plays as it is, with a note", status.includes("先前以日文處理"), `status "${status}"`);
    note("edit survived the restart", (await zhOf(5)).includes("這是我改的一句") && (await p.locator(`${row(5)} ${tid("edited-mark")}`).count()) === 1, `cue 5 "${await zhOf(5)}"`);
    note("source language kept on the project", JSON.parse(readFileSync(join(folder, "project.json"), "utf8")).source_lang === "ja", "project.json source_lang ja");
    await review("ja-restart-note", "重新開啟：先前以日文處理，已直接播放，修改仍在");
  } else if (phase === "en") {
    await caption("英文流程回歸");
    await p.selectOption(tid("source-lang"), "en");
    const video = join(clips, "en-75s.mp4");
    await p.fill(tid("video-path"), video);
    await review("en-import-form", "en: 匯入，影片語言 英文（預設）");
    await p.click(tid("import"));
    const prog = await watchProgress("en");
    const body = jobBodies.at(-1);
    note("job body says en", body !== undefined && JSON.parse(body).source_lang === "en", `POST /jobs body ${body}`);
    const folder = folderOf("en-75s");
    const proj = JSON.parse(readFileSync(join(folder, "project.json"), "utf8"));
    note("english project processed", proj.source_lang === undefined && existsSync(join(folder, "en.srt")) && existsSync(join(folder, "subs.en.json")), `${prog.seconds.toFixed(0)} s; project.json has no source_lang; files en.srt, subs.en.json present`);
    const disk = JSON.parse(readFileSync(join(folder, "subs.en.json"), "utf8")).cues;
    note("english cue file keeps its layout", disk.every((c) => "en" in c && !("lang" in c) && !("src" in c)), `${disk.length} cues with the en key`);
    await p.waitForSelector(tid("cue-list"));
    await playerChecks("en", { japanese: false });
    await offsetCheck("en", folder);
    const EDIT = await editChecks("en", folder, { japanese: false });
    await exportChecks("en", folder, "en-75s", "en", EDIT);
    await libraryChecks("en", [["en-75s", false], ["Agent", false]]);
    // the old demo project (English, processed before this PR) opens straight in the player
    await p.fill(tid("video-path"), join(process.env.P24A_ROOT ?? "D:/WebProject/speech-subtitle-ai", "一個人指揮50多個Agent-lauren @poteto X.mp4"));
    await p.click(tid("import"));
    await p.waitForSelector(`${tid("cue-list")} li`, { timeout: 60000 });
    const first = await srcOf(1);
    note("old English project plays", /[A-Za-z]{3}/.test(first), `cue 1 "${first}", zh "${(await zhOf(1)).slice(0, 20)}"`);
    await review("en-old-project", "en: 舊的英文專案直接播放");
  } else if (phase === "queue") {
    const A = join(clips, "queue-ja-60s.mp4");
    const B = join(clips, "queue-en-45s.mp4");
    const emit = (event, payload) => p.evaluate(([e, pl]) => window.__TAURI_INTERNALS__.invoke("plugin:event|emit", { event: e, payload: pl }), [event, payload]);
    await step("批次佇列：一個日文、一個英文", 700);
    await emit("tauri://drag-enter", { paths: [], position: { x: 10, y: 10 } });
    await emit("tauri://drag-drop", { paths: [A, B], position: { x: 10, y: 10 } });
    await p.waitForSelector(tid("add-dialog"));
    const sources0 = await p.locator(tid("add-row-source")).evaluateAll((els) => els.map((e) => e.value));
    await p.locator(tid("add-row-source")).nth(0).selectOption("ja");
    const sources = await p.locator(tid("add-row-source")).evaluateAll((els) => els.map((e) => e.value));
    const targets = await p.locator(tid("add-row-lang")).evaluateAll((els) => els.map((e) => ({ value: e.value, options: [...e.options].map((o) => o.value) })));
    const noteShown = await p.locator(tid("add-source-note")).count();
    note("add dialog per item video language", sources0.join() === "en,en" && sources.join() === "ja,en" && targets[0].options.join() === "zh-TW" && targets[1].options.length > 3 && noteShown === 1, `before ${sources0.join()}, after ${sources.join()}; row 1 targets ${targets[0].options.join()}; row 2 has ${targets[1].options.length} targets; note shown ${noteShown}`);
    await review("queue-add-dialog", "佇列：加入對話框，每個項目可選影片語言");
    const sent = [];
    p.on("request", (r) => { if (r.method() === "POST" && r.url().endsWith("/api/queue/items")) sent.push(r.postData()); });
    await p.click(tid("add-submit"));
    await p.waitForSelector(tid("add-dialog"), { state: "detached" });
    await until("2 rows", async () => (await p.locator("li.batch-row").count()) === 2, 20000);
    const items = JSON.parse(sent.at(-1)).items;
    note("queue body carries source_lang", items.length === 2 && items.find((i) => i.path.includes("queue-ja")).source_lang === "ja" && items.find((i) => i.path.includes("queue-en")).source_lang === "en", sent.at(-1));
    await review("queue-running-1280", "佇列：日文與英文各一項處理中");
    const tags = await p.evaluate(() => [...document.querySelectorAll("li.batch-row")].map((li) => ({ name: li.querySelector(".batch-name b")?.textContent, lang: li.querySelector(".batch-lang")?.textContent, src: li.querySelector(".chip-src")?.textContent ?? null })));
    note("queue tags", tags.find((t) => t.name.includes("queue-ja"))?.src === "日文影片" && tags.find((t) => t.name.includes("queue-en"))?.src === null, JSON.stringify(tags));
    await resize(960, 600);
    await review("queue-running-960", "佇列 960 px");
    await resize(1280, 720);
    await oneRow("queue");
    await until("both done", async () => (await p.evaluate(() => [...document.querySelectorAll("li.batch-row")].map((li) => li.dataset.state))).every((s) => s === "done"), 15 * 60 * 1000, 1500);
    await review("queue-done", "佇列：兩項都完成");
    const jaFolder = folderOf("queue-ja-60s");
    const enFolder = folderOf("queue-en-45s");
    note("queue projects by language", JSON.parse(readFileSync(join(jaFolder, "project.json"), "utf8")).source_lang === "ja" && JSON.parse(readFileSync(join(enFolder, "project.json"), "utf8")).source_lang === undefined && existsSync(join(jaFolder, "ja.srt")) && existsSync(join(enFolder, "en.srt")), "ja project has source_lang ja and ja.srt; en project has en.srt and no source_lang");
    const jaCues = diskCues(jaFolder);
    note("queue Japanese output", jaCues.length > 5 && jaCues.every((c) => c.lang === "ja" && !hasKana(c.zh)), `${jaCues.length} cues, all lang ja, no kana in the Chinese`);
    // open the Japanese item from the queue
    const open = p.locator(tid("qopen-" + (await p.evaluate(() => [...document.querySelectorAll("li.batch-row")].find((li) => li.querySelector(".batch-name b")?.textContent.includes("queue-ja")).dataset.rowId))));
    await open.click();
    await p.waitForSelector(`${tid("cue-list")} li`, { timeout: 60000 });
    note("open the Japanese item from the queue", hasKana(await srcOf(2)) || /[\u4e00-\u9fff]/.test(await srcOf(2)), `cue 2 "${(await srcOf(2)).slice(0, 30)}"`);
    await review("queue-open-ja", "佇列：開啟日文項目，播放器顯示原文與繁體中文");
    await libraryChecks("queue", [["queue-ja-60s", true], ["queue-en-45s", false]]);
  } else if (phase === "mixed") {
    const video = join(clips, "kirby-5-15.mp4");
    await homeChecks();
    await step("匯入混合語言影片：影片語言選日文與英文混合", 600);
    await p.selectOption(tid("source-lang"), "ja+en");
    await p.fill(tid("video-path"), video);
    await review("mixed-import-form", "匯入：影片語言 日文與英文混合，路徑已貼上");
    await importVideo(video, "ja+en");
    const prog = await watchProgress("mixed");
    const body = jobBodies.at(-1);
    note("job body carries source_lang ja+en", body !== undefined && JSON.parse(body).source_lang === "ja+en", `POST /jobs body ${body}`);
    const folder = folderOf("kirby-5-15");
    const proj = JSON.parse(readFileSync(join(folder, "project.json"), "utf8"));
    note("mixed project processed", proj.source_lang === "ja+en" && existsSync(join(folder, "src.srt")) && existsSync(join(folder, "subs.src.json")) && existsSync(join(folder, "subs.zh-TW.json")), `${prog.seconds.toFixed(0)} s, steps seen ${prog.steps.join(" / ")}; project.json source_lang ${proj.source_lang}; files ${readdirSync(folder).filter((f) => /srt|json|md/.test(f)).join(" ")}`);
    await p.waitForSelector(tid("cue-list"));
    const { cueCount } = await playerChecks("mixed", { japanese: true, mixed: true });
    await mixedChecks("mixed", folder);
    await offsetCheck("mixed", folder);
    const EDIT = await editChecks("mixed", folder, { japanese: true });
    await mixedChecks("mixed after edits", folder, { quiet: true });
    await p.click(tid("tab-summary"));
    await p.waitForSelector(tid("summary"));
    await review("mixed-summary", "mixed: 重點摘要（繁體中文）");
    await p.click(tid("tab-cues"));
    await exportChecks("mixed", folder, "kirby-5-15", "ja+en", EDIT);
    await shotAndBurn("mixed", folder, { japanese: true });
    await libraryChecks("mixed", [["kirby-5-15", "日英混合"], ["Agent", false]]);
    note("mixed cue count", cueCount > 100, `${cueCount} cues`);
  } else if (phase === "mixed-restart") {
    const video = join(clips, "kirby-5-15.mp4");
    const folder = folderOf("kirby-5-15");
    await importVideo(video, "en");
    await p.waitForSelector(`${tid("cue-list")} li`, { timeout: 60000 });
    const status = await p.textContent(tid("side-status"));
    note("a finished mixed project plays as it is, with a note", status.includes("先前以日文與英文混合處理"), `status "${status}"`);
    note("edit survived the restart", (await zhOf(5)).includes("這是我改的一句") && (await p.locator(`${row(5)} ${tid("edited-mark")}`).count()) === 1, `cue 5 "${await zhOf(5)}"`);
    note("marks and source language kept", JSON.parse(readFileSync(join(folder, "project.json"), "utf8")).source_lang === "ja+en" && (await p.locator(tid("lang-mark")).count()) > 50, "project.json source_lang ja+en, the list has marks");
    await review("mixed-restart-note", "重新開啟：先前以日文與英文混合處理，已直接播放，修改仍在");
  } else if (phase === "mixed-queue") {
    const A = join(clips, "queue-mixed-90s.mp4");
    const B = join(clips, "queue-en-45s.mp4");
    const emit = (event, payload) => p.evaluate(([e, pl]) => window.__TAURI_INTERNALS__.invoke("plugin:event|emit", { event: e, payload: pl }), [event, payload]);
    await step("批次佇列：一個混合語言、一個英文", 700);
    await emit("tauri://drag-enter", { paths: [], position: { x: 10, y: 10 } });
    await emit("tauri://drag-drop", { paths: [A, B], position: { x: 10, y: 10 } });
    await p.waitForSelector(tid("add-dialog"));
    await p.locator(tid("add-row-source")).nth(0).selectOption("ja+en");
    const sources = await p.locator(tid("add-row-source")).evaluateAll((els) => els.map((e) => e.value));
    const targets = await p.locator(tid("add-row-lang")).evaluateAll((els) => els.map((e) => [...e.options].map((o) => o.value)));
    const noteText = await p.textContent(tid("add-source-note"));
    const optionTexts = await p.locator(`${tid("add-row-source")} >> nth=0`).evaluate((e) => [...e.options].map((o) => o.textContent));
    note("add dialog offers the mixed choice per item", sources.join() === "ja+en,en" && targets[0].join() === "zh-TW" && targets[1].length > 3 && noteText.includes("24 GB") && optionTexts.length === 3, `sources ${sources.join()}; row 1 targets ${targets[0].join()}; row 2 has ${targets[1].length}; note "${noteText}"; options ${optionTexts.join()}`);
    await review("queue-add-dialog-mixed", "佇列：加入對話框，一項選日文與英文混合");
    const sent = [];
    p.on("request", (r) => { if (r.method() === "POST" && r.url().endsWith("/api/queue/items")) sent.push(r.postData()); });
    await p.click(tid("add-submit"));
    await p.waitForSelector(tid("add-dialog"), { state: "detached" });
    await until("2 rows", async () => (await p.locator("li.batch-row").count()) === 2, 20000);
    const items = JSON.parse(sent.at(-1)).items;
    note("queue body carries source_lang ja+en", items.find((i) => i.path.includes("queue-mixed")).source_lang === "ja+en" && items.find((i) => i.path.includes("queue-en")).source_lang === "en", sent.at(-1));
    await review("queue-running-mixed-1280", "佇列：混合語言與英文各一項處理中");
    const tags = await p.evaluate(() => [...document.querySelectorAll("li.batch-row")].map((li) => ({ name: li.querySelector(".batch-name b")?.textContent, src: li.querySelector(".chip-src")?.textContent ?? null })));
    note("queue tags", tags.find((t) => t.name.includes("queue-mixed"))?.src === "日英混合" && tags.find((t) => t.name.includes("queue-en"))?.src === null, JSON.stringify(tags));
    await resize(960, 600);
    await review("queue-running-mixed-960", "佇列 960 px");
    await resize(1280, 720);
    await oneRow("queue, mixed");
    await until("both done", async () => (await p.evaluate(() => [...document.querySelectorAll("li.batch-row")].map((li) => li.dataset.state))).every((s) => s === "done"), 20 * 60 * 1000, 1500);
    await review("queue-done-mixed", "佇列：兩項都完成");
    const mFolder = folderOf("queue-mixed-90s");
    const eFolder = folderOf("queue-en-45s");
    note("queue projects by language", JSON.parse(readFileSync(join(mFolder, "project.json"), "utf8")).source_lang === "ja+en" && existsSync(join(mFolder, "src.srt")) && existsSync(join(eFolder, "en.srt")), "mixed project has source_lang ja+en and src.srt; english project has en.srt");
    const cues = diskCues(mFolder);
    const langs = new Set(cues.map((c) => c.lang));
    note("queue mixed output", cues.length > 10 && [...langs].every((l) => l === "ja" || l === "en") && cues.every((c) => !hasKana(c.zh)), `${cues.length} cues, languages ${[...langs].join()}, no kana in the Chinese`);
    const open = p.locator(tid("qopen-" + (await p.evaluate(() => [...document.querySelectorAll("li.batch-row")].find((li) => li.querySelector(".batch-name b")?.textContent.includes("queue-mixed")).dataset.rowId))));
    await open.click();
    await p.waitForSelector(`${tid("cue-list")} li`, { timeout: 60000 });
    note("open the mixed item from the queue", (await p.locator(tid("lang-mark")).count()) > 5, `${await p.locator(tid("lang-mark")).count()} marks in the list`);
    await review("queue-open-mixed", "佇列：開啟混合語言項目，清單每條字幕有語言記號");
    await libraryChecks("queue", [["queue-mixed-90s", "日英混合"], ["queue-en-45s", false]]);
  } else if (phase === "unavailable") {
    await step("這台電腦沒有 Qwen3 檔案：混合語言不能選", 700);
    const opt = p.locator(`${tid("source-lang")} option[value="ja+en"]`);
    const text = await opt.textContent();
    const disabled = await opt.evaluate((e) => e.disabled);
    note("mixed choice disabled with a reason in the picker", disabled && text.includes("這台電腦沒有安裝混合語言所需的模型") && (await p.inputValue(tid("source-lang"))) === "en", `option "${text}", disabled ${disabled}`);
    await oneRow("home, mixed unavailable");
    await fileBoxChecks("home, mixed unavailable", HOME_BOX);
    await review("unavailable-home", "沒有 Qwen3 檔案：混合語言選項不能選，並說明原因");
    await p.click(tid("batch-open-add"));
    await p.waitForSelector(tid("add-dialog"));
    const dialogOpt = await p.locator(`${tid("add-default-source")} option[value="ja+en"]`).evaluate((e) => ({ disabled: e.disabled, text: e.textContent }));
    note("mixed choice disabled in the add dialog", dialogOpt.disabled && dialogOpt.text.includes("這台電腦沒有安裝混合語言所需的模型"), JSON.stringify(dialogOpt));
    await review("unavailable-add-dialog", "沒有 Qwen3 檔案：加入對話框的混合語言選項不能選");
    await p.click(tid("add-close"));
    // the backend refuses the job anyway when the picker is bypassed, and the window shows its text as is
    const video = join(clips, "queue-mixed-90s.mp4");
    await p.route("**/api/languages", async (route) => {
      const res = await route.fetch();
      const json = await res.json();
      json.sources = json.sources.map((s) => ({ ...s, available: true, reason: null }));
      await route.fulfill({ response: res, json });
    });
    await p.click(tid("settings-open"));
    await p.waitForSelector(tid("settings-page"));
    await p.click(tid("settings-open"));
    await p.waitForSelector(tid("ready"));
    await sleep(1200);
    const bypassed = await p.locator(`${tid("source-lang")} option[value="ja+en"]`).evaluate((e) => e.disabled);
    note("with the check faked as available the choice opens", !bypassed, "GET /api/languages answered through a route that sets available true");
    await p.selectOption(tid("source-lang"), "ja+en");
    await p.fill(tid("video-path"), video);
    await p.click(tid("import"));
    await p.waitForSelector(tid("error"), { timeout: 30000 });
    const shown = await p.textContent(tid("error"));
    await review("unavailable-backend-refusal", "繞過選單時，後端的拒絕訊息原文顯示");
    note("the backend refusal is shown as is", shown.includes("Japanese and English talks need the Qwen3-ASR engine") && shown.includes("24 GB profile"), `error text "${shown.slice(0, 220)}"`);
    await p.unroute("**/api/languages");
  } else if (phase === "nofont") {
    const video = join(clips, "cedec-25-35.mp4");
    await importVideo(video, "ja");
    await p.waitForSelector(`${tid("cue-list")} li`, { timeout: 60000 });
    await p.evaluate(() => document.querySelector("video").pause());
    await p.keyboard.press("Shift+s");
    await p.waitForSelector(`${tid("toast")}[data-error="true"]`, { timeout: 20000 });
    const toast = await p.textContent(tid("toast-text"));
    await review("ja-nofont-screenshot-error", "沒有日文字型：burned screenshot 的錯誤訊息");
    note("missing font message in a screenshot", toast.includes("這台電腦沒有可以顯示日文字幕的字型"), `toast "${toast}"`);
    await p.click(tid("export-menu"));
    await p.click(tid("export-burn-clip"));
    await p.waitForSelector(tid("burn-progress"), { timeout: 15000 });
    await sleep(800);
    const burnText = await p.textContent(tid("burn-progress"));
    await review("ja-nofont-burn-error", "沒有日文字型：燒入字幕的錯誤訊息");
    note("missing font message in the burn card", burnText.includes("這台電腦沒有可以顯示日文字幕的字型"), `burn card "${burnText.replace(/\s+/g, " ")}"`);
  } else if (phase === "layout") {
    const demo = join(process.env.P24A_ROOT ?? "D:/WebProject/speech-subtitle-ai", "一個人指揮50多個Agent-lauren @poteto X.mp4");
    const waitPlayer = async () => {
      await until("player", async () => (await p.locator(`${tid("cue-list")} li`).count()) > 0 && (await p.locator(tid("importing")).count()) === 0, 10 * 60 * 1000, 500);
      await p.evaluate(() => document.querySelector("video")?.pause());
    };
    const heightIs = async (label, lo, hi) => {
      const out = [];
      for (const [w, h] of [[1280, 720], [960, 600]]) {
        await resize(w, h);
        const m = await header();
        out.push(m.height);
        note(`header ${lo}-${hi} px and one row at ${w} (${label})`, m.height >= lo && m.height <= hi && m.spread <= 3, `header ${m.height.toFixed(1)} px, centers spread ${m.spread} px`);
      }
      await resize(1280, 720);
    };
    const inHeader = (sel) => p.locator(`header ${sel}`).count();

    await step("首頁：工具列一排，輸入框寬度", 600);
    await heightIs("home, English", 48, 50);
    await fileBoxChecks("home, English", HOME_BOX);
    await p.selectOption(tid("source-lang"), "ja");
    await heightIs("home, Japanese note", 48, 50);
    await fileBoxChecks("home, Japanese note", HOME_BOX);
    if (!(await p.locator(`${tid("source-lang")} option[value="ja+en"]`).evaluate((e) => e.disabled))) {
      await p.selectOption(tid("source-lang"), "ja+en");
      await heightIs("home, mixed note", 48, 50);
      await fileBoxChecks("home, mixed note", HOME_BOX_MIXED);
    }
    await p.selectOption(tid("source-lang"), "en");

    await importVideo(demo, "en");
    await waitPlayer();
    await heightIs("player, English", 50, 52);
    note("English player: no picker and no note", (await inHeader(tid("source-lang"))) === 0 && (await p.locator(tid("source-lang")).count()) === 0 && (await p.locator(tid("source-note")).count()) === 0, "the toolbar of the English player is as before");
    await fileBoxChecks("player, English", PLAYER_BOX);
    await review("player-en-1280", "英文播放器：工具列一排，輸入框可讀");
    await resize(960, 600);
    await review("player-en-960", "英文播放器 960 px：輸入框可讀");
    await p.fill(tid("video-path"), demo);
    const shown = await p.evaluate(() => {
      const i = document.querySelector('[data-testid="video-path"]');
      return { client: i.clientWidth, value: i.value.length };
    });
    note("pasted path is visible in the player at 960", shown.client >= 60 && shown.value > 40, `input client width ${shown.client} px for a ${shown.value} character path`);
    await p.click(tid("import"));
    await waitPlayer();
    note("pasted path in the player opens the project at 960", (await p.locator(tid("error")).count()) === 0, "player shown, no error");
    await resize(1280, 720);

    await p.click(tid("home"));
    await p.waitForSelector(tid("library-list"));
    await p.selectOption(tid("source-lang"), "ja");
    await p.fill(tid("video-path"), join(clips, "queue-ja-60s.mp4"));
    await p.click(tid("import"));
    await waitPlayer();
    const jaBody = jobBodies.at(-1);
    note("Japanese import starts with source_lang ja", jaBody !== undefined && JSON.parse(jaBody).source_lang === "ja", `POST /jobs body ${jaBody}`);
    await heightIs("player, Japanese", 50, 52);
    const bar = await p.evaluate(() => ({ value: document.querySelector('.source-bar [data-testid="source-lang"]')?.value ?? null, note: document.querySelector('[data-testid="source-note"]')?.textContent ?? null }));
    note("Japanese player: picker and note sit under the toolbar", bar.value === "ja" && (bar.note ?? "").includes("繁體中文") && (await inHeader(tid("source-lang"))) === 0, `picker ${bar.value}, note "${bar.note}"`);
    await fileBoxChecks("player, Japanese", PLAYER_BOX);
    await review("player-ja-1280", "日文播放器：工具列一排，影片語言與說明在工具列下面");
    await resize(960, 600);
    await review("player-ja-960", "日文播放器 960 px：輸入框可讀");
    await p.selectOption(tid("source-lang"), "en");
    await sleep(300);
    note("the picker in the player switches back to English", (await p.locator(tid("source-note")).count()) === 0 && (await p.locator(tid("source-lang")).count()) === 0, "note and picker gone");
    await p.fill(tid("video-path"), join(clips, "queue-en-45s.mp4"));
    await p.click(tid("import"));
    await p.waitForSelector(tid("importing"), { timeout: 20000 });
    await waitPlayer();
    const enBody = jobBodies.at(-1);
    note("English import from the player starts with source_lang en", enBody !== undefined && JSON.parse(enBody).source_lang === "en", `POST /jobs body ${enBody}`);
    await heightIs("player, English after import", 50, 52);
    await resize(1280, 720);

    await p.click(tid("home"));
    await p.waitForSelector(tid("library-list"));
    await p.selectOption(tid("source-lang"), "ja+en");
    await p.fill(tid("video-path"), join(clips, "queue-mixed-90s.mp4"));
    await p.click(tid("import"));
    await waitPlayer();
    const mixedBody = jobBodies.at(-1);
    note("mixed import starts with source_lang ja+en", mixedBody !== undefined && JSON.parse(mixedBody).source_lang === "ja+en", `POST /jobs body ${mixedBody}`);
    await heightIs("player, mixed", 50, 52);
    const mbar = await p.evaluate(() => ({ value: document.querySelector('.source-bar [data-testid="source-lang"]')?.value ?? null, note: document.querySelector('[data-testid="source-note"]')?.textContent ?? null }));
    note("mixed player: picker and note sit under the toolbar", mbar.value === "ja+en" && mbar.note === MIXED_NOTE && (await inHeader(tid("source-lang"))) === 0, `picker ${mbar.value}, note "${mbar.note}"`);
    await fileBoxChecks("player, mixed", PLAYER_BOX);
    await review("player-mixed-1280", "混合語言播放器：工具列一排，影片語言與說明在工具列下面");
    await resize(960, 600);
    await review("player-mixed-960", "混合語言播放器 960 px：輸入框可讀");
    await resize(1280, 720);
  } else {
    throw new Error(`unknown phase ${phase}`);
  }
} catch (e) {
  note("phase aborted", false, String(e?.stack ?? e));
  await p.screenshot({ path: join(shots, `abort-${phase}.png`) }).catch(() => undefined);
}
await finish();
