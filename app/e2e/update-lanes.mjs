// Drives the settings 檢查更新 section and the wizard's Visual C++ note against a local update server.
//   node e2e/update-lanes.mjs <exe> <shots-dir> <work-dir> <test-key-file>
// <exe> must be built with the test public key and plugins.updater.dangerousInsecureTransportProtocol
// (see installer/README.md, "Testing the updater"). The server and the key are throwaway; the real
// updater key is never read. The install step is never pressed: the proof ends at "downloaded,
// signature verified". Own DevTools port and WebView2 profile, no OS input, open_url is logged to a file.
import { execFileSync } from "node:child_process";
import { createServer } from "node:http";
import { mkdirSync, readFileSync, rmSync, writeFileSync, existsSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { launch, sleep } from "./lib.mjs";

const here = dirname(fileURLToPath(import.meta.url));
const [exe, shots, work, keyFile] = process.argv.slice(2);
if (!exe || !shots || !work || !keyFile) throw new Error("usage: update-lanes.mjs <exe> <shots-dir> <work-dir> <test-key-file>");
mkdirSync(shots, { recursive: true });
mkdirSync(work, { recursive: true });
const PORT = Number(process.env.VST_CDP_PORT ?? 9432);
const T = (id) => `[data-testid="${id}"]`;
const failures = [];
const check = (ok, what, detail = "") => {
  console.log(`${ok ? "PASS" : "FAIL"} ${what}${detail ? ` | ${detail}` : ""}`);
  if (!ok) failures.push(what);
};

check(readFileSync(exe).includes("VST_OPEN_URL_LOG"), "the exe knows the VST_OPEN_URL_LOG seam, so no link can open a real browser");

const tauriCli = resolve(here, "../node_modules/@tauri-apps/cli/tauri.js");
function sign(file) {
  execFileSync(process.execPath, [tauriCli, "signer", "sign", "-f", keyFile, "-p", "", file], { stdio: "pipe" });
  return readFileSync(`${file}.sig`, "utf8").trim();
}

const goodBytes = Buffer.from("not a real installer: update proof, good bytes\n".repeat(20000));
const evilBytes = Buffer.from("not a real installer: update proof, TAMPERED bytes\n".repeat(20000));
writeFileSync(join(work, "good-setup.exe"), goodBytes);
writeFileSync(join(work, "evil-setup.exe"), evilBytes);
const goodSig = sign(join(work, "good-setup.exe"));

const hits = [];
let mode = "ok";
const server = createServer((req, res) => {
  hits.push(`${mode} ${req.url}`);
  const base = `http://127.0.0.1:${server.address().port}`;
  const manifest = (file, signature) =>
    JSON.stringify({
      version: "0.2.0",
      notes: "測試用的新版",
      pub_date: "2026-11-07T00:00:00Z",
      platforms: { "windows-x86_64": { signature, url: `${base}/${file}` } },
    });
  if (req.url === "/latest.json") {
    if (mode === "login") {
      res.writeHead(302, { Location: "/users/sign_in" }).end();
    } else if (mode === "hang") {
      return;
    } else if (mode === "stall") {
      res.writeHead(200, { "Content-Type": "application/json" }).end(manifest("stall-setup.exe", goodSig));
    } else if (mode === "missing") {
      res.writeHead(404).end("not found");
    } else if (mode === "same") {
      res.writeHead(200, { "Content-Type": "application/json" }).end(manifest("good-setup.exe", goodSig).replace("0.2.0", "0.1.0"));
    } else if (mode === "tampered") {
      res.writeHead(200, { "Content-Type": "application/json" }).end(manifest("evil-setup.exe", goodSig));
    } else {
      res.writeHead(200, { "Content-Type": "application/json" }).end(manifest("good-setup.exe", goodSig));
    }
  } else if (req.url === "/stall-setup.exe") {
    res.writeHead(200, { "Content-Type": "application/octet-stream", "Content-Length": goodBytes.length });
    res.write(goodBytes.subarray(0, 4096));
  } else if (req.url === "/users/sign_in") {
    res.writeHead(200, { "Content-Type": "text/html" }).end("<html><body>Sign in to GitLab</body></html>");
  } else if (req.url === "/good-setup.exe" || req.url === "/evil-setup.exe") {
    res.writeHead(200, { "Content-Type": "application/octet-stream" }).end(req.url.startsWith("/good") ? goodBytes : evilBytes);
  } else {
    res.writeHead(404).end();
  }
});
await new Promise((r) => server.listen(0, "127.0.0.1", r));
const SERVER = `http://127.0.0.1:${server.address().port}`;

async function start(url, tag) {
  const ud = join(work, `ud-${tag}`);
  rmSync(ud, { recursive: true, force: true });
  mkdirSync(ud, { recursive: true });
  const projects = join(work, `projects-${tag}`);
  mkdirSync(projects, { recursive: true });
  const openLog = join(shots, `open-url-${tag}.log`);
  rmSync(openLog, { force: true });
  const app = await launch({
    exe,
    projects,
    port: PORT,
    shots,
    ready: T("wizard"),
    env: {
      VST_USER_DATA: ud,
      VST_UPDATE_URL: url,
      VST_OPEN_URL_LOG: openLog,
      VST_SIMULATE_NO_VCRUNTIME: "1",
      VST_BACKEND_PYTHON: resolve(here, "../../.venv/Scripts/python.exe"),
      WEBVIEW2_USER_DATA_FOLDER: join(work, `webview-${tag}`),
    },
  });
  const session = await app.page.context().newCDPSession(app.page);
  const { windowId } = await session.send("Browser.getWindowForTarget");
  app.resize = async (width, height) => {
    await session.send("Browser.setWindowBounds", { windowId, bounds: { windowState: "normal", width, height } });
    await sleep(400);
  };
  app.openLog = openLog;
  return app;
}

async function openUpdates(app) {
  const p = app.page;
  await p.click(T("wizard-skip"));
  await p.waitForSelector(T("settings-open"));
  await p.click(T("settings-open"));
  await p.click(T("section-update"));
  await p.waitForSelector(T("update-section"));
}

const text = (p, id) => p.textContent(T(id)).then((t) => (t ?? "").trim());
const fits = (p) =>
  p.evaluate(() => {
    const box = document.querySelector('[data-testid="update-section"]').getBoundingClientRect();
    return { right: Math.round(box.right), width: window.innerWidth, scrollW: document.documentElement.scrollWidth };
  });
async function click(p, id) {
  await p.click(T(id));
}

try {
  // Server-backed lanes.
  const app = await start(`${SERVER}/latest.json`, "main");
  const p = app.page;
  try {
    console.log(`cold start ${app.coldStartMs} ms`);
    await sleep(3000);
    check(hits.length === 0, "nothing contacts the update server at startup", `${hits.length} requests in 3 s`);

    await p.waitForSelector(T("wizard-vcredist"));
    const vcText = await text(p, "wizard-vcredist");
    check(/Visual C\+\+/.test(vcText), "wizard warns about the missing Visual C++ runtime before any download", vcText.slice(0, 60));
    await app.shot("wizard-vcredist.png");
    await p.click(`${T("wizard-vcredist")} a`);
    for (let i = 0; i < 40 && !existsSync(app.openLog); i++) await sleep(100);
    const logged = existsSync(app.openLog) ? readFileSync(app.openLog, "utf8").trim() : "";
    check(
      logged === "https://learn.microsoft.com/cpp/windows/latest-supported-vc-redist",
      "the wizard link is recorded in the open_url log and no browser starts",
      logged,
    );

    await openUpdates(app);
    check((await text(p, "update-check")) === "檢查更新", "the settings page has a 檢查更新 button");
    check(!(await p.isVisible(T("update-status") + " > *")), "idle: no state is shown before a press");
    await app.resize(1280, 720);
    await app.shot("update-idle-1280.png");

    mode = "ok";
    await click(p, "update-check");
    await p.waitForSelector(T("update-available"));
    check(/0\.2\.0/.test(await text(p, "update-available")) && /0\.1\.0/.test(await text(p, "update-available")), "update available shows the new and the current version", await text(p, "update-available"));
    await app.shot("update-available-1280.png");
    await app.resize(960, 600);
    const fit = await fits(p);
    check(fit.right <= fit.width && fit.scrollW <= fit.width, "960x600: the update section fits without horizontal scroll", JSON.stringify(fit));
    await app.shot("update-available-960.png");
    await app.resize(1280, 720);

    const before = hits.length;
    await click(p, "update-download");
    await p.waitForSelector(T("update-downloaded"), { timeout: 30000 });
    check(hits.slice(before).some((h) => h.endsWith("/good-setup.exe")), "the installer was downloaded from the local server", hits.slice(before).join(", "));
    check(/簽章驗證通過/.test(await text(p, "update-downloaded")), "downloaded: the signature was verified against the configured public key");
    check(await p.isVisible(T("update-install")), "the install action is offered, not pressed");
    await app.shot("update-downloaded-1280.png");
    await app.resize(960, 600);
    await app.shot("update-downloaded-960.png");
    await app.resize(1280, 720);

    mode = "same";
    await click(p, "update-check");
    await p.waitForSelector(T("update-uptodate"));
    check(/已是最新版/.test(await text(p, "update-uptodate")), "same version: up to date", await text(p, "update-uptodate"));
    await app.shot("update-uptodate-1280.png");

    mode = "login";
    await click(p, "update-check");
    await p.waitForSelector(T("update-failed"));
    const login = await text(p, "update-failed");
    check(/需要先登入/.test(login) && !/json|expected|decode/i.test(login), "a redirect to a login page fails plainly", login);
    await app.shot("update-failed-login-1280.png");
    await app.resize(960, 600);
    await app.shot("update-failed-login-960.png");
    await app.resize(1280, 720);

    mode = "missing";
    await click(p, "update-check");
    await p.waitForFunction(() => document.querySelector('[data-testid="update-failed"]')?.textContent?.includes("更新來源"));
    check(true, "a 404 fails plainly", await text(p, "update-failed"));

    mode = "tampered";
    await click(p, "update-check");
    await p.waitForSelector(T("update-available"));
    await click(p, "update-download");
    await p.waitForSelector(T("update-failed"), { timeout: 30000 });
    const bad = await text(p, "update-failed");
    check(/簽章不符/.test(bad) && !(await p.isVisible(T("update-install"))), "a download whose bytes do not match the signature is refused and cannot be installed", bad);
    await app.shot("update-failed-signature-1280.png");

    mode = "stall";
    await click(p, "update-check");
    await p.waitForSelector(T("update-available"));
    const s0 = Date.now();
    await click(p, "update-download");
    await p.waitForSelector(T("update-failed"), { timeout: 60000 });
    const stalledFor = Date.now() - s0;
    const stalledText = await text(p, "update-failed");
    check(stalledFor >= 28000 && stalledFor <= 40000 && /沒有再收到資料/.test(stalledText) && !/timeout|timed out/i.test(stalledText), "a download that stops sending data fails after about 30 s with a plain message", `${stalledFor} ms: ${stalledText}`);
    check(!(await p.isVisible(T("update-install"))), "a stalled download cannot be installed");
    check(await p.isEnabled(T("update-check")), "after a stalled download the check button is enabled again");
    await app.shot("update-failed-stalled-1280.png");

    mode = "hang";
    const t0 = Date.now();
    await click(p, "update-check");
    check(await p.isEnabled(T("section-models")), "while a check hangs, the rest of the page still answers");
    await p.waitForSelector(T("update-failed"), { timeout: 30000 });
    const waited = Date.now() - t0;
    check(waited >= 9000 && waited <= 14000 && /沒有在 10 秒內回應/.test(await text(p, "update-failed")), "a server that never answers fails after about 10 s", `${waited} ms: ${await text(p, "update-failed")}`);
    await app.shot("update-failed-timeout-1280.png");
  } finally {
    const { leftovers } = await app.closeWindow();
    check(leftovers.length === 0, "window closed, nothing of the app left", leftovers.join(", "));
  }

  // Unreachable endpoint: nothing listens there.
  const closed = await start("http://127.0.0.1:9/latest.json", "closed");
  try {
    console.log(`cold start with an unreachable update address: ${closed.coldStartMs} ms`);
    await openUpdates(closed);
    const t0 = Date.now();
    await click(closed.page, "update-check");
    await closed.page.waitForSelector(T("update-failed"), { timeout: 30000 });
    const reason = await text(closed.page, "update-failed");
    check(/連不上更新伺服器/.test(reason), "an unreachable endpoint fails plainly", `${Date.now() - t0} ms: ${reason}`);
    await closed.shot("update-failed-unreachable-1280.png");
  } finally {
    const { leftovers } = await closed.closeWindow();
    check(leftovers.length === 0, "window closed, nothing of the app left", leftovers.join(", "));
  }
} finally {
  server.close();
}
console.log(failures.length ? `FAILED: ${failures.join("; ")}` : "all update lanes passed");
process.exit(failures.length ? 1 : 0);
