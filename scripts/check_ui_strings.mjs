// The guard for the multi-language UI (docs/I18N-PLAN.md). User-facing text belongs in
// app/src/i18n/catalog. This script counts the literals still written in the code and compares the
// count per file with app/i18n-baseline.json, so the number can fall and never rise.
//
//   npm run check:strings              check, from app/ (what CI runs)
//   npm run check:strings -- --list    print every literal with file:line (the inventory)
//   npm run check:strings -- --update  lower the baseline to today's counts (never raises it)
//
// What counts as a user-facing literal, outside tests and app/src/i18n:
//   - a string or template literal with a CJK character, a kana or a full-width character
//   - JSX text, or a title, aria-label, placeholder or alt attribute, with a Latin phrase that is
//     not one identifier-like token ("Hello world" counts, "Ollama" and "GPU" do not)
// Single Latin words are left out on purpose: brand names and units would drown the signal.
//
// Known limits, kept on purpose so the scanner stays small:
//   - Latin text in code (setError("Could not save"), new Error("...")) is never counted. Code
//     strings are checked for CJK only, so a new English-only string in code passes.
//   - A unicode escape (backslash, u, four hex digits) of a CJK character is not CJK to the scanner.
//   - A Latin phrase in an attribute expression is counted only when the expression is one plain
//     string, as in title={"Close"}. A ternary or a template with ${} is not.
//   - The count is per file. Swapping one literal for another in the same file leaves the count
//     equal and passes, and so does moving one out of a file while adding one to it.

import { readFileSync, readdirSync, statSync, writeFileSync } from "node:fs";
import { dirname, join, relative, sep } from "node:path";
import { fileURLToPath } from "node:url";

const root = process.env.UI_STRINGS_ROOT ?? join(dirname(fileURLToPath(import.meta.url)), "..", "app");
const srcDir = join(root, "src");
const baselinePath = join(root, "i18n-baseline.json");

const CJK = /[　-ヿ㐀-䶿一-鿿＀-￯]/;
const USER_ATTRS = new Set(["title", "aria-label", "placeholder", "alt"]);

