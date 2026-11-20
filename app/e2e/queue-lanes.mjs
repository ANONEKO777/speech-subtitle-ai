// P17u live check of the batch queue screen: add many, languages, reorder, pause, cancel, retry,
// live progress, backend kill and restart, open a finished item, on-done opt-in and countdown.
// node e2e/queue-lanes.mjs <projects-dir> <clips-dir> <shots-dir> <power-log> [port]
// Env: VST_USER_DATA must be a disposable copy, and PYTHONPATH must put the fake power executor
// (a sitecustomize.py that replaces backend.core.power.system_power) in front. This driver refuses to
// arm sleep unless the fake wrote its marker to <power-log>.
import { existsSync, readFileSync, readdirSync } from "node:fs";
import { join } from "node:path";
import { descendants, launch, powershell, sleep, strayProcesses } from "./lib.mjs";

const [projects, clips, shots, powerLog, portArg] = process.argv.slice(2);
if (!projects || !clips || !shots || !powerLog) throw new Error("usage: queue-lanes.mjs <projects> <clips> <shots> <power-log> [port]");
const port = Number(portArg ?? 9333);
const results = [];
const note = (lane, ok, detail) => {
  results.push({ lane, ok, detail });
  console.log(`${ok ? "PASS" : "FAIL"} ${lane} ${detail}`);
};
const strays0 = strayProcesses();
const T0 = Date.now();
const stamp = () => `${((Date.now() - T0) / 1000).toFixed(1)}s`;

const app = await launch({ projects, shots, port });
const p = app.page;
console.log(`app pid ${app.pid}, cold start ${app.coldStartMs} ms`);

const until = async (label, fn, ms = 30000, step = 200) => {
  const end = Date.now() + ms;
  for (;;) {
    const v = await fn();
    if (v) return v;
    if (Date.now() > end) throw new Error(`timeout: ${label}`);
    await sleep(step);
  }
};
const rows = () =>
  p.evaluate(() =>
    [...document.querySelectorAll("li.batch-row")].map((li) => ({
      id: li.dataset.rowId,
      name: li.querySelector(".batch-name b")?.textContent ?? "",
      state: li.dataset.state,
      lang: li.querySelector(".batch-lang")?.textContent ?? "",
      step: li.querySelector(".batch-step")?.textContent ?? "",
      percent: li.querySelector(".percent")?.textContent ?? "",
      eta: li.querySelector(".batch-eta-item")?.textContent ?? "",
      error: li.querySelector(".batch-error")?.textContent ?? "",
    })),
  );
const names = async () => (await rows()).map((r) => r.name.replace(/\.mp4$/, ""));
const row = async (name) => (await rows()).find((r) => r.name.startsWith(name));
const idOf = async (name) => (await row(name)).id;
const tid = (id) => `[data-testid="${id}"]`;
const text = (sel) => p.locator(sel).first().innerText();
const logText = () => (existsSync(powerLog) ? readFileSync(powerLog, "utf8") : "");

await p.setViewportSize({ width: 1280, height: 800 }).catch(() => undefined);

// 1 empty state
await p.waitForSelector(tid("batch-panel"));
note("1 empty queue", (await p.locator(tid("batch-empty")).count()) === 1 && (await text(tid("batch-count"))) === "0/0", "the home screen shows the panel with the empty text");
await app.shot("01-empty.png");

// 2 pause the queue first, so the order can be set up
await p.click(tid("batch-pause"));
await until("paused note", async () => (await p.locator(tid("batch-paused-note")).count()) === 1);
note("2 queue pause", (await text(tid("batch-pause"))).includes("繼續"), "the button turns into resume and the note shows");

