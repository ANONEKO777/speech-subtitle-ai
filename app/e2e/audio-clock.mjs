// An audio file (mp3) with a finished project: the subtitle and the cue list must follow the playing time with no seek.
// node e2e/audio-clock.mjs <projects-dir> <mp3> <shots-dir> [port]   Env: VST_USER_DATA, WEBVIEW2_USER_DATA_FOLDER (disposable folders), VST_APP_EXE.
// The projects folder holds a finished project of the file (scripts/make_p26b_seed.py makes one for a video; the same steps for an mp3 are in the P38 note).
import { launch, sleep } from "./lib.mjs";

const [projects, media, shots, port = "9471"] = process.argv.slice(2);
if (!projects || !media || !shots) throw new Error("usage: audio-clock.mjs <projects> <mp3> <shots> [port]");
if (!process.env.VST_USER_DATA || !process.env.WEBVIEW2_USER_DATA_FOLDER) throw new Error("set VST_USER_DATA and WEBVIEW2_USER_DATA_FOLDER to disposable folders");
// The disposable user data folder has stand-in model files, so the first-run wizard would show: skip it as a person can.
const START_S = Number(process.env.AUDIO_START_S ?? 0); // where to start playing (a real talk: pick a stretch with speech)
const STRICT = process.env.AUDIO_STRICT !== "0"; // the lateness check needs the invented seed's timing (cues 1.5 s long)
const app = await launch({ projects, shots, port: Number(port), ready: "body" });
const p = app.page;
await p.evaluate(() => localStorage.setItem("vst.wizard.skipped", "1"));
await p.reload();
await p.waitForSelector('[data-testid="ready"]', { timeout: 30000 });
let failed = 0;
const check = (ok, text) => {
  console.log(`${ok ? "PASS" : "FAIL"} ${text}`);
  if (!ok) failed++;
};
try {
  await p.fill('[data-testid="video-path"]', media);
  await p.click('[data-testid="import"]');
  await p.waitForSelector('[data-testid="video"]', { timeout: 60000 });
  await p.waitForSelector('[data-testid="cue-list"] li');
  const starts = await p.$$eval('[data-testid="cue-list"] li[data-start]', (els) => els.map((e) => Number(e.getAttribute("data-start"))));
  check(starts.length >= 3, `the cue list has ${starts.length} cues`);
  const sizes = await p.evaluate(() => {
    const v = document.querySelector("video");
    return new Promise((r) => (v.readyState >= 1 ? r(v.videoWidth) : v.addEventListener("loadedmetadata", () => r(v.videoWidth), { once: true })));
  });
  check(sizes === 0, `the file has no picture (videoWidth ${sizes})`);
  await p.evaluate((start) => {
    const v = document.querySelector("video");
    v.muted = true;
    window.__frames = 0;
    const count = () => {
      window.__frames++;
      v.requestVideoFrameCallback(count);
    };
    v.requestVideoFrameCallback(count);
    v.currentTime = start;
    void v.play();
  }, START_S);
  await p.waitForFunction((start) => document.querySelector("video").currentTime > start + 0.3,  START_S, { timeout: 20000 }).catch(() => undefined);
  // Sample the shown subtitle and the highlighted cue against the clock for 9 s, with no seek.
  const rows = [];
  for (let i = 0; i < 45; i++) {
    rows.push(
      await p.evaluate(() => {
        const v = document.querySelector("video");
        const sub = document.querySelector('[data-testid="subtitle"]');
        const on = document.querySelector('[data-testid="cue-list"] [data-active="true"]');
        return { t: v.currentTime, paused: v.paused, sub: sub?.innerText.trim() ?? "", on: on?.getAttribute("data-start") ?? null, rawSub: sub?.innerHTML.length ?? 0 };
      }),
    );
    await sleep(200);
  }
  console.log(`info the browser presented ${await p.evaluate(() => window.__frames)} video frames; window ${await p.evaluate(() => `${document.visibilityState}, focus ${document.hasFocus()}`)}`);
  const moved = rows.at(-1).t - rows[0].t;
  check(moved > 7, `the clock ran ${moved.toFixed(1)} s without a seek`);
  const texts = new Set(rows.map((r) => r.sub).filter(Boolean));
  check(texts.size >= 3, `the subtitle changed ${texts.size} times while playing: ${[...texts].map((t) => JSON.stringify(t)).join(" | ")}`);
  // A sample is late when it is 300 ms to 1.2 s into a cue (the cues of the seed last 1.5 s) and the subtitle is empty or the list highlights another cue.
  const stale = rows.filter((r) => {
    const own = starts.find((s) => r.t * 1000 >= s + 300 && r.t * 1000 <= s + 1200);
    return own !== undefined && (r.sub === "" || Number(r.on) !== own);
  });
  check(rows.some((r) => r.on !== null && starts.indexOf(Number(r.on)) >= 1), "the highlighted cue moved on past the first one");
  if (STRICT) check(stale.length === 0, `the subtitle and the highlighted cue were never late by more than 300 ms (${stale.length} late samples)`);
  await app.shot("audio-playing.png");
} finally {
  const { leftovers } = await app.closeWindow();
  check(leftovers.length === 0, `no backend of this run left (${leftovers.join(", ") || "none"})`);
}
process.exit(failed ? 1 : 0);
