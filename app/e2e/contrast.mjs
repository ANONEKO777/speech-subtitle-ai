// WCAG contrast of every text and focus pairing, computed from the tokens in src/styles.css.
// node e2e/contrast.mjs [out.txt]   exits 1 when a pairing misses its minimum.
import { readFileSync, writeFileSync } from "node:fs";

const css = readFileSync(new URL("../src/styles.css", import.meta.url), "utf8");
const tokens = Object.fromEntries([...css.matchAll(/--([\w-]+):\s*([^;]+);/g)].map((m) => [m[1], m[2].trim()]));

function parse(v) {
  const t = tokens[v.replace(/^--/, "")] ?? v;
  const hex = t.match(/^#([\da-f]{3}|[\da-f]{6})$/i);
  if (hex) {
    const h = hex[1].length === 3 ? [...hex[1]].map((c) => c + c).join("") : hex[1];
    return [0, 2, 4].map((i) => parseInt(h.slice(i, i + 2), 16)).concat(1);
  }
  const rgb = t.match(/^rgb\((\d+) (\d+) (\d+)(?: \/ ([\d.]+))?\)$/);
  if (rgb) return [+rgb[1], +rgb[2], +rgb[3], rgb[4] === undefined ? 1 : +rgb[4]];
  throw new Error(`cannot parse ${v}`);
}
const over = (top, under) => {
  const a = top[3];
  return [0, 1, 2].map((i) => top[i] * a + under[i] * (1 - a)).concat(1);
};
const lum = ([r, g, b]) => {
  const f = (c) => ((c /= 255) <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4);
  return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b);
};
const ratio = (fg, bg) => {
  const [a, b] = [lum(over(fg, bg)), lum(bg)].sort((x, y) => y - x);
  return (a + 0.05) / (b + 0.05);
};
const stack = (...layers) => layers.map(parse).reduce((under, top) => over(top, under));

// [label, foreground, background layers bottom to top, minimum]
const T = 4.5;
const N = 3;
const rows = [
  ["cue timestamp", "--text-faint", ["--surface-1"], T],
  ["cue timestamp, row hover", "--text-faint", ["--surface-1", "--hover"], T],
  ["cue timestamp, active (amber on amber-soft)", "--accent", ["--surface-1", "--accent-soft"], T],
  ["cue en line", "--text-muted", ["--surface-1"], T],
  ["cue en line, row hover", "--text-muted", ["--surface-1", "--hover"], T],
  ["path placeholder", "--text-faint", ["--bg"], T],
  ["path field icon (non-text)", "--text-faint", ["--bg"], N],
  ["progress pending step label, card top", "--text-faint", ["--surface-2"], T],
  ["progress pending step label, card bottom", "--text-faint", ["--surface-1"], T],
  ["progress path line, card top", "--text-faint", ["--surface-2"], T],
  ["progress path line, card bottom", "--text-faint", ["--surface-1"], T],
  ["progress done step label", "--text-muted", ["--surface-1"], T],
  ["status pill", "--text-muted", ["--surface-1"], T],
  ["inactive mode segment", "--text-muted", ["--bg"], T],
  ["ghost button 取消", "--text-muted", ["--surface-1"], T],
  ["tool control text", "--text-muted", ["--bg"], T],
  ["body text on page", "--text", ["--bg"], T],
  ["import button text on amber", "--accent-text", ["--accent"], T],
  ["error text", "--danger", ["--bg", "--danger-soft"], T],
  ["notice text", "--on-accent-light", ["--stage", "--accent-soft"], T],
  ["focus ring on page", "--focus-ring", ["--bg"], N],
  ["focus ring on header", "--focus-ring", ["--surface-2"], N],
  ["focus ring on panel", "--focus-ring", ["--surface-1"], N],
  ["focus ring on button face", "--focus-ring", ["--surface-3"], N],
  ["old focus ring (accent-ring) on page, for comparison", "--accent-ring", ["--bg"], 0],
];

const out = ["pairing                                               ratio  min   result"];
let fails = 0;
for (const [label, fg, bgs, min] of rows) {
  const r = ratio(parse(fg), stack(...bgs));
  const ok = r >= min;
  if (!ok) fails++;
  out.push(`${label.padEnd(54)}${r.toFixed(2).padStart(5)}  ${String(min).padEnd(4)}  ${min === 0 ? "info" : ok ? "PASS" : "FAIL"}`);
}
out.push(`--text-faint ${tokens["text-faint"]}, --focus-ring ${tokens["focus-ring"]}; ${fails} failing`);
console.log(out.join("\n"));
if (process.argv[2]) writeFileSync(process.argv[2], out.join("\n") + "\n");
process.exit(fails ? 1 : 0);