// 3 drop several files at once
const A = join(clips, "alpha-90s.mp4");
const B = join(clips, "bravo-60s.mp4");
const C = join(clips, "charlie-45s.mp4");
const D = join(clips, "corrupt-delta.mp4");
const emit = (event, payload) => p.evaluate(([e, pl]) => window.__TAURI_INTERNALS__.invoke("plugin:event|emit", { event: e, payload: pl }), [event, payload]);
await emit("tauri://drag-enter", { paths: [], position: { x: 10, y: 10 } });
await emit("tauri://drag-drop", { paths: [A, B, C, D], position: { x: 10, y: 10 } });
await p.waitForSelector(tid("add-dialog"));
const dropped = await p.locator(tid("add-row")).count();
note("3 drop of several files", dropped === 4, `${dropped} rows in the add dialog`);

// 4 languages: default, apply to all, per item, experimental label. A row holds a set of targets, so a pick is the set of its checkboxes.
const setTargets = async (control, codes) => {
  await control.click();
  const list = p.locator(tid("add-row-lang-list") + ", " + tid("add-default-lang-list")).first();
  for (const want of [true, false]) {
    for (const input of await list.locator("input").all()) {
      const code = (await input.getAttribute("data-testid")).replace(/^add-(row|default)-lang-/, "");
      if (codes.includes(code) === want && (await input.isChecked()) !== want) await input.click();
    }
  }
  await p.keyboard.press("Escape");
};
const rowCodes = () => p.locator(tid("add-row-lang")).evaluateAll((els) => els.map((e) => e.dataset.codes));
await p.locator(tid("add-default-lang")).click();
const langOptions = await p.locator(tid("add-default-lang-list") + " label").allInnerTexts();
await p.keyboard.press("Escape");
await setTargets(p.locator(tid("add-default-lang")), ["ja"]);
await p.click(tid("add-apply-all"));
const allJa = (await rowCodes()).every((v) => v === "ja");
await setTargets(p.locator(tid("add-row-lang")).nth(0), ["zh-TW"]);
await setTargets(p.locator(tid("add-row-lang")).nth(3), ["zh-TW"]);
await setTargets(p.locator(tid("add-row-lang")).nth(1), ["ko"]);
await p.locator(tid("add-row-lang")).nth(1).click();
const exp = await p.locator(tid("add-row-lang-list") + " .chip-exp").count();
await p.keyboard.press("Escape");
await app.shot("02-add-dialog-ko.png");
await setTargets(p.locator(tid("add-row-lang")).nth(1), ["ja"]);
const values = await rowCodes();
note("4 languages", allJa && exp === 1 && values.join() === "zh-TW,ja,ja,zh-TW" && langOptions.some((o) => o.includes("實驗性")), `apply-all gave all ja; experimental chip shown once for ko; final ${values.join()}; ${langOptions.filter((o) => o.includes("實驗性")).length} options labeled`);
await app.shot("02-add-dialog.png");
await p.click(tid("add-submit"));
await p.waitForSelector(tid("add-dialog"), { state: "detached" });
await until("4 rows", async () => (await rows()).length === 4);
let r = await rows();
note("5 items queued paused", r.every((x) => x.state === "queued") && (await names()).join() === "alpha-90s,bravo-60s,charlie-45s,corrupt-delta" && r[0].lang.includes("繁") && r[1].lang.includes("日"), `states ${r.map((x) => x.state).join()}, langs ${r.map((x) => x.lang).join(" | ")}`);
await app.shot("03-queued.png");

