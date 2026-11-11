// Drives the built Tauri window through WebView2's DevTools port.
// Usage: import { launch } from "./lib.mjs"; const app = await launch({ projects });
import { execFileSync, spawn } from "node:child_process";
import { mkdirSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { chromium } from "playwright-core";
import { openSeams } from "./seams.mjs";

const here = dirname(fileURLToPath(import.meta.url));
export const EXE = process.env.VST_APP_EXE ?? resolve(here, "../src-tauri/target/release/video-subtitle-translator.exe");
export const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

export function powershell(script) {
  return execFileSync("powershell", ["-NoProfile", "-Command", script], { encoding: "utf8" }).trim();
}

const ROOT = resolve(here, "../..");

/** The app's data folder: VST_USER_DATA when set, else the same default the shell uses. */
export function userDataDir() {
  return process.env.VST_USER_DATA || join(process.env.LOCALAPPDATA ?? "", "video-subtitle-translator");
}

/**
 * "pid name" lines for this repo's backend (found by its venv path) and for every whisper-cli,
 * crispasr and llama-server on the machine, other agents' included. Pass the list taken before
 * the launch to see only what appeared since.
 */
export function strayProcesses(before = []) {
  const out = powershell(
    `Get-CimInstance Win32_Process | Where-Object { ($_.Name -match '^python' -and $_.CommandLine -and $_.CommandLine.Contains('${ROOT}')) -or $_.Name -match '^(whisper-cli|crispasr|llama-server)' } | ForEach-Object { "$($_.ProcessId) $($_.Name)" }`,
  );
  const now = out ? out.split("\n").map((l) => l.trim()) : [];
  return now.filter((line) => !before.includes(line));
}

/** "pid name" for every process below `rootPid`, found through parent ids. */
export function descendants(rootPid) {
  const out = powershell(
    `Get-CimInstance Win32_Process | ForEach-Object { "$($_.ProcessId) $($_.ParentProcessId) $($_.Name)" }`,
  );
  const rows = out.split("\n").map((l) => l.trim().split(" ")).filter((r) => r.length >= 3);
  const found = [];
  const queue = [String(rootPid)];
  while (queue.length) {
    const parent = queue.shift();
    for (const [pid, ppid, name] of rows) {
      if (ppid === parent && !found.some((f) => f.startsWith(pid + " "))) {
        found.push(`${pid} ${name}`);
        queue.push(pid);
      }
    }
  }
  return found;
}

/**
 * Starts the app (`exe` defaults to the release build). `env` adds variables for the app and its backend (VST_USER_DATA, VST_SIMULATE_CUDA_FAILURE). VST_OPEN_URL_LOG and VST_OPEN_FOLDER_LOG default to files in `shots`, so links and folders are recorded, never opened,
 * and `ready` is the selector that means the start screen is up (the wizard has its own).
 */
export async function launch({ projects, port = Number(process.env.VST_CDP_PORT ?? 9222), shots = "shots", env = {}, ready = '[data-testid="ready"]', exe = EXE }) {
  mkdirSync(shots, { recursive: true });
  const started = Date.now();
  const child = spawn(exe, [], {
    env: {
      ...process.env,
      ...openSeams(shots, { ...process.env, ...env }),
      ...env,
      VST_PROJECTS: projects,
      WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS: `--remote-debugging-port=${port}`,
    },
    stdio: "ignore",
  });
  let browser;
  for (let i = 0; i < 200 && !browser; i++) {
    try {
      browser = await chromium.connectOverCDP(`http://127.0.0.1:${port}`);
    } catch {
      await sleep(50);
    }
  }
  if (!browser) throw new Error("cannot reach the window's DevTools port");
  const context = browser.contexts()[0];
  const page = context?.pages()[0] ?? (await context.waitForEvent("page"));
  await page.waitForSelector(ready, { timeout: 30000 });
  const coldStartMs = Date.now() - started;
  const marks = await page.evaluate(() => ({
    origin: performance.timeOrigin,
    ready: performance.getEntriesByName("backend-ready")[0]?.startTime ?? null,
  }));
  const pageStartMs = Math.round(marks.origin - started);
  const readyMarkMs = marks.ready === null ? null : Math.round(marks.origin + marks.ready - started);
  return {
    pid: child.pid,
    page,
    browser,
    coldStartMs,
    pageStartMs,
    readyMarkMs,
    shot: async (name) => {
      const file = join(shots, name);
      await page.screenshot({ path: file });
      return file;
    },
    /**
     * Closes the window the way a user does and waits for the app to end. Returns the processes
     * that were below the app (backend, ASR, llama) and the ones of them still alive 1.5 s later.
     */
    closeWindow: async () => {
      const family = descendants(child.pid);
      powershell(`(Get-Process -Id ${child.pid}).CloseMainWindow() | Out-Null`);
      for (let i = 0; i < 100; i++) {
        if (child.exitCode !== null) {
          await sleep(1500);
          const alive = new Set(powershell(`(Get-Process | ForEach-Object { $_.Id }) -join " "`).split(" "));
          return { family, leftovers: family.filter((f) => alive.has(f.split(" ")[0])) };
        }
        await sleep(100);
      }
      throw new Error("the app did not exit after its window was closed");
    },
    kill: () => child.kill(),
  };
}
