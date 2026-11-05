// Lane 1 as a one-shot proof: import a video, wait for the player, check the subtitle sits below
// the video, save a screenshot. node e2e/import-play.mjs <projects-dir> <video> <shots-dir> [name]
import { launch, sleep } from "./lib.mjs";

const [projects, video, shots, name = "import-to-play.png"] = process.argv.slice(2);
if (!projects || !video || !shots) throw new Error("usage: import-play.mjs <projects> <video> <shots> [name]");
const app = await launch({ projects, shots });
console.log(`cold start ${app.coldStartMs} ms (window ${app.pageStartMs} ms, backend ready in page ${app.readyMarkMs} ms)`);
const p = app.page;
await p.fill('[data-testid="video-path"]', video);
await p.click('[data-testid="import"]');
await p.waitForSelector('[data-testid="video"]', { timeout: 15 * 60 * 1000 });
await p.waitForSelector('[data-testid="cue-list"] li');
await p.click('[data-testid="cue-3"] button');
await sleep(800);
await p.evaluate(() => document.querySelector("video").pause());
const box = await p.evaluate(() => ({
  video: document.querySelector('[data-testid="video"]').getBoundingClientRect().toJSON(),
  subtitle: document.querySelector('[data-testid="subtitle"]').getBoundingClientRect().toJSON(),
  text: document.querySelector('[data-testid="subtitle"]').innerText,
  cues: document.querySelectorAll('[data-testid="cue-list"] li').length,
}));
const file = await app.shot(name);
const below = box.subtitle.top >= box.video.bottom - 0.5;
console.log(`${below ? "PASS" : "FAIL"} subtitle below video (video bottom ${box.video.bottom}, subtitle top ${box.subtitle.top}); ${box.cues} cues; text ${JSON.stringify(box.text)}; screenshot ${file}`);
const { family, leftovers: stray } = await app.closeWindow();
console.log(`${stray.length ? "FAIL" : "PASS"} no backend left after the window closed. Below the app: ${family.join(", ")}. Still alive: ${stray.join(", ") || "none"}`);
process.exit(below && stray.length === 0 ? 0 : 1);