// 6 reorder by dragging the third row above the first
const handle = async (name) => p.locator(tid(`qdrag-${await idOf(name)}`)).boundingBox();
const from = await handle("charlie");
const first = await handle("alpha");
await p.mouse.move(from.x + from.width / 2, from.y + from.height / 2);
await p.mouse.down();
await p.mouse.move(from.x + 10, (from.y + first.y) / 2, { steps: 6 });
await p.mouse.move(from.x + 10, first.y - 4, { steps: 6 });
await app.shot("04a-dragging.png");
await p.mouse.up();
await until("order after drag", async () => (await names())[0] === "charlie-45s", 8000).catch(async (e) => {
  console.log(`drag diagnostics: order ${(await names()).join()}, toast ${(await p.locator(tid("toast-text")).count()) ? await text(tid("toast-text")) : "none"}`);
  await app.shot("04b-drag-failed.png");
  throw e;
});
note("6 drag to reorder", (await names()).join() === "charlie-45s,alpha-90s,bravo-60s,corrupt-delta", `order now ${(await names()).join()}`);
// keyboard nudge, then back
await p.locator(tid(`qdrag-${await idOf("bravo")}`)).focus();
await p.keyboard.press("ArrowUp");
await until("nudge", async () => (await names())[1] === "bravo-60s");
note("6b keyboard reorder", (await names()).join() === "charlie-45s,bravo-60s,alpha-90s,corrupt-delta", `order now ${(await names()).join()}`);
await p.locator(tid(`qdrag-${await idOf("bravo")}`)).focus();
await p.keyboard.press("ArrowDown");
await until("nudge back", async () => (await names())[2] === "bravo-60s");
await app.shot("04-reordered.png");

// 6c drag the top row to the bottom and the bottom row to the top, ten times each; the page and the backend must agree
const serverIds = () =>
  p.evaluate(async () => {
    const b = await window.__TAURI_INTERNALS__.invoke("backend_info");
    const res = await fetch(`http://127.0.0.1:${b.port}/api/queue`, { headers: { authorization: `Bearer ${b.token}` } });
    return (await res.json()).items.sort((x, y) => x.position - y.position).map((i) => i.id);
  });
const dragRow = async (fromIndex, toIndex) => {
  const list = await rows();
  const src = await p.locator(tid(`qdrag-${list[fromIndex].id}`)).boundingBox();
  const dst = await p.locator(tid(`qrow-${list[toIndex].id}`)).boundingBox();
  const y = toIndex > fromIndex ? dst.y + dst.height - 2 : dst.y + 2;
  await p.mouse.move(src.x + src.width / 2, src.y + src.height / 2);
  await p.mouse.down();
  await p.mouse.move(src.x + 10, (src.y + y) / 2, { steps: 6 });
  await p.mouse.move(src.x + 10, y, { steps: 6 });
  await p.mouse.up();
};
const dragResults = { up: 0, down: 0 };
for (let n = 1; n <= 10; n++) {
  for (const dir of ["down", "up"]) {
    const before = (await rows()).map((x) => x.id);
    const last = before.length - 1;
    const want = dir === "down" ? [...before.slice(1), before[0]] : [before[last], ...before.slice(0, last)];
    await dragRow(dir === "down" ? 0 : last, dir === "down" ? last : 0);
    const settled = await until(`drag ${dir} ${n}`, async () => (await serverIds()).join() === want.join(), 4000).then(() => true, () => false);
    await sleep(150);
    const ui = (await rows()).map((x) => x.id);
    const server = await serverIds();
    const ok = settled && ui.join() === want.join() && server.join() === want.join();
    if (ok) dragResults[dir]++;
    else console.log(`    FAIL drag ${dir} ${n}: ui=${ui.join()} srv=${server.join()} want=${want.join()}`);
  }
}
note("6c drag reorder downward x10", dragResults.down === 10, `${dragResults.down}/10 ok (page and GET /api/queue agree)`);
note("6c drag reorder upward x10", dragResults.up === 10, `${dragResults.up}/10 ok (page and GET /api/queue agree)`);

// 7 item pause and resume, cancel and retry on queued items
const bId = await idOf("bravo");
await p.click(tid(`qpause-${bId}`));
await until("item paused", async () => (await row("bravo")).state === "paused");
const pausedOk = (await p.locator(tid(`qresume-${bId}`)).count()) === 1;
await app.shot("05a-item-paused.png");
await p.click(tid(`qresume-${bId}`));
await until("item resumed", async () => (await row("bravo")).state === "queued");
note("7 item pause and resume", pausedOk, "paused shows resume; resume returns to queued");
await p.click(tid(`qcancel-${bId}`));
await until("item cancelled", async () => (await row("bravo")).state === "cancelled");
const cancelOk = (await p.locator(tid(`qretry-${bId}`)).count()) === 1;
await app.shot("05b-item-cancelled.png");
await p.click(tid(`qretry-${bId}`));
await until("item retried", async () => (await row("bravo")).state === "queued");
note("8 cancel and retry", cancelOk && (await names()).join() === "charlie-45s,alpha-90s,corrupt-delta,bravo-60s", `retry moved bravo to the end: ${(await names()).join()}`);
await app.shot("05-before-run.png");

