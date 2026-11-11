"use strict";
// Run: JSDOM_DIR=<node_modules/jsdom dir> LABEL_HTML=<built label.html> node --test scripts/p23b_page/page.test.js
// The page is built by scripts/p23b_make_page.py. No browser opens and no audio plays.
const test = require("node:test");
const assert = require("node:assert");
const fs = require("node:fs");
const path = require("node:path");

const logic = require("./logic.js");
let JSDOM;
try {
  ({ JSDOM } = require("jsdom"));
} catch (e) {
  ({ JSDOM } = require(process.env.JSDOM_DIR));
}
const PAGE = process.env.LABEL_HTML;

const items = [1, 2, 3, 4].map((n) => ({ id: "s" + n, clip: "clips/s" + n + ".mp3" }));

test("logic: answer, change, order, note, export shape", () => {
  const st = logic.createState(items);
  logic.answer(st, "ja", "t1");
  logic.goto(st, 1);
  logic.setNote(st, "  noisy ");
  logic.answer(st, "both", "t2");
  assert.equal(logic.setOrder(st, "en_ja").order, "en_ja");
  logic.goto(st, 0);
  logic.answer(st, "en", "t3");
  assert.equal(logic.answeredCount(st), 2);
  assert.equal(logic.firstUnanswered(st), 2);
  const out = logic.exportLabels(st, "now");
  assert.deepEqual(Object.keys(out).sort(), ["answered", "exported_at", "labels", "tool", "total", "version"]);
  assert.deepEqual(out.labels[0], { id: "s1", label: "en", order: null, note: "", position: 1, timestamp: "t3" });
  assert.deepEqual(out.labels[1], { id: "s2", label: "both", order: "en_ja", note: "  noisy ", position: 2, timestamp: "t2" });
  assert.equal(out.labels.length, 2);
  assert.throws(() => logic.answer(st, "fr", "t"));
});

test("logic: changing both to another label clears the order", () => {
  const st = logic.createState(items);
  logic.answer(st, "both", "t");
  logic.setOrder(st, "ja_en");
  logic.answer(st, "ja", "t");
  assert.equal(logic.exportLabels(st, "n").labels[0].order, null);
  assert.equal(logic.setOrder(st, "ja_en"), null);
});

test("logic: restore keeps valid answers and survives junk", () => {
  const st = logic.createState(items);
  logic.answer(st, "both", "t");
  logic.setOrder(st, "ja_en");
  logic.goto(st, 2);
  const raw = logic.serialize(st);
  const back = logic.restore(logic.createState(items), raw);
  assert.equal(back.index, 2);
  assert.equal(back.answers.s1.order, "ja_en");
  for (const junk of [null, "", "{", "[]", '{"answers":5}', '{"answers":{"s1":{"label":"zz"},"x":{"label":"ja"}},"index":99}']) {
    const s = logic.restore(logic.createState(items), junk);
    assert.equal(logic.answeredCount(s), 0);
    assert.ok(s.index <= items.length);
  }
});

function openPage(store, opts = {}) {
  const html = fs.readFileSync(PAGE, "utf8");
  const calls = { play: 0, blobs: [] };
  const dom = new JSDOM(html, {
    url: "http://localhost/label.html",
    runScripts: "dangerously",
    pretendToBeVisual: true,
    beforeParse(win) {
      win.HTMLMediaElement.prototype.play = function () { calls.play += 1; return Promise.resolve(); };
      win.HTMLMediaElement.prototype.pause = function () {};
      win.HTMLMediaElement.prototype.load = function () {};
      win.URL.createObjectURL = (b) => { calls.blobs.push(b); return "blob:test"; };
      win.URL.revokeObjectURL = () => {};
      win.HTMLAnchorElement.prototype.click = function () {};
      if (opts.brokenStorage) {
        Object.defineProperty(win, "localStorage", { get() { throw new Error("blocked"); } });
      } else if (store) {
        win.localStorage.setItem(store.key, store.value);
      }
    },
  });
  return { dom, win: dom.window, doc: dom.window.document, calls };
}

function key(win, k, target) {
  const ev = new win.KeyboardEvent("keydown", { key: k, bubbles: true, cancelable: true, code: k === " " ? "Space" : undefined });
  (target || win.document.body).dispatchEvent(ev);
  return ev;
}

