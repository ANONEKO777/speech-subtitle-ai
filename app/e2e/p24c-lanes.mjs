// P24c live check of the automatic video language in the real window, driven over CDP only.
// node e2e/p24c-lanes.mjs <phase> <projects-dir> <clips-dir> <shots-dir> [port]
// phase: player (only the English player after an import: nothing is asked, no band) | pick (a path typed into the import box: the suggestion, the kept choice, the hint, a failed guess, the
//   queue add dialog, and the toolbar with the note shown) | unavailable (a user data folder without the Qwen3 files)
// Env: VST_USER_DATA, WEBVIEW2_USER_DATA_FOLDER (disposable folders), P24C_JA_TALK (a long Japanese talk),
//   P24C_MIXED_TALK (a long talk in Japanese and English, a speaker and an interpreter), P24C_EN_TALK (a long
//   English talk): a row whose variable is unset is skipped with a message, P24C_MEDIA (review PNGs of those
//   videos go here, outside the repo), P24C_REVIEW_PREFIX.
// <projects-dir> holds a finished project of queue-en-45s.mp4 from <clips-dir>, so the one import the lane presses
// (to measure the English player) plays it at once and no job runs. Every action goes
// through the DevTools protocol; the native file dialog is not used. Exit 1 on a failed check.
import { execFileSync } from "node:child_process";
import { copyFileSync, existsSync, mkdirSync, rmSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import { launch, sleep, strayProcesses } from "./lib.mjs";

const [phase, projects, clips, shots, portArg] = process.argv.slice(2);
if (!phase || !projects || !clips || !shots) throw new Error("usage: p24c-lanes.mjs <pick|player|unavailable> <projects> <clips> <shots> [port]");
const media = process.env.P24C_MEDIA ?? shots;
const prefix = process.env.P24C_REVIEW_PREFIX ?? "P24c-review";
if (!process.env.VST_USER_DATA || !process.env.WEBVIEW2_USER_DATA_FOLDER) throw new Error("set VST_USER_DATA and WEBVIEW2_USER_DATA_FOLDER to disposable folders");

const VIDEO = {
  en: join(clips, "queue-en-45s.mp4"),
  enLong: process.env.P24C_EN_TALK ?? null,
  ja: process.env.P24C_JA_TALK ?? null,
  mixed: process.env.P24C_MIXED_TALK ?? null,
  jaClip: join(clips, "queue-ja-60s.mp4"),
  mixedClip: join(clips, "queue-mixed-90s.mp4"),
  music: join(clips, "chords-60s.mp4"),
};
const skip = (what, variable) => console.log(`SKIP ${what}: set ${variable} to a video path to run it`);
const tid = (id) => `[data-testid="${id}"]`;
const results = [];
const table = [];
const check = (name, ok, detail) => {
  results.push({ name, ok, detail });
  console.log(`${ok ? "PASS" : "FAIL"} ${name} ${detail}`);
};

const detectCalls = [];
const before = strayProcesses();
const app = await launch({ projects, shots, port: Number(portArg ?? 9460), env: { VST_UPDATE_URL: "http://127.0.0.1:9/none.json" } });
const p = app.page;
console.log(`app pid ${app.pid}, cold start ${app.coldStartMs} ms, phase ${phase}`);
p.on("response", async (r) => {
  if (!r.url().includes("/api/languages/detect")) return;
  detectCalls.push({ url: r.url(), status: r.status(), body: await r.json().catch(() => null) });
});
const session = await p.context().newCDPSession(p);
const { windowId } = await session.send("Browser.getWindowForTarget");
const resize = async (width, height) => {
  await session.send("Browser.setWindowBounds", { windowId, bounds: { windowState: "normal", width, height } });
  await sleep(600);
};
const emit = (event, payload) => p.evaluate(([e, pl]) => window.__TAURI_INTERNALS__.invoke("plugin:event|emit", { event: e, payload: pl }), [event, payload]);

const FFMPEG = process.env.P24C_FFMPEG ?? "C:/Program Files/ffmpeg-n6.1-latest-win64-gpl-shared-6.1/bin/ffmpeg.exe";
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
    let el = document.getElementById("p24c-cap");
    if (!el) {
      el = document.createElement("div");
      el.id = "p24c-cap";
      el.style.cssText =
        "position:fixed;left:50%;bottom:6px;transform:translateX(-50%);z-index:99999;padding:4px 12px;border-radius:8px;background:rgba(0,0,0,.78);color:#ffd699;font:13px 'Segoe UI','Microsoft JhengHei',sans-serif;pointer-events:none;white-space:nowrap";
      document.body.appendChild(el);
    }
    el.textContent = t;
    el.style.display = t ? "block" : "none";
  }, text);