// 9 resume the queue and watch it run
const marker = logText();
const gpuBefore = powershell(`(Get-Process whisper-cli,crispasr,llama-server -ErrorAction SilentlyContinue | Measure-Object).Count`);
console.log(`${stamp()} gpu processes before the run: ${gpuBefore}`);
await p.click(tid("batch-pause"));
await until("running", async () => (await rows()).some((x) => x.state === "running"), 60000);
const samples = [];
let shotRun = false;
const seenSteps = new Set();
const overallSamples = [];
const etaTexts = new Set();
let killedAt = null;
let lostSeen = false;
let relinked = false;
let killedItem = null;
const deadline = Date.now() + 25 * 60 * 1000;
let killed = false;
let pausedRunning = false;
let cancelledRunning = false;
while (Date.now() < deadline) {
  const rs = await rows();
  const run = rs.find((x) => x.state === "running");
  const overall = Number(await p.locator(tid("batch-overall")).getAttribute("aria-valuenow"));
  overallSamples.push(overall);
  etaTexts.add(await text(tid("batch-eta")));
  if (run) {
    seenSteps.add(`${run.name}:${run.step}`);
    samples.push(`${stamp()} ${run.name} ${run.step} ${run.percent} eta=${run.eta}`);
    if (!shotRun && run.percent && parseInt(run.percent) > 10) {
      shotRun = true;
      await app.shot("06-running.png");
    }
    if (!pausedRunning && run.name.startsWith("charlie") && run.step.includes("翻譯")) {
      pausedRunning = true;
      await p.click(tid(`qpause-${run.id}`));
      await until("running item paused", async () => (await row("charlie")).state === "paused");
      await app.shot("06b-running-item-paused.png");
      const shown = await text(tid(`qstate-${run.id}`));
      await sleep(1500);
      await p.click(tid(`qresume-${run.id}`));
      await until("paused item runs again", async () => ["queued", "running"].includes((await row("charlie")).state));
      note("9b pause a running item", shown === "已暫停", `charlie paused while translating (row says ${shown}); the queue went on with the next item; resumed, it ran again`);
    }
    if (!cancelledRunning && run.name.startsWith("bravo") && run.step.includes("翻譯")) {
      cancelledRunning = true;
      await p.click(tid(`qcancel-${run.id}`));
      await until("running item cancelled", async () => (await row("bravo")).state === "cancelled");
      await app.shot("06c-running-item-cancelled.png");
      await p.click(tid(`qretry-${run.id}`));
      await until("cancelled item queued", async () => (await row("bravo")).state !== "cancelled");
      note("9c cancel a running item then retry", true, "bravo cancelled while translating, retried, and runs to the end");
    }
    if (!killed && run.name.startsWith("alpha") && run.step.includes("翻譯")) {
      killed = true;
      killedItem = run;
      const family = descendants(app.pid).filter((f) => /python/i.test(f));
      console.log(`${stamp()} killing backend: ${family.join("; ")}`);
      const keep = family.map((f) => f.split(" ")[0]);
      powershell(`Stop-Process -Id ${[...keep].reverse().join(",")} -Force`);
      killedAt = Date.now();
    }
  }
  if (killed && !relinked) {
    const link = await p.locator(tid("batch-link")).count();
    if (link > 0 && !lostSeen) {
      lostSeen = true;
      await app.shot("07-connection-lost.png");
      console.log(`${stamp()} UI shows the lost-connection banner`);
    }
    const state = await p.locator(tid("batch-panel")).getAttribute("data-link");
    if (lostSeen && state === "live" && link === 0) {
      relinked = true;
      console.log(`${stamp()} UI reconnected after ${((Date.now() - killedAt) / 1000).toFixed(1)}s`);
      await app.shot("08-reconnected.png");
    }
  }
  if (rs.every((x) => ["done", "failed", "cancelled"].includes(x.state))) break;
  await sleep(500);
}
r = await rows();
const final = Object.fromEntries(r.map((x) => [x.name.split("-")[0], x.state]));
note("9 queue ran", final.charlie === "done" && final.alpha === "done" && final.bravo === "done" && final.corrupt === "failed", `final ${JSON.stringify(final)}`);
const stepsSeen = [...seenSteps].map((s) => s.split(":")[1].replace(/（.*/, ""));
note("10 live step and progress", new Set(stepsSeen).size >= 4, `distinct steps seen: ${[...new Set(stepsSeen)].join(",")}; ${samples.length} samples; first ${samples[0]}; last ${samples[samples.length - 1]}`);
note("11 overall progress", overallSamples[overallSamples.length - 1] === 100 && Math.max(...overallSamples) === 100, `overall went ${overallSamples[0]} to ${overallSamples[overallSamples.length - 1]}%; ETA texts: ${[...etaTexts].join(" | ")}`);
note("12 kill and restart", killed && lostSeen && relinked, `killed ${killedItem?.name} in translate; banner seen ${lostSeen}; reconnected ${relinked}; alpha finished ${final.alpha}`);
const corrupt = r.find((x) => x.name.startsWith("corrupt"));
note("13 corrupt file fails alone", corrupt.state === "failed" && corrupt.error.length > 0, `error: ${corrupt.error.slice(0, 120)}`);
await app.shot("09-all-finished.png");

