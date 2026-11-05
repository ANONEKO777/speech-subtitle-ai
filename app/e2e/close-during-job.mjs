// Lane 6 under load: close the window while ASR runs and check nothing below the app survives.
// node e2e/close-during-job.mjs <projects-dir> <new-video> <shots-dir>   (needs the GPU free)
import { writeFileSync } from "node:fs";
import { join } from "node:path";
import { descendants, launch, sleep } from "./lib.mjs";

const [projects, video, shots] = process.argv.slice(2);
if (!projects || !video || !shots) throw new Error("usage: close-during-job.mjs <projects> <video> <shots>");
const app = await launch({ projects, shots });
await app.page.fill('[data-testid="video-path"]', video);
await app.page.click('[data-testid="import"]');
let asr = [];
for (let i = 0; i < 240 && asr.length === 0; i++) {
  await sleep(250);
  asr = descendants(app.pid).filter((p) => /whisper-cli|crispasr/.test(p));
}
if (asr.length === 0) throw new Error("ASR never started");
await app.shot("close-during-asr.png");
const { family, leftovers } = await app.closeWindow();
const line = `closed the window while ASR ran (${asr.join(", ")}). Below the app: ${family.join(", ")}. Still alive 1.5 s after exit: ${leftovers.join(", ") || "none"}`;
writeFileSync(join(shots, "shutdown-during-asr.txt"), line + "\n");
console.log(`${leftovers.length ? "FAIL" : "PASS"} ${line}`);
process.exit(leftovers.length ? 1 : 0);
