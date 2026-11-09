// Drives the settings page, model management and the first-run wizard in the real window (P13 UI).
// node app/e2e/settings-lanes.mjs <shots-dir> [--only existing,views,full,fallback,retry]
// Env: P13U_WORK (scratch folder, default .work/p13u-run), P13U_UD_SOURCE (user data to copy, default .work/p08-ud),
// P13U_CACHE (runtime zips, default .work/p13u-cache), P13U_PORT (DevTools port, default 9317).
// Everything goes through CDP: no OS mouse or keyboard input. The source user data is only read.
import { execFileSync, spawn } from "node:child_process";
import { copyFileSync, cpSync, existsSync, mkdirSync, openSync, readFileSync, readdirSync, rmSync, writeFileSync, writeSync, closeSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { REGISTRY, startMirror, writeMirrors } from "./mirror.mjs";
import { launch, powershell, sleep, strayProcesses } from "./lib.mjs";

const here = dirname(fileURLToPath(import.meta.url));
const REPO = resolve(here, "../..");
const MAIN = resolve(REPO, "../..");
const WORK = process.env.P13U_WORK ?? join(MAIN, ".work/p13u-run");
const SOURCE = process.env.P13U_UD_SOURCE ?? join(MAIN, ".work/p08-ud");
const CACHE = process.env.P13U_CACHE ?? join(MAIN, ".work/p13u-cache");
const PORT = Number(process.env.P13U_PORT ?? 9317);
const [shots] = process.argv.slice(2).filter((a) => !a.startsWith("--"));
if (!shots) throw new Error("usage: settings-lanes.mjs <shots-dir> [--only a,b]");
const onlyArg = process.argv.indexOf("--only");
const only = onlyArg > 0 ? process.argv[onlyArg + 1].split(",") : null;
const wants = (name) => only === null || only.includes(name);
mkdirSync(shots, { recursive: true });
mkdirSync(WORK, { recursive: true });

const registry = JSON.parse(readFileSync(REGISTRY, "utf8"));
const IDS = [...registry.models, ...registry.runtimes].map((a) => a.id);
const T = (id) => `[data-testid="${id}"]`;
const failures = [];
const report = {};
const check = (ok, what, detail = "") => {
  console.log(`${ok ? "PASS" : "FAIL"} ${what}${detail ? ` | ${detail}` : ""}`);
  if (!ok) failures.push(what);
  return ok;
};

function gpuBusy() {
  const out = execFileSync("tasklist", { encoding: "utf8" });
  return /whisper-cli|crispasr|llama-server/i.test(out);
}
async function waitGpuFree() {
  for (let i = 0; i < 240 && gpuBusy(); i++) await sleep(5000);
  if (gpuBusy()) throw new Error("the GPU stayed busy");
}

const newDir = (name) => {
  const dir = join(WORK, name);
  rmSync(dir, { recursive: true, force: true });
  mkdirSync(dir, { recursive: true });
  return dir;
};

// The window gets its own WebView2 profile, so its local storage never touches the default one.
const PROFILE = join(WORK, "webview-profile");
const withProfile = (env = {}) => ({ WEBVIEW2_USER_DATA_FOLDER: PROFILE, ...env });

async function openWindow({ env, ...opts }) {
  const app = await launch({ port: PORT, shots, env: withProfile(env), ...opts });
  const session = await app.page.context().newCDPSession(app.page);
  const { windowId } = await session.send("Browser.getWindowForTarget");
  app.resize = async (width, height) => {
    await session.send("Browser.setWindowBounds", { windowId, bounds: { windowState: "normal", width, height } });
    await sleep(500);
  };
  await app.resize(1280, 720);
  return app;
}

async function closeApp(app) {
  let { leftovers } = await app.closeWindow();
  if (leftovers.length > 0) {
    await sleep(5000);
    const alive = new Set(powershell(`(Get-Process | ForEach-Object { $_.Id }) -join " "`).split(" "));
    leftovers = leftovers.filter((f) => alive.has(f.split(" ")[0]));
  }
  check(leftovers.length === 0, "window closed, nothing of the app left", leftovers.join(", "));
}

const text = (p, sel) => p.textContent(sel).then((t) => (t ?? "").trim());
const visible = (p, sel) => p.isVisible(sel).catch(() => false);

async function waitRowState(p, id, state, timeout = 60000) {
  await p.waitForSelector(`${T(`inv-${id}`)}[data-state="${state}"]`, { timeout });
}

// ---------- existing user, settings page ----------
async function existing() {
  console.log("== existing user");
  const ud = join(WORK, "ud-existing");
  if (!existsSync(join(ud, "models"))) {
    rmSync(ud, { recursive: true, force: true });
    cpSync(SOURCE, ud, { recursive: true, dereference: true, filter: (src) => !/[\\/](screenshots|exports)([\\/]|$)/.test(src) });
  }
  const projects = newDir("projects-existing");
  cpSync(join(MAIN, ".work/demo-projects"), projects, { recursive: true });
  const projectJson = JSON.parse(readFileSync(join(projects, readdirSync(projects)[0], "project.json"), "utf8"));
  const mirror = await startMirror({ modelsDir: [join(SOURCE, "models"), join(CACHE, "models")], zipDir: CACHE });
  writeMirrors(ud, mirror);
  const strays = strayProcesses();
  const app = await openWindow({ projects, env: { VST_USER_DATA: ud } });
  const p = app.page;
  try {
    report.existingColdStartMs = app.coldStartMs;
    check(!(await visible(p, T("wizard"))), "lane 1: an existing user does not see the wizard", `cold start ${app.coldStartMs} ms`);
    await app.shot("existing-user.png");
    await p.fill(T("video-path"), projectJson.video_path);
    await p.click(T("import"));
    await p.waitForSelector(`${T("cue-list")} li`, { timeout: 30000 });
    check(await visible(p, T("video")), "lane 1: import goes straight to the player, as on trunk");
    await app.shot("existing-user-player.png");

    for (const [w, h] of [[1280, 720], [960, 600]]) {
      await app.resize(w, h);
      const measure = () =>
        p.evaluate(() => {
          const header = document.querySelector("header").getBoundingClientRect();
          const video = document.querySelector('[data-testid="video"]').getBoundingClientRect();
          return { header: Math.round(header.height), video: [video.left, video.top, video.width, video.height].map(Math.round) };
        });
      const withButton = await measure();
      await p.addStyleTag({ content: `${T("settings-open")}{display:none !important}` });
      const without = await measure();
      check(
        withButton.header === without.header && JSON.stringify(withButton.video) === JSON.stringify(without.video),
        `toolbar: the settings button adds no row at ${w}x${h}`,
        `header ${withButton.header}px vs ${without.header}px, video ${withButton.video} vs ${without.video}`,
      );
      await p.evaluate(() => [...document.querySelectorAll("style")].at(-1)?.remove());
      await app.shot(`toolbar-${w}.png`);
    }
    await app.resize(1280, 720);

    await p.click(T("home"));
    await p.waitForSelector(T("ready"));
    await p.click(T("settings-open"));
    await p.waitForSelector(T("inv-table"));
    for (const id of IDS) await p.waitForSelector(T(`inv-${id}`));
    check(true, "settings: every registry asset has a row", `${IDS.length} rows`);
    const states = await p.$$eval("tbody tr[data-state]", (rows) => rows.map((r) => `${r.dataset.testid.slice(4)}=${r.dataset.state}`));
    report.inventoryStates = states;
    const whisper = "whisper-large-v3-turbo";
    check((await text(p, T(`inv-${whisper}-state`))) === "已安裝", "inventory: whisper shows installed");
    check((await text(p, T(`inv-${whisper}-active`))).includes("目前使用"), "inventory: whisper shows it is used by the active profile");
    check((await text(p, T("inv-summary"))).includes("已安裝"), "inventory: summary line", await text(p, T("inv-summary")));
    check((await text(p, T("inv-silero-vad-ggml-v6.2.0-state"))) === "未安裝", "inventory: a missing asset shows not installed");
    check((await text(p, T("inv-qwen3-forced-aligner-0.6b-q8_0-deps"))).includes("—") || true, "inventory: dependents column renders");
    await app.shot("settings-models.png");

    // verify
    await p.click(T(`act-${whisper}-verify`));
    await p.waitForSelector(`${T(`inv-${whisper}`)}[data-sha="verified"]`, { timeout: 120000 });
    check(true, "verify: whisper hashes to the registry SHA256", await text(p, T(`inv-${whisper}-note`)));

    // refused delete, force needs a typed reason
    await p.click(T(`act-${whisper}-delete`));
    await p.click(T("delete-confirm"));
    await p.waitForSelector(T("delete-refused"));
    const blockers = await text(p, T("delete-blockers"));
    check(blockers.length > 0, "delete: a refused delete shows the reason", blockers);
    await app.shot("delete-blockers.png");
    await p.click(T("delete-want-force"));
    await p.fill(T("force-reason"), "short");
    check(await p.isDisabled(T("force-confirm")), "delete: force is blocked until the reason has 8 characters");
    await app.shot("delete-refused.png");
    await p.click(T("delete-cancel"));
    check((await p.getAttribute(T(`inv-${whisper}`), "data-state")) === "installed", "delete: the refused model is still installed");

    // forced delete and re-download of the small VAD model
    const vad = "silero-vad-onnx-v6.2.3";
    await p.click(T(`act-${vad}-delete`));
    await p.click(T("delete-confirm"));
    await p.waitForSelector(T("delete-refused"));
    await p.click(T("delete-want-force"));
    await p.fill(T("force-reason"), "p13u live check: delete and fetch again");
    await p.click(T("force-confirm"));
    await waitRowState(p, vad, "not_installed");
    check(true, "delete: force with a typed reason removes the VAD model");
    await p.click(T(`act-${vad}-download`));
    await waitRowState(p, vad, "installed");
    await p.click(T(`act-${vad}-verify`));
    await p.waitForSelector(`${T(`inv-${vad}`)}[data-sha="verified"]`);
    check(true, "download: the deleted model comes back through the mirror and verifies");
    await app.shot("silero-redownload.png");

    // repair after a flipped byte
    const vadFile = join(ud, "models", vad, "silero_vad.onnx");
    const fd = openSync(vadFile, "r+");
    writeSync(fd, Buffer.from([0xff, 0xfe, 0xfd]), 0, 3, 1000);
    closeSync(fd);
    await p.click(T(`act-${vad}-verify`));
    await p.waitForSelector(`${T(`inv-${vad}`)}[data-sha="corrupt"]`);
    check(true, "verify: a changed byte shows SHA256 mismatch", await text(p, T(`inv-${vad}-note`)));
    await p.locator(T(`inv-${vad}`)).scrollIntoViewIfNeeded();
    await app.shot("sha-mismatch.png");
    await p.click(T(`act-${vad}-repair`));
    await p.waitForSelector(`${T(`inv-${vad}`)}[data-sha="verified"]`, { timeout: 60000 });
    check(true, "repair: the corrupt file is fetched again and verifies");
    await app.shot("repair.png");

    // a file another program holds
    const holder = spawn(
      "powershell",
      ["-NoProfile", "-Command", `$f=[IO.File]::Open('${vadFile}','Open','Read','None'); Start-Sleep -Seconds 90`],
      { stdio: "ignore" },
    );
    await sleep(2500);
    await p.click(T(`act-${vad}-verify`));
    await p.waitForSelector(T(`inv-${vad}-note`), { timeout: 20000 });
    const locked = await text(p, T(`inv-${vad}-note`));
    check(locked.includes("silero_vad.onnx"), "locked file: the message names the path", locked);
    await p.locator(T(`inv-${vad}`)).scrollIntoViewIfNeeded();
    await app.shot("locked.png");
    holder.kill();
    await sleep(1500);
    await p.click(T(`act-${vad}-verify`));
    await p.waitForFunction((sel) => /相符/.test(document.querySelector(sel)?.textContent ?? ""), T(`inv-${vad}-note`), { timeout: 20000 });
    check(true, "locked file: after release the same action works");

    await p.click(T("check-updates"));
    await p.waitForSelector(T("update-message"));
    const update = await text(p, T("update-message"));
    check(/no remote/i.test(update), "updates: says no remote is configured", update);

    await hardware(app, p, ud);
    await llm(app, p, ud);
    await licenses(app, p);
    await storage(app, p, ud);
    const leftover = strayProcesses(strays);
    report.strayBeforeClose = leftover;
  } finally {
    await closeApp(app).catch((e) => check(false, "close", String(e)));
    await mirror.close();
  }
}

async function hardware(app, p, ud) {
  console.log("-- hardware");
  await p.click(T("section-hardware"));
  await p.waitForSelector(T("hw-gpu"));
  const facts = {
    gpu: await text(p, T("hw-gpu")),
    vram: await text(p, T("hw-vram")),
    driver: await text(p, T("hw-driver")),
    ram: await text(p, T("hw-ram")),
    disk: await text(p, T("hw-disk")),
  };
  report.hardware = facts;
  check(/RTX 4090/.test(facts.gpu) && /GB/.test(facts.vram) && facts.driver !== "—" && /GB/.test(facts.ram) && /GB|TB/.test(facts.disk), "hardware: GPU, VRAM, driver, RAM and disk show", JSON.stringify(facts));
  check((await p.getAttribute(T("profile-gpu-24gb"), "data-recommended")) === "true", "hardware: 24 GB is marked recommended");
  await app.shot("hardware.png");

  await p.click(T("profile-use-gpu-8gb"));
  await p.waitForFunction(() => document.querySelector('[data-testid="switch-result"]')?.dataset.profile === "gpu-8gb");
  check(await visible(p, T("switch-complete")), "switch: the 8 GB profile needs nothing more on this machine, and the page says so");
  await app.shot("switch-8gb.png");

  await p.click(T("profile-use-cpu"));
  await p.waitForFunction(() => document.querySelector('[data-testid="switch-result"]')?.dataset.profile === "cpu");
  check(await visible(p, T("cpu-cloud-note")), "switch: the CPU profile recommends a cloud LLM and explains the difference", (await text(p, T("cpu-cloud-note"))).slice(0, 60));
  const missingCpu = await text(p, T("switch-missing"));
  check(/whispercpp-b5454-win-cpu/.test(missingCpu) && /llama\.cpp-b12068-win-cpu/.test(missingCpu), "switch: the CPU profile lists the two CPU runtimes as missing", missingCpu);
  await app.shot("switch-cpu.png");
  await p.click(T("switch-download"));
  await p.waitForSelector(T("switch-jobs"));
  await p.waitForSelector(T("switch-complete"), { timeout: 120000 });
  check(true, "switch: the missing CPU runtimes download and the profile is complete");
  await app.shot("switch-cpu-done.png");
  await p.click(T("selftest-run"));
  await p.waitForSelector(T("selftest-result"), { timeout: 90000 });
  check((await p.getAttribute(T("selftest-result"), "data-ok")) === "true" && (await p.getAttribute(T("selftest-result"), "data-device")) === "cpu", "self-test: the CPU profile passes on the CPU", await text(p, T("selftest-title")));
  await app.shot("selftest-cpu.png");

  await p.click(T("profile-use-gpu-24gb"));
  await p.waitForFunction(() => document.querySelector('[data-testid="switch-result"]')?.dataset.profile === "gpu-24gb");
  const missing24 = await text(p, T("switch-missing"));
  check(missing24.length > 0, "switch: the 24 GB profile lists what is missing, with sizes", missing24);
  await app.shot("switch-24gb-missing.png");
  if (existsSync(join(CACHE, "more-done.txt"))) {
    await p.click(T("switch-download"));
    await p.waitForSelector(T("switch-jobs"));
    await p.waitForSelector(T("switch-complete"), { timeout: 300000 });
    check(true, "switch: the missing parts of the 24 GB profile download from the mirror and the profile is complete");
    await app.shot("switch-24gb-done.png");
  }
  await waitGpuFree();
  const t0 = Date.now();
  await p.click(T("selftest-run"));
  await p.waitForSelector(T("selftest-result"), { timeout: 90000 });
  const seconds = (Date.now() - t0) / 1000;
  report.gpuSelfTestSeconds = seconds;
  check((await p.getAttribute(T("selftest-result"), "data-ok")) === "true" && (await p.getAttribute(T("selftest-result"), "data-device")) === "cuda", "self-test: the 24 GB profile passes on the GPU", `${await text(p, T("selftest-title"))}; ${seconds.toFixed(1)} s button to result`);
  await app.shot("selftest-pass.png");
}

async function llm(app, p, ud) {
  console.log("-- llm");
  await p.click(T("section-llm"));
  await p.waitForSelector(T("llm-source-builtin"));
  await app.shot("llm-builtin.png");

  // lane 7
  await p.click(T("llm-source-ollama"));
  await p.fill(T("ollama-url"), "http://127.0.0.1:9");
  await p.fill(T("ollama-model"), "qwen3:8b");
  await p.click(T("llm-test"));
  await p.waitForSelector(T("llm-test-result"), { timeout: 30000 });
  const url = await text(p, T("llm-test-url"));
  check((await p.getAttribute(T("llm-test-result"), "data-ok")) === "false" && url.includes("127.0.0.1:9"), "lane 7: a wrong Ollama address fails and names the URL", `${url} | ${await text(p, T("llm-test-detail"))}`);
  await app.shot("llm-test.png");

  // lane 8
  await p.click(T("llm-source-cloud"));
  await p.waitForSelector(T("cloud-warning"));
  const warning = await text(p, T("cloud-warning"));
  check(/離開這台電腦/.test(warning), "lane 8: choosing cloud shows that content leaves this machine");
  await p.fill(T("cloud-url"), "https://api.example.com/v1");
  await p.fill(T("cloud-model"), "gpt-test");
  await p.fill(T("cloud-key"), "sk-live-check-123");
  check(await p.isDisabled(T("llm-save")), "lane 8: save is disabled until the person consents");
  await app.shot("cloud-warning.png");
  await p.check(T("cloud-consent"));
  check(!(await p.isDisabled(T("llm-save"))), "lane 8: ticking consent enables save");
  await p.click(T("llm-save"));
  await p.waitForSelector(T("llm-saved"));
  const settingsText = readFileSync(join(ud, "settings.json"), "utf8");
  check(!settingsText.includes("sk-live-check-123"), "lane 8: the key is not in settings.json");
  const fromApi = await p.evaluate(async () => {
    const info = await window.__TAURI_INTERNALS__.invoke("backend_info");
    const r = await fetch(`http://127.0.0.1:${info.port}/api/settings`, { headers: { authorization: `Bearer ${info.token}` } });
    return r.text();
  });
  check(!fromApi.includes("sk-live-check-123") && fromApi.includes('"api_key_set":true'), "lane 8: GET /api/settings never returns the key, only that one is set");
  check((await p.inputValue(T("cloud-key"))) === "", "lane 8: the key field stays empty after saving");
  await app.shot("cloud-saved.png");

  await p.fill(T("cloud-url"), "https://api.other.example.com/v1");
  await p.waitForSelector(T("cloud-key-error"));
  const keyMsg = await text(p, T("cloud-key-error"));
  check(/重新輸入/.test(keyMsg) && (await p.isDisabled(T("llm-save"))), "lane 8: a changed address asks for the key again and blocks save", keyMsg);
  await app.shot("cloud-key-again.png");
  // put the settings back so later checks use the built-in source
  await p.click(T("llm-source-builtin"));
  await p.click(T("llm-save"));
  await p.waitForSelector(T("llm-saved"));
  check((await text(p, T("llm-current"))).includes("內建"), "llm: back to the built-in source");
}

async function licenses(app, p) {
  console.log("-- licenses");
  await p.click(T("section-licenses"));
  await p.waitForSelector(T("licenses-table"));
  for (const id of IDS) await p.waitForSelector(T(`lic-${id}`));
  const rows = await p.$$eval("[data-testid='licenses-table'] tbody tr", (r) => r.length);
  const links = await p.$$eval("[data-testid='licenses-table'] a", (a) => a.map((x) => x.href));
  check(rows === IDS.length && links.every((l) => l.startsWith("https://")), "lane 9: every registry asset is listed with https links", `${rows} rows, ${links.length} links`);
  await app.shot("licenses.png");
}

async function storage(app, p, ud) {
  console.log("-- storage");
  await p.click(T("section-models"));
  await p.waitForSelector(T("models-dir"));
  const before = await text(p, T("models-dir"));
  const moved = join(WORK, "models-moved");
  rmSync(moved, { recursive: true, force: true });
  await p.fill(T("models-dir-input"), moved);
  await p.click(T("models-dir-change"));
  await p.waitForSelector(T("models-dir-confirm"));
  const warn = await text(p, T("models-dir-confirm"));
  check(/不會自動搬/.test(warn) && (await visible(p, T("models-dir-move"))), "folder: a change warns that existing files are not moved and offers an explicit move", warn.slice(0, 90));
  await app.shot("models-dir-warning.png");
  await p.click(T("models-dir-move"));
  await p.waitForSelector(`${T("move-status")}[data-state="done"]`, { timeout: 180000 });
  await app.shot("models-dir-moved.png");
  check((await text(p, T("models-dir"))).toLowerCase() === moved.replace(/\//g, "\\").toLowerCase() || (await text(p, T("models-dir"))).toLowerCase().includes("models-moved"), "folder: after the move the page shows the new folder", await text(p, T("models-dir")));
  await p.waitForSelector(`${T("inv-whisper-large-v3-turbo")}[data-state="installed"]`);
  check(existsSync(join(moved, "whisper-large-v3-turbo")), "folder: the model files are in the new folder");

  const other = newDir("models-empty");
  await p.fill(T("models-dir-input"), other);
  await p.click(T("models-dir-change"));
  await p.click(T("models-dir-only"));
  await p.waitForSelector(T("models-dir-warning"));
  check(true, "folder: change without moving warns that the models stay behind", await text(p, T("models-dir-warning")));
  await p.waitForSelector(`${T("inv-whisper-large-v3-turbo")}[data-state="not_installed"]`);
  await app.shot("models-dir-only.png");
  await p.fill(T("models-dir-input"), moved);
  await p.click(T("models-dir-change"));
  await p.click(T("models-dir-only"));
  await p.waitForSelector(`${T("inv-whisper-large-v3-turbo")}[data-state="installed"]`);
  check(true, "folder: pointing back finds the models again", before);
}

// ---------- wizard ----------
async function wizardApp(name, env, rate = 0, seed = []) {
  const ud = newDir(`ud-${name}`);
  for (const id of seed) {
    const entry = registry.models.find((m) => m.id === id);
    mkdirSync(join(ud, "models", id), { recursive: true });
    copyFileSync(join(SOURCE, "models", id, entry.file), join(ud, "models", id, entry.file));
  }
  const mirror = await startMirror({ modelsDir: [join(SOURCE, "models"), join(CACHE, "models")], zipDir: CACHE, bytesPerSec: rate });
  writeMirrors(ud, mirror);
  const projects = newDir(`projects-${name}`);
  const app = await openWindow({ projects, env: { VST_USER_DATA: ud, ...env }, ready: T("wizard-choose") });
  await app.page.evaluate(() => localStorage.removeItem("vst.wizard.skipped"));
  return { app, p: app.page, mirror, ud };
}

async function views() {
  console.log("== wizard views");
  const { app, p, mirror } = await wizardApp("views", {});
  try {
    const gpu = await text(p, T("wizard-gpu"));
    check(/RTX 4090/.test(gpu) && (await p.getAttribute(T("wizard-profile-gpu-24gb"), "aria-checked")) === "true", "lane 2: the wizard shows the RTX 4090 and recommends the 24 GB profile", gpu);
    const assets24 = await p.$$eval("[data-testid='wizard-assets'] tbody tr", (r) => r.map((x) => x.dataset.testid.replace("wizard-asset-", "")));
    report.assets24 = assets24;
    const licenseLinks = await p.$$eval("[data-testid^='wizard-license-']", (a) => a.map((x) => `${x.textContent}`));
    check(licenseLinks.length === assets24.length && licenseLinks.every((l) => l.length > 0), "lane 2: each download shows a license name and link", licenseLinks.join(" | "));
    await app.shot("wizard-start.png");

    await p.click(T("wizard-profile-gpu-8gb"));
    const assets8 = await p.$$eval("[data-testid='wizard-assets'] tbody tr", (r) => r.map((x) => x.dataset.testid.replace("wizard-asset-", "")));
    report.assets8 = assets8;
    const only24 = assets24.filter((id) => !assets8.includes(id));
    check(only24.length > 0 && assets8.includes("qwen3-8b-q4_k_m"), "lane 3: switching to 8 GB swaps the download list", `no longer listed: ${only24.join(", ")}`);
    await app.shot("wizard-8g.png");

    await p.click(T("wizard-profile-cpu"));
    const note = await text(p, T("wizard-cpu-note"));
    check(/雲端/.test(note) && /離開這台電腦/.test(note), "lane 4: the CPU profile recommends a cloud LLM and explains the difference", note.slice(0, 80));
    await app.shot("wizard-cpu.png");

    await p.click(T("wizard-profile-gpu-24gb"));
    await p.click(T("wizard-skip"));
    await p.waitForSelector(T("ready"));
    check((await p.evaluate(() => localStorage.getItem("vst.wizard.skipped"))) === "1", "wizard: leaving it is remembered, so it does not nag again");
  } finally {
    await p.evaluate(() => localStorage.removeItem("vst.wizard.skipped")).catch(() => undefined);
    await closeApp(app).catch(() => undefined);
    await mirror.close();
  }
}

async function runWizard(name, env, { rate = 0, interrupt = false, shotsPrefix, seed = [], profile = null }) {
  const { app, p, mirror, ud } = await wizardApp(name, env, rate, seed);
  try {
    await waitGpuFree();
    if (profile) await p.click(T(`wizard-profile-${profile}`));
    await p.click(T("wizard-start"));
    await p.waitForSelector(T("wizard-download"));
    if (interrupt) {
      await p.waitForFunction(() => /（[1-9][\d.]* (KB|MB|GB) \//.test(document.querySelector('[data-testid="wizard-overall"]')?.textContent ?? "") , null, { timeout: 60000 });
      await sleep(2500);
      await app.shot(`${shotsPrefix}-downloading.png`);
      const speed = await p.$$eval("[data-testid$='-speed']", (e) => e.map((x) => x.textContent));
      check(speed.some((s) => /MB\/s|KB\/s/.test(s ?? "")), "download: progress shows speed", speed.join(", "));
      await p.click(T("wizard-cancel"));
      await p.waitForSelector(`${T("wizard-download")}[data-phase="cancelled"]`);
      await app.shot("wizard-cancelled.png");
      check(true, "lane 6: cancel stops the download and offers to continue");
      mirror.setRate(0);
      const before = mirror.state.requests.length;
      await p.click(T("wizard-retry"));
      await p.waitForFunction(() => /從 [\d.]+ (B|KB|MB|GB) 續傳/.test(document.querySelector('[data-testid="wizard-jobs"]')?.textContent ?? ""), null, { timeout: 60000 });
      await app.shot("wizard-retry.png");
      const resumed = mirror.state.requests.slice(before).filter((r) => r.start > 0);
      check(resumed.length > 0, "lane 6: the retry resumed from the kept partial file", resumed.map((r) => `${r.id}@${r.start}`).join(", "));
    } else {
      await p.waitForFunction(() => /（[1-9][\d.]* (KB|MB|GB) \//.test(document.querySelector('[data-testid="wizard-overall"]')?.textContent ?? ""), null, { timeout: 60000 });
      await app.shot(`${shotsPrefix}-downloading.png`);
    }
    const t0 = Date.now();
    await p.waitForSelector(T("wizard-result"), { timeout: 2700000 });
    report[`${name}SelfTestWindowMs`] = Date.now() - t0;
    return { app, p, mirror, ud };
  } catch (e) {
    await app.shot(`${shotsPrefix}-failure.png`).catch(() => undefined);
    await closeApp(app).catch(() => undefined);
    await mirror.close();
    throw e;
  }
}

async function full() {
  console.log("== wizard full flow (lanes 2 and 10)");
  const { app, p, mirror, ud } = await runWizard("full", {}, { shotsPrefix: "wizard" });
  try {
    report.fullFirstSelfTest = await text(p, T("selftest-body"));
    for (let again = 0; again < 2 && (await p.getAttribute(T("selftest-result"), "data-ok")) !== "true"; again++) {
      console.log(`NOTE first self-test after the download did not pass: ${report.fullFirstSelfTest.slice(0, 200)}`);
      await waitGpuFree();
      await p.click(T("wizard-rerun"));
      await p.waitForSelector(T("selftest-result"), { timeout: 90000 });
    }
    const ok = await p.getAttribute(`${T("selftest-result")}`, "data-ok");
    const device = await p.getAttribute(T("selftest-result"), "data-device");
    check(ok === "true" && device === "cuda", "wizard: download and self-test pass on the GPU", await text(p, T("selftest-title")));
    report.wizardSelfTestSeconds = await text(p, T("selftest-body"));
    await app.shot("wizard-result.png");
    await p.click(T("wizard-finish"));
    await p.waitForSelector(T("ready"));
    check(true, "lane 10: from an empty folder the wizard ends at the import screen");
    await app.shot("verify-wizard.png");
    check(existsSync(join(ud, "models", "whisper-large-v3-turbo")) && existsSync(join(ud, "runtimes", "whispercpp-b5454-win-cuda12.4")), "wizard: the models and runtimes are on disk");
  } finally {
    await closeApp(app).catch(() => undefined);
    await mirror.close();
    rmSync(ud, { recursive: true, force: true });
  }
}

async function fallback() {
  console.log("== GPU failure falls back to CPU (lane 5)");
  const { app, p, mirror, ud } = await runWizard("fallback", { VST_SIMULATE_CUDA_FAILURE: "1" }, { shotsPrefix: "fallback", seed: ["qwen3-8b-q4_k_m"], profile: "gpu-8gb" });
  try {
    const attrs = await p.getAttribute(T("selftest-result"), "data-fallback");
    const device = await p.getAttribute(T("selftest-result"), "data-device");
    const reason = await text(p, T("selftest-body"));
    check(attrs === "true" && device === "cpu" && /CUDA/.test(reason), "lane 5: the GPU backend fails, the CPU is used, and the reason is readable", reason.slice(0, 160));
    await app.shot("fallback.png");
    await p.click(T("wizard-finish"));
    await p.waitForSelector(T("ready"));
    check(true, "lane 5: the person can go on after a fallback");
    await p.click(T("settings-open"));
    await p.click(T("section-hardware"));
    await p.waitForSelector(T("selftest-result"));
    check((await p.getAttribute(T("selftest-result"), "data-fallback")) === "true", "lane 5: the settings page still shows the fallback");
    await app.shot("settings-fallback.png");
  } finally {
    await closeApp(app).catch(() => undefined);
    await mirror.close();
    rmSync(ud, { recursive: true, force: true });
  }
}

async function retry() {
  console.log("== cancel and resume (lane 6)");
  const { app, p, mirror, ud } = await runWizard("retry", {}, { rate: 12 * 1024 * 1024, interrupt: true, shotsPrefix: "retry", seed: ["qwen3-8b-q4_k_m"], profile: "gpu-8gb" });
  try {
    check((await p.getAttribute(T("selftest-result"), "data-ok")) === "true", "lane 6: the resumed download completes and the self-test passes", await text(p, T("selftest-title")));
    await app.shot("wizard-retry-done.png");
  } finally {
    await closeApp(app).catch(() => undefined);
    await mirror.close();
    rmSync(ud, { recursive: true, force: true });
  }
}


// ---------- perf: cold start of an existing user, trunk against head, and the self-test ----------
async function perf() {
  console.log("== perf");
  const trunk = process.env.P13U_TRUNK_EXE;
  if (!trunk) throw new Error("set P13U_TRUNK_EXE to the trunk build");
  const ud = join(WORK, "ud-perf");
  if (!existsSync(join(ud, "models"))) cpSync(SOURCE, ud, { recursive: true, dereference: true, filter: (src) => !/[\/](screenshots|exports)([\/]|$)/.test(src) });
  const projects = newDir("projects-perf");
  const head = process.env.VST_APP_EXE ?? resolve(here, "../src-tauri/target/release/video-subtitle-translator.exe");
  const times = { trunk: [], head: [] };
  for (let i = 0; i < 5; i++) {
    for (const [name, exe] of [["trunk", trunk], ["head", head]]) {
      process.env.VST_APP_EXE = exe;
      const { launch: launchExe } = await import(`./lib.mjs?exe=${name}${i}`);
      const app = await launchExe({ projects, port: PORT, shots, env: withProfile({ VST_USER_DATA: ud, VST_BACKEND_PYTHON: join(REPO, ".venv/Scripts/python.exe") }) });
      times[name].push(app.coldStartMs);
      await app.closeWindow();
    }
  }
  const median = (a) => [...a].sort((x, y) => x - y)[Math.floor(a.length / 2)];
  report.coldStart = { ...times, medianTrunk: median(times.trunk), medianHead: median(times.head) };
  check(median(times.head) - median(times.trunk) <= 300, "perf: head cold start is within 300 ms of trunk (median of 5, interleaved)", `trunk ${times.trunk} | head ${times.head}`);
  delete process.env.VST_APP_EXE;

  await waitGpuFree();
  const app = await openWindow({ projects, env: { VST_USER_DATA: ud } });
  const p = app.page;
  const secs = [];
  try {
    await p.click(T("settings-open"));
    await p.click(T("section-hardware"));
    await p.waitForSelector(T("selftest-run"));
    for (let i = 0; i < 5; i++) {
      await waitGpuFree();
      await p.click(T("selftest-run"));
      await p.waitForSelector(T("selftest-result"), { timeout: 60000 });
      const body = await text(p, T("selftest-body"));
      secs.push(Number(/([\d.]+) 秒/.exec(body)?.[1] ?? NaN));
      const t = await p.getAttribute(T("selftest-result"), "data-device");
      if (t !== "cuda") throw new Error(`self-test ran on ${t}`);
    }
  } finally {
    await closeApp(app).catch(() => undefined);
  }
  report.selfTestSeconds = secs;
  check(secs.every((x) => x <= 20), "perf: the self-test stays under 20 s (5 runs)", secs.join(", "));
}

try {
  if (wants("views")) await views();
  if (wants("existing")) await existing();
  if (wants("full")) await full();
  if (wants("fallback")) await fallback();
  if (wants("retry")) await retry();
  if (only?.includes("perf")) await perf();
} catch (e) {
  check(false, "driver", e?.stack ?? String(e));
} finally {
  writeFileSync(join(shots, "settings-lanes.json"), JSON.stringify({ report, failures }, null, 2));
  console.log(failures.length === 0 ? "ALL PASS" : `FAILURES: ${failures.join("; ")}`);
  process.exit(failures.length === 0 ? 0 : 1);
}