// 14 finished toast and notification
await until("finished toast", async () => (await p.locator(tid("toast-text")).count()) === 1, 30000);
powershell(`Add-Type -AssemblyName System.Windows.Forms,System.Drawing; $b=[System.Windows.Forms.Screen]::PrimaryScreen.Bounds; $w=520; $h=260; $bmp=New-Object System.Drawing.Bitmap $w,$h; $g=[System.Drawing.Graphics]::FromImage($bmp); $g.CopyFromScreen(($b.Right-$w),($b.Bottom-$h-30),0,0,$bmp.Size); $bmp.Save('${join(shots, "10b-windows-notification.png").replace(/\\/g, "/")}')`);
const toast = await p.locator(tid("toast-text")).count();
note("14 finished toast", toast === 1 && (await text(tid("toast-text"))).includes("佇列已全部處理完"), toast ? await text(tid("toast-text")) : "no toast");
await app.shot("10-done-toast.png");

// 15 click a finished item: it opens in the player in its own language
const cId = await idOf("charlie");
await p.click(tid(`qopen-${cId}`));
await p.waitForSelector(tid("video"), { timeout: 30000 });
await p.click(tid("cue-3"));
await sleep(500);
const cueText = await p.locator(tid("cue-3")).innerText();
note("15 open finished item", /[぀-ヿ]/.test(cueText), `the player opened in ja: cue 3 reads ${cueText.replace(/\n/g, " / ").slice(0, 80)}`);
await app.shot("11-open-in-player.png");

// 16 queue stays reachable from the player
const chip = await p.locator(tid("queue-chip")).innerText();
await p.click(tid("queue-chip"));
await until("queue tab", async () => (await p.locator(tid("batch-panel")).count()) === 1);
note("16 queue inside the player", (await p.locator(tid("video")).count()) === 1 && (await p.locator(tid("batch-panel")).count()) === 1, `chip says "${chip.replace(/\n/g, " ")}"; video and queue tab both on screen`);
await app.shot("12-player-queue-tab.png");

