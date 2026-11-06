// Checks the four READMEs: same heading outline, same images and links, every relative target exists,
// every in-page anchor matches a heading, a language switcher on top, and no long dashes.
// node docs/media/tools/check-readmes.mjs   (run from the repository root)
import { existsSync, readFileSync, statSync } from "node:fs";

const FILES = ["README.md", "README.en.md", "README.zh-CN.md", "README.ja.md"];
const failures = [];
const fail = (file, what) => failures.push(`${file}: ${what}`);

const slug = (title) =>
  title
    .trim()
    .toLowerCase()
    .replace(/[^\p{L}\p{N}\s-]/gu, "")
    .replace(/\s/g, "-");

const parsed = FILES.map((file) => {
  const text = readFileSync(file, "utf8");
  const body = text.replace(/```[\s\S]*?```/g, "");
  const headings = [...body.matchAll(/^(#{1,6}) (.+)$/gm)].map((m) => ({ level: m[1].length, title: m[2] }));
  const targets = [...body.matchAll(/(?:\]\(|src=")([^)"\s]+)/g)].map((m) => m[1]);
  return { file, text, body, headings, targets };
});

const [first] = parsed;
for (const doc of parsed) {
  const outline = doc.headings.map((h) => h.level).join("");
  if (outline !== first.headings.map((h) => h.level).join("")) fail(doc.file, `heading outline ${outline} differs from ${first.file}`);

  const isMedia = (t) => !/^(https?:|#)/.test(t) && !/^README[\w.-]*\.md$/.test(t);
  const relative = doc.targets.filter(isMedia);
  const firstRelative = first.targets.filter(isMedia);
  if (JSON.stringify(relative) !== JSON.stringify(firstRelative)) fail(doc.file, "relative links and images differ from " + first.file);
  for (const target of relative) {
    if (!existsSync(target)) fail(doc.file, `missing target ${target}`);
    else if (statSync(target).size === 0) fail(doc.file, `empty target ${target}`);
  }

  const slugs = new Set(doc.headings.map((h) => slug(h.title)));
  for (const target of doc.targets.filter((t) => t.startsWith("#"))) {
    if (!slugs.has(decodeURIComponent(target.slice(1)))) fail(doc.file, `anchor ${target} matches no heading`);
  }

  const external = doc.targets.filter((t) => /^https?:/.test(t));
  const firstExternal = first.targets.filter((t) => /^https?:/.test(t));
  if (JSON.stringify(external) !== JSON.stringify(firstExternal)) fail(doc.file, "external links differ from " + first.file);

  const top = doc.text.split("\n").slice(0, 6).join("\n");
  for (const other of FILES) if (other !== doc.file && !top.includes(`](${other})`)) fail(doc.file, `no switcher link to ${other}`);
  if (/[—―–]/.test(doc.text)) fail(doc.file, "contains a long dash");
}

console.log(failures.length ? failures.join("\n") : `ok: ${FILES.length} READMEs, ${first.headings.length} headings, ${first.targets.length} links each`);
process.exit(failures.length ? 1 : 0);