const PLAIN_STRING_EXPRESSION = /^\{\s*(?:(["'])((?:\\.|(?!\1)[^\\\n])*)\1|`([^`$\\]*)`)\s*\}/;

const isPhrase = (text) => {
  const t = text.replace(/\s+/g, " ").trim();
  return /[A-Za-z]{2}/.test(t) && !/^[\w.\-:/@#]+$/.test(t);
};
const isUserText = (text) => CJK.test(text) || isPhrase(text);

/** Scans one source file and returns the user-facing literals as { line, kind, text }. */
export function scan(src, { jsx }) {
  const found = [];
  let i = 0;
  const lineAt = (pos) => {
    let n = 1;
    for (let k = 0; k < pos; k++) if (src.charCodeAt(k) === 10) n++;
    return n;
  };
  const add = (pos, kind, text) => found.push({ line: lineAt(pos), kind, text: text.replace(/\s+/g, " ").trim().slice(0, 60) });
  const fail = (what) => {
    throw new Error(`${what} near line ${lineAt(i)}`);
  };

  function skipComment() {
    if (src.startsWith("//", i)) {
      while (i < src.length && src[i] !== "\n") i++;
      return true;
    }
    if (src.startsWith("/*", i)) {
      const end = src.indexOf("*/", i + 2);
      if (end < 0) fail("unterminated comment");
      i = end + 2;
      return true;
    }
    return false;
  }

  function scanString(quote) {
    const start = i++;
    let text = "";
    while (i < src.length && src[i] !== quote) {
      if (src[i] === "\\") text += src[i++];
      if (src[i] === "\n") fail("unterminated string");
      text += src[i++];
    }
    if (i >= src.length) fail("unterminated string");
    i++;
    if (CJK.test(text)) add(start, "string", text);
  }

  function scanTemplate() {
    const start = i++;
    let text = "";
    while (i < src.length && src[i] !== "`") {
      if (src[i] === "\\") text += src[i++];
      else if (src[i] === "$" && src[i + 1] === "{") {
        i += 2;
        scanCode("}");
        continue;
      }
      text += src[i++];
    }
    if (i >= src.length) fail("unterminated template");
    i++;
    if (CJK.test(text)) add(start, "template", text);
  }

  /** Scans code until the `}` that closes an expression, or to the end of the file when `end` is null. */
  function scanCode(end) {
    let depth = 0;
    let prev = "";
    let prev2 = "";
    let word = "";
    while (i < src.length) {
      const c = src[i];
      if (/\s/.test(c)) {
        i++;
        continue;
      }
      if (c === "/" && skipComment()) continue;
      if (c === '"' || c === "'") {
        scanString(c);
        prev2 = prev;
        prev = '"';
        continue;
      }
      if (c === "`") {
        scanTemplate();
        prev2 = prev;
        prev = '"';
        continue;
      }
      if (c === "/") {
        const regexAllowed = prev === "" || "(,=:[!&|?{};".includes(prev) || word === "return" || word === "typeof";
        if (regexAllowed) {
          i++;
          let inClass = false;
          while (i < src.length && (src[i] !== "/" || inClass)) {
            if (src[i] === "\\") i++;
            else if (src[i] === "[") inClass = true;
            else if (src[i] === "]") inClass = false;
            else if (src[i] === "\n") fail("unterminated regular expression");
            i++;
          }
          i++;
          while (/[a-z]/i.test(src[i] ?? "")) i++;
          prev2 = prev;
          prev = '"';
          word = "";
          continue;
        }
      }
      if (c === "{") depth++;
      if (c === "}") {
        if (depth === 0 && end === "}") {
          i++;
          return;
        }
        depth--;
      }
      if (jsx && c === "<" && /[A-Za-z>]/.test(src[i + 1] ?? "")) {
        const arrow = prev === ">" && prev2 === "=";
        if (prev === "" || "(,=:[?&|!;{".includes(prev) || arrow || word === "return") {
          scanElement();
          prev2 = prev;
          prev = '"';
          word = "";
          continue;
        }
      }
      if (/[\w$]/.test(c)) {
        let j = i;
        while (j < src.length && /[\w$]/.test(src[j])) j++;
        word = src.slice(i, j);
        i = j;
        prev2 = prev;
        prev = "a";
        continue;
      }
      prev2 = prev;
      prev = c;
      word = "";
      i++;
    }
    if (end !== null) fail("unclosed expression");
  }

  function skipBlank() {
    for (;;) {
      while (/\s/.test(src[i] ?? "")) i++;
      if (!(src[i] === "/" && skipComment())) return;
    }
  }

  /** At `<` of a JSX element or fragment. Returns after its closing `>`. */
  function scanElement() {
    i++;
    const tag = /^[\w.:-]*/.exec(src.slice(i))[0];
    i += tag.length;
    for (;;) {
      skipBlank();
      if (i >= src.length) fail("unterminated JSX tag");
      if (src.startsWith("/>", i)) {
        i += 2;
        return;
      }
      if (src[i] === ">") {
        i++;
        break;
      }
      if (src[i] === "{") {
        i++;
        scanCode("}");
        continue;
      }
      const name = /^[\w:.-]+/.exec(src.slice(i));
      if (!name) fail(`unexpected "${src[i]}" in a JSX tag`);
      i += name[0].length;
      skipBlank();
      if (src[i] !== "=") continue;
      i++;
      skipBlank();
      if (src[i] === '"' || src[i] === "'") {
        const start = i;
        const close = src.indexOf(src[i], i + 1);
        if (close < 0) fail("unterminated JSX attribute");
        const value = src.slice(i + 1, close);
        i = close + 1;
        if (CJK.test(value) || (USER_ATTRS.has(name[0]) && isPhrase(value))) add(start, `attribute ${name[0]}`, value);
      } else if (src[i] === "{") {
        const phrase = USER_ATTRS.has(name[0]) ? PLAIN_STRING_EXPRESSION.exec(src.slice(i)) : null;
        const value = phrase && (phrase[2] ?? phrase[3]);
        if (phrase && !CJK.test(value) && isPhrase(value)) {
          add(i, `attribute ${name[0]}`, value);
          i += phrase[0].length;
        } else {
          i++;
          scanCode("}");
        }
      } else if (src[i] === "<") scanElement();
    }
    let text = "";
    let textStart = i;
    const flush = () => {
      if (isUserText(text)) add(textStart + text.length - text.trimStart().length, "text", text);
      text = "";
    };
    while (i < src.length) {
      const c = src[i];
      if (c === "<" && src[i + 1] === "/") {
        flush();
        const close = src.indexOf(">", i);
        if (close < 0) fail("unterminated closing tag");
        i = close + 1;
        return;
      }
      if (c === "<") {
        flush();
        scanElement();
        textStart = i;
        continue;
      }
      if (c === "{") {
        flush();
        i++;
        scanCode("}");
        textStart = i;
        continue;
      }
      if (text === "") textStart = i;
      text += c;
      i++;
    }
    fail(`JSX element <${tag}> is not closed`);
  }

  scanCode(null);
  return found;
}

function* sources(dir) {
  for (const name of readdirSync(dir).sort()) {
    const path = join(dir, name);
    if (statSync(path).isDirectory()) {
      if (path !== join(srcDir, "i18n")) yield* sources(path);
    } else if (/\.tsx?$/.test(name) && !/\.test\.tsx?$/.test(name) && !name.endsWith(".d.ts")) yield path;
  }
}

export function inventory() {
  const files = {};
  const problems = [];
  for (const path of sources(srcDir)) {
    const rel = relative(root, path).split(sep).join("/");
    try {
      const hits = scan(readFileSync(path, "utf8"), { jsx: path.endsWith(".tsx") });
      if (hits.length > 0) files[rel] = hits;
    } catch (e) {
      problems.push(`${rel}: ${e.message}`);
    }
  }
  return { files, problems };
}

function main(argv) {
  const { files, problems } = inventory();
  if (problems.length > 0) {
    console.error("The scan could not read these files, so its answer would not be reliable:\n  " + problems.join("\n  "));
    return 2;
  }
  const counts = Object.fromEntries(Object.entries(files).map(([f, hits]) => [f, hits.length]));
  const total = Object.values(counts).reduce((a, b) => a + b, 0);

  if (argv.includes("--list")) {
    for (const [file, hits] of Object.entries(files)) for (const h of hits) console.log(`${file}:${h.line}  ${h.kind}  ${h.text}`);
    console.log(`${total} literals in ${Object.keys(counts).length} files`);
    return 0;
  }

  let baseline = { initial: total, files: {} };
  try {
    baseline = JSON.parse(readFileSync(baselinePath, "utf8"));
  } catch (e) {
    if (e.code !== "ENOENT") throw e;
  }
  const allowed = baseline.files ?? {};

  if (argv.includes("--update")) {
    const next = {};
    for (const file of Object.keys(counts).sort()) next[file] = Math.min(counts[file], allowed[file] ?? counts[file]);
    const raised = Object.keys(counts).filter((f) => counts[f] > (allowed[f] ?? counts[f]));
    if (raised.length > 0) console.error(`Not raising the baseline for: ${raised.join(", ")}`);
    const initial = baseline.initial ?? total;
    writeFileSync(baselinePath, serialize({ initial, files: next }));
    console.log(`baseline written: ${sum(next)} of ${initial} baseline literals remain`);
    return raised.length > 0 ? 1 : 0;
  }

  const over = [];
  const stale = [];
  for (const file of Object.keys({ ...allowed, ...counts }).sort()) {
    const now = counts[file] ?? 0;
    const was = allowed[file] ?? 0;
    if (now > was) over.push({ file, now, was });
    else if (now < was) stale.push({ file, now, was });
  }
  console.log(`${total} of ${baseline.initial} baseline literals remain`);
  if (over.length > 0) {
    console.error("\nUser-facing text written in the code. Put it in app/src/i18n/catalog and use t(key):");
    for (const { file, now, was } of over) {
      console.error(`  ${file}: ${now} literals, baseline allows ${was}`);
      for (const h of files[file].slice(was === 0 ? 0 : -(now - was))) console.error(`    ${file}:${h.line}  ${h.kind}  ${h.text}`);
    }
  }
  if (stale.length > 0) {
    console.error("\nThe baseline is higher than the code. Lower it so the gain cannot be lost: npm run check:strings -- --update");
    for (const { file, now, was } of stale) console.error(`  ${file}: ${now} literals, baseline says ${was}`);
  }
  return over.length > 0 || stale.length > 0 ? 1 : 0;
}

const sum = (counts) => Object.values(counts).reduce((a, b) => a + b, 0);
const serialize = ({ initial, files }) =>
  `{\n  "initial": ${initial},\n  "files": {\n${Object.entries(files)
    .map(([f, n]) => `    ${JSON.stringify(f)}: ${n}`)
    .join(",\n")}\n  }\n}\n`;

if (process.argv[1] === fileURLToPath(import.meta.url)) process.exit(main(process.argv.slice(2)));