test("page: file is self-contained and shows no model guesses, strata, or times", () => {
  const html = fs.readFileSync(PAGE, "utf8");
  assert.ok(!/(src|href)\s*=\s*["']https?:/i.test(html), "no external resource");
  assert.ok(!/url\(\s*["']?https?:/i.test(html));
  for (const word of ["whisper", "qwen", "stratum", "guesses", "start_s", "end_s", "disagree", "ja_then_en", "fragment"]) {
    assert.ok(!html.toLowerCase().includes(word), "page leaks " + word);
  }
  assert.ok(html.includes("clips/s"));
});

test("page: keyboard flow, go back, order, persistence, export", async () => {
  const { win, doc, calls } = openPage(null);
  const count = () => doc.getElementById("count").textContent;
  assert.match(count(), /第 1 題，共 120 題/);
  const first = win.__p23b.state.items[0].id;
  assert.match(doc.getElementById("audio").getAttribute("src"), /^clips\/s\d+\.mp3$/);

  key(win, " ");
  assert.equal(calls.play, 1);
  assert.match(count(), /第 1 題/);

  key(win, "1");
  assert.match(count(), /第 2 題/);
  key(win, "3");
  assert.match(count(), /第 2 題/);
  assert.ok(doc.getElementById("order").classList.contains("on"));
  key(win, "6");
  assert.match(count(), /第 3 題/);
  key(win, "2");
  key(win, "4");
  assert.match(count(), /第 5 題/);
  assert.equal(doc.getElementById("answered").textContent, "已答 4");

  key(win, "ArrowLeft");
  key(win, "ArrowLeft");
  assert.match(count(), /第 3 題/);
  key(win, "1");
  assert.equal(win.__p23b.state.answers[win.__p23b.state.items[2].id].label, "ja");

  const note = doc.getElementById("note");
  note.focus();
  note.value = "bgm";
  note.dispatchEvent(new win.Event("input", { bubbles: true }));
  const ignored = key(win, "2", note);
  assert.equal(ignored.defaultPrevented, false);
  assert.match(count(), /第 4 題/);
  doc.querySelector("button[data-label=en]").click();
  assert.match(count(), /第 5 題/);
  const item3 = win.__p23b.state.answers[win.__p23b.state.items[3].id];
  assert.equal(item3.label, "en");
  assert.equal(item3.note, "bgm");
  assert.equal(doc.getElementById("note").value, "");

  const raw = win.localStorage.getItem(win.localStorage.key(0));
  const key0 = win.localStorage.key(0);
  const again = openPage({ key: key0, value: raw });
  assert.equal(again.doc.getElementById("answered").textContent, "已答 4");
  assert.match(again.doc.getElementById("count").textContent, /第 5 題/);

  win.__p23b.exportLabels();
  assert.equal(calls.blobs.length, 1);
  const text = await new Promise((res, rej) => {
    const fr = new win.FileReader();
    fr.onload = () => res(fr.result);
    fr.onerror = rej;
    fr.readAsText(calls.blobs[0]);
  });
  const out = JSON.parse(text);
  assert.equal(out.total, 120);
  assert.equal(out.labels.length, 4);
  for (const l of out.labels) {
    assert.deepEqual(Object.keys(l).sort(), ["id", "label", "note", "order", "position", "timestamp"]);
    assert.ok(["ja", "en", "both", "unclear"].includes(l.label));
    assert.ok(!Number.isNaN(Date.parse(l.timestamp)));
  }
  const both = out.labels.find((l) => l.label === "both");
  assert.equal(both.order, "en_ja");
  assert.equal(out.labels[0].id, first);
});

test("page: typing digits in the note box does not answer", () => {
  const { win, doc } = openPage(null);
  const note = doc.getElementById("note");
  const ev = key(win, "1", note);
  assert.equal(ev.defaultPrevented, false);
  assert.match(doc.getElementById("count").textContent, /第 1 題/);
});

test("page: works when localStorage throws", () => {
  const { win, doc } = openPage(null, { brokenStorage: true });
  key(win, "1");
  assert.match(doc.getElementById("count").textContent, /第 2 題/);
  assert.match(doc.getElementById("status").textContent, /無法存在瀏覽器/);
});

test("page: finishing shows the done card", () => {
  const { win, doc } = openPage(null);
  for (let i = 0; i < 120; i++) key(win, "4");
  assert.ok(!doc.getElementById("done").classList.contains("hidden"));
  assert.ok(doc.getElementById("quiz").classList.contains("hidden"));
  assert.equal(doc.getElementById("answered").textContent, "已答 120");
  assert.ok(path.basename(PAGE));
});
