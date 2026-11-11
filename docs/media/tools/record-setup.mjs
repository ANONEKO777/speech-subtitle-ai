// Records the settings page and the first-run wizard, with screenshots. The wizard downloads from the
// local mirror in app/e2e/mirror.mjs (real bytes, throttled), so nothing touches the network.
// VST_USER_DATA is the existing user data (models inside). <wizard-ud> and <mirror-cache> are
// disposable: the first is written to, the second holds the runtime zips and extra models.
// node docs/media/tools/record-setup.mjs <projects-dir> <out-dir> <wizard-ud> <mirror-cache> <models-dir>
import { writeFileSync } from "node:fs";
import { join } from "node:path";
import { pathToFileURL } from "node:url";
import { fixWindow, lib, sleep, snap, startCast } from "./capture.mjs";

const [projects, out, wizardUd, cache, modelsDir] = process.argv.slice(2);
if (!projects || !out || !wizardUd || !cache || !modelsDir) throw new Error("usage: record-setup.mjs <projects> <out> <wizard-ud> <mirror-cache> <models-dir>");
const { startMirror, writeMirrors } = await import(pathToFileURL(join(process.cwd(), "app/e2e/mirror.mjs")).href);
const port = Number(process.env.VST_CDP_PORT ?? 9445);
const tid = (id) => `[data-testid="${id}"]`;

async function session(name, options, run) {
  const app = await lib.launch({ projects, shots: out, port, ...options });
  const p = app.page;
  console.log("viewport", await fixWindow(p));
  await p.mouse.move(640, 700);
  const cast = await startCast(p, join(out, `cast-${name}`));
  const t0 = Date.now();
  const marks = {};
  const mark = (label) => (marks[label] = (Date.now() - t0) / 1000);
  mark("start");
  await run(p, mark, (file) => snap(p, join(out, file)));
  mark("end");
  writeFileSync(join(out, `marks-${name}.json`), JSON.stringify(marks));
  console.log(name, await cast.stop());
  const { leftovers } = await app.closeWindow();
  console.log(name, "leftovers", leftovers);
}

await session("settings", {}, async (p, mark, shot) => {
  await sleep(1200);
  await p.click(tid("settings-open"));
  await p.waitForSelector(tid("inv-table"));
  await p.mouse.move(640, 700);
  await sleep(1800);
  await shot("settings-models.png");
  mark("models");
  await p.mouse.wheel(0, 380);
  await sleep(1800);
  mark("hardware");
  await p.click(tid("section-hardware"));
  await p.waitForSelector(tid("hw-gpu"));
  await p.mouse.move(640, 700);
  await sleep(2500);
  await shot("settings-hardware.png");
  await sleep(1200);
  mark("llm");
  await p.click(tid("section-llm"));
  await sleep(2600);
  await shot("settings-llm.png");
  mark("licenses");
  await p.click(tid("section-licenses"));
  await sleep(2200);
});

const mirror = await startMirror({ modelsDir: [modelsDir, join(cache, "models")], zipDir: cache, bytesPerSec: 24 * 1024 * 1024 });
writeMirrors(wizardUd, mirror);
try {
  await session("wizard", { env: { VST_USER_DATA: wizardUd }, ready: tid("wizard-choose") }, async (p, mark, shot) => {
    await p.evaluate(() => localStorage.removeItem("vst.wizard.skipped"));
    await sleep(2600);
    await p.mouse.move(640, 700);
    await shot("wizard.png");
    mark("choose");
    await p.click(tid("wizard-profile-gpu-8gb"));
    await sleep(2000);
    await p.click(tid("wizard-profile-gpu-24gb"));
    await sleep(1600);
    mark("download");
    await p.click(tid("wizard-start"));
    await p.waitForSelector(tid("wizard-jobs"));
    await sleep(9000);
    await p.mouse.move(640, 700);
    await shot("wizard-downloading.png");
    await sleep(2500);
    await p.click(tid("wizard-cancel"));
    await sleep(1500);
  });
} finally {
  await mirror.close();
}