// 16b the toolbar stays on one row (header under 60 px, P16 measured 50.8) and the video boxes stay where P16 put them (1280x720 [13,64,903,483], 960x600 [13,64,582,365])
const resize = async (width, height) => {
  await p.setViewportSize({ width, height });
  await sleep(700);
};
const layout = () =>
  p.evaluate(() => {
    const box = (sel) => {
      const b = document.querySelector(sel).getBoundingClientRect();
      return [b.x, b.y, b.width, b.height].map(Math.round);
    };
    const tops = [...document.querySelectorAll("header button, header input")].map((e) => Math.round(e.getBoundingClientRect().top));
    return { header: document.querySelector("header").getBoundingClientRect().height, tops, video: box('[data-testid="video"]'), subtitle: box('[data-testid="subtitle"]') };
  });
for (const [w, h, video] of [[1280, 720, [13, 64, 903, 483]], [960, 600, [13, 64, 582, 365]]]) {
  await resize(w, h);
  const l = await layout();
  note(`16b toolbar at ${w}`, l.header < 60 && l.video.every((v, i) => Math.abs(v - video[i]) <= 1), `header ${l.header.toFixed(1)} px, video [${l.video}], subtitle [${l.subtitle}]`);
  await app.shot(`12b-toolbar-${w}.png`);
}
await resize(1280, 800);

// 17 on-done opt-in with a warning, then the countdown with the fake executor
const marked = logText().includes("patched");
note("17a fake power executor in place", marked, `marker in ${powerLog}: ${marked}`);
if (!marked) throw new Error("the fake power executor is not in place, refusing to arm sleep");
await p.selectOption(tid("ondone-select"), "sleep");
await p.waitForSelector(tid("ondone-warn"));
await p.locator(tid("ondone-warn")).scrollIntoViewIfNeeded();
const disabledBefore = await p.locator(tid("ondone-confirm")).isDisabled();
await app.shot("13-ondone-warning.png");
await p.check(tid("ondone-agree"));
await p.click(tid("ondone-confirm"));
await p.waitForSelector(tid("ondone-armed"));
note("17 opt-in", disabledBefore && (await p.locator(tid("ondone-armed")).count()) === 1, "confirm disabled until the box is ticked; armed note shown after");
await app.shot("14-ondone-armed.png");
const dId = (await rows()).find((x) => x.name.startsWith("corrupt")).id;
await p.click(tid(`qretry-${dId}`));
await p.waitForSelector(tid("countdown"), { timeout: 30000 });
const s1 = Number(await text(tid("countdown-seconds")));
await app.shot("15-countdown.png");
await sleep(4000);
const s2 = Number(await text(tid("countdown-seconds")));
note("18 countdown shown", s1 >= 55 && s2 <= s1 - 3, `seconds ${s1} then ${s2} four seconds later`);
await p.click(tid("countdown-cancel"));
await p.waitForSelector(tid("countdown"), { state: "detached", timeout: 10000 });
await sleep(4000);
const fired = logText().split("\n").filter((l) => l.includes("FAKE"));
note("19 countdown cancelled", fired.length === 0 && (await p.locator(tid("countdown")).count()) === 0, `modal gone; fake executor calls: ${fired.length}`);
await p.selectOption(tid("ondone-select"), "notify");
await until("notify saved", async () => (await p.locator(tid("ondone-armed")).count()) === 0);
await app.shot("16-after-cancel.png");

// 20 remove finished
await p.click(tid("batch-clear"));
await until("cleared", async () => (await rows()).length === 0);
note("20 clear finished", true, "all finished rows removed");
await app.shot("17-cleared.png");

const closed = await app.closeWindow();
const strays = strayProcesses(strays0);
note("21 shutdown", closed.leftovers.length === 0 && strays.length === 0, `leftovers ${closed.leftovers.join(",") || "none"}; strays ${strays.join(",") || "none"}`);
console.log("--- timeline samples ---");
console.log(samples.filter((_, i) => i % 6 === 0).join("\n"));
const failed = results.filter((x) => !x.ok);
console.log(`${results.length - failed.length}/${results.length} PASS`);
process.exit(failed.length === 0 ? 0 : 1);