const shot = async (dir, name) => {
  await p.evaluate(() => {
    const el = document.getElementById("p24c-cap");
    if (el) el.style.display = "none";
  });
  await sleep(100);
  await p.screenshot({ path: join(dir, name) });
};

/** A minute of three sine tones: sound that holds no speech, which Whisper names a language all the same. */
function makeChords(out) {
  if (existsSync(out)) return;
  const tones = [261.6, 329.6, 392];
  const inputs = tones.flatMap((hz) => ["-f", "lavfi", "-i", `sine=f=${hz}:d=60`]);
  execFileSync(FFMPEG, ["-v", "error", "-y", "-f", "lavfi", "-i", "color=c=black:s=320x180:d=60", ...inputs, "-filter_complex", "[1][2][3]amix=inputs=3:normalize=0,volume=0.5[a]", "-map", "0:v", "-map", "[a]", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", out]);
}

/** Types a path into the import box and waits for the window to say what it heard (or to say nothing). */
async function pick(path, { within = 60000 } = {}) {
  const started = Date.now();
  await p.fill(tid("video-path"), path);
  const note = p.locator(`${tid("detect-note")}[data-state="done"]`);
  let ms = null;
  while (Date.now() - started < within) {
    if (await note.count()) {
      ms = Date.now() - started;
      break;
    }
    await sleep(100);
  }
  return read(ms);
}
const read = async (ms) =>
  p.evaluate((elapsed) => {
    const q = (id) => document.querySelector(`[data-testid="${id}"]`);
    return {
      ms: elapsed,
      note: q("detect-note")?.textContent ?? null,
      detected: q("detect-note")?.getAttribute("data-detected") ?? null,
      hint: q("detect-hint")?.textContent ?? null,
      switchLabel: q("detect-switch")?.textContent ?? null,
      picker: (document.querySelector('header [data-testid="source-lang"]') ?? q("source-lang"))?.value ?? null,
      error: q("error")?.textContent ?? null,
    };
  }, ms);
const settle = () => sleep(1200);
const clear = async () => {
  await p.fill(tid("video-path"), "");
  await sleep(300);
};
const row = (label, truth, got) => {
  table.push({ label, truth, suggested: got.picker, seconds: got.ms === null ? null : Number((got.ms / 1000).toFixed(1)), note: got.note });
  console.log(`  ${label}: true ${truth}, picker ${got.picker}, ${got.ms === null ? "no note" : `${(got.ms / 1000).toFixed(1)} s`}, "${got.note}"`);
};

const measure = () =>
  p.evaluate(() => {
    const q = (id) => document.querySelector(`[data-testid="${id}"]`);
    const h = document.querySelector("header");
    const mids = [...h.querySelectorAll("button, input, select")].map((e) => {
      const b = e.getBoundingClientRect();
      return Math.round(b.top + b.height / 2);
    });
    const w = (e) => (e ? Number(e.getBoundingClientRect().width.toFixed(1)) : null);
    return { header: Number(h.getBoundingClientRect().height.toFixed(1)), spread: Math.max(...mids) - Math.min(...mids), box: w(q("video-path")) };
  });

/** The English player after an import, with the box still holding the imported path: nothing is asked and no band opens under the toolbar. */
async function englishPlayer() {
  await clear();
  await p.selectOption(tid("source-lang"), "en");
  const askedBeforeImport = detectCalls.length;
  await p.fill(tid("video-path"), VIDEO.en);
  await p.click(tid("import"));
  await p.waitForSelector(`${tid("cue-list")} li`, { timeout: 60000 });
  await p.evaluate(() => document.querySelector("video")?.pause());
  await sleep(7000);
  const inPlayer = await p.evaluate(() => ({
    bar: document.querySelectorAll(".source-bar").length,
    note: document.querySelectorAll('[data-testid="detect-note"]').length,
    picker: document.querySelectorAll('[data-testid="source-lang"]').length,
  }));
  check("English player after an import: nothing is asked and no band appears under the toolbar", detectCalls.length === askedBeforeImport && inPlayer.bar === 0 && inPlayer.note === 0 && inPlayer.picker === 0, `${detectCalls.length - askedBeforeImport} requests in 7 s, ${JSON.stringify(inPlayer)}`);
  for (const [w, h, wantBox] of [[1280, 720, 130.6], [960, 600, 67.2]]) {
    await resize(w, h);
    const bare = await measure();
    const asked = detectCalls.length;
    await p.fill(tid("video-path"), VIDEO.jaClip);
    await sleep(7000);
    const noted = await measure();
    const band = await p.locator(".source-bar").count();
    check(`English player ${w}: a path typed in the box asks nothing, and file box and header are as on main`, detectCalls.length === asked && band === 0 && Math.abs(noted.box - wantBox) <= 0.5 && bare.header === noted.header && noted.spread <= 3, `${detectCalls.length - asked} requests, band ${band}, box ${bare.box} -> ${noted.box} (main ${wantBox}), header ${bare.header} -> ${noted.header}, spread ${noted.spread}`);
    if (w === 1280) await shot(shots, "p24c-en-player-typed-1280.png");
    await p.fill(tid("video-path"), "");
    await sleep(300);
  }
}

try {
  if (phase === "pick") {
    const SEC = 20;
    await resize(1280, 720);
    check("the picker starts on English and no note shows", (await read(null)).picker === "en" && (await p.locator(tid("detect-note")).count()) === 0, "idle home screen");

    await caption("英文剪輯：貼上路徑，約 4 秒後出現偵測結果");
    const en = await pick(VIDEO.en);
    row("English clip (45 s, public)", "en", en);
    check("English clip: suggested English, sure", en.picker === "en" && en.detected === "en" && /^偵測到：英文（信心 \d+%）$/.test(en.note ?? "") && en.hint === null, `picker ${en.picker}, "${en.note}", hint ${en.hint}`);
    await shot(shots, "p24c-en-home-1280.png");
    await shot(media, `${prefix}-1-english-1280.png`);
    await resize(960, 600);
    await shot(shots, "p24c-en-home-960.png");
    await shot(media, `${prefix}-2-english-960.png`);
    await resize(1280, 720);

    if (VIDEO.enLong) {
      await clear();
      const enLong = await pick(VIDEO.enLong);
      row("English talk", "en", enLong);
      check("English talk: English", enLong.picker === "en" && enLong.detected === "en", `"${enLong.note}"`);
    } else skip("English talk", "P24C_EN_TALK");

    if (VIDEO.ja) {
      await clear();
      await caption("日文講座：預選日文");
      const ja = await pick(VIDEO.ja);
      row("Japanese talk", "ja", ja);
      check("Japanese talk: preselected 日文, sure", ja.picker === "ja" && ja.detected === "ja" && /^偵測到：日文（信心 \d+%）$/.test(ja.note ?? ""), `picker ${ja.picker}, "${ja.note}"`);
      check("Japanese talk: the note under the toolbar and the format note both show", (await p.locator(tid("source-note")).count()) === 1, "source-note shown with the detect note");
      await shot(media, `${prefix}-3-japanese-1280.png`);
      await resize(960, 600);
      await shot(media, `${prefix}-4-japanese-960.png`);
      await resize(1280, 720);
    } else skip("Japanese talk", "P24C_JA_TALK");

    if (VIDEO.mixed) {
      await clear();
      await caption("日英混合講座：預選日文與英文混合");
      const mixed = await pick(VIDEO.mixed);
      row("Japanese then English talk", "ja+en", mixed);
      const mixedOk = mixed.picker === "ja+en" && mixed.detected === "ja+en";
      check("mixed talk: preselected 日文與英文混合", mixedOk, `picker ${mixed.picker}, "${mixed.note}"`);
      await shot(media, `${prefix}-5-mixed-1280.png`);
      await resize(960, 600);
      await shot(media, `${prefix}-6-mixed-960.png`);
      await resize(1280, 720);
    } else skip("mixed talk", "P24C_MIXED_TALK");

    await clear();
    for (const [key, truth, label] of [["jaClip", "ja", "Japanese clip (60 s)"], ["mixedClip", "ja+en", "mixed clip (90 s)"]]) {
      const got = await pick(VIDEO[key]);
      row(label, truth, got);
      check(`${label}: ${truth}`, got.detected === truth, `"${got.note}"`);
      await clear();
    }

    const jaAny = VIDEO.ja ?? VIDEO.jaClip;
    await caption("自己選了英文：偵測到日文也不會換掉，只出現提示");
    await p.selectOption(tid("source-lang"), "en");
    const kept = await pick(jaAny);
    check("hand choice kept: still 英文 after a Japanese talk was heard", kept.picker === "en" && kept.detected === "ja", `picker ${kept.picker}, heard ${kept.detected}`);
    check("hint shown with the switch", /聽起來是日文，目前選的是英文/.test(kept.hint ?? "") && kept.switchLabel === "改成日文", `hint "${kept.hint}", button "${kept.switchLabel}"`);
    await shot(media, `${prefix}-7-hint-1280.png`);
    await resize(960, 600);
    await shot(media, `${prefix}-8-hint-960.png`);
    await resize(1280, 720);
    await caption("一鍵切換");
    await sleep(900);
    await p.click(tid("detect-switch"));
    await sleep(900);
    const switched = await read(null);
    check("one click switches the picker and the hint goes", switched.picker === "ja" && (await p.locator(tid("detect-hint")).count()) === 0, `picker ${switched.picker}`);
    await p.selectOption(tid("source-lang"), "en");
    check("choosing again by hand brings the hint back", (await p.locator(tid("detect-hint")).count()) === 1, "hint shown for English over a Japanese talk");

    await clear();
    await p.selectOption(tid("source-lang"), "ja");
    const keptJa = await pick(VIDEO.en);
    check("hand choice 日文 kept for an English clip, with a hint", keptJa.picker === "ja" && /聽起來是英文，目前選的是日文/.test(keptJa.hint ?? ""), `picker ${keptJa.picker}, hint "${keptJa.hint}"`);
    await p.fill(tid("video-path"), `${VIDEO.en}x`);
    await sleep(150);
    check("the note and the hint of the old path go at the first change of the path", (await p.locator(tid("detect-note")).count()) === 0 && (await p.locator(tid("detect-hint")).count()) === 0, "nothing under the toolbar 150 ms after the path changed");
    await clear();
    await p.selectOption(tid("source-lang"), "ja+en");
    const keptMixed = await pick(jaAny);
    check("hand choice mixed kept for a Japanese video, with no hint to leave it", keptMixed.picker === "ja+en" && keptMixed.detected === "ja" && keptMixed.hint === null, `picker ${keptMixed.picker}, heard ${keptMixed.detected}, hint ${keptMixed.hint}`);
    await clear();
    await p.selectOption(tid("source-lang"), "en");

    for (const [label, path] of [["a path that does not exist", "D:\\nope\\missing.mp4"], ["a file that is not media", "D:\\WebProject\\speech-subtitle-ai\\README.md"]]) {
      await p.fill(tid("video-path"), path);
      await sleep(2500);
      const quiet = await read(null);
      check(`failed guess is silent: ${label}`, quiet.note === null && quiet.hint === null && quiet.picker === "en" && quiet.error === null, `note ${quiet.note}, picker ${quiet.picker}, error ${quiet.error}`);
    }
    await clear();

    makeChords(VIDEO.music);
    const answered = detectCalls.length;
    await p.fill(tid("video-path"), VIDEO.music);
    const waitUntil = Date.now() + 30000;
    while (detectCalls.length === answered && Date.now() < waitUntil) await sleep(200);
    await sleep(500);
    const music = await read(null);
    const musicAnswer = detectCalls[detectCalls.length - 1];
    check("music with no speech: asked, no guess, no note, picker untouched", musicAnswer?.status === 200 && musicAnswer.body?.detected === null && music.note === null && music.hint === null && music.picker === "en", `answer ${JSON.stringify({ status: musicAnswer?.status, detected: musicAnswer?.body?.detected, clear: musicAnswer?.body?.clear })}, note ${music.note}, picker ${music.picker}`);
    await clear();

    await caption("加入佇列：每個檔案各自偵測");
    await emit("tauri://drag-enter", { paths: [], position: { x: 10, y: 10 } });
    await emit("tauri://drag-drop", { paths: [VIDEO.jaClip, VIDEO.en, VIDEO.mixedClip], position: { x: 10, y: 10 } });
    await p.waitForSelector(tid("add-dialog"));
    const started = Date.now();
    await p.waitForFunction(() => document.querySelectorAll('[data-testid="add-row-detect"][data-state="done"]').length === 3, null, { timeout: 120000 });
    const dialogMs = Date.now() - started;
    const rows = await p.locator(tid("add-row")).evaluateAll((els) =>
      els.map((li) => ({
        name: li.querySelector("b")?.textContent,
        source: li.querySelector('[data-testid="add-row-source"]')?.value,
        note: li.querySelector('[data-testid="add-row-detect"]')?.textContent,
        hint: li.querySelector('[data-testid="add-row-hint"]')?.textContent ?? null,
      })),
    );
    console.log(JSON.stringify(rows));
    check("add dialog: each row got its own language", rows.map((r) => r.source).join() === "ja,en,ja+en", `${rows.map((r) => r.source).join()} in ${(dialogMs / 1000).toFixed(1)} s for three rows`);
    await shot(media, `${prefix}-9-add-dialog-1280.png`);
    await p.locator(tid("add-row-source")).nth(1).selectOption("ja");
    const afterPick = await p.locator(tid("add-row-hint")).evaluateAll((els) => els.map((e) => e.textContent));
    check("add dialog: a row changed by hand keeps it and shows the hint", (await p.locator(tid("add-row-source")).nth(1).inputValue()) === "ja" && afterPick.length === 1 && /聽起來是英文/.test(afterPick[0]), `hints ${JSON.stringify(afterPick)}`);
    await shot(media, `${prefix}-10-add-dialog-hint-1280.png`);
    await p.locator(tid("add-row-switch")).click();
    check("add dialog: the switch puts the row back", (await p.locator(tid("add-row-source")).nth(1).inputValue()) === "en" && (await p.locator(tid("add-row-hint")).count()) === 0, "row 2 is English again");
    await resize(960, 600);
    await shot(media, `${prefix}-11-add-dialog-960.png`);
    await resize(1280, 720);
    await p.click(tid("add-close"));
    await p.waitForSelector(tid("add-dialog"), { state: "detached" });

    await caption("");
    for (const [lang, key] of [["en", "en"], ["ja", "jaClip"], ["ja+en", "mixedClip"]]) {
      await clear();
      await p.selectOption(tid("source-lang"), lang);
      for (const [w, h] of [[1280, 720], [960, 600]]) {
        await resize(w, h);
        const bare = await measure();
        await pick(VIDEO[key]);
        const noted = await measure();
        check(`toolbar unchanged by the note: home ${lang} ${w}`, bare.header === noted.header && bare.box === noted.box && noted.header < 52 && noted.spread <= 3, `header ${bare.header} -> ${noted.header}, box ${bare.box} -> ${noted.box}, spread ${noted.spread}`);
        await clear();
      }
    }
    await resize(1280, 720);

    await englishPlayer();
  } else if (phase === "player") {
    await resize(1280, 720);
    await englishPlayer();
  } else if (phase === "unavailable") {
    await resize(1280, 720);
    const optionDisabled = await p.locator(`${tid("source-lang")} option[value="ja+en"]`).evaluate((e) => e.disabled);
    check("mixed is disabled in the picker on this machine", optionDisabled, `disabled ${optionDisabled}`);
    const mixed = await pick(VIDEO.mixedClip);
    row("mixed clip (90 s), no Qwen3 files", "ja+en", mixed);
    check("mixed heard, main language preselected, mixed said to be unavailable", mixed.detected === "ja+en" && mixed.picker !== "ja+en" && /這台電腦無法處理混合語言/.test(mixed.note ?? ""), `picker ${mixed.picker}, "${mixed.note}"`);
    await shot(media, `${prefix}-12-mixed-unavailable-1280.png`);
    await p.selectOption(tid("source-lang"), mixed.picker === "ja" ? "en" : "ja");
    await sleep(400);
    const hint = await read(null);
    check("a different choice gets a hint to the main language, never to mixed", /大部分是/.test(hint.hint ?? "") && hint.switchLabel !== "改成日文與英文混合", `hint "${hint.hint}", button "${hint.switchLabel}"`);
  }
} finally {
  await session.send("Page.stopScreencast").catch(() => undefined);
  await sleep(300);
  if (frames.length > 0) {
    let list = "";
    for (let i = 0; i < frames.length; i++) {
      const d = i + 1 < frames.length ? Math.max(0.04, Math.min(2.2, frames[i + 1] - frames[i])) : 0.8;
      list += `file '${String(i).padStart(5, "0")}.jpg'
duration ${d.toFixed(3)}
`;
    }
    list += `file '${String(frames.length - 1).padStart(5, "0")}.jpg'
`;
    writeFileSync(join(frameDir, "list.txt"), list);
    const video = join(shots, `phase-${phase}.mp4`);
    execFileSync(FFMPEG, ["-v", "error", "-y", "-f", "concat", "-safe", "0", "-i", join(frameDir, "list.txt"), "-vf", "scale=1280:800:force_original_aspect_ratio=decrease,pad=1280:800:(ow-iw)/2:(oh-ih)/2,fps=15,format=yuv420p", "-c:v", "libx264", "-crf", "26", video]);
    if (phase === "pick") copyFileSync(video, join(media, `${prefix}.mp4`));
    console.log(`recording ${frames.length} frames -> ${video}`);
  }
  const closed = await app.closeWindow();
  const left = strayProcesses(before);
  check("window closed and no whisper-cli, crispasr or llama-server of ours left", closed.leftovers.length === 0 && left.length === 0, `leftovers ${JSON.stringify(closed.leftovers)}, new strays ${JSON.stringify(left)}`);
  const failed = results.filter((r) => !r.ok);
  console.log(`${results.length - failed.length} passed, ${failed.length} failed`);
  writeFileSync(join(shots, `p24c-${phase}.json`), JSON.stringify({ phase, results, table }, null, 1));
  process.exitCode = failed.length ? 1 : 0;
}
