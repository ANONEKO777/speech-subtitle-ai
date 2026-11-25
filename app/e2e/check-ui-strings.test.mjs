import { spawnSync } from "node:child_process";
import { mkdirSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { scan } from "../../scripts/check_ui_strings.mjs";

const script = join(dirname(fileURLToPath(import.meta.url)), "..", "..", "scripts", "check_ui_strings.mjs");
const kinds = (src, jsx = true) => scan(src, { jsx }).map((h) => `${h.kind}:${h.text}`);

describe("what counts as a user-facing literal", () => {
  it("counts a string, a template and a JSX text with Chinese, Japanese or full-width text", () => {
    expect(kinds('const a = "取消"; const b = `共 ${n} 項`; const c = <p>你好</p>; const d = "こんにちは"; const e = "（";')).toEqual([
      "string:取消",
      "template:共 項",
      "text:你好",
      "string:こんにちは",
      "string:（",
    ]);
  });

  it("counts the attributes a screen reader or a tooltip reads", () => {
    expect(kinds('const a = <button title="Close the window" aria-label="關閉" placeholder="Type here" alt="A chart" />;')).toEqual([
      "attribute title:Close the window",
      "attribute aria-label:關閉",
      "attribute placeholder:Type here",
      "attribute alt:A chart",
    ]);
  });

  it("counts a Latin phrase written as a plain string expression in an attribute", () => {
    expect(kinds("const a = <button title={\"Close the window\"} aria-label={'Close it'} alt={`A chart`} />;")).toEqual([
      "attribute title:Close the window",
      "attribute aria-label:Close it",
      "attribute alt:A chart",
    ]);
    expect(kinds('const a = <i title={"GPU"} data-testid={"a b"} title={name} aria-label={"關閉"} />;')).toEqual(["string:關閉"]);
  });

  it("counts a Latin phrase in JSX text, and leaves names, units and identifiers alone", () => {
    expect(kinds("const a = <p>Hello world</p>;")).toEqual(["text:Hello world"]);
    expect(kinds('const a = <p>Ollama</p>; const b = <i title="GPU" data-testid="a b" className="x y" />; const c = <b>{n}</b>;')).toEqual([]);
  });

  it("ignores code that is not text: comments, plain strings, regular expressions, numbers", () => {
    const src = '// 取消\n/* 你好 */\nconst a = "idle"; const re = /[（"](.*)/; const n = 3 < 4 ? 1 : 2;';
    expect(kinds(src)).toEqual([]);
  });

  it("does not take a comparison or a generic for JSX, and finds text after one", () => {
    expect(kinds('const a = x < y; const b = new Map<string, number>(); const c = f<string>("取消");')).toEqual(["string:取消"]);
  });

  it("finds text inside an expression inside JSX, in either direction", () => {
    expect(kinds('const a = <ul>{items.map((i) => <li key={i}>{cond ? "是" : <b>否</b>}</li>)}</ul>;')).toEqual(["string:是", "text:否"]);
  });

  it("reads .ts files without JSX, where < is a type argument", () => {
    expect(kinds('const a = <Foo>"x"; const b = "取消";', false)).toEqual(["string:取消"]);
  });

  it("refuses to answer when it cannot read a file, instead of passing silently", () => {
    expect(() => scan("const a = <p>unclosed", { jsx: true })).toThrow(/not closed|unterminated/);
  });
});

describe("the check against the baseline", () => {
  let dir;
  const write = (rel, text) => {
    mkdirSync(dirname(join(dir, rel)), { recursive: true });
    writeFileSync(join(dir, rel), text);
  };
  const run = (...args) => {
    const r = spawnSync(process.execPath, [script, ...args], { env: { ...process.env, UI_STRINGS_ROOT: dir }, encoding: "utf8" });
    return { code: r.status, out: r.stdout + r.stderr };
  };
  const baseline = () => JSON.parse(readFileSync(join(dir, "i18n-baseline.json"), "utf8"));

  beforeEach(() => {
    dir = mkdtempSync(join(tmpdir(), "ui-strings-"));
    write("src/a.tsx", 'export const A = () => <p>你好</p>;\nexport const b = "取消";\n');
    write("src/i18n/catalog.ts", 'export const x = "你好";\n');
    write("src/a.test.tsx", 'expect(x).toBe("你好");\n');
    expect(run("--update").code).toBe(0);
  });
  afterEach(() => rmSync(dir, { recursive: true, force: true }));

  it("passes on the code it was baselined from and prints the progress line", () => {
    const r = run();
    expect(r.code).toBe(0);
    expect(r.out).toContain("2 of 2 baseline literals remain");
    expect(baseline().files).toEqual({ "src/a.tsx": 2 });
  });

  it("fails when a file gains a literal, and names the line", () => {
    write("src/a.tsx", 'export const A = () => <p>你好</p>;\nexport const b = "取消";\nexport const c = "新增";\n');
    const r = run();
    expect(r.code).toBe(1);
    expect(r.out).toContain("src/a.tsx: 3 literals, baseline allows 2");
    expect(r.out).toContain("src/a.tsx:3");
  });

  it("fails when a new file brings a literal", () => {
    write("src/b.ts", 'export const d = "新檔案";\n');
    const r = run();
    expect(r.code).toBe(1);
    expect(r.out).toContain("src/b.ts: 1 literals, baseline allows 0");
  });

  it("passes for a literal in app/src/i18n and in a test", () => {
    write("src/i18n/more.ts", 'export const y = "更多";\n');
    write("src/b.test.ts", 'it("取消", () => {});\n');
    expect(run().code).toBe(0);
  });

  it("passes a Latin word a person types as a name, and fails a Latin phrase in JSX", () => {
    write("src/a.tsx", 'export const A = () => <p>你好</p>;\nexport const b = "取消";\nexport const n = <i>Ollama</i>;\n');
    expect(run().code).toBe(0);
    write("src/a.tsx", 'export const A = () => <p>你好</p>;\nexport const b = "取消";\nexport const n = <i>Hello world</i>;\n');
    expect(run().code).toBe(1);
  });

  it("fails when a literal moved out until the baseline is lowered, then holds the lower number", () => {
    write("src/a.tsx", 'export const A = () => <p>你好</p>;\n');
    const stale = run();
    expect(stale.code).toBe(1);
    expect(stale.out).toContain("1 of 2 baseline literals remain");
    expect(stale.out).toContain("--update");
    expect(run("--update").code).toBe(0);
    expect(baseline()).toEqual({ initial: 2, files: { "src/a.tsx": 1 } });
    write("src/a.tsx", 'export const A = () => <p>你好</p>;\nexport const z = "又一個";\n');
    expect(run().code).toBe(1);
  });

  it("never raises the baseline on --update", () => {
    write("src/a.tsx", 'export const A = () => <p>你好</p>;\nexport const b = "取消";\nexport const c = "新增";\n');
    expect(run("--update").code).toBe(1);
    expect(baseline().files).toEqual({ "src/a.tsx": 2 });
  });

  it("exits 2 when a file cannot be scanned", () => {
    write("src/broken.tsx", "export const A = () => <p>oops\n");
    expect(run().code).toBe(2);
  });

  it("lists every literal with its line for the inventory", () => {
    const r = run("--list");
    expect(r.out).toContain("src/a.tsx:1  text  你好");
    expect(r.out).toContain("src/a.tsx:2  string  取消");
  });
});
