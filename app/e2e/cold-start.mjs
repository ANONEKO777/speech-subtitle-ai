// Five launches, each timed from spawn to the ready hint. node e2e/cold-start.mjs <projects-dir> <shots-dir>
import { launch } from "./lib.mjs";

const [projects, shots] = process.argv.slice(2);
const times = [];
for (let i = 0; i < 5; i++) {
  const app = await launch({ projects, shots });
  times.push(app.coldStartMs);
  console.log(`run ${i + 1}: ${app.coldStartMs} ms (window ${app.pageStartMs} ms, backend ready ${app.readyMarkMs} ms)`);
  await app.closeWindow();
}
console.log(`max ${Math.max(...times)} ms, rule 4000 ms`);
